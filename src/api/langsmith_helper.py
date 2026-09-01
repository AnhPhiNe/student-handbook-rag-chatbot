import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from langsmith import Client

logger = logging.getLogger("student_handbook_rag.api.langsmith_helper")

_client: Client | None = None
TRACE_SCHEMA_VERSION = "hcmue-query-plan-v2"

_CITATION_TRACE_FIELDS = (
    "chunk_id",
    "parent_section_id",
    "source_parent_id",
    "title",
    "article_label",
    "parent_article",
    "source_pages",
    "source_label",
    "cohort",
    "source_cohort",
    "applicable_cohorts",
    "applicability_validated",
    "document_id",
    "task_id",
    "supports_task_ids",
    "chunk_type",
    "evidence_kind",
)


def _tracing_enabled() -> bool:
    """Honor the explicit LangSmith switch while preserving legacy deployments."""
    raw_value = os.environ.get("LANGSMITH_TRACING")
    if raw_value is None:
        raw_value = os.environ.get("LANGCHAIN_TRACING_V2")
    if raw_value is None:
        return True
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def get_langsmith_client() -> Client | None:
    global _client
    if not _tracing_enabled():
        return None
    if _client is not None:
        return _client

    api_key = os.environ.get("LANGSMITH_API_KEY") or os.environ.get(
        "LANGCHAIN_API_KEY"
    )
    if not api_key:
        return None

    try:
        _client = Client(api_key=api_key)
        return _client
    except Exception as exc:
        logger.warning(f"Failed to initialize LangSmith Client: {exc}")
        return None


def _runtime_identity() -> dict[str, Any]:
    """Resolve public runtime versions lazily without importing API dependencies."""
    try:
        from src.generation.answer_pipeline import PIPELINE_VERSION
        from src.generation.prompt_builder import ANSWER_PROMPT_VERSION
        from src.retrieval.core.ai_router import ROUTER_PROMPT_VERSION
        from src.retrieval.core.query_plan import (
            QUERY_PLAN_NORMALIZER_VERSION,
            QUERY_PLAN_SCHEMA_VERSION,
        )

        return {
            "pipeline_version": PIPELINE_VERSION,
            "answer_prompt_version": ANSWER_PROMPT_VERSION,
            "router_prompt_version": ROUTER_PROMPT_VERSION,
            "query_plan_schema_version": QUERY_PLAN_SCHEMA_VERSION,
            "query_plan_normalizer_version": QUERY_PLAN_NORMALIZER_VERSION,
        }
    except Exception:  # pragma: no cover - defensive for partial runtimes.
        logger.debug("langsmith_runtime_identity_unavailable", exc_info=True)
        return {}


def _compact_source_records(records: Any) -> list[dict[str, Any]]:
    """Keep source identity and binding while omitting source text and scores."""
    compact: list[dict[str, Any]] = []
    if not isinstance(records, list):
        return compact
    for record in records:
        if not isinstance(record, dict):
            continue
        metadata = (
            record.get("metadata")
            if isinstance(record.get("metadata"), dict)
            else {}
        )
        item = {
            field: record.get(field, metadata.get(field))
            for field in _CITATION_TRACE_FIELDS
            if record.get(field, metadata.get(field)) is not None
        }
        if item:
            compact.append(item)
    return compact


def _compact_structured_results(results: Any) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    if not isinstance(results, list):
        return compact
    for result in results:
        if not isinstance(result, dict):
            continue
        rows = result.get("rows")
        provenance = (
            result.get("provenance")
            if isinstance(result.get("provenance"), dict)
            else {}
        )
        compact.append(
            {
                "id": result.get("id"),
                "lookup_type": result.get("lookup_type"),
                "presentation_type": result.get("presentation_type"),
                "title": result.get("title"),
                "cohort": result.get("cohort"),
                "row_count": len(rows) if isinstance(rows, list) else 0,
                "source_type": provenance.get("source_type"),
                "document_id": provenance.get("document_id"),
                "source_pages": provenance.get("source_pages"),
            }
        )
    return compact


