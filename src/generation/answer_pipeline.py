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
from src.retrieval.core.query_context import select_effective_query
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

PIPELINE_VERSION = "v31-query-plan-multitask"
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
            selected_citations = list(retrieval_result.get("citations") or [])[:10]
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
            "query_plan": res.get("query_plan"),
            "task_results": res.get("task_results") or [],
            "coverage_by_task": res.get("coverage_by_task") or {},
            "planner_fallback": res.get("planner_fallback"),
            "supports_task_ids": res.get("supports_task_ids") or {},
            "llm_called": llm_called,
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
            selected_citations = list(retrieval_result.get("citations") or [])[:10]
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

        planning_config = self.config.get("planning", {})
        planning_enabled = _env_bool(
            "STUDENT_RAG_QUERY_PLAN_ENABLED",
            bool(planning_config.get("enabled", True)),
        )
        if planning_enabled and hasattr(self.router, "plan"):
            return self._run_query_plan(
                query=query,
                cohort=cohort,
                chat_history=chat_history,
            )

        router_input_query = self.slang_normalizer.replace_for_router(query)
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
        router_decision = {
            **router_decision,
            "query_handling": query_handling,
            "effective_query": effective_query,
            "router_input_query": router_input_query,
        }
        if handling.needs_clarification:
            return {
                "query": query,
                "retrieval_query": query,
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

        if router_decision.get("route") == "out_of_domain":
            router_decision = {
                **router_decision,
                "intent": "out_of_domain",
            }
            return {
                "query": query,
                "retrieval_query": query,
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

        normalized_retrieval_query = self.slang_normalizer.normalize_for_retrieval(
            effective_query
        )

        cohorts = router_decision.get("cohorts") or []
        is_multi_cohort = bool(
            router_decision.get("is_multi_cohort") and len(cohorts) >= 2
        )

        if not is_multi_cohort:
            return self._execute_single_cohort_retrieval(
                query=query,
                effective_query=effective_query,
                normalized_retrieval_query=normalized_retrieval_query,
                cohort=cohort,
                router_decision=router_decision,
                query_handling=query_handling,
                chat_history=chat_history,
            )

        sub_results: list[dict[str, Any]] = []
        for c in cohorts:
            sub_res = self._execute_single_cohort_retrieval(
                query=query,
                effective_query=effective_query,
                normalized_retrieval_query=normalized_retrieval_query,
                cohort=c,
                router_decision=router_decision,
                query_handling=query_handling,
                chat_history=chat_history,
            )
            sub_results.append(sub_res)

        merged_retrieved_items: list[dict[str, Any]] = []
        seen_item_keys: set[Any] = set()
        for sub in sub_results:
            for item in sub.get("retrieved_items") or []:
                item_cohort = (
                    item.get("metadata", {}).get("cohort")
                    or sub.get("selected_cohort")
                )
                item_id = str(item.get("chunk_id") or item.get("_id") or "")
                key = (item_cohort, item_id)
                if key not in seen_item_keys:
                    seen_item_keys.add(key)
                    merged_retrieved_items.append(item)

        merged_citations: list[dict[str, Any]] = []
        seen_cit_keys: set[Any] = set()
        for sub in sub_results:
            for cit in sub.get("citations") or []:
                cit_cohort = cit.get("cohort") or sub.get("selected_cohort")
                key = (
                    cit_cohort,
                    cit.get("document_id"),
                    cit.get("title") or cit.get("source_parent_id"),
                    tuple(cit.get("source_pages") or []),
                )
                if key not in seen_cit_keys:
                    seen_cit_keys.add(key)
                    merged_citations.append(cit)

        structured_results_list = [
            sub.get("structured_result")
            for sub in sub_results
            if sub.get("structured_result")
        ]
        if len(structured_results_list) > 1:
            merged_structured: Any = {
                "lookup_type": "multi_cohort_structured",
                "cohorts": cohorts,
                "sub_lookups": structured_results_list,
                "result": structured_results_list,
                "table_name": f"So sánh bảng số liệu các khóa: {', '.join(cohorts)}",
                "source_label": "Dữ liệu bảng quy chế tra cứu theo từng khóa",
            }
        elif len(structured_results_list) == 1:
            merged_structured = structured_results_list[0]
        else:
            merged_structured = None

        return {
            "query": query,
            "retrieval_query": normalized_retrieval_query,
            "intent": router_decision.get("intent") or "multi_cohort_comparison",
            "strategy": "multi_cohort_fusion",
            "router_decision": router_decision,
            "structured_result": merged_structured,
            "retrieved_items": merged_retrieved_items,
            "citations": merged_citations[:10],
            "needs_llm_answer": True,
            "needs_clarification": False,
            "clarification_question": None,
            "out_of_domain": False,
            "selected_cohort": ", ".join(cohorts),
            "query_handling": query_handling,
            "effective_query": effective_query,
            "raw_query": query,
            "deterministic_validated": False,
        }

    def _run_query_plan(
        self,
        *,
        query: str,
        cohort: str | None,
        chat_history: list[dict[str, str]] | None,
    ) -> dict[str, Any]:
        """Plan and execute at most three independent, non-recursive tasks."""
        router_input_query = self.slang_normalizer.replace_for_router(query)
        try:
            raw_plan = self.router.plan(
                router_input_query,
                chat_history=chat_history,
                cohort=cohort,
            )
        except TypeError:
            raw_plan = self.router.plan(
                router_input_query,
                chat_history=chat_history,
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
        effective_query = str(
            plan.get("standalone_query")
            if plan.get("context_mode") == "follow_up"
            else plan.get("normalized_query")
            or query
        ).strip() or query
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
        coverage_by_task: dict[str, str] = {}
        clarification_questions: list[str] = []

        for task in plan.get("tasks") or []:
            task_id = str(task.get("id") or f"t{len(task_results) + 1}")
            mode = task.get("mode")
            task_cohorts = task.get("cohorts") or ([cohort] if cohort else [None])
            task_cohorts = list(dict.fromkeys(task_cohorts))
            task_evidence: list[dict[str, Any]] = []
            cohort_coverage: dict[str, str] = {}
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
                        chat_history=chat_history,
                    )
                cohort_key = str(task_cohort or "default")
                cohort_coverage[cohort_key] = sub_result["coverage"]
                task_evidence.extend(sub_result.get("evidence") or [])
                task_citations.extend(sub_result.get("citations") or [])
                task_items.extend(sub_result.get("retrieved_items") or [])
                structured = sub_result.get("structured_result")
                if structured:
                    structured_results.append(structured)
                clarification = sub_result.get("clarification_question")
                if clarification:
                    clarification_questions.append(str(clarification))

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
        return {
            **base_result,
            "intent": "multi_task" if len(task_results) > 1 else (task_results[0].get("intent") if task_results else "open_question"),
            "strategy": "query_plan_execution",
            "execution_mode": "mixed" if len(task_modes - {"clarify"}) > 1 else next(iter(task_modes), "regulation"),
            "lookup_type": None,
            "structured_result": structured_result,
            "retrieved_items": merged_items,
            "citations": selected_citations,
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
            probe_other_domains=False,
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
        coverage = "covered" if citations else "uncovered"
        return {
            "coverage": coverage,
            "evidence": [evidence],
            "structured_result": evidence,
            "citations": citations,
            "retrieved_items": [],
        }

    def _execute_planned_rag_task(
        self,
        *,
        task: dict[str, Any],
        task_id: str,
        cohort: str | None,
        chat_history: list[dict[str, str]] | None,
    ) -> dict[str, Any]:
        task_query = str(task.get("question") or "").strip()
        retrieval_query = self.slang_normalizer.normalize_for_retrieval(task_query)
        result = run_hybrid_retrieval_pipeline(
            query=task_query,
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
            top_k=int(self.config.get("planning", {}).get("rag_top_k", 5)),
            batch_size=self.config["retrieval"].get("batch_size", 8),
            normalize_embeddings=self.config["embedding"].get("normalize_embeddings", True),
            cohort=cohort,
            candidate_multiplier=int(self.config["retrieval"].get("candidate_multiplier", 5)),
            min_candidates=int(self.config["retrieval"].get("min_candidates", 25)),
            chat_history=chat_history,
            intent=task.get("intent") or "open_question",
            strategy="regulation",
            retrieval_query=retrieval_query,
        )
        items = []
        for item in (result.get("retrieved_items") or [])[:5]:
            copied = dict(item)
            metadata = dict(copied.get("metadata") or {})
            metadata.update({"task_id": task_id, "supports_task_ids": [task_id], "cohort": metadata.get("cohort") or cohort})
            copied["metadata"] = metadata
            copied["task_id"] = task_id
            copied["supports_task_ids"] = [task_id]
            items.append(copied)
        citations = [
            {**citation, "task_id": task_id, "supports_task_ids": [task_id], "cohort": citation.get("cohort") or cohort}
            for citation in (result.get("citations") or [])[:5]
        ]
        coverage = "covered" if items and citations else "uncovered"
        evidence = [{
            "task_id": task_id,
            "cohort": cohort,
            "retrieval_query": retrieval_query,
            "source_ids": [str(item.get("chunk_id") or item.get("_id") or "") for item in items],
        }]
        return {"coverage": coverage, "evidence": evidence, "citations": citations, "retrieved_items": items}

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

    def _execute_single_cohort_retrieval(
        self,
        *,
        query: str,
        effective_query: str,
        normalized_retrieval_query: str,
        cohort: str | None,
        router_decision: dict[str, Any],
        query_handling: dict[str, Any],
        chat_history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        if router_decision.get("execution_mode") == "structured":
            from src.retrieval.core.structured_dispatcher import resolve_structured_decision
            resolution = resolve_structured_decision(
                router_decision,
                query=normalized_retrieval_query,
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
                structured_citations = enrich_citations_with_parent_details(
                    build_citation_from_lookup(resolution.result),
                    getattr(self, "parent_sources_by_id", {}),
                )
                return {
                    "query": query,
                    "retrieval_query": normalized_retrieval_query,
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
            retrieval_query=normalized_retrieval_query,
        )
        # Only resolve structured tables if explicitly designated by Router (e.g. mixed mode or lookup_type present)
        if not result.get("structured_result") and (
            router_decision.get("execution_mode") == "mixed"
            or router_decision.get("lookup_type")
        ):
            from src.retrieval.core.structured_dispatcher import resolve_structured_decision
            supp_resolution = resolve_structured_decision(
                router_decision,
                query=normalized_retrieval_query,
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

        result["selected_cohort"] = cohort
        result["router_decision"] = router_decision
        result["raw_query"] = query
        result["effective_query"] = effective_query
        result["query_handling"] = query_handling
        return result

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
            "retrieval_query": retrieval_result.get("retrieval_query"),
            "citations": retrieval_result.get("citations", []),
            "citations_used": selected_citations,
            "related_references": retrieval_result.get("related_references", []),
            "structured_result": retrieval_result.get("structured_result"),
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
