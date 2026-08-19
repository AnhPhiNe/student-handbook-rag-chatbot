import os
import time
from contextvars import ContextVar
from collections.abc import Iterator
from pathlib import Path
from typing import Any


from src.common.cohort import resolve_cohort_from_query
from src.retrieval.core.citation_builder import (
    build_citation_from_lookup,
    enrich_citations_with_parent_details,
)
from src.retrieval.core.hybrid_pipeline import run_hybrid_retrieval_pipeline
from src.retrieval.core.query_context import (
    select_effective_query,
    validated_correction_provenance,
)
from src.retrieval.core.request_execution import RequestExecutionContext
from src.retrieval.core.structured_routing import (
    bind_effective_cohort,
    reject_invalid_plan,
    load_lookup_registry,
    validate_router_decision,
)
from src.retrieval.core.vector_retriever import (
    get_chroma_collection,
    load_embedding_model,
)
from src.retrieval.core.slang_normalizer import SlangNormalizer
from .answer_formatter import (
    format_final_answer,
    format_final_response,
    normalize_unlabeled_enumeration_references,
)
from .answer_guardrails import (
    build_clarification_question,
    build_fallback_answer,
    detect_ambiguous_query,
    is_low_confidence,
    is_out_of_domain_query,
)
from .citation_formatter import select_relevant_citations
from .context_allocation import ContextAllocationConfig, build_context_for_prompt
from .gemini_client import GeminiClient
from .io_utils import load_json, load_yaml
from .prompt_builder import (
    DEFAULT_MAX_CONTEXT_CHARS,
    build_answer_prompt,
)
from .response_cache import get_response_cache


DEFAULT_CONFIG_PATH = Path("configs/answer_generation.yaml")