def _task_summaries(source: dict[str, Any]) -> list[dict[str, Any]]:
    plan = (
        source.get("query_plan")
        if isinstance(source.get("query_plan"), dict)
        else {}
    )
    plan_tasks = plan.get("tasks") if isinstance(plan.get("tasks"), list) else []
    task_results = (
        source.get("task_results")
        if isinstance(source.get("task_results"), list)
        else []
    )
    results_by_id = {
        str(result.get("task_id")): result
        for result in task_results
        if isinstance(result, dict) and result.get("task_id")
    }
    coverage_by_task = source.get("coverage_by_task")
    coverage_by_task = coverage_by_task if isinstance(coverage_by_task, dict) else {}

    summaries: list[dict[str, Any]] = []
    for task in plan_tasks:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id") or "")
        result = results_by_id.get(task_id, {})
        evidence = result.get("evidence")
        summaries.append(
            {
                "task_id": task_id,
                "question": task.get("question"),
                "mode": task.get("mode"),
                "lookup_type": task.get("lookup_type"),
                "intent": task.get("intent"),
                "cohorts": list(task.get("cohorts") or []),
                "coverage": result.get("coverage") or coverage_by_task.get(task_id),
                "coverage_by_cohort": result.get("coverage_by_cohort") or {},
                "evidence_count": len(evidence) if isinstance(evidence, list) else 0,
                "citation_count": int(result.get("citation_count") or 0),
                "needs_clarification": bool(
                    task.get("mode") == "clarify" or task.get("clarification_question")
                ),
            }
        )
    return summaries


