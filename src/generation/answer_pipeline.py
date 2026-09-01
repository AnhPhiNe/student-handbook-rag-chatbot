import hashlib
import json
import os
import time
from contextvars import ContextVar
from collections.abc import Iterator
from pathlib import Path
from typing import Any


from src.common.cohort import (
    is_validated_source_applicable,
    resolve_cohort_from_query,
)
from src.retrieval.core.citation_builder import (
    build_citation_from_lookup,
    enrich_citations_with_parent_details,
)
from src.retrieval.core.graph_traverser import NetworkXGraphTraverser
from src.retrieval.core.hybrid_pipeline import (
    build_related_references,
    run_hybrid_retrieval_pipeline,
    select_graph_related_parent_candidates,
)
from src.retrieval.core.vector_retriever import (
    load_embedding_model,
)
from src.retrieval.core.slang_normalizer import SlangNormalizer
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
from src.common.io import load_json, load_yaml
from .prompt_builder import (
    ANSWER_PROMPT_VERSION,
    DEFAULT_MAX_CONTEXT_CHARS,
    build_answer_prompt_bundle,
)
from .response_cache import get_response_cache
from .structured_result_presenter import build_structured_results


DEFAULT_CONFIG_PATH = Path("configs/answer_generation.yaml")

PIPELINE_VERSION = "v61-directory-alias-pools"
STREAM_OUTPUT_GUARDRAIL_BUFFER_CHARS = 256
_evaluation_telemetry: ContextVar[dict[str, Any] | None] = ContextVar(
    "answer_pipeline_evaluation_telemetry", default=None
)


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


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


def _merge_structured_citation_content(
    existing: dict[str, Any],
    incoming: dict[str, Any],
) -> str:
    """Preserve every distinct table when one handbook section backs several.

    Citation identity remains the canonical parent section, while the evidence
    payload retains each table and its applicability. This prevents source
    deduplication from silently discarding a sibling structured table.
    """

    tables: list[dict[str, Any]] = []
    seen: set[str] = set()
    for citation in (existing, incoming):
        try:
            payload = json.loads(str(citation.get("content") or ""))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        candidates = (
            payload.get("tables")
            if isinstance(payload, dict) and isinstance(payload.get("tables"), list)
            else [payload]
        )
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            table = dict(candidate)
            table.setdefault("table_name", citation.get("title"))
            table.setdefault("applicability", citation.get("applicability"))
            identity = json.dumps(table, ensure_ascii=False, sort_keys=True, default=str)
            if identity in seen:
                continue
            seen.add(identity)
            tables.append(table)

    if not tables:
        return str(existing.get("content") or "")
    return json.dumps({"tables": tables}, ensure_ascii=False, indent=2, default=str)


