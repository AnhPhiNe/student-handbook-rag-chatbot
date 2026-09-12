import hashlib
import logging
import threading
import time
from collections.abc import Iterator
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.common.cohort import resolve_cohort_from_query
from src.common.env_loader import env_bool
from src.common.io import load_json, load_yaml
from src.retrieval.core.slang_normalizer import SlangNormalizer
from src.retrieval.core.embedding_model import (
    load_embedding_model,
)
from src.retrieval.runtime_config import load_retrieval_runtime_config

from .answer_formatter import (
    clean_stream_fragment,
    clean_stream_start,
    format_final_answer,
    format_final_response,
    sources_section_start,
)
from .answer_guardrails import (
    build_clarification_question,
    build_fallback_answer,
    detect_ambiguous_query,
    is_low_confidence,
    is_out_of_domain_query,
)
from .citation_formatter import (
    prioritize_citations_by_answer_anchors,
    select_relevant_citations,
)
from .gemini_client import GeminiClient
from .prompt_builder import (
    ANSWER_PROMPT_VERSION,
    DEFAULT_MAX_CONTEXT_CHARS,
    build_answer_prompt_bundle,
)
from .plan_executor import PlanExecutor, StructuredCatalogs
from .response_cache import get_response_cache
from .structured_result_presenter import build_structured_results

DEFAULT_CONFIG_PATH = Path("configs/answer_generation.yaml")

PIPELINE_VERSION = "v76-structured-resolution-contract"
STREAM_OUTPUT_GUARDRAIL_BUFFER_CHARS = 256
logger = logging.getLogger("student_handbook_rag.generation.answer_pipeline")
_evaluation_telemetry: ContextVar[dict[str, Any] | None] = ContextVar(
    "answer_pipeline_evaluation_telemetry", default=None
)


def _normalize_retrieval_cohort(cohort: str | None) -> str | None:
    if cohort is None:
        return None
    normalized = str(cohort).strip()
    if normalized.lower() in {"", "general", "all"}:
        return None
    return normalized


def _authorized_context_fingerprint(context_used: str) -> dict[str, str]:
    return {
        "authorized_evidence_sha256": hashlib.sha256(
            context_used.encode("utf-8")
        ).hexdigest()
    }



@dataclass(slots=True)
class PreparedAnswer:
    """Carry all retrieval and planning state shared by sync and streaming renderers."""

    query: str
    effective_query: str
    cohort: str | None
    retrieval_result: dict[str, Any] = field(default_factory=dict)
    selected_citations: list[dict[str, Any]] = field(default_factory=list)
    all_citations: list[dict[str, Any]] = field(default_factory=list)
    public_retrieval_citations: list[dict[str, Any]] = field(default_factory=list)
    related_references: list[dict[str, Any]] = field(default_factory=list)
    prompt: str = ""
    context_used: str = ""
    cache_key: str | None = None
    cached: dict[str, Any] | None = None
    terminal_status: str | None = None
    terminal_answer: str | None = None
    fallback_reason: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    clarification_needed: bool = False
    query_type_override: str | None = None