PIPELINE_VERSION = "v33-single-cohort-contract-hardening"
STREAM_OUTPUT_GUARDRAIL_BUFFER_CHARS = 128
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
        self.entity_registry = load_json(self.config["input"]["entity_registry"])
        
        query_expansion_rules_path = self.config["input"].get("query_expansion_rules")
        self.expansion_rules = (
            load_json(query_expansion_rules_path)
            if query_expansion_rules_path and Path(query_expansion_rules_path).is_file()
            else {}
        )
        self.slang_normalizer = SlangNormalizer(
            program_directory=self.program_directory,
        )


        self.model = load_embedding_model(self.config["embedding"]["model_name"])
        try:
            collection_name = (
                os.getenv("QDRANT_COLLECTION_NAME")
                or os.getenv("STUDENT_RAG_HYBRID_COLLECTION")
                or self.config["vectorstore"].get(
                    "collection_name", "student_handbook_semantic_v4"
                )
            )
            self.collection = get_chroma_collection(
                persist_dir=self.config["vectorstore"].get(
                    "persist_dir", "data/vectorstore/chroma"
                ),
                collection_name=collection_name,
            )
        except Exception as exc:
            import logging

            logging.getLogger(__name__).warning(
                f"Skip Chroma initialization because Qdrant hybrid retrieval is configured: {exc}"
            )
            self.collection = None

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
        self.context_allocation = ContextAllocationConfig.from_config(
            self.config.get("context_allocation")
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

        The sync path runs router + retrieval,
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

        if retrieval_result.get("infrastructure_error"):
            final_answer = build_fallback_answer(
                query=effective_query,
                retrieval_result=retrieval_result,
                reason="retrieval_error",
            )
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=final_answer,
                context_used="",
                selected_citations=[],
                status="retrieval_error",
                error_type=str(
                    retrieval_result.get("error_type") or "retrieval_error"
                ),
                error_message=str(retrieval_result.get("error_message") or ""),
                llm_called=False,
                used_cache=False,
            )

        context_started = time.monotonic()
        context_used = build_context_for_prompt(
            retrieval_result,
            query=effective_query,
            max_context_chars=self.max_context_chars,
            allocation_config=self.context_allocation,
        )
        if telemetry is not None:
            telemetry["context_build_ms"] = (time.monotonic() - context_started) * 1000
            telemetry["context_chars"] = len(context_used)
            telemetry["source_count"] = len(
                retrieval_result.get("retrieved_items") or []
            )

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
        if detect_ambiguous_query(effective_query, retrieval_result):
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
        if is_out_of_domain_query(effective_query, retrieval_result):
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

        cache_key = self.response_cache.make_cache_key(
            query=effective_query,
            retrieval_result=retrieval_result,
            selected_citations=selected_citations,
            cohort=cohort,
            context_fingerprint=self.context_allocation.cache_fingerprint(),
            pipeline_version=PIPELINE_VERSION,
        )
        cached = self.response_cache.get(cache_key)
        if cached:
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=str(cached.get("answer") or ""),
                context_used=context_used,
                selected_citations=selected_citations,
                status=str(cached.get("status") or "answered"),
                error_type=cached.get("error_type"),
                error_message=cached.get("error_message"),
                llm_called=False,
                used_cache=True,
            )

        all_citations = retrieval_result.get("citations") or []

        prompt_started = time.monotonic()
        prompt = build_answer_prompt(
            query=effective_query,
            retrieval_result=retrieval_result,
            selected_citations=None,
            max_context_chars=self.max_context_chars,
            cohort=cohort,
            context_allocation=self.context_allocation,
        )
        if telemetry is not None:
            telemetry["prompt_build_ms"] = (time.monotonic() - prompt_started) * 1000
            telemetry["prompt_chars"] = len(prompt)

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
                selected_citations=all_citations,
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
                selected_citations=all_citations,
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
        output = self._build_output(
            query=query,
            retrieval_result=retrieval_result,
            final_answer=final_answer,
            context_used=context_used,
            selected_citations=all_citations,
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
                "citations": all_citations,
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
        citations_used: list[dict[str, Any]] | None = None,
        related_references: list[dict[str, Any]] | None = None,
        llm_called: bool = False,
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

        resolved_fallback = fallback_reason or ("none" if status == "answered" else status)
        resolved_citations = citations_used if citations_used is not None else (res.get("citations_used") or res.get("citations") or [])
        resolved_related = related_references if related_references is not None else (res.get("related_references") or [])

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
            "citations_used": resolved_citations,
            "related_references": resolved_related,
            "detected_entities": res.get("detected_entities") or [],
            "target_chunk_types": res.get("target_chunk_types") or [],
            "llm_called": llm_called,
            "debug": {
                "plan_version": router_decision.get("plan_version"),
                "effective_cohort": res.get("selected_cohort") or router_decision.get("cohort"),
                "retrieval_executed": bool(res.get("retrieval_executed")),
                "partial_status": self._partial_status(res),
                "request_results": res.get("request_results") or [],
                "request_execution_contexts": res.get("request_execution_contexts") or [],
            },
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

        if retrieval_result.get("infrastructure_error"):
            fallback = build_fallback_answer(
                query=effective_query,
                retrieval_result=retrieval_result,
                reason="retrieval_error",
            )
            yield self._build_stream_metadata(
                retrieval_result,
                status="retrieval_error",
                effective_query=effective_query,
                fallback_reason=str(
                    retrieval_result.get("error_type") or "retrieval_error"
                ),
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
        if detect_ambiguous_query(effective_query, retrieval_result):
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

        if is_out_of_domain_query(effective_query, retrieval_result):
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

        all_citations = retrieval_result.get("citations") or []
        related_references = retrieval_result.get("related_references") or []

        prompt = build_answer_prompt(
            query=effective_query,
            retrieval_result=retrieval_result,
            selected_citations=None,
            max_context_chars=self.max_context_chars,
            cohort=cohort,
            context_allocation=self.context_allocation,
        )

        yield {"type": "progress", "message": "Đang tổng hợp câu trả lời..."}
        yield self._build_stream_metadata(
            retrieval_result,
            status="answered",
            effective_query=effective_query,
            citations_used=all_citations,
            related_references=related_references,
            llm_called=True,
            run_id=run_id,
        )

        try:
            llm_client = self._get_llm_client()
            start_time_llm = datetime.now(timezone.utc).isoformat()
            self._throttle_llm_call()
            streamed_answer_parts: list[str] = []
            pending_stream_text = ""
            for chunk in llm_client.generate_stream(prompt):
                chunk_text = str(chunk)
                streamed_answer_parts.append(chunk_text)
                pending_stream_text += chunk_text
                pending_stream_text = normalize_unlabeled_enumeration_references(
                    pending_stream_text
                )
                if len(pending_stream_text) > STREAM_OUTPUT_GUARDRAIL_BUFFER_CHARS:
                    safe_text = pending_stream_text[
                        :-STREAM_OUTPUT_GUARDRAIL_BUFFER_CHARS
                    ]
                    pending_stream_text = pending_stream_text[
                        -STREAM_OUTPUT_GUARDRAIL_BUFFER_CHARS:
                    ]
                    yield {"type": "token", "text": safe_text}

            if pending_stream_text:
                yield {
                    "type": "token",
                    "text": normalize_unlabeled_enumeration_references(
                        pending_stream_text
                    ),
                }
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
        except Exception:
            fallback = build_fallback_answer(
                effective_query, retrieval_result, reason="api_error"
            )
            yield {"type": "token", "text": fallback}

        # Chặn việc yield sources text dưới dạng văn bản thô
        # sources_text = format_sources_text(selected_citations)
        # if sources_text:
        #     yield {"type": "token", "text": f"\n\n{sources_text}"}

        yield {"type": "done", "tracker": tracker}

    def _run_retrieval(
        self,
        query: str,
        cohort: str | None = None,
        chat_history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Run the backend retrieval/router stack with the active cohort context."""
        os.environ["STUDENT_RAG_DISABLE_PHORANKER"] = "1"

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
                model=self.model,
                collection=self.collection,
                scoring_tables=self.scoring_tables,
                formula_rules=self.formula_rules,
                entity_registry=self.entity_registry,
                expansion_rules=self.expansion_rules,
                office_directory=self.student_office_profiles,
                student_service_directory=self.student_service_directory,
                student_faculty_profiles=self.student_faculty_profiles,
                foreign_language_tables=self.foreign_language_tables,
                structured_tables_registry=self.structured_tables_registry,
                program_directory=self.program_directory,
                top_k=self.config["retrieval"]["default_top_k"],
                batch_size=self.config["retrieval"].get("batch_size", 8),
                normalize_embeddings=self.config["embedding"].get(
                    "normalize_embeddings", True
                ),
                cohort=cohort,
                candidate_multiplier=int(
                    self.config["retrieval"].get("candidate_multiplier", 5)
                ),
                min_candidates=int(self.config["retrieval"].get("min_candidates", 25)),
                chat_history=chat_history,
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

        # The planner sees the immutable user query. Alias/slang expansion is a
        # code-derived retrieval concern and must not alter planner grounding.
        router_input_query = query
        try:
            router_decision = self.router.route(
                router_input_query,
                chat_history=chat_history,
                cohort=cohort,
            )
        except TypeError:
            router_decision = self.router.route(
                router_input_query,
                chat_history=chat_history,
            )
        handling = select_effective_query(
            query,
            router_decision,
            chat_history=chat_history,
            selected_cohort=cohort,
        )
        query_handling = handling.to_dict()
        effective_query = handling.effective_query or query
        registry = load_lookup_registry()
        router_decision = bind_effective_cohort(
            router_decision,
            raw_query=query,
            effective_query=effective_query,
            selected_cohort=cohort,
            registry=registry,
        )
        router_decision = {
            **router_decision,
            "query_handling": query_handling,
            "effective_query": effective_query,
            "router_input_query": router_input_query,
        }
        if router_decision.get("router_error_type"):
            return {
                "query": query,
                "retrieval_query": None,
                "retrieval_executed": False,
                "intent": "router_error",
                "strategy": "router_infrastructure_error",
                "router_decision": router_decision,
                "structured_result": None,
                "retrieved_items": [],
                "citations": [],
                "needs_llm_answer": False,
                "needs_clarification": False,
                "clarification_question": None,
                "out_of_domain": False,
                "infrastructure_error": True,
                "error_type": str(router_decision.get("router_error_type")),
                "error_message": str(router_decision.get("router_error") or ""),
                "selected_cohort": router_decision.get("cohort"),
                "query_handling": query_handling,
                "effective_query": effective_query,
                "raw_query": query,
                "deterministic_validated": False,
            }

        if router_decision.get("route") in {"structured", "rag"} and isinstance(
            router_decision.get("lookup_requests"), list
        ):
            runtime_validation_errors = validate_router_decision(
                router_decision,
                query=query,
                selected_cohort=router_decision.get("cohort"),
                grounding_context=effective_query,
                registry=registry,
                validated_corrections=validated_correction_provenance(
                    router_decision, handling
                ),
            )
            if runtime_validation_errors:
                router_decision = reject_invalid_plan(
                    router_decision,
                    runtime_validation_errors,
                    query=effective_query,
                )
                router_decision["runtime_validation_errors"] = (
                    runtime_validation_errors
                )
        if handling.needs_clarification:
            return {
                "query": query,
                "retrieval_query": None,
                "retrieval_executed": False,
                "intent": router_decision.get("intent"),
                "strategy": "query_context_clarification",
                "router_decision": router_decision,
                "structured_result": None,
                "retrieved_items": [],
                "citations": [],
                "needs_llm_answer": False,
                "needs_clarification": True,
                "clarification_question": handling.clarification_question,
                "out_of_domain": False,
                "selected_cohort": cohort,
                "query_handling": query_handling,
                "effective_query": effective_query,
                "raw_query": query,
                "deterministic_validated": False,
            }

        if router_decision.get("route") == "clarify":
            return {
                "query": query,
                "retrieval_query": None,
                "retrieval_executed": False,
                "intent": router_decision.get("intent") or "clarify",
                "strategy": "router_clarification",
                "router_decision": router_decision,
                "structured_result": None,
                "retrieved_items": [],
                "citations": [],
                "needs_llm_answer": False,
                "needs_clarification": True,
                "clarification_question": router_decision.get("clarification_question"),
                "out_of_domain": False,
                "selected_cohort": cohort,
                "query_handling": query_handling,
                "effective_query": effective_query,
                "raw_query": query,
                "deterministic_validated": False,
            }

        if router_decision.get("route") == "out_of_domain":
            router_decision = {
                **router_decision,
                "intent": "out_of_domain",
            }
            return {
                "query": query,
                "retrieval_query": None,
                "retrieval_executed": False,
                "intent": "out_of_domain",
                "strategy": "none",
                "router_decision": router_decision,
                "structured_result": None,
                "retrieved_items": [],
                "citations": [],
                "needs_llm_answer": False,
                "needs_clarification": False,
                "clarification_question": None,
                "out_of_domain": True,
                "selected_cohort": cohort,
                "query_handling": query_handling,
                "effective_query": effective_query,
                "raw_query": query,
                "deterministic_validated": False,
            }

        retrieval_query = self.slang_normalizer.normalize_for_retrieval(effective_query)

        cohorts = router_decision.get("cohorts") or []
        is_multi_cohort = bool(
            router_decision.get("is_multi_cohort") and len(cohorts) >= 2
        )

        if not is_multi_cohort:
            effective_cohort = _normalize_retrieval_cohort(
                router_decision.get("cohort")
            )
            return self._execute_single_cohort_retrieval(
                query=query,
                effective_query=effective_query,
                retrieval_query=retrieval_query,
                cohort=effective_cohort,
                router_decision=router_decision,
                query_handling=query_handling,
                chat_history=chat_history,
            )

        return {
            "query": query,
            "retrieval_query": None,
            "retrieval_executed": False,
            "intent": "multi_cohort_not_supported",
            "strategy": "query_context_clarification",
            "router_decision": router_decision,
            "structured_result": None,
            "retrieved_items": [],
            "citations": [],
            "needs_llm_answer": False,
            "needs_clarification": True,
            "clarification_question": "Hiện tại mình chỉ hỗ trợ một khóa cho mỗi câu hỏi. Bạn hãy chọn hoặc hỏi từng khóa riêng nhé.",
            "out_of_domain": False,
            "selected_cohort": cohort,
            "query_handling": query_handling,
            "effective_query": effective_query,
            "raw_query": query,
            "deterministic_validated": False,
        }

    def _execute_single_cohort_retrieval(
        self,
        *,
        query: str,
        effective_query: str,
        retrieval_query: str,
        cohort: str | None,
        router_decision: dict[str, Any],
        query_handling: dict[str, Any],
        chat_history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        if isinstance(router_decision.get("lookup_requests"), list):
            return self._execute_semantic_requests(
                query=query,
                effective_query=effective_query,
                retrieval_query=retrieval_query,
                cohort=cohort,
                router_decision=router_decision,
                query_handling=query_handling,
                chat_history=chat_history,
            )

        if router_decision.get("execution_mode") == "structured":
            from src.retrieval.core.structured_dispatcher import resolve_structured_decision
            resolution = resolve_structured_decision(
                router_decision,
                query=retrieval_query,
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
            if resolution and resolution.result:
                is_clarification = resolution.result_kind == "clarification"
                structured_citations = (
                    []
                    if is_clarification
                    else build_citation_from_lookup(resolution.result)
                )
                structured_citations = enrich_citations_with_parent_details(
                    structured_citations,
                    getattr(self, "parent_sources_by_id", {}),
                )
                return {
                    "query": query,
                    "retrieval_query": retrieval_query,
                    "intent": router_decision.get("intent"),
                    "strategy": resolution.strategy,
                    "router_decision": router_decision,
                    "structured_result": resolution.result,
                    "retrieved_items": [],
                    "citations": structured_citations,
                    "needs_llm_answer": False,
                    "needs_clarification": is_clarification,
                    "clarification_question": resolution.result.get("clarification_question") if is_clarification else None,
                    "out_of_domain": False,
                    "selected_cohort": cohort,
                    "query_handling": query_handling,
                    "effective_query": effective_query,
                    "raw_query": query,
                    "deterministic_validated": not is_clarification
                }

        result = run_hybrid_retrieval_pipeline(
            query=effective_query,
            model=self.model,
            collection=self.collection,
            scoring_tables=self.scoring_tables,
            formula_rules=self.formula_rules,
            entity_registry=self.entity_registry,
            expansion_rules=self.expansion_rules,
            office_directory=self.student_office_profiles,
            student_service_directory=self.student_service_directory,
            student_faculty_profiles=self.student_faculty_profiles,
            foreign_language_tables=self.foreign_language_tables,
            structured_tables_registry=self.structured_tables_registry,
            program_directory=self.program_directory,
            top_k=self.config["retrieval"]["default_top_k"],
            batch_size=self.config["retrieval"].get("batch_size", 8),
            normalize_embeddings=self.config["embedding"].get(
                "normalize_embeddings", True
            ),
            cohort=cohort,
            candidate_multiplier=int(
                self.config["retrieval"].get("candidate_multiplier", 5)
            ),
            min_candidates=int(self.config["retrieval"].get("min_candidates", 25)),
            chat_history=chat_history,
            intent=router_decision.get("intent"),
            strategy=router_decision.get("execution_mode") or "hybrid_graph_retrieval",
            retrieval_query=retrieval_query,
        )
        # Only resolve structured tables if explicitly designated by Router (e.g. mixed mode or lookup_type present)
        if not result.get("structured_result") and (
            router_decision.get("execution_mode") == "mixed"
            or router_decision.get("lookup_type")
        ):
            from src.retrieval.core.structured_dispatcher import resolve_structured_decision
            supp_resolution = resolve_structured_decision(
                router_decision,
                query=retrieval_query,
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
            if supp_resolution and supp_resolution.result:
                result["structured_result"] = supp_resolution.result
                structured_citations = build_citation_from_lookup(
                    supp_resolution.result
                )
                structured_citations = enrich_citations_with_parent_details(
                    structured_citations,
                    getattr(self, "parent_sources_by_id", {}),
                )
                result["citations"] = [
                    *(result.get("citations") or []),
                    *structured_citations,
                ]

        result["selected_cohort"] = cohort
        result["router_decision"] = router_decision
        result["raw_query"] = query
        result["effective_query"] = effective_query
        result["query_handling"] = query_handling
        return result

    def _execute_semantic_requests(
        self,
        *,
        query: str,
        effective_query: str,
        retrieval_query: str,
        cohort: str | None,
        router_decision: dict[str, Any],
        query_handling: dict[str, Any],
        chat_history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        from src.retrieval.core.structured_dispatcher import resolve_structured_decision

        requests = [
            (index, request)
            for index, request in enumerate(router_decision.get("lookup_requests") or [])
            if isinstance(request, dict)
            and request.get("request_kind") in {"structured", "rag"}
        ]
        if not requests:
            return {
                "query": query,
                "retrieval_query": retrieval_query,
                "intent": router_decision.get("intent"),
                "strategy": "semantic_request_no_match",
                "router_decision": router_decision,
                "structured_result": None,
                "retrieved_items": [],
                "citations": [],
                "unresolved_lookup_requests": [],
                "request_results": [],
                "needs_llm_answer": False,
                "needs_clarification": False,
                "clarification_question": None,
                "out_of_domain": False,
                "selected_cohort": cohort,
                "query_handling": query_handling,
                "effective_query": effective_query,
                "raw_query": query,
                "deterministic_validated": False,
            }

        execution_contexts = self._build_request_execution_contexts(
            requests,
            effective_query=effective_query,
            cohort=cohort,
        )
        structured_results: list[dict[str, Any]] = []
        structured_citations: list[dict[str, Any]] = []

        rag_results: list[dict[str, Any]] = []
        unresolved_requests: list[dict[str, Any]] = []
        request_results: list[dict[str, Any]] = []
        for request_index, request in requests:
            request_kind = request.get("request_kind")
            execution_context = execution_contexts[request_index]
            if request_kind == "structured":
                try:
                    resolution = resolve_structured_decision(
                        {**router_decision, "lookup_requests": [request]},
                        query=effective_query,
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
                        request_contexts={
                            0: RequestExecutionContext(
                                request_id=execution_context.request_id,
                                request_index=0,
                                request_kind=execution_context.request_kind,
                                query_span=execution_context.query_span,
                                effective_query=execution_context.effective_query,
                                effective_cohort=execution_context.effective_cohort,
                                retrieval_query=execution_context.retrieval_query,
                                retrieval_config=execution_context.retrieval_config,
                            )
                        },
                    )
                except Exception as exc:
                    resolution = None
                    unresolved_requests.append(
                        self._request_result_metadata(
                            request,
                            execution_context,
                            status="error",
                            reason=f"structured_exception:{type(exc).__name__}",
                        )
                    )
                    request_results.append(unresolved_requests[-1])
                    continue

                if (
                    resolution
                    and resolution.status == "ok"
                    and resolution.result_kind != "clarification"
                    and self._has_structured_value(resolution.result)
                ):
                    resolved_result = {
                        **resolution.result,
                        "request_id": execution_context.request_id,
                        "request_index": execution_context.request_index,
                        "query_span": execution_context.query_span,
                        "request_cohort": execution_context.effective_cohort,
                    }
                    structured_results.append(resolved_result)
                    citations = enrich_citations_with_parent_details(
                        build_citation_from_lookup(resolved_result),
                        getattr(self, "parent_sources_by_id", {}),
                    )
                    structured_citations.extend(
                        self._annotate_structured_citations(citations, execution_context)
                    )
                    request_results.append(
                        self._request_result_metadata(
                            request,
                            execution_context,
                            status="ok",
                            confidence=resolution.confidence,
                            provenance=resolution.provenance,
                        )
                    )
                    continue

                reason = (
                    "structured_clarification"
                    if resolution and resolution.result_kind == "clarification"
                    else str((resolution.provenance or {}).get("reason") or f"structured_{resolution.status}")
                    if resolution
                    else "structured_no_match"
                )
                failure_status = resolution.status if resolution else "no_match"
                unresolved = self._request_result_metadata(
                    request,
                    execution_context,
                    status=failure_status,
                    reason=reason,
                    confidence=resolution.confidence if resolution else None,
                    provenance=resolution.provenance if resolution else None,
                )
                unresolved_requests.append(unresolved)
                request_results.append(unresolved)
                continue

            try:
                rag_result = self._run_semantic_request_rag(
                    execution_context=execution_context,
                    request=request,
                    chat_history=chat_history,
                )
            except Exception as exc:
                unresolved = self._request_result_metadata(
                    request,
                    execution_context,
                    status="error",
                    reason=f"rag_exception:{type(exc).__name__}",
                )
                unresolved_requests.append(unresolved)
                request_results.append(unresolved)
                continue
            rag_results.append(rag_result)
            status = "ok" if self._has_rag_evidence(rag_result) else "no_match"
            metadata = self._request_result_metadata(
                request, execution_context, status=status
            )
            request_results.append(metadata)
            if status != "ok":
                unresolved_requests.append(metadata)

        merged_items: list[dict[str, Any]] = []
        merged_citations = list(structured_citations)
        related_items: list[dict[str, Any]] = []
        related_references: list[dict[str, Any]] = []
        for rag_result in rag_results:
            merged_items.extend(rag_result.get("retrieved_items") or [])
            merged_citations.extend(rag_result.get("citations") or [])
            related_items.extend(rag_result.get("related_items") or [])
            related_references.extend(rag_result.get("related_references") or [])

        merged_items = self._deduplicate_request_items(merged_items)
        merged_citations = self._deduplicate_request_citations(merged_citations)
        has_rag = any(self._has_rag_evidence(result) for result in rag_results)
        is_multi_request = len(requests) > 1
        if len(structured_results) == 1:
            structured_result = structured_results[0]
        elif structured_results:
            structured_result = {
                "lookup_type": "multi_request",
                "result": structured_results,
                "sub_results": [
                    {
                        "request_id": result.get("request_id"),
                        "request_index": result.get("request_index"),
                        "query_span": result.get("query_span"),
                        "lookup_type": result.get("lookup_type"),
                        "result": result,
                        "source_records": result.get("source_records") or [],
                    }
                    for result in structured_results
                ],
                "source_records": [
                    source
                    for result in structured_results
                    for source in result.get("source_records") or []
                ],
            }
        else:
            structured_result = None
        error_requests = [
            item for item in request_results if item.get("status") == "error"
        ]
        has_verified_result = bool(structured_results) or has_rag
        infrastructure_error = bool(error_requests) and not has_verified_result
        needs_llm_answer = bool(
            has_verified_result
            and (has_rag or is_multi_request or bool(unresolved_requests))
        )
        deterministic_validated = bool(
            len(requests) == 1
            and structured_result
            and not unresolved_requests
            and not has_rag
        )
        strategy = "semantic_request_executor"
        no_verified_result = not has_verified_result and not infrastructure_error
        return {
            "query": query,
            "retrieval_query": retrieval_query,
            "intent": router_decision.get("intent"),
            "strategy": strategy,
            "router_decision": router_decision,
            "structured_result": structured_result,
            "retrieved_items": merged_items,
            "related_items": related_items,
            "related_references": related_references,
            "citations": merged_citations,
            "unresolved_lookup_requests": unresolved_requests,
            "request_results": request_results,
            "needs_llm_answer": needs_llm_answer,
            "needs_clarification": no_verified_result,
            "clarification_question": (
                "Mình chưa tìm được nguồn đáng tin cậy cho phần bạn hỏi. "
                "Bạn có thể nêu rõ hơn tên nội dung hoặc chương trình không?"
                if no_verified_result
                else None
            ),
            "out_of_domain": False,
            "infrastructure_error": infrastructure_error,
            "error_type": (
                "request_execution_error" if infrastructure_error else None
            ),
            "error_message": (
                "; ".join(
                    f"{item.get('request_id')}: {item.get('reason')}"
                    for item in error_requests
                )
                if infrastructure_error
                else None
            ),
            "selected_cohort": cohort,
            "query_handling": query_handling,
            "effective_query": effective_query,
            "raw_query": query,
            "deterministic_validated": deterministic_validated,
            "retrieval_executed": bool(requests),
            "request_execution_contexts": [
                context.debug_dict() for context in execution_contexts.values()
            ],
        }

    @staticmethod
    def _request_applies_to_cohort(
        request: dict[str, Any],
        cohort: str | None,
    ) -> bool:
        refs = {
            _normalize_retrieval_cohort(value)
            for value in request.get("cohort_refs") or []
            if _normalize_retrieval_cohort(value)
        }
        normalized_cohort = _normalize_retrieval_cohort(cohort)
        return not refs or not normalized_cohort or normalized_cohort in refs

    @staticmethod
    def _structured_request_indexes(resolution: Any | None) -> set[int]:
        if not resolution or not isinstance(resolution.result, dict):
            return set()
        result = resolution.result
        if result.get("lookup_type") == "multi_request":
            return {
                int(item["request_index"])
                for item in result.get("sub_results") or []
                if isinstance(item, dict) and item.get("request_index") is not None
            }
        request_index = result.get("request_index")
        return {int(request_index)} if request_index is not None else {0}

    def _build_request_execution_contexts(
        self,
        requests: list[tuple[int, dict[str, Any]]],
        *,
        effective_query: str,
        cohort: str | None,
    ) -> dict[int, RequestExecutionContext]:
        return {
            request_index: RequestExecutionContext(
                request_id=f"r{request_index + 1}",
                request_index=request_index,
                request_kind=str(request.get("request_kind") or ""),
                query_span=str(request.get("query_span") or effective_query).strip(),
                effective_query=effective_query,
                effective_cohort=cohort,
                retrieval_query=self.slang_normalizer.normalize_for_retrieval(
                    str(request.get("query_span") or effective_query).strip()
                ),
                retrieval_config={
                    "top_k": self.config["retrieval"]["default_top_k"],
                    "index_version": (self.config.get("input") or {}).get(
                        "structured_tables_registry"
                    ),
                },
            )
            for request_index, request in requests
        }

    @staticmethod
    def _has_structured_value(result: dict[str, Any] | None) -> bool:
        if not isinstance(result, dict):
            return False
        if result.get("exists") is True or result.get("formula_text"):
            return True
        for key in ("result", "rows", "items", "table"):
            value = result.get(key)
            if isinstance(value, (list, dict)) and value:
                return True
            if value not in (None, "", [], {}):
                return True
        return False

    @staticmethod
    def _has_rag_evidence(result: dict[str, Any]) -> bool:
        return bool(result.get("retrieved_items") or result.get("citations"))

    @staticmethod
    def _annotate_structured_citations(
        citations: list[dict[str, Any]],
        execution_context: RequestExecutionContext,
    ) -> list[dict[str, Any]]:
        return [
            {
                **citation,
                "request_id": execution_context.request_id,
                "request_index": execution_context.request_index,
                "query_span": execution_context.query_span,
                "request_cohort": execution_context.effective_cohort,
            }
            for citation in citations
        ]

    @staticmethod
    def _request_result_metadata(
        request: dict[str, Any],
        execution_context: RequestExecutionContext,
        *,
        status: str,
        reason: str | None = None,
        confidence: float | str | None = None,
        provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "request_id": execution_context.request_id,
            "request_index": execution_context.request_index,
            "request_kind": request.get("request_kind"),
            "lookup_type": request.get("lookup_type"),
            "intent": request.get("intent"),
            "query_span": execution_context.query_span,
            "cohort": execution_context.effective_cohort,
            "status": status,
            "reason": reason,
            "confidence": confidence,
            "provenance": provenance or {},
        }

    def _run_semantic_request_rag(
        self,
        *,
        execution_context: RequestExecutionContext,
        request: dict[str, Any],
        chat_history: list[dict[str, str]] | None,
    ) -> dict[str, Any]:
        result = run_hybrid_retrieval_pipeline(
            query=execution_context.query_span,
            model=self.model,
            collection=self.collection,
            scoring_tables=self.scoring_tables,
            formula_rules=self.formula_rules,
            entity_registry=self.entity_registry,
            expansion_rules=self.expansion_rules,
            office_directory=self.student_office_profiles,
            student_service_directory=self.student_service_directory,
            student_faculty_profiles=self.student_faculty_profiles,
            foreign_language_tables=self.foreign_language_tables,
            structured_tables_registry=self.structured_tables_registry,
            program_directory=self.program_directory,
            top_k=self.config["retrieval"]["default_top_k"],
            batch_size=self.config["retrieval"].get("batch_size", 8),
            normalize_embeddings=self.config["embedding"].get(
                "normalize_embeddings", True
            ),
            cohort=execution_context.effective_cohort,
            candidate_multiplier=int(
                self.config["retrieval"].get("candidate_multiplier", 5)
            ),
            min_candidates=int(self.config["retrieval"].get("min_candidates", 25)),
            chat_history=chat_history,
            intent=request.get("intent") or "open_question",
            strategy="semantic_request_rag",
            retrieval_query=execution_context.retrieval_query,
        )
        return self._annotate_request_result(result, execution_context=execution_context)

    @staticmethod
    def _annotate_request_result(
        result: dict[str, Any],
        *,
        execution_context: RequestExecutionContext,
    ) -> dict[str, Any]:
        annotated = dict(result)
        items = []
        for item in result.get("retrieved_items") or []:
            enriched = dict(item)
            metadata = dict(enriched.get("metadata") or {})
            metadata.update(
                {
                    "request_id": execution_context.request_id,
                    "request_index": execution_context.request_index,
                    "query_span": execution_context.query_span,
                    "request_cohort": execution_context.effective_cohort,
                }
            )
            enriched["metadata"] = metadata
            enriched["request_id"] = execution_context.request_id
            enriched["request_index"] = execution_context.request_index
            enriched["query_span"] = execution_context.query_span
            enriched["request_cohort"] = execution_context.effective_cohort
            items.append(enriched)
        citations = []
        for citation in result.get("citations") or []:
            enriched = dict(citation)
            enriched.update(
                {
                    "request_id": execution_context.request_id,
                    "request_index": execution_context.request_index,
                    "query_span": execution_context.query_span,
                    "request_cohort": execution_context.effective_cohort,
                }
            )
            citations.append(enriched)
        annotated["retrieved_items"] = items
        annotated["citations"] = citations
        annotated["request_id"] = execution_context.request_id
        annotated["request_index"] = execution_context.request_index
        annotated["query_span"] = execution_context.query_span
        annotated["request_cohort"] = execution_context.effective_cohort
        return annotated

    @staticmethod
    def _deduplicate_request_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduplicated = []
        seen = set()
        for item in items:
            metadata = item.get("metadata") or {}
            key = (
                item.get("request_index"),
                item.get("request_cohort") or metadata.get("cohort"),
                item.get("chunk_id") or item.get("_id"),
            )
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append(item)
        return deduplicated

    @staticmethod
    def _deduplicate_request_citations(
        citations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        deduplicated = []
        seen = set()
        for citation in citations:
            key = (
                citation.get("request_index"),
                citation.get("request_cohort") or citation.get("cohort"),
                citation.get("document_id"),
                citation.get("table_id") or citation.get("source_parent_id"),
                citation.get("title"),
            )
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append(citation)
        return deduplicated

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
            "detected_entities": retrieval_result.get("detected_entities") or [],
            "target_chunk_types": retrieval_result.get("target_chunk_types") or [],
            "raw_query": query,
            "fallback_reason": error_type or (status if status in {"out_of_domain", "needs_clarification", "low_confidence", "retrieval_error", "api_error"} else "none"),
            "retrieved_chunks_count": len(retrieval_result.get("retrieved_items") or []),
            # Deprecated compatibility field. Request-scoped values live in debug.
            "retrieval_query": None,
            "citations": retrieval_result.get("citations", []),
            "citations_used": selected_citations,
            "related_references": retrieval_result.get("related_references", []),
            "structured_result": retrieval_result.get("structured_result"),
            "formula_result": retrieval_result.get("formula_result"),
            "tool_result": retrieval_result.get("tool_result"),
            "llm_called": llm_called,
            "model_used": model_used,
            "model": model_used,
            "used_cache": used_cache,
            "clarification_needed": clarification_needed,
            "debug": {
                "plan_version": (router_decision or {}).get("plan_version"),
                "effective_cohort": retrieval_result.get("selected_cohort"),
                "retrieval_executed": bool(retrieval_result.get("retrieval_executed")),
                "partial_status": self._partial_status(retrieval_result),
                "request_results": retrieval_result.get("request_results") or [],
                "request_execution_contexts": retrieval_result.get(
                    "request_execution_contexts"
                )
                or [],
            },
            "context_used": context_used,
            "tracker": tracker,
            "evaluation_telemetry": self._finalize_evaluation_telemetry(
                used_cache=used_cache,
                llm_called=llm_called,
            ),
        }

    @staticmethod
    def _partial_status(retrieval_result: dict[str, Any]) -> str:
        request_results = retrieval_result.get("request_results") or []
        if not request_results:
            return "not_applicable"
        statuses = [str(item.get("status") or "error") for item in request_results if isinstance(item, dict)]
        if statuses and all(status == "ok" for status in statuses):
            return "complete"
        if any(status == "ok" for status in statuses):
            return "partial"
        return "failed"

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
