import os
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Any

from langsmith import Client

logger = logging.getLogger("student_handbook_rag.api.langsmith_helper")

_client: Client | None = None


def get_langsmith_client() -> Client | None:
    global _client
    if _client is not None:
        return _client

    api_key = os.environ.get("LANGCHAIN_API_KEY")
    if not api_key:
        return None

    try:
        _client = Client(api_key=api_key)
        return _client
    except Exception as exc:
        logger.warning(f"Failed to initialize LangSmith Client: {exc}")
        return None


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
    """Helper chuẩn hóa toàn bộ Metadata gửi lên LangSmith từ bất kỳ route nào (Sync/Stream).
    Loại bỏ hoàn toàn duplicate code và hardcode giữa các router API.
    """
    src = source or {}
    router_decision = src.get("router_decision") or {}
    query_handling = src.get("query_handling") or router_decision.get("query_handling") or {}

    status = status_override or src.get("status") or "answered"
    execution_mode = src.get("execution_mode") or router_decision.get("execution_mode") or "regulation"
    lookup_type = src.get("lookup_type") or router_decision.get("lookup_type")
    query_type = (
        src.get("query_type")
        or router_decision.get("query_type")
        or query_handling.get("context_mode")
        or "standalone"
    )
    model_name = src.get("model") or src.get("model_used") or "gemini-3.1-flash-lite"
    citations = src.get("citations_used") or src.get("citations") or []
    related = src.get("related_references") or []
    resolved_cohort = cohort or src.get("cohort") or (router_decision or {}).get("cohort") or "default"

    meta = {
        "cohort": resolved_cohort,
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
        "detected_entities": src.get("detected_entities") or [],
        "target_chunk_types": src.get("target_chunk_types") or [],
        "raw_query": query,
        "effective_query": src.get("effective_query") or query,
        "fallback_reason": src.get("fallback_reason") or ("none" if status == "answered" else str(status)),
        "used_cache": src.get("used_cache", False),
        "llm_called": src.get("llm_called", True),
        "chat_history_turns": len(chat_history or []),
        "chat_history": chat_history or [],
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

    project_name = os.environ.get("LANGCHAIN_PROJECT", "hcmue-student-handbook-rag")
    meta = metadata or {}
    trace_tags = list(tags or [])

    resolved_cohort = session_id or meta.get("cohort")
    if resolved_cohort:
        meta.setdefault("cohort", resolved_cohort)
        trace_tags.append(f"cohort:{resolved_cohort}")

    if meta.get("intent"):
        trace_tags.append(f"intent:{meta['intent']}")
    if meta.get("strategy"):
        trace_tags.append(f"strategy:{meta['strategy']}")
    if meta.get("execution_mode"):
        trace_tags.append(f"mode:{meta['execution_mode']}")
    if meta.get("lookup_type"):
        trace_tags.append(f"lookup:{meta['lookup_type']}")
    if meta.get("status"):
        trace_tags.append(f"status:{meta['status']}")

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
        meta.setdefault("cohort", session_id)
        client.create_run(
            id=run_uuid,
            name=name or "HCMUE Student Handbook Assistant",
            run_type="chain",
            inputs={
                "query": input_text,
                "chat_history": meta.get("chat_history", []),
            },
            outputs={
                "answer": output_text,
                "status": meta.get("status", "ok"),
                "citations_count": len(meta.get("citations_used") or []),
                "related_references_count": len(meta.get("related_references") or []),
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
                        "output": output_text,
                        "generations": [{"text": output_text}],
                        "llm_output": {
                            "token_usage": step_usage,
                            "model_name": step_model,
                        },
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