class AnswerPipeline:
    """Orchestrate planning, retrieval, generation, citations, caching, and telemetry."""

    def __init__(
        self,
        config_path: str | Path = DEFAULT_CONFIG_PATH,
        llm_client: Any | None = None,
    ) -> None:
        self.config_path = Path(config_path)
        self.config = load_yaml(self.config_path)
        self.retrieval_config = load_retrieval_runtime_config()

        self.formula_rules = load_json(self.config["input"]["formula_rules"])
        student_service_directory_path = self.config["input"].get(
            "student_service_directory"
        )
        self.student_service_directory = (
            load_json(student_service_directory_path)
            if student_service_directory_path
            and Path(student_service_directory_path).is_file()
            else []
        )
        student_office_profiles_path = self.config["input"].get(
            "student_office_profiles"
        )
        self.student_office_profiles = (
            load_json(student_office_profiles_path)
            if student_office_profiles_path
            and Path(student_office_profiles_path).is_file()
            else []
        )
        student_faculty_profiles_path = self.config["input"].get(
            "student_faculty_profiles"
        )
        self.student_faculty_profiles = (
            load_json(student_faculty_profiles_path)
            if student_faculty_profiles_path
            and Path(student_faculty_profiles_path).is_file()
            else []
        )
        structured_tables_registry_path = self.config["input"].get(
            "structured_tables_registry"
        )
        self.structured_tables_registry = (
            load_json(structured_tables_registry_path)
            if structured_tables_registry_path
            and Path(structured_tables_registry_path).is_file()
            else []
        )
        parent_docstore_path = self.config["input"].get("parent_docstore")
        parent_docstore_items = (
            load_json(parent_docstore_path)
            if parent_docstore_path and Path(parent_docstore_path).is_file()
            else []
        )
        self.parent_sources_by_id = {
            str(item.get("_id")): item
            for item in parent_docstore_items
            if isinstance(item, dict) and item.get("_id")
        }
        self.program_directory = load_json(self.config["input"]["program_directory"])
        self.slang_normalizer = SlangNormalizer(
            program_directory=self.program_directory,
        )

        self.model = load_embedding_model(
            self.retrieval_config["embedding"]["model_name"]
        )

        llm_config = self.config.get("llm", {})
        self.llm_config = llm_config
        if llm_config.get("provider") != "gemini":
            raise ValueError("AnswerPipeline requires llm.provider='gemini'.")
        self.model_name = str(llm_config.get("model_name") or "").strip()
        if not self.model_name:
            raise ValueError("AnswerPipeline requires llm.model_name.")

        if env_bool("STUDENT_RAG_OFFLINE_EVAL"):
            self.config.setdefault("cache", {})["enabled"] = False
        elif env_bool("STUDENT_RAG_QUALITY_EVAL"):
            # Quality evaluation must exercise retrieval and generation.
            self.config.setdefault("cache", {})["enabled"] = False

        self._component_init_lock = threading.Lock()
        self._plan_executor: PlanExecutor | None = None
        self.router = None
        self._llm_client = llm_client
        self.max_context_chars = int(
            llm_config.get("max_context_chars", DEFAULT_MAX_CONTEXT_CHARS)
        )
        self.request_sleep_seconds = float(llm_config.get("request_sleep_seconds", 2))
        self._last_llm_call_at = 0.0

        cache_config = self.config.get("cache", {})
        self.response_cache = get_response_cache(
            enabled=cache_config.get("enabled", True),
            ttl_seconds=cache_config.get("ttl_seconds", 86400),
            max_entries=cache_config.get("max_entries", 1000),
        )

    def _selection_source_limit(self) -> int:
        citations = self.config.get("citations", {})
        return max(1, int(citations.get("selection_max_sources", 5)))

    def _public_source_limit(self) -> int:
        citations = self.config.get("citations", {})
        return max(1, int(citations.get("public_max_sources", 10)))

    def _retrieval_top_k(self) -> int:
        retrieval_config = getattr(self, "retrieval_config", {}) or {}
        retrieval = retrieval_config.get("retrieval", {})
        return max(1, int(retrieval.get("default_top_k", 5)))

    def prepare_answer(
        self,
        query: str,
        *,
        chat_history: list[dict[str, str]] | None,
        cohort: str | None,
        tracker: Any,
        router_started_at: str,
        telemetry: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> PreparedAnswer:
        """Run shared routing, retrieval, guardrails, prompt, and cache lookup."""

        from datetime import datetime, timezone

        effective_query = query
        cohort = _normalize_retrieval_cohort(resolve_cohort_from_query(query, cohort))
        retrieval_started = time.monotonic()
        try:
            retrieval_result = self._run_retrieval(
                query,
                cohort,
                chat_history=chat_history,
            )
        except Exception as exc:
            logger.exception(
                "answer_retrieval_failed",
                extra={
                    "trace_id": trace_id,
                    "cohort": cohort,
                    "query_length": len(query),
                },
            )
            return PreparedAnswer(
                query=query,
                effective_query=effective_query,
                cohort=cohort,
                terminal_status="retrieval_error",
                terminal_answer=build_fallback_answer(
                    query=effective_query,
                    retrieval_result=None,
                    reason="retrieval_error",
                ),
                fallback_reason="retrieval_error",
                error_type="retrieval_error",
                error_message=str(exc),
            )

        if retrieval_result.get("router_usage"):
            usage = retrieval_result["router_usage"]
            tracker.record(
                step_name="AI Router",
                model=retrieval_result.get("router_model", ""),
                input_tokens=usage.get("input", 0),
                output_tokens=usage.get("output", 0),
                total_tokens=usage.get("total", 0),
                start_time=router_started_at,
                end_time=datetime.now(timezone.utc).isoformat(),
            )
        if telemetry is not None:
            telemetry["routing_retrieval_parent_lookup_ms"] = (
                time.monotonic() - retrieval_started
            ) * 1000

        effective_query = str(retrieval_result.get("effective_query") or query).strip()
        prepared = PreparedAnswer(
            query=query,
            effective_query=effective_query,
            cohort=cohort,
            retrieval_result=retrieval_result,
        )

        if retrieval_result.get("needs_clarification"):
            prepared.terminal_status = "needs_clarification"
            prepared.terminal_answer = retrieval_result.get(
                "clarification_question", "Bạn có thể làm rõ câu hỏi được không?"
            )
            prepared.fallback_reason = "needs_clarification"
            prepared.clarification_needed = True
            return prepared

        if not retrieval_result.get("query_plan") and detect_ambiguous_query(
            effective_query, retrieval_result
        ):
            prepared.terminal_status = "needs_clarification"
            prepared.terminal_answer = build_clarification_question(
                effective_query, retrieval_result
            )
            prepared.fallback_reason = "ambiguous_query"
            prepared.clarification_needed = True
            prepared.query_type_override = "ambiguous"
            return prepared

        if retrieval_result.get("out_of_domain"):
            prepared.terminal_status = "out_of_domain"
            prepared.terminal_answer = (
                "Câu hỏi này nằm ngoài phạm vi Sổ tay sinh viên nên mình không thể hỗ trợ được. "
                "Sổ tay chủ yếu bao gồm các nội dung như: quy chế đào tạo, "
                "thủ tục hành chính, học bổng, rèn luyện, ký túc xá, thông tin phòng ban và khoa/ngành. "
                "Bạn có thể hỏi lại theo một nội dung liên quan đến sổ tay nhé!"
            )
            prepared.fallback_reason = "out_of_domain"
            return prepared

        if not retrieval_result.get("query_plan") and is_out_of_domain_query(
            effective_query, retrieval_result
        ):
            prepared.terminal_status = "out_of_domain"
            prepared.terminal_answer = build_fallback_answer(
                effective_query,
                retrieval_result,
                reason="out_of_domain",
            )
            prepared.fallback_reason = "out_of_domain"
            return prepared

        if retrieval_result.get("query_plan"):
            prepared.selected_citations = list(
                retrieval_result.get("evidence_citations")
                or retrieval_result.get("citations")
                or []
            )
        else:
            prepared.selected_citations = select_relevant_citations(
                retrieval_result.get("citations"),
                intent=retrieval_result.get("intent"),
                retrieval_result=retrieval_result,
                max_sources=self._selection_source_limit(),
            )

        guardrails = self.config.get("guardrails", {})
        if guardrails.get("skip_llm_on_low_confidence", True) and is_low_confidence(
            retrieval_result
        ):
            prepared.terminal_status = "low_confidence"
            prepared.terminal_answer = format_final_answer(
                build_fallback_answer(
                    effective_query,
                    retrieval_result,
                    reason="low_confidence",
                ),
                prepared.selected_citations,
            )
            prepared.fallback_reason = "low_confidence"
            prepared.error_type = "retrieval"
            prepared.error_message = "Retrieval returned empty or insufficient context."
            return prepared

        prepared.all_citations = list(
            retrieval_result.get("evidence_citations")
            or retrieval_result.get("citations")
            or []
        )
        prepared.public_retrieval_citations = list(
            retrieval_result.get("citations") or []
        )
        prepared.related_references = list(
            retrieval_result.get("related_references") or []
        )

        context_started = time.monotonic()
        prepared.prompt, prepared.context_used = build_answer_prompt_bundle(
            query=effective_query,
            retrieval_result=retrieval_result,
            selected_citations=prepared.selected_citations,
            max_context_chars=self.max_context_chars,
            cohort=cohort,
        )
        if telemetry is not None:
            telemetry["context_build_ms"] = (time.monotonic() - context_started) * 1000
            telemetry["context_chars"] = len(prepared.context_used)
            telemetry["source_count"] = len(
                retrieval_result.get("retrieved_items") or []
            )
            telemetry["prompt_chars"] = len(prepared.prompt)

        prepared.cache_key = self.response_cache.make_cache_key(
            query=effective_query,
            retrieval_result=retrieval_result,
            selected_citations=prepared.selected_citations,
            cohort=cohort,
            context_fingerprint=_authorized_context_fingerprint(prepared.context_used),
            pipeline_version=PIPELINE_VERSION,
            answer_prompt_version=ANSWER_PROMPT_VERSION,
        )
        prepared.cached = self.response_cache.get(prepared.cache_key)
        return prepared

    def answer(
        self,
        query: str,
        chat_history: list[dict[str, str]] | None = None,
        cohort: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Return a complete answer for one user query.

        The sync path runs planning + retrieval,
        applies deterministic guardrails for structured/tool answers, builds a
        bounded context for true-RAG questions, then calls the configured LLM
        only when generation is actually required.
        """
        telemetry = (
            {
                "started_at_monotonic": time.monotonic(),
                "retry_count": 0,
                "cooldown_events": 0,
            }
            if env_bool("STUDENT_RAG_EVAL_TELEMETRY")
            else None
        )
        _evaluation_telemetry.set(telemetry)
        from datetime import datetime, timezone

        from src.common.usage_tracker import UsageTracker

        tracker = UsageTracker()
        trace_id = str(kwargs.get("trace_id") or "").strip() or None
        start_time_router = datetime.now(timezone.utc).isoformat()
        prepared = self.prepare_answer(
            query,
            chat_history=chat_history,
            cohort=cohort,
            tracker=tracker,
            router_started_at=start_time_router,
            telemetry=telemetry,
            trace_id=trace_id,
        )
        effective_query = prepared.effective_query
        cohort = prepared.cohort
        retrieval_result = prepared.retrieval_result
        selected_citations = prepared.selected_citations
        context_used = prepared.context_used
        prompt = prepared.prompt

        if prepared.terminal_status:
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=prepared.terminal_answer or "",
                context_used=context_used,
                selected_citations=selected_citations,
                status=prepared.terminal_status,
                error_type=prepared.error_type,
                error_message=prepared.error_message,
                llm_called=False,
                used_cache=False,
                clarification_needed=prepared.clarification_needed,
            )

        cache_key = prepared.cache_key
        cached = prepared.cached
        if cached:
            cached_answer = str(cached.get("answer") or "")
            cached_citations = prioritize_citations_by_answer_anchors(
                cached.get("citations") or retrieval_result.get("citations") or [],
                cached_answer,
                max_sources=self._public_source_limit(),
            )
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=cached_answer,
                context_used=context_used,
                selected_citations=cached_citations,
                status=str(cached.get("status") or "answered"),
                error_type=cached.get("error_type"),
                error_message=cached.get("error_message"),
                llm_called=False,
                used_cache=True,
            )

        all_citations = prepared.all_citations
        public_retrieval_citations = prepared.public_retrieval_citations

        try:
            llm_client = self._get_llm_client()
        except Exception as exc:
            logger.exception(
                "answer_llm_initialization_failed",
                extra={"trace_id": trace_id},
            )
            final_answer = format_final_answer(
                build_fallback_answer(
                    effective_query, retrieval_result, reason="api_error"
                ),
                selected_citations,
            )
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=final_answer,
                context_used=context_used,
                selected_citations=public_retrieval_citations,
                status="api_error",
                error_type="api_init_error",
                error_message=str(exc),
                llm_called=False,
                used_cache=False,
            )

        self._throttle_llm_call()
        start_time_llm = datetime.now(timezone.utc).isoformat()
        llm_started = time.monotonic()
        llm_result = llm_client.generate(prompt)
        end_time_llm = datetime.now(timezone.utc).isoformat()
        if telemetry is not None:
            telemetry["gemini_ms"] = (time.monotonic() - llm_started) * 1000
            telemetry["key_fingerprint"] = llm_result.get("key_fingerprint")
            telemetry["retry_count"] = max(0, int(llm_result.get("attempts") or 1) - 1)
        self._last_llm_call_at = time.monotonic()

        if llm_result.get("ok"):
            u = llm_result.get("usage") or {}
            tracker.record(
                step_name="LLM Generation",
                model=llm_result.get("model_used") or self.model_name,
                input_tokens=u.get("input", 0),
                output_tokens=u.get("output", 0),
                total_tokens=u.get("total", 0),
                start_time=start_time_llm,
                end_time=end_time_llm,
            )

        if not llm_result.get("ok"):
            error_type = llm_result.get("error_type") or "api_error"
            logger.warning(
                "answer_generation_failed",
                extra={
                    "trace_id": trace_id,
                    "error_type": error_type,
                    "error_message": llm_result.get("error_message"),
                },
            )
            final_answer = format_final_answer(
                build_fallback_answer(
                    effective_query, retrieval_result, reason=error_type
                ),
                selected_citations,
            )
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=final_answer,
                context_used=context_used,
                selected_citations=public_retrieval_citations,
                status="api_error",
                error_type=error_type,
                error_message=llm_result.get("error_message"),
                llm_called=True,
                used_cache=False,
                model_used=llm_result.get("model_used"),
                tracker=tracker,
            )

        llm_text = str(llm_result.get("text") or "").strip()

        final_answer = format_final_response(
            llm_text,
            primary_citations=selected_citations,
        )
        public_citations = prioritize_citations_by_answer_anchors(
            all_citations,
            final_answer,
            max_sources=self._public_source_limit(),
        )
        output = self._build_output(
            query=query,
            retrieval_result=retrieval_result,
            final_answer=final_answer,
            context_used=context_used,
            selected_citations=public_citations,
            status="answered",
            error_type=None,
            error_message=None,
            llm_called=True,
            used_cache=False,
            model_used=llm_result.get("model_used"),
            tracker=tracker,
        )
        self.response_cache.set(
            cache_key,
            {
                "answer": final_answer,
                "status": "answered",
                "error_type": None,
                "error_message": None,
                "citations": public_citations,
            },
        )

        return output

    def _build_stream_metadata(
        self,
        retrieval_result: dict[str, Any] | None,
        *,
        status: str,
        effective_query: str,
        fallback_reason: str | None = None,
        error_type: str | None = None,
        citations_used: list[dict[str, Any]] | None = None,
        related_references: list[dict[str, Any]] | None = None,
        llm_called: bool = False,
        used_cache: bool = False,
        run_id: str | None = None,
        query_type_override: str | None = None,
    ) -> dict[str, Any]:
        """Build standardized metadata chunk for streaming responses dynamically."""
        res = retrieval_result or {}
        query_handling = res.get("query_handling") or {}

        execution_mode = res.get("execution_mode") or "regulation"
        lookup_type = res.get("lookup_type")
        query_type = (
            query_type_override
            or res.get("query_type")
            or query_handling.get("context_mode")
            or "standalone"
        )
        model_name = getattr(self, "model_name", None)

        resolved_fallback = fallback_reason or (
            "none" if status in {"answered", "streaming"} else status
        )
        resolved_citations = (
            citations_used
            if citations_used is not None
            else (res.get("citations_used") or res.get("citations") or [])
        )
        resolved_related = (
            related_references
            if related_references is not None
            else (res.get("related_references") or [])
        )
        structured_results = build_structured_results(
            res.get("structured_result"),
            citations=list(res.get("citations") or res.get("citations_used") or []),
        )

        return {
            "type": "metadata",
            "run_id": run_id,
            "cohort": res.get("cohort") or res.get("selected_cohort") or "default",
            "status": status,
            "intent": res.get("intent"),
            "strategy": res.get("strategy"),
            "execution_mode": execution_mode,
            "lookup_type": lookup_type,
            "query_type": query_type,
            "model": model_name,
            "effective_query": effective_query,
            "query_handling": query_handling if query_handling else None,
            "fallback_reason": resolved_fallback,
            "error_type": error_type,
            "citations_used": resolved_citations,
            "related_references": resolved_related,
            "structured_results": structured_results,
            "target_chunk_types": res.get("target_chunk_types") or [],
            "query_plan": res.get("query_plan"),
            "task_results": res.get("task_results") or [],
            "coverage_by_task": res.get("coverage_by_task") or {},
            "planner_fallback": res.get("planner_fallback"),
            "supports_task_ids": res.get("supports_task_ids") or {},
            "llm_called": llm_called,
            "used_cache": used_cache,
        }

    def answer_stream(
        self,
        query: str,
        chat_history: list[dict[str, str]] | None = None,
        cohort: str | None = None,
        **kwargs,
    ) -> Iterator[dict[str, Any]]:
        """Stream progress events and answer tokens for one user query.

        This mirrors ``answer`` but yields progress, metadata, token, and done
        events so the frontend can show retrieval progress and stream LLM output
        without changing the underlying routing, guardrail, or citation logic.
        """
        run_id = None

        from datetime import datetime, timezone

        from src.common.usage_tracker import UsageTracker

        tracker = UsageTracker()
        trace_id = str(kwargs.get("trace_id") or "").strip() or None

        yield {"type": "progress", "message": "Đang phân tích câu hỏi..."}

        start_time_router = datetime.now(timezone.utc).isoformat()
        yield {"type": "progress", "message": "Đang tìm kiếm thông tin trong Sổ tay..."}
        prepared = self.prepare_answer(
            query,
            chat_history=chat_history,
            cohort=cohort,
            tracker=tracker,
            router_started_at=start_time_router,
            trace_id=trace_id,
        )
        effective_query = prepared.effective_query
        cohort = prepared.cohort
        retrieval_result = prepared.retrieval_result
        selected_citations = prepared.selected_citations

        if prepared.terminal_status:
            metadata_result = (
                None
                if prepared.terminal_status == "retrieval_error"
                else retrieval_result
            )
            yield self._build_stream_metadata(
                metadata_result,
                status=prepared.terminal_status,
                effective_query=effective_query,
                fallback_reason=prepared.fallback_reason,
                error_type=prepared.error_type,
                citations_used=selected_citations,
                query_type_override=prepared.query_type_override,
                run_id=run_id,
            )
            yield {"type": "token", "text": prepared.terminal_answer or ""}
            yield {
                "type": "done",
                "status": prepared.terminal_status,
                "error_type": prepared.error_type,
                "used_cache": False,
                "tracker": tracker,
                "citations_used": selected_citations,
            }
            return

        yield {"type": "progress", "message": "Đang phân tích tài liệu tìm được..."}
        all_citations = prepared.all_citations
        public_retrieval_citations = prepared.public_retrieval_citations
        related_references = prepared.related_references
        prompt = prepared.prompt
        cache_key = prepared.cache_key
        cached = prepared.cached
        if cached:
            cached_answer = str(cached.get("answer") or "")
            cached_citations = prioritize_citations_by_answer_anchors(
                cached.get("citations") or public_retrieval_citations,
                cached_answer,
                max_sources=self._public_source_limit(),
            )
            yield self._build_stream_metadata(
                retrieval_result,
                status=str(cached.get("status") or "answered"),
                effective_query=effective_query,
                citations_used=cached_citations,
                related_references=related_references,
                llm_called=False,
                used_cache=True,
                run_id=run_id,
            )
            yield {"type": "token", "text": cached_answer}
            yield {
                "type": "done",
                "status": str(cached.get("status") or "answered"),
                "used_cache": True,
                "tracker": tracker,
                "citations_used": cached_citations,
            }
            return

        yield {"type": "progress", "message": "Đang tổng hợp câu trả lời..."}
        llm_called = False
        yield self._build_stream_metadata(
            retrieval_result,
            status="streaming",
            effective_query=effective_query,
            citations_used=public_retrieval_citations,
            related_references=related_references,
            llm_called=llm_called,
            run_id=run_id,
        )

        final_answer_for_citations = ""
        terminal_status = "answered"
        terminal_error_type: str | None = None
        emitted_answer_parts: list[str] = []
        try:
            llm_client = self._get_llm_client()
            start_time_llm = datetime.now(timezone.utc).isoformat()
            self._throttle_llm_call()
            pending_stream_text = ""
            stream_prefix_emitted = False
            suppress_source_tail = False
            stream_result: dict[str, Any] = {}
            llm_called = True
            llm_stream = iter(llm_client.generate_stream(prompt))
            while True:
                try:
                    chunk = next(llm_stream)
                except StopIteration as completed:
                    if isinstance(completed.value, dict):
                        stream_result = completed.value
                    break
                chunk_text = str(chunk)
                if suppress_source_tail:
                    continue
                pending_stream_text += chunk_text
                if not stream_prefix_emitted:
                    pending_stream_text = clean_stream_start(pending_stream_text)
                source_start = sources_section_start(pending_stream_text)
                if source_start is not None:
                    pending_stream_text = pending_stream_text[:source_start]
                    suppress_source_tail = True
                pending_stream_text = clean_stream_fragment(pending_stream_text)
                if len(pending_stream_text) > STREAM_OUTPUT_GUARDRAIL_BUFFER_CHARS:
                    safe_text = pending_stream_text[
                        :-STREAM_OUTPUT_GUARDRAIL_BUFFER_CHARS
                    ]
                    pending_stream_text = pending_stream_text[
                        -STREAM_OUTPUT_GUARDRAIL_BUFFER_CHARS:
                    ]
                    if safe_text:
                        stream_prefix_emitted = True
                        emitted_answer_parts.append(safe_text)
                        yield {"type": "token", "text": safe_text}

            if pending_stream_text:
                final_tail = format_final_response(
                    pending_stream_text,
                    primary_citations=selected_citations,
                )
                if final_tail:
                    emitted_answer_parts.append(final_tail)
                    yield {"type": "token", "text": final_tail}
            final_answer_for_citations = "".join(emitted_answer_parts)
            end_time_llm = datetime.now(timezone.utc).isoformat()
            self._last_llm_call_at = time.monotonic()

            stream_usage = stream_result.get("usage") or {}
            if stream_usage:
                tracker.record(
                    step_name="LLM Generation",
                    model=stream_result.get("model_used")
                    or getattr(llm_client, "model_name", ""),
                    input_tokens=stream_usage.get("input", 0),
                    output_tokens=stream_usage.get("output", 0),
                    total_tokens=stream_usage.get("total", 0),
                    start_time=start_time_llm,
                    end_time=end_time_llm,
                )
        except Exception as exc:
            logger.exception(
                "answer_stream_generation_failed",
                extra={"trace_id": trace_id},
            )
            terminal_status = "api_error"
            terminal_error_type = type(exc).__name__
            if emitted_answer_parts:
                final_answer_for_citations = "".join(emitted_answer_parts)
            else:
                fallback = build_fallback_answer(
                    effective_query, retrieval_result, reason="api_error"
                )
                final_answer_for_citations = fallback
                yield {"type": "token", "text": fallback}

        final_citations = prioritize_citations_by_answer_anchors(
            all_citations,
            final_answer_for_citations,
            max_sources=self._public_source_limit(),
        )
        yield self._build_stream_metadata(
            retrieval_result,
            status=terminal_status,
            effective_query=effective_query,
            fallback_reason=("api_error" if terminal_status == "api_error" else None),
            error_type=terminal_error_type,
            citations_used=final_citations,
            related_references=related_references,
            llm_called=llm_called,
            run_id=run_id,
        )

        if terminal_status == "answered":
            self.response_cache.set(
                cache_key,
                {
                    "answer": final_answer_for_citations,
                    "status": "answered",
                    "error_type": None,
                    "error_message": None,
                    "citations": final_citations,
                },
            )

        yield {
            "type": "done",
            "status": terminal_status,
            "error_type": terminal_error_type,
            "used_cache": False,
            "tracker": tracker,
            "citations_used": final_citations,
        }

    def _get_router(self) -> Any:
        """Return the process pipeline's lazily initialized router."""

        if self.router is None:
            with self._component_init_lock:
                if self.router is None:
                    from src.retrieval.core.ai_router import AIRouter

                    self.router = AIRouter.from_config()
        return self.router

    def _run_retrieval(
        self,
        query: str,
        cohort: str | None = None,
        chat_history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Run the active QueryPlan and retrieval stack for one cohort context."""
        self._get_router()

        return self.plan_executor.run(
            query=query,
            cohort=cohort,
            chat_history=chat_history,
        )

    @property
    def plan_executor(self) -> PlanExecutor:
        """Build the plan executor once, after the catalogs are loaded."""
        if self._plan_executor is None:
            self._plan_executor = PlanExecutor(
                router=self.router,
                slang_normalizer=self.slang_normalizer,
                catalogs=StructuredCatalogs(
                    formula_rules=self.formula_rules,
                    office_directory=self.student_office_profiles,
                    student_service_directory=self.student_service_directory,
                    student_faculty_profiles=self.student_faculty_profiles,
                    structured_tables_registry=self.structured_tables_registry,
                    program_directory=self.program_directory,
                ),
                parent_sources_by_id=self.parent_sources_by_id,
                top_k=self._retrieval_top_k(),
                public_source_limit=self._public_source_limit(),
                model=self.model,
            )
        return self._plan_executor

    def _get_llm_client(self) -> Any:
        """Lazily create the configured LLM client for generated true-RAG answers."""
        if self._llm_client is None:
            with self._component_init_lock:
                if self._llm_client is None:
                    llm_config = self.config["llm"]
                    provider = llm_config.get("provider", "gemini")
                    if provider == "gemini":
                        self._llm_client = GeminiClient(
                            model_name=llm_config["model_name"],
                            temperature=llm_config.get("temperature", 0.2),
                            max_output_tokens=llm_config.get(
                                "max_output_tokens", 1024
                            ),
                            max_retries=llm_config.get("max_retries", 3),
                            retry_base_delay_seconds=llm_config.get(
                                "retry_base_delay_seconds", 2
                            ),
                            retry_max_delay_seconds=llm_config.get(
                                "retry_max_delay_seconds", 20
                            ),
                            request_timeout_seconds=llm_config.get(
                                "request_timeout_seconds", 60
                            ),
                            api_keys_env_var=llm_config.get(
                                "api_keys_env_var", "GEMINI_API_KEYS"
                            ),
                            key_pool_config=llm_config.get("key_pool"),
                        )
        return self._llm_client

    def _throttle_llm_call(self) -> None:
        """Respect configured spacing between outbound LLM calls."""
        if self.request_sleep_seconds <= 0 or self._last_llm_call_at <= 0:
            return

        elapsed = time.monotonic() - self._last_llm_call_at
        remaining = self.request_sleep_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _build_output(
        self,
        query: str,
        retrieval_result: dict[str, Any],
        final_answer: str,
        context_used: str,
        selected_citations: list[dict[str, Any]],
        status: str,
        error_type: str | None,
        error_message: str | None,
        llm_called: bool,
        used_cache: bool,
        clarification_needed: bool = False,
        model_used: str | None = None,
        tracker: Any = None,
    ) -> dict[str, Any]:
        """Assemble the canonical answer result consumed by all adapters."""

        query_handling = retrieval_result.get("query_handling")
        if not isinstance(query_handling, dict):
            query_handling = None
        run_id = None
        if model_used is None:
            model_used = getattr(self, "model_name", None)
        return {
            "run_id": run_id,
            "query": query,
            "effective_query": retrieval_result.get("effective_query")
            or (query_handling or {}).get("effective_query")
            or query,
            "cohort": retrieval_result.get("cohort")
            or retrieval_result.get("selected_cohort")
            or "default",
            "query_handling": query_handling,
            "answer": final_answer,
            "status": status,
            "error_type": error_type,
            "error_message": error_message,
            "intent": retrieval_result.get("intent"),
            "strategy": retrieval_result.get("strategy"),
            "execution_mode": retrieval_result.get("execution_mode") or "regulation",
            "lookup_type": retrieval_result.get("lookup_type"),
            "query_type": retrieval_result.get("query_type") or "standalone",
            "target_chunk_types": retrieval_result.get("target_chunk_types") or [],
            "raw_query": query,
            "fallback_reason": error_type
            or (
                status
                if status
                in {
                    "out_of_domain",
                    "needs_clarification",
                    "low_confidence",
                    "retrieval_error",
                    "api_error",
                }
                else "none"
            ),
            "retrieved_chunks_count": len(
                retrieval_result.get("retrieved_items") or []
            ),
            "retrieval_query": retrieval_result.get("retrieval_query"),
            "citations": retrieval_result.get("citations", []),
            "citations_used": selected_citations,
            "related_references": retrieval_result.get("related_references", []),
            "structured_result": retrieval_result.get("structured_result"),
            "structured_results": build_structured_results(
                retrieval_result.get("structured_result"),
                citations=list(retrieval_result.get("citations") or []),
            ),
            "formula_result": retrieval_result.get("formula_result"),
            "tool_result": retrieval_result.get("tool_result"),
            "query_plan": retrieval_result.get("query_plan"),
            "task_results": retrieval_result.get("task_results") or [],
            "coverage_by_task": retrieval_result.get("coverage_by_task") or {},
            "planner_fallback": retrieval_result.get("planner_fallback"),
            "supports_task_ids": retrieval_result.get("supports_task_ids") or {},
            "llm_called": llm_called,
            "model_used": model_used,
            "model": model_used,
            "used_cache": used_cache,
            "clarification_needed": clarification_needed,
            "context_used": context_used,
            "tracker": tracker,
            "evaluation_telemetry": self._finalize_evaluation_telemetry(
                used_cache=used_cache,
                llm_called=llm_called,
            ),
        }

    @staticmethod
    def _finalize_evaluation_telemetry(
        *, used_cache: bool, llm_called: bool
    ) -> dict[str, Any] | None:
        """Finalize request-level metrics from completed task results."""

        telemetry = _evaluation_telemetry.get()
        if telemetry is None:
            return None
        output = dict(telemetry)
        started_at = float(output.pop("started_at_monotonic", time.monotonic()))
        output["total_ms"] = (time.monotonic() - started_at) * 1000
        output["cache_hit"] = used_cache
        output["llm_called"] = llm_called
        return output