class AnswerPipeline:
    def __init__(
        self,
        config_path: str | Path = DEFAULT_CONFIG_PATH,
        llm_client: Any | None = None,
    ) -> None:
        self.config_path = Path(config_path)
        self.config = load_yaml(self.config_path)

        self.scoring_tables = load_json(self.config["input"]["scoring_tables"])
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
        foreign_language_table_path = self.config["input"].get(
            "foreign_language_equivalency_table"
        )
        self.foreign_language_tables = (
            load_json(foreign_language_table_path)
            if foreign_language_table_path
            and Path(foreign_language_table_path).is_file()
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


        self.model = load_embedding_model(self.config["embedding"]["model_name"])

        llm_config = self.config.get("llm", {})
        self.llm_config = llm_config
        if llm_config.get("provider") != "gemini":
            raise ValueError(
                "AnswerPipeline requires llm.provider='gemini'."
            )

        if _env_bool("STUDENT_RAG_OFFLINE_EVAL"):
            self.config.setdefault("cache", {})["enabled"] = False
        elif _env_bool("STUDENT_RAG_QUALITY_EVAL"):
            # Quality evaluation must exercise retrieval and generation.
            self.config.setdefault("cache", {})["enabled"] = False

        self._llm_client = llm_client
        self.max_context_chars = int(
            llm_config.get("max_context_chars", DEFAULT_MAX_CONTEXT_CHARS)
        )
        self.request_sleep_seconds = float(llm_config.get("request_sleep_seconds", 2))
        self._last_llm_call_at = 0.0

        cache_config = self.config.get("cache", {})
        self.response_cache = get_response_cache(
            path=Path(cache_config.get("path", "data/cache/answer_response_cache.json")),
            enabled=cache_config.get("enabled", True),
            ttl_seconds=cache_config.get("ttl_seconds", 86400),
        )

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
            if _env_bool("STUDENT_RAG_EVAL_TELEMETRY")
            else None
        )
        _evaluation_telemetry.set(telemetry)
        effective_query = query
        from src.api.usage_tracker import UsageTracker
        from datetime import datetime, timezone

        tracker = UsageTracker()
        start_time_router = datetime.now(timezone.utc).isoformat()

        # Let an explicit cohort in the query win over the UI selector.
        cohort = _normalize_retrieval_cohort(resolve_cohort_from_query(query, cohort))

        try:
            retrieval_started = time.monotonic()
            retrieval_result = self._run_retrieval(
                query,
                cohort,
                chat_history=chat_history,
            )
            if retrieval_result.get("router_usage"):
                tracker.record(
                    step_name="AI Router",
                    model=retrieval_result.get("router_model", ""),
                    input_tokens=retrieval_result["router_usage"].get("input", 0),
                    output_tokens=retrieval_result["router_usage"].get("output", 0),
                    total_tokens=retrieval_result["router_usage"].get("total", 0),
                    start_time=start_time_router,
                    end_time=datetime.now(timezone.utc).isoformat(),
                )
            if telemetry is not None:
                telemetry["routing_retrieval_parent_lookup_ms"] = (
                    time.monotonic() - retrieval_started
                ) * 1000
            effective_query = str(
                retrieval_result.get("effective_query") or query
            ).strip()
        except Exception as exc:
            final_answer = build_fallback_answer(
                query=effective_query,
                retrieval_result=None,
                reason="retrieval_error",
            )
            return self._build_output(
                query=query,
                retrieval_result={},
                final_answer=final_answer,
                context_used="",
                selected_citations=[],
                status="retrieval_error",
                error_type="retrieval_error",
                error_message=str(exc),
                llm_called=False,
                used_cache=False,
            )

        # This stays empty unless Composer is called.  When it is called below,
        # it is replaced with the exact authorized evidence JSON in the prompt.
        context_used = ""

        if retrieval_result.get("needs_clarification"):
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=retrieval_result.get(
                    "clarification_question", "Bạn có thể làm rõ câu hỏi được không?"
                ),
                context_used=context_used,
                selected_citations=[],
                status="needs_clarification",
                error_type=None,
                error_message=None,
                llm_called=False,
                used_cache=False,
                clarification_needed=True,
            )

        # Cau hoi van thuoc domain nhung thieu scope thi hoi lai, khong dua vao LLM tra loi doan.
        if not retrieval_result.get("query_plan") and detect_ambiguous_query(effective_query, retrieval_result):
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=build_clarification_question(
                    effective_query, retrieval_result
                ),
                context_used=context_used,
                selected_citations=[],
                status="needs_clarification",
                error_type=None,
                error_message=None,
                llm_called=False,
                used_cache=False,
                clarification_needed=True,
            )

        # Co out_of_domain tu router thi dung ngay, khong dua context rong vao LLM.
        if retrieval_result.get("out_of_domain"):
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=(
                    "Câu hỏi này nằm ngoài phạm vi Sổ tay sinh viên nên mình không thể hỗ trợ được. "
                    "Sổ tay chủ yếu bao gồm các nội dung như: quy chế đào tạo, "
                    "thủ tục hành chính, học bổng, rèn luyện, ký túc xá, thông tin phòng ban và khoa/ngành. "
                    "Bạn có thể hỏi lại theo một nội dung liên quan đến sổ tay nhé!"
                ),
                context_used="",
                selected_citations=[],
                status="out_of_domain",
                error_type=None,
                error_message=None,
                llm_called=False,
                used_cache=False,
            )

        # Lop OOD thu 2: kiem tra chat luong retrieval de bat cac cau ngoai pham vi bi route nham.
        if not retrieval_result.get("query_plan") and is_out_of_domain_query(effective_query, retrieval_result):
            final_answer = build_fallback_answer(
                effective_query,
                retrieval_result,
                reason="out_of_domain",
            )
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=final_answer,
                context_used="",
                selected_citations=[],
                status="out_of_domain",
                error_type=None,
                error_message=None,
                llm_called=False,
                used_cache=False,
            )
        citations_config = self.config.get("citations", {})
        guardrails_config = self.config.get("guardrails", {})

        if retrieval_result.get("query_plan"):
            selected_citations = list(
                retrieval_result.get("evidence_citations")
                or retrieval_result.get("citations")
                or []
            )
        else:
            selected_citations = select_relevant_citations(
                retrieval_result.get("citations"),
                intent=retrieval_result.get("intent"),
                retrieval_result=retrieval_result,
                max_sources=int(citations_config.get("max_sources", 2)),
            )

        if guardrails_config.get(
            "skip_llm_on_low_confidence", True
        ) and is_low_confidence(retrieval_result):
            final_answer = format_final_answer(
                build_fallback_answer(
                    effective_query, retrieval_result, reason="low_confidence"
                ),
                selected_citations,
            )
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=final_answer,
                context_used=context_used,
                selected_citations=selected_citations,
                status="low_confidence",
                error_type="retrieval",
                error_message="Retrieval returned empty or insufficient context.",
                llm_called=False,
                used_cache=False,
            )

        context_started = time.monotonic()
        prompt, context_used = build_answer_prompt_bundle(
            query=effective_query,
            retrieval_result=retrieval_result,
            selected_citations=selected_citations,
            max_context_chars=self.max_context_chars,
            cohort=cohort,
        )
        if telemetry is not None:
            telemetry["context_build_ms"] = (
                time.monotonic() - context_started
            ) * 1000
            telemetry["context_chars"] = len(context_used)
            telemetry["source_count"] = len(
                retrieval_result.get("retrieved_items") or []
            )
            telemetry["prompt_chars"] = len(prompt)

        cache_key = self.response_cache.make_cache_key(
            query=effective_query,
            retrieval_result=retrieval_result,
            selected_citations=selected_citations,
            cohort=cohort,
            context_fingerprint=_authorized_context_fingerprint(context_used),
            pipeline_version=PIPELINE_VERSION,
            answer_prompt_version=ANSWER_PROMPT_VERSION,
        )
        cached = self.response_cache.get(cache_key)
        if cached:
            cached_answer = str(cached.get("answer") or "")
            cached_citations = prioritize_citations_by_answer_anchors(
                cached.get("citations") or retrieval_result.get("citations") or [],
                cached_answer,
                max_sources=10,
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

        all_citations = (
            retrieval_result.get("evidence_citations")
            or retrieval_result.get("citations")
            or []
        )
        public_retrieval_citations = retrieval_result.get("citations") or []

        try:
            llm_client = self._get_llm_client()
        except Exception as exc:
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
                model=llm_result.get("model_used") or "gemini-3.1-flash-lite",
                input_tokens=u.get("input", 0),
                output_tokens=u.get("output", 0),
                total_tokens=u.get("total", 0),
                start_time=start_time_llm,
                end_time=end_time_llm,
            )

        if not llm_result.get("ok"):
            error_type = llm_result.get("error_type") or "api_error"
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
            max_sources=10,
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
        router_decision = res.get("router_decision") or {}
        query_handling = res.get("query_handling") or router_decision.get("query_handling") or {}

        execution_mode = res.get("execution_mode") or router_decision.get("execution_mode") or "regulation"
        lookup_type = res.get("lookup_type") or router_decision.get("lookup_type")
        query_type = (
            query_type_override
            or res.get("query_type")
            or router_decision.get("query_type")
            or query_handling.get("context_mode")
            or "standalone"
        )
        model_name = (getattr(self, "llm_config", {}) or {}).get("model_name", "gemini-3.1-flash-lite")

        resolved_fallback = fallback_reason or (
            "none" if status in {"answered", "streaming"} else status
        )
        resolved_citations = citations_used if citations_used is not None else (res.get("citations_used") or res.get("citations") or [])
        resolved_related = related_references if related_references is not None else (res.get("related_references") or [])
        structured_results = build_structured_results(
            res.get("structured_result"),
            citations=list(res.get("citations") or res.get("citations_used") or []),
        )

        return {
            "type": "metadata",
            "run_id": run_id,
            "cohort": (res.get("cohort") or (router_decision or {}).get("cohort") or "default"),
            "status": status,
            "intent": res.get("intent") or router_decision.get("intent"),
            "strategy": res.get("strategy") or router_decision.get("strategy"),
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

        from src.api.usage_tracker import UsageTracker
        from datetime import datetime, timezone

        tracker = UsageTracker()

        yield {"type": "progress", "message": "Đang phân tích câu hỏi..."}

        start_time_router = datetime.now(timezone.utc).isoformat()
        effective_query = query
        cohort = _normalize_retrieval_cohort(resolve_cohort_from_query(query, cohort))

        yield {"type": "progress", "message": "Đang tìm kiếm thông tin trong Sổ tay..."}
        try:
            # Retrieval chạy đồng bộ trước, sau đó mới stream token LLM về frontend.
            retrieval_result = self._run_retrieval(
                query,
                cohort=cohort,
                chat_history=chat_history,
            )

            if retrieval_result.get("router_usage"):
                tracker.record(
                    step_name="AI Router",
                    model=retrieval_result.get("router_model", ""),
                    input_tokens=retrieval_result["router_usage"].get("input", 0),
                    output_tokens=retrieval_result["router_usage"].get("output", 0),
                    total_tokens=retrieval_result["router_usage"].get("total", 0),
                    start_time=start_time_router,
                    end_time=datetime.now(timezone.utc).isoformat(),
                )

            effective_query = str(
                retrieval_result.get("effective_query") or query
            ).strip()
        except Exception:
            fallback = build_fallback_answer(
                query=effective_query, retrieval_result=None, reason="retrieval_error"
            )
            yield self._build_stream_metadata(
                None,
                status="retrieval_error",
                effective_query=effective_query,
                fallback_reason="retrieval_error",
                run_id=run_id,
            )
            yield {"type": "token", "text": fallback}
            yield {"type": "done", "tracker": tracker}
            return

        if retrieval_result.get("needs_clarification"):
            clarification_msg = retrieval_result.get(
                "clarification_question", "Bạn có thể làm rõ câu hỏi được không?"
            )
            yield self._build_stream_metadata(
                retrieval_result,
                status="needs_clarification",
                effective_query=effective_query,
                fallback_reason="needs_clarification",
                run_id=run_id,
            )
            yield {"type": "token", "text": clarification_msg}
            yield {"type": "done", "tracker": tracker}
            return

        # Neu cau hoi mo ho, stream cau hoi lam ro nhu mot token block thay vi goi LLM.
        if not retrieval_result.get("query_plan") and detect_ambiguous_query(effective_query, retrieval_result):
            clarification_msg = build_clarification_question(
                effective_query, retrieval_result
            )
            yield self._build_stream_metadata(
                retrieval_result,
                status="needs_clarification",
                effective_query=effective_query,
                fallback_reason="ambiguous_query",
                query_type_override="ambiguous",
                run_id=run_id,
            )
            yield {"type": "token", "text": clarification_msg}
            yield {"type": "done", "tracker": tracker}
            return

        # Out-of-domain duoc chan truoc khi tao prompt de tranh LLM tra loi ngoai nguon.
        if retrieval_result.get("out_of_domain"):
            out_of_domain_msg = (
                "Câu hỏi này nằm ngoài phạm vi Sổ tay sinh viên nên mình không thể hỗ trợ được. "
                "Sổ tay chủ yếu bao gồm các nội dung như: quy chế đào tạo, "
                "thủ tục hành chính, học bổng, rèn luyện, ký túc xá, thông tin phòng ban và khoa/ngành. "
                "Bạn có thể hỏi lại theo một nội dung liên quan đến sổ tay nhé!"
            )
            yield self._build_stream_metadata(
                retrieval_result,
                status="out_of_domain",
                effective_query=effective_query,
                fallback_reason="out_of_domain",
                run_id=run_id,
            )
            yield {"type": "token", "text": out_of_domain_msg}
            yield {"type": "done", "tracker": tracker}
            return

        if not retrieval_result.get("query_plan") and is_out_of_domain_query(effective_query, retrieval_result):
            out_of_domain_msg = build_fallback_answer(
                effective_query,
                retrieval_result,
                reason="out_of_domain",
            )
            yield self._build_stream_metadata(
                retrieval_result,
                status="out_of_domain",
                effective_query=effective_query,
                fallback_reason="out_of_domain",
                run_id=run_id,
            )
            yield {"type": "token", "text": out_of_domain_msg}
            yield {"type": "done", "tracker": tracker}
            return

        yield {"type": "progress", "message": "Đang phân tích tài liệu tìm được..."}

        citations_config = self.config.get("citations", {})
        guardrails_config = self.config.get("guardrails", {})

        if retrieval_result.get("query_plan"):
            selected_citations = list(
                retrieval_result.get("evidence_citations")
                or retrieval_result.get("citations")
                or []
            )
        else:
            selected_citations = select_relevant_citations(
                retrieval_result.get("citations"),
                intent=retrieval_result.get("intent"),
                retrieval_result=retrieval_result,
                max_sources=int(citations_config.get("max_sources", 2)),
            )

        # Low confidence: yield fallback as single chunk
        if guardrails_config.get(
            "skip_llm_on_low_confidence", True
        ) and is_low_confidence(retrieval_result):
            final_answer = format_final_answer(
                build_fallback_answer(
                    effective_query, retrieval_result, reason="low_confidence"
                ),
                selected_citations,
            )
            yield self._build_stream_metadata(
                retrieval_result,
                status="low_confidence",
                effective_query=effective_query,
                fallback_reason="low_confidence",
                citations_used=selected_citations,
                run_id=run_id,
            )
            yield {"type": "token", "text": final_answer}
            yield {"type": "done", "tracker": tracker}
            return

        all_citations = (
            retrieval_result.get("evidence_citations")
            or retrieval_result.get("citations")
            or []
        )
        public_retrieval_citations = retrieval_result.get("citations") or []
        related_references = retrieval_result.get("related_references") or []

        prompt, context_used = build_answer_prompt_bundle(
            query=effective_query,
            retrieval_result=retrieval_result,
            selected_citations=selected_citations,
            max_context_chars=self.max_context_chars,
            cohort=cohort,
        )
        cache_key = self.response_cache.make_cache_key(
            query=effective_query,
            retrieval_result=retrieval_result,
            selected_citations=selected_citations,
            cohort=cohort,
            context_fingerprint=_authorized_context_fingerprint(context_used),
            pipeline_version=PIPELINE_VERSION,
            answer_prompt_version=ANSWER_PROMPT_VERSION,
        )
        cached = self.response_cache.get(cache_key)
        if cached:
            cached_answer = str(cached.get("answer") or "")
            cached_citations = prioritize_citations_by_answer_anchors(
                cached.get("citations") or public_retrieval_citations,
                cached_answer,
                max_sources=10,
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
        yield self._build_stream_metadata(
            retrieval_result,
            status="streaming",
            effective_query=effective_query,
            citations_used=public_retrieval_citations,
            related_references=related_references,
            llm_called=True,
            run_id=run_id,
        )

        final_answer_for_citations = ""
        terminal_status = "answered"
        terminal_error_type: str | None = None
        try:
            llm_client = self._get_llm_client()
            start_time_llm = datetime.now(timezone.utc).isoformat()
            self._throttle_llm_call()
            emitted_answer_parts: list[str] = []
            pending_stream_text = ""
            stream_prefix_emitted = False
            suppress_source_tail = False
            for chunk in llm_client.generate_stream(prompt):
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

            if (
                hasattr(llm_client, "_last_stream_usage")
                and llm_client._last_stream_usage
            ):
                tracker.record(
                    step_name="LLM Generation",
                    model=getattr(llm_client, "_last_stream_model", ""),
                    input_tokens=llm_client._last_stream_usage.get("input", 0),
                    output_tokens=llm_client._last_stream_usage.get("output", 0),
                    total_tokens=llm_client._last_stream_usage.get("total", 0),
                    start_time=start_time_llm,
                    end_time=end_time_llm,
                )
        except Exception as exc:
            terminal_status = "api_error"
            terminal_error_type = type(exc).__name__
            fallback = build_fallback_answer(
                effective_query, retrieval_result, reason="api_error"
            )
            final_answer_for_citations = fallback
            yield {"type": "token", "text": fallback}

        final_citations = prioritize_citations_by_answer_anchors(
            all_citations,
            final_answer_for_citations,
            max_sources=10,
        )
        yield self._build_stream_metadata(
            retrieval_result,
            status=terminal_status,
            effective_query=effective_query,
            fallback_reason=("api_error" if terminal_status == "api_error" else None),
            error_type=terminal_error_type,
            citations_used=final_citations,
            related_references=related_references,
            llm_called=True,
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

    def _run_retrieval(
        self,
        query: str,
        cohort: str | None = None,
        chat_history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Run the active QueryPlan and retrieval stack for one cohort context."""
        if _env_bool("STUDENT_RAG_EVAL_FORCE_REGULATION_RAG"):
            query_handling = {
                "raw_query": query,
                "effective_query": query,
                "mode": "raw",
                "context_mode": "standalone",
                "source": "eval_force_regulation",
                "normalized_query": None,
                "standalone_query": None,
                "referenced_turns": [],
                "normalization_confidence": "none",
                "context_confidence": "none",
                "validation_errors": [],
                "needs_clarification": False,
                "clarification_question": None,
            }
            retrieval_query = self.slang_normalizer.normalize_for_retrieval(query)
            result = run_hybrid_retrieval_pipeline(
                query=query,
                top_k=self.config["retrieval"]["default_top_k"],
                cohort=cohort,
                intent="open_question",
                strategy="regulation",
                retrieval_query=retrieval_query,
            )
            router_decision = {
                "route": "rag",
                "execution_mode": "regulation",
                "intent": "open_question",
                "lookup_type": None,
                "cohort": cohort,
                "retrieval_query": retrieval_query,
                "query_handling": query_handling,
                "eval_force_regulation": True,
            }
            result["selected_cohort"] = cohort
            result["router_decision"] = router_decision
            result["raw_query"] = query
            result["effective_query"] = query
            result["query_handling"] = query_handling
            result["retrieval_query"] = retrieval_query
            return result

        if not hasattr(self, "router"):
            from src.retrieval.core.ai_router import AIRouter
            self.router = AIRouter.from_config()

        return self._run_query_plan(
            query=query,
            cohort=cohort,
            chat_history=chat_history,
        )

    def _run_query_plan(
        self,
        *,
        query: str,
        cohort: str | None,
        chat_history: list[dict[str, str]] | None,
    ) -> dict[str, Any]:
        """Plan and execute at most three independent, non-recursive tasks."""
        router_input_query = self.slang_normalizer.replace_for_router(query)
        raw_plan = self.router.plan(
            router_input_query,
            chat_history=chat_history,
            cohort=cohort,
        )

        plan_keys = (
            "schema_version",
            "context_mode",
            "normalized_query",
            "standalone_query",
            "referenced_turns",
            "out_of_domain",
            "tasks",
        )
        plan = {key: raw_plan.get(key) for key in plan_keys}
        planner_fallback = raw_plan.get("planner_fallback")
        effective_query_candidate = (
            plan.get("standalone_query")
            if plan.get("context_mode") == "follow_up"
            else plan.get("normalized_query")
        )
        effective_query = str(effective_query_candidate or query).strip() or query
        query_handling = {
            "raw_query": query,
            "effective_query": effective_query,
            "mode": "standalone_rewrite" if plan.get("context_mode") == "follow_up" else "normalized",
            "context_mode": plan.get("context_mode") or "standalone",
            "source": "query_plan",
            "normalized_query": plan.get("normalized_query"),
            "standalone_query": plan.get("standalone_query"),
            "referenced_turns": plan.get("referenced_turns") or [],
            "validation_errors": raw_plan.get("planner_validation_errors") or [],
            "needs_clarification": False,
            "clarification_question": None,
        }
        base_result = {
            "query": query,
            "retrieval_query": self.slang_normalizer.normalize_for_retrieval(effective_query),
            "effective_query": effective_query,
            "raw_query": query,
            "selected_cohort": cohort,
            "query_handling": query_handling,
            "query_plan": plan,
            "planner_fallback": planner_fallback,
            "router_usage": raw_plan.get("usage"),
            "router_model": raw_plan.get("model_used"),
        }
        if plan.get("out_of_domain"):
            return {
                **base_result,
                "intent": "out_of_domain",
                "strategy": "query_plan",
                "execution_mode": "none",
                "structured_result": None,
                "retrieved_items": [],
                "citations": [],
                "task_results": [],
                "coverage_by_task": {},
                "supports_task_ids": {},
                "needs_llm_answer": False,
                "needs_clarification": False,
                "clarification_question": None,
                "out_of_domain": True,
            }

        task_results: list[dict[str, Any]] = []
        structured_results: list[dict[str, Any]] = []
        all_items: list[dict[str, Any]] = []
        all_citations: list[dict[str, Any]] = []
        all_related_references: list[dict[str, Any]] = []
        coverage_by_task: dict[str, str] = {}
        clarification_questions: list[str] = []

        for task in plan.get("tasks") or []:
            task_id = str(task.get("id") or f"t{len(task_results) + 1}")
            mode = task.get("mode")
            task_cohorts = task.get("cohorts") or ([cohort] if cohort else [None])
            task_cohorts = list(dict.fromkeys(task_cohorts))
            task_evidence: list[dict[str, Any]] = []
            cohort_coverage: dict[str, str] = {}
            clarification_by_cohort: dict[str, str] = {}
            task_citations: list[dict[str, Any]] = []
            task_items: list[dict[str, Any]] = []

            if mode == "clarify":
                question = str(task.get("clarification_question") or "Bạn có thể làm rõ yêu cầu này không?")
                clarification_questions.append(question)
                coverage_by_task[task_id] = "needs_clarification"
                task_results.append({
                    "task_id": task_id,
                    "question": task.get("question"),
                    "mode": mode,
                    "coverage": "needs_clarification",
                    "clarification_question": question,
                    "cohorts": task_cohorts,
                    "evidence": [],
                })
                continue

            for task_cohort in task_cohorts:
                if mode == "structured":
                    sub_result = self._execute_planned_structured_task(
                        task=task,
                        task_id=task_id,
                        cohort=task_cohort,
                    )
                else:
                    sub_result = self._execute_planned_rag_task(
                        task=task,
                        task_id=task_id,
                        cohort=task_cohort,
                    )
                cohort_key = str(task_cohort or "default")
                cohort_coverage[cohort_key] = sub_result["coverage"]
                task_evidence.extend(sub_result.get("evidence") or [])
                task_citations.extend(sub_result.get("citations") or [])
                task_items.extend(sub_result.get("retrieved_items") or [])
                all_related_references.extend(
                    sub_result.get("related_references") or []
                )
                structured = sub_result.get("structured_result")
                if structured:
                    structured_results.append(structured)
                clarification = sub_result.get("clarification_question")
                if clarification:
                    clarification_questions.append(str(clarification))
                    clarification_by_cohort[cohort_key] = str(clarification)

            statuses = list(cohort_coverage.values())
            if statuses and all(status == "covered" for status in statuses):
                coverage = "covered"
            elif any(status == "needs_clarification" for status in statuses):
                coverage = "needs_clarification"
            else:
                coverage = "uncovered"
            coverage_by_task[task_id] = coverage
            all_items.extend(task_items)
            all_citations.extend(task_citations)
            task_results.append({
                "task_id": task_id,
                "question": task.get("question"),
                "mode": mode,
                "lookup_type": task.get("lookup_type"),
                "intent": task.get("intent"),
                "cohorts": task_cohorts,
                "coverage": coverage,
                "coverage_by_cohort": cohort_coverage,
                "clarification_by_cohort": clarification_by_cohort,
                "evidence": task_evidence,
                "citation_count": len(task_citations),
            })

        merged_items = self._merge_task_items(all_items)
        merged_citations = self._merge_task_citations(all_citations)
        selected_citations = self._select_task_primary_citations(
            merged_citations,
            coverage_by_task,
            max_sources=int(self.config.get("planning", {}).get("max_citations", 10)),
        )
        covered_any = any(value == "covered" for value in coverage_by_task.values())
        clarify_any = any(value == "needs_clarification" for value in coverage_by_task.values())
        if len(structured_results) == 1:
            structured_result: dict[str, Any] | None = structured_results[0]
        elif structured_results:
            structured_result = {
                "lookup_type": "multi_task_structured",
                "sub_lookups": structured_results,
                "result": structured_results,
                "table_name": "Dữ liệu tra cứu có cấu trúc theo từng yêu cầu",
                "source_label": "Sổ tay sinh viên HCMUE",
            }
        else:
            structured_result = None
        task_modes = {str(task.get("mode")) for task in (plan.get("tasks") or [])}
        executable_modes = task_modes - {"clarify"}
        if len(executable_modes) > 1:
            execution_mode = "mixed"
        elif executable_modes:
            execution_mode = next(iter(executable_modes))
        elif "clarify" in task_modes:
            execution_mode = "clarify"
        else:
            execution_mode = "regulation"
        return {
            **base_result,
            "intent": "multi_task" if len(task_results) > 1 else (task_results[0].get("intent") if task_results else "open_question"),
            "strategy": "query_plan_execution",
            "execution_mode": execution_mode,
            "lookup_type": None,
            "structured_result": structured_result,
            "retrieved_items": merged_items,
            "evidence_citations": merged_citations,
            "citations": selected_citations,
            "related_references": self._merge_related_references(
                all_related_references
            ),
            "task_results": task_results,
            "coverage_by_task": coverage_by_task,
            "supports_task_ids": {
                str(citation.get("chunk_id") or index): citation.get("supports_task_ids") or []
                for index, citation in enumerate(selected_citations)
            },
            "needs_llm_answer": covered_any,
            "needs_clarification": bool(clarify_any and not covered_any),
            "clarification_question": clarification_questions[0] if clarification_questions else None,
            "out_of_domain": False,
            "deterministic_validated": bool(structured_results),
        }

    def _execute_planned_structured_task(
        self,
        *,
        task: dict[str, Any],
        task_id: str,
        cohort: str | None,
    ) -> dict[str, Any]:
        from src.retrieval.core.structured_dispatcher import resolve_structured_decision

        decision = {
            "route": "structured",
            "execution_mode": "structured",
            "intent": task.get("intent"),
            "lookup_type": task.get("lookup_type"),
            "slots": task.get("slots") or {},
            "slot_spans": task.get("slot_spans") or {},
            "cohort": cohort,
            "cohorts": [cohort] if cohort else [],
            "retrieval_query": task.get("question"),
        }
        resolution = resolve_structured_decision(
            decision,
            query=self.slang_normalizer.normalize_for_retrieval(str(task.get("question") or "")),
            cohort=cohort,
            scoring_tables=self.scoring_tables,
            formula_rules=self.formula_rules,
            office_directory=self.student_office_profiles,
            student_service_directory=self.student_service_directory,
            student_faculty_profiles=self.student_faculty_profiles,
            foreign_language_tables=self.foreign_language_tables,
            structured_tables_registry=self.structured_tables_registry,
            program_directory=self.program_directory,
            model=self.model,
        )
        if not resolution or not resolution.result:
            return {"coverage": "uncovered", "evidence": [], "citations": [], "retrieved_items": []}
        if resolution.result_kind == "clarification":
            return {
                "coverage": "needs_clarification",
                "clarification_question": resolution.result.get("clarification_question"),
                "evidence": [],
                "citations": [],
                "retrieved_items": [],
            }
        evidence = {**resolution.result, "task_id": task_id, "cohort": resolution.result.get("cohort") or cohort}
        citations = enrich_citations_with_parent_details(
            build_citation_from_lookup(evidence),
            getattr(self, "parent_sources_by_id", {}),
        )
        citations = [
            {**citation, "task_id": task_id, "supports_task_ids": [task_id], "cohort": citation.get("cohort") or cohort}
            for citation in citations
        ]
        related_references = self._structured_related_references(
            citations,
            cohort=cohort,
        )
        coverage = "covered" if citations else "uncovered"
        return {
            "coverage": coverage,
            "evidence": [evidence],
            "structured_result": evidence,
            "citations": citations,
            "related_references": related_references,
            "retrieved_items": [],
        }

    def _execute_planned_rag_task(
        self,
        *,
        task: dict[str, Any],
        task_id: str,
        cohort: str | None,
    ) -> dict[str, Any]:
        task_query = str(task.get("question") or "").strip()
        retrieval_query = self.slang_normalizer.normalize_for_retrieval(task_query)
        result = run_hybrid_retrieval_pipeline(
            query=task_query,
            top_k=int(self.config.get("planning", {}).get("rag_top_k", 5)),
            cohort=cohort,
            intent=task.get("intent") or "open_question",
            strategy="regulation",
            retrieval_query=retrieval_query,
        )
        items = []
        for item in result.get("retrieved_items") or []:
            if not is_validated_source_applicable(item, cohort):
                continue
            copied = dict(item)
            metadata = dict(copied.get("metadata") or {})
            metadata.update({"task_id": task_id, "supports_task_ids": [task_id], "cohort": metadata.get("cohort") or cohort})
            copied["metadata"] = metadata
            copied["task_id"] = task_id
            copied["supports_task_ids"] = [task_id]
            items.append(copied)
            if len(items) >= 5:
                break
        citations = [
            {**citation, "task_id": task_id, "supports_task_ids": [task_id], "cohort": citation.get("cohort") or cohort}
            for citation in (result.get("citations") or [])
            if is_validated_source_applicable(citation, cohort)
        ]
        citations = citations[:5]
        coverage = "covered" if items and citations else "uncovered"
        evidence = [{
            "task_id": task_id,
            "cohort": cohort,
            "retrieval_query": retrieval_query,
            "source_ids": [str(item.get("chunk_id") or item.get("_id") or "") for item in items],
        }]
        return {
            "coverage": coverage,
            "evidence": evidence,
            "citations": citations,
            "retrieved_items": items,
            "related_references": result.get("related_references") or [],
        }

    def _structured_related_references(
        self,
        citations: list[dict[str, Any]],
        *,
        cohort: str | None,
    ) -> list[dict[str, Any]]:
        """Expose direct graph neighbors for structured source articles as UI metadata."""
        primary_ids = list(
            dict.fromkeys(
                str(
                    citation.get("source_parent_id")
                    or citation.get("parent_section_id")
                    or citation.get("chunk_id")
                    or ""
                ).strip()
                for citation in citations
                if isinstance(citation, dict)
            )
        )
        primary_ids = [parent_id for parent_id in primary_ids if parent_id]
        if not primary_ids:
            return []

        graph = getattr(self, "_structured_graph", None)
        if graph is None:
            graph = NetworkXGraphTraverser()
            self._structured_graph = graph
        expanded = graph.expand_context(primary_ids, max_depth=1)
        candidates = select_graph_related_parent_candidates(primary_ids, expanded)
        related_items: list[dict[str, Any]] = []
        for rank, candidate in enumerate(candidates, start=1):
            parent_id = str(candidate.get("parent_id") or "").strip()
            parent = getattr(self, "parent_sources_by_id", {}).get(parent_id)
            if not isinstance(parent, dict):
                continue
            if cohort and not is_validated_source_applicable(parent, cohort):
                continue
            metadata = dict(parent.get("metadata") or {})
            related_items.append(
                {
                    **parent,
                    "chunk_id": parent_id,
                    "content": parent.get("content") or "",
                    "metadata": {
                        **metadata,
                        "related_source_primary_id": candidate.get(
                            "source_primary_id"
                        ),
                        "related_graph_depth": candidate.get("depth"),
                        "related_rank": rank,
                    },
                }
            )
        return build_related_references(related_items)

    @staticmethod
    def _merge_related_references(
        references: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for reference in references:
            if not isinstance(reference, dict):
                continue
            key = (
                str(reference.get("primary_chunk_id") or ""),
                str(reference.get("related_chunk_id") or ""),
            )
            if not all(key) or key in seen:
                continue
            seen.add(key)
            item = dict(reference)
            display_label = f"R{len(merged) + 1}"
            if item.get("canonical_source_id"):
                item["display_label"] = display_label
                item["id"] = item["canonical_source_id"]
            else:
                item.pop("display_label", None)
                item["id"] = display_label
            merged.append(item)
        return merged

    @staticmethod
    def _merge_task_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for item in items:
            metadata = item.get("metadata") or {}
            key = (
                str(metadata.get("cohort") or "default"),
                str(item.get("chunk_id") or item.get("_id") or metadata.get("source_parent_id") or ""),
            )
            if key not in merged:
                merged[key] = dict(item)
                merged[key]["supports_task_ids"] = list(item.get("supports_task_ids") or [])
            else:
                supports = merged[key].setdefault("supports_task_ids", [])
                for task_id in item.get("supports_task_ids") or []:
                    if task_id not in supports:
                        supports.append(task_id)
        return list(merged.values())

    @staticmethod
    def _merge_task_citations(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[tuple[Any, ...], dict[str, Any]] = {}
        for citation in citations:
            canonical_source_id = (
                citation.get("source_parent_id")
                or citation.get("parent_section_id")
                or citation.get("chunk_id")
                or citation.get("document_id")
                or citation.get("source_section")
                or citation.get("title")
            )
            key = (str(citation.get("cohort") or "default"), str(canonical_source_id or ""))
            if key not in merged:
                merged[key] = dict(citation)
                merged[key]["supports_task_ids"] = list(citation.get("supports_task_ids") or [])
            else:
                supports = merged[key].setdefault("supports_task_ids", [])
                for task_id in citation.get("supports_task_ids") or []:
                    if task_id not in supports:
                        supports.append(task_id)
                if (
                    merged[key].get("evidence_kind") == "structured_result"
                    and citation.get("evidence_kind") == "structured_result"
                ):
                    merged[key]["content"] = _merge_structured_citation_content(
                        merged[key],
                        citation,
                    )
                    merged[key]["source_pages"] = sorted(
                        {
                            *list(merged[key].get("source_pages") or []),
                            *list(citation.get("source_pages") or []),
                        }
                    )
        return list(merged.values())

    @staticmethod
    def _select_task_primary_citations(
        citations: list[dict[str, Any]],
        coverage_by_task: dict[str, str],
        *,
        max_sources: int,
    ) -> list[dict[str, Any]]:
        selected: list[dict[str, Any]] = []
        selected_ids: set[int] = set()
        for task_id, coverage in coverage_by_task.items():
            if coverage != "covered":
                continue
            for index, citation in enumerate(citations):
                if task_id in (citation.get("supports_task_ids") or []):
                    if index not in selected_ids:
                        selected.append(citation)
                        selected_ids.add(index)
                    break
        for index, citation in enumerate(citations):
            if len(selected) >= max_sources:
                break
            if index not in selected_ids:
                selected.append(citation)
        return selected[:max_sources]

    def _get_llm_client(self) -> Any:
        """Lazily create the configured LLM client for generated true-RAG answers."""
        if self._llm_client is None:
            llm_config = self.config["llm"]
            provider = llm_config.get("provider", "gemini")
            if provider == "gemini":
                self._llm_client = GeminiClient(
                    model_name=llm_config.get("model_name", "gemini-3.1-flash-lite"),
                    temperature=llm_config.get("temperature", 0.2),
                    max_output_tokens=llm_config.get("max_output_tokens", 1024),
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
        router_decision = retrieval_result.get("router_decision")
        query_handling = retrieval_result.get("query_handling")
        if not isinstance(query_handling, dict) and isinstance(router_decision, dict):
            query_handling = router_decision.get("query_handling")
        if not isinstance(query_handling, dict):
            query_handling = None
        run_id = None
        if model_used is None:
            llm_cfg = getattr(self, "llm_config", {}) or {}
            model_used = llm_cfg.get("model_name", "gemini-3.1-flash-lite")
        return {
            "run_id": run_id,
            "query": query,
            "effective_query": retrieval_result.get("effective_query")
            or (query_handling or {}).get("effective_query")
            or query,
            "cohort": retrieval_result.get("cohort") or (router_decision or {}).get("cohort") or "default",
            "query_handling": query_handling,
            "router_decision": router_decision,
            "answer": final_answer,
            "status": status,
            "error_type": error_type,
            "error_message": error_message,
            "intent": retrieval_result.get("intent"),
            "strategy": retrieval_result.get("strategy"),
            "execution_mode": retrieval_result.get("execution_mode") or (router_decision or {}).get("execution_mode") or "regulation",
            "lookup_type": retrieval_result.get("lookup_type") or (router_decision or {}).get("lookup_type"),
            "query_type": retrieval_result.get("query_type") or (router_decision or {}).get("query_type") or "standalone",
            "target_chunk_types": retrieval_result.get("target_chunk_types") or [],
            "raw_query": query,
            "fallback_reason": error_type or (status if status in {"out_of_domain", "needs_clarification", "low_confidence", "retrieval_error", "api_error"} else "none"),
            "retrieved_chunks_count": len(retrieval_result.get("retrieved_items") or []),
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
        telemetry = _evaluation_telemetry.get()
        if telemetry is None:
            return None
        output = dict(telemetry)
        started_at = float(output.pop("started_at_monotonic", time.monotonic()))
        output["total_ms"] = (time.monotonic() - started_at) * 1000
        output["cache_hit"] = used_cache
        output["llm_called"] = llm_called
        return output