def _ordered_unique(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def build_trace_metadata(
    source: dict[str, Any] | None,
    *,
    query: str,
    cohort: str | None = None,
    chat_history: list[dict[str, str]] | None = None,
    latency_ms: float | None = None,
    ttft_ms: float | None = None,
    status_override: str | None = None,
) -> dict[str, Any]:
    """Build a compact, privacy-conscious trace for the QueryPlan runtime."""
    src = source or {}
    router_decision = src.get("router_decision") or {}
    query_handling = (
        src.get("query_handling")
        or router_decision.get("query_handling")
        or {}
    )

    status = status_override or src.get("status") or "answered"
    execution_mode = (
        src.get("execution_mode")
        or router_decision.get("execution_mode")
        or "regulation"
    )
    lookup_type = src.get("lookup_type") or router_decision.get("lookup_type")
    query_type = (
        src.get("query_type")
        or router_decision.get("query_type")
        or query_handling.get("context_mode")
        or "standalone"
    )
    model_name = src.get("model") or src.get("model_used") or "gemini-3.1-flash-lite"
    citations = _compact_source_records(
        src.get("citations_used") or src.get("citations") or []
    )
    related = _compact_source_records(src.get("related_references") or [])
    structured_results = _compact_structured_results(src.get("structured_results") or [])
    task_summaries = _task_summaries(src)
    resolved_cohort = (
        cohort
        or src.get("cohort")
        or (router_decision or {}).get("cohort")
        or "default"
    )
    plan = src.get("query_plan") if isinstance(src.get("query_plan"), dict) else {}
    cohorts = _ordered_unique(
        [
            *[
                task_cohort
                for task in task_summaries
                for task_cohort in task.get("cohorts") or []
            ],
            resolved_cohort,
        ]
    )
    coverage_values = [
        str(task.get("coverage") or "unknown") for task in task_summaries
    ]
    planner_fallback = src.get("planner_fallback")

    meta = {
        "trace_schema_version": TRACE_SCHEMA_VERSION,
        **_runtime_identity(),
        "cohort": resolved_cohort,
        "selected_cohort": resolved_cohort,
        "cohorts": cohorts,
        "is_multi_cohort": len(cohorts) > 1,
        "status": status,
        "intent": src.get("intent") or router_decision.get("intent"),
        "strategy": src.get("strategy") or router_decision.get("strategy"),
        "execution_mode": execution_mode,
        "lookup_type": lookup_type,
        "query_type": query_type,
        "model": model_name,
        "citations_used": citations,
        "citations_count": len(citations),
        "related_references": related,
        "related_references_count": len(related),
        "structured_result_summaries": structured_results,
        "structured_results_count": len(structured_results),
        "context_mode": plan.get("context_mode") or query_type,
        "task_count": len(task_summaries),
        "task_modes": _ordered_unique(
            [task.get("mode") for task in task_summaries]
        ),
        "lookup_types": _ordered_unique(
            [task.get("lookup_type") for task in task_summaries]
        ),
        "task_summaries": task_summaries,
        "coverage_by_task": src.get("coverage_by_task") or {},
        "covered_task_count": sum(value == "covered" for value in coverage_values),
        "partial_task_count": sum(value == "partial" for value in coverage_values),
        "uncovered_task_count": sum(value == "uncovered" for value in coverage_values),
        "clarification_task_count": sum(
            bool(task.get("needs_clarification")) for task in task_summaries
        ),
        "planner_fallback": planner_fallback,
        "planner_fallback_used": bool(planner_fallback),
        "target_chunk_types": src.get("target_chunk_types") or [],
        "effective_query": src.get("effective_query") or query,
        "retrieved_chunks_count": int(src.get("retrieved_chunks_count") or 0),
        "fallback_reason": src.get("fallback_reason")
        or ("none" if status == "answered" else str(status)),
        "used_cache": src.get("used_cache", False),
        "llm_called": src.get("llm_called", True),
        "chat_history_turns": len(chat_history or []),
        "has_chat_history": bool(chat_history),
        "qdrant_collection": os.environ.get("QDRANT_COLLECTION_NAME"),
        "mongo_parent_collection": os.environ.get("MONGODB_PARENT_COLLECTION"),
    }

    if latency_ms is not None:
        meta["latency_ms"] = latency_ms
    if ttft_ms is not None:
        meta["ttft_ms"] = ttft_ms

    return meta


def push_trace_to_langsmith(
    trace_id: str,
    name: str = "HCMUE Student Handbook Assistant",
    session_id: str | None = None,
    input_text: str | Any = "",
    output_text: str | Any = "",
    metadata: dict | None = None,
    latency_ms: float | None = None,
    model: str | None = None,
    usage: dict | None = None,
    tags: list[str] | None = None,
    tracker: Any = None,
) -> None:
    """Gửi thông tin Trace + Run tree lên LangSmith.
    Chạy trong Background Thread độc lập để không block phản hồi API/SSE.
    """
    client = get_langsmith_client()
    if not client:
        return

    project_name = os.environ.get("LANGSMITH_PROJECT") or os.environ.get(
        "LANGCHAIN_PROJECT", "hcmue-student-handbook-rag"
    )
    meta = dict(metadata or {})
    trace_tags = list(tags or [])

    resolved_cohort = session_id or meta.get("cohort")
    if resolved_cohort:
        meta.setdefault("cohort", resolved_cohort)
    for trace_cohort in meta.get("cohorts") or [resolved_cohort]:
        if trace_cohort:
            trace_tags.append(f"cohort:{trace_cohort}")

    if meta.get("status"):
        trace_tags.append(f"status:{meta['status']}")
    if meta.get("context_mode"):
        trace_tags.append(f"context:{meta['context_mode']}")
    trace_tags.append(f"tasks:{int(meta.get('task_count') or 0)}")
    if int(meta.get("task_count") or 0) > 1:
        trace_tags.append("multi_task:true")
    if meta.get("is_multi_cohort"):
        trace_tags.append("multi_cohort:true")
    for task_mode in meta.get("task_modes") or []:
        trace_tags.append(f"task_mode:{task_mode}")
    for lookup_type in meta.get("lookup_types") or []:
        trace_tags.append(f"lookup:{lookup_type}")
    for coverage in _ordered_unique(
        [task.get("coverage") for task in meta.get("task_summaries") or []]
    ):
        trace_tags.append(f"coverage:{coverage}")
    if meta.get("planner_fallback_used"):
        trace_tags.append("planner_fallback:true")
    trace_tags.append(f"llm_called:{str(bool(meta.get('llm_called'))).lower()}")
    trace_tags.append(f"cache_hit:{str(bool(meta.get('used_cache'))).lower()}")
    trace_tags = list(dict.fromkeys(trace_tags))

    used_model = model or meta.get("model") or "gemini-3.1-flash-lite"
    meta.setdefault("model", used_model)
    now = datetime.now(timezone.utc)
    end_time = now
    if latency_ms:
        start_time = now - timedelta(milliseconds=latency_ms)
    else:
        start_time = now

    try:
        # Validate/Format UUID for LangSmith run_id
        run_uuid = None
        if trace_id:
            try:
                run_uuid = uuid.UUID(trace_id)
            except (ValueError, AttributeError):
                run_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, str(trace_id))

        # Auto-compute total usage from tracker if not explicitly passed
        final_usage = dict(usage or {})
        if not final_usage and tracker and hasattr(tracker, "get_total_usage"):
            tot = tracker.get_total_usage()
            inp = int(tot.get("input_tokens", 0))
            out = int(tot.get("output_tokens", 0))
            t_tok = int(tot.get("total_tokens", 0)) or (inp + out)
            if t_tok or inp or out:
                final_usage = {
                    "input_tokens": inp,
                    "output_tokens": out,
                    "total_tokens": t_tok,
                    "prompt_tokens": inp,
                    "completion_tokens": out,
                }

        extra_dict: dict[str, Any] = {
            "metadata": meta,
        }
        if final_usage:
            extra_dict["usage"] = final_usage

        # 1. Tạo Root Run (Parent Chain)
        meta.setdefault("cohort", resolved_cohort)
        citations_payload = meta.get("citations_used") or []
        related_payload = meta.get("related_references") or []
        client.create_run(
            id=run_uuid,
            name=name or "HCMUE Student Handbook Assistant",
            run_type="chain",
            inputs={
                "query": input_text,
                "student_cohort": resolved_cohort,
            },
            outputs={
                "answer": output_text,
                "status": meta.get("status", "ok"),
                "task_count": meta.get("task_count", 0),
                "task_summaries": meta.get("task_summaries") or [],
                "coverage_by_task": meta.get("coverage_by_task") or {},
                "citations_count": len(citations_payload),
                "citations": citations_payload,
                "related_references": related_payload,
                "structured_results": meta.get("structured_result_summaries") or [],
            },
            start_time=start_time,
            end_time=end_time,
            project_name=project_name,
            tags=trace_tags,
            extra=extra_dict,
        )

        # 2. Tạo các Sub-Runs (Child steps) nếu có telemetry tracker
        if tracker and hasattr(tracker, "get_steps"):
            steps = tracker.get_steps() or []
            for step in steps:
                step_name = step.get("step_name") or "Pipeline Step"
                step_type = (
                    "llm"
                    if "llm" in step_name.lower() or "gemini" in step_name.lower() or "router" in step_name.lower()
                    else "retriever"
                )
                # Parse start/end datetime for exact LLM latency calculation
                step_start_raw = step.get("start_time")
                step_end_raw = step.get("end_time")
                step_start = None
                step_end = None
                if step_start_raw and step_end_raw:
                    try:
                        step_start = datetime.fromisoformat(str(step_start_raw))
                        step_end = datetime.fromisoformat(str(step_end_raw))
                    except Exception:
                        pass

                if not step_start or not step_end:
                    step_lat = step.get("latency_ms") or 1500
                    step_end = now
                    step_start = now - timedelta(milliseconds=step_lat)

                inp = int(step.get("input_tokens", 0))
                out = int(step.get("output_tokens", 0))
                t_tok = int(step.get("total_tokens", 0)) or (inp + out)
                step_usage = {
                    "input_tokens": inp,
                    "output_tokens": out,
                    "total_tokens": t_tok,
                    "prompt_tokens": inp,
                    "completion_tokens": out,
                }

                step_model = step.get("model") or "gemini-3.1-flash-lite"
                provider = "google_genai" if "gemini" in step_model.lower() else "groq"
                step_extra: dict[str, Any] = {
                    "metadata": {
                        **step.get("metadata", {}),
                        "model": step_model,
                        "ls_provider": provider,
                        "ls_model_name": step_model,
                        "ls_model_type": "chat",
                    },
                    "invocation_params": {
                        "model": step_model,
                        "model_name": step_model,
                    },
                }
                if step_usage.get("total_tokens"):
                    step_extra["usage"] = step_usage

                step_outputs: dict[str, Any] = step.get("outputs") or {}
                if not step_outputs:
                    step_outputs = {
                        "status": "completed",
                        "model": step_model,
                        "token_usage": step_usage,
                    }

                client.create_run(
                    id=uuid.uuid4(),
                    name=step_name,
                    run_type=step_type,
                    parent_run_id=run_uuid,
                    inputs=step.get("inputs", {"query": input_text, "prompts": [input_text]}),
                    outputs=step_outputs,
                    start_time=step_start,
                    end_time=step_end,
                    project_name=project_name,
                    extra=step_extra,
                )
    except Exception as exc:
        logger.warning(f"[LangSmith] Trace submission error: {exc}")


def push_feedback_to_langsmith(
    run_id: str,
    score: float,
    comment: str | None = None,
    feedback_key: str = "user-rating",
) -> None:
    """Gửi đánh giá Like/Dislike (1.0 / 0.0) từ sinh viên lên LangSmith."""
    client = get_langsmith_client()
    if not client or not run_id:
        return

    try:
        run_uuid = None
        try:
            run_uuid = uuid.UUID(run_id)
        except (ValueError, AttributeError):
            run_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, str(run_id))

        client.create_feedback(
            run_id=run_uuid,
            key=feedback_key,
            score=score,
            comment=comment,
        )
        logger.info(f"[LangSmith] Feedback recorded for run {run_id}: score={score}")
    except Exception as exc:
        logger.warning(f"[LangSmith] Feedback submission error: {exc}")
