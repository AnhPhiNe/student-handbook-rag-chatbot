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


def push_trace_to_langsmith(
    trace_id: str,
    name: str,
    session_id: str | None,
    input_text: str | Any,
    output_text: str | Any,
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

    if meta.get("intent"):
        trace_tags.append(f"intent:{meta['intent']}")
    if meta.get("strategy"):
        trace_tags.append(f"strategy:{meta['strategy']}")
    if session_id:
        trace_tags.append(f"cohort:{session_id}")

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

        extra_dict: dict[str, Any] = {
            "metadata": meta,
        }
        if usage:
            extra_dict["usage"] = usage

        # 1. Tạo Root Run (Parent Chain)
        client.create_run(
            id=run_uuid,
            name=name or "HCMUE Student Handbook Assistant",
            run_type="chain",
            inputs={"query": input_text, "chat_history": meta.get("chat_history", [])},
            outputs={"answer": output_text, "status": meta.get("status", "ok")},
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
                step_type = "llm" if "llm" in step_name.lower() or "gemini" in step_name.lower() or "router" in step_name.lower() else "retriever"
                step_latency = step.get("latency_ms", 0)
                step_end = now
                step_start = now - timedelta(milliseconds=step_latency) if step_latency else now

                client.create_run(
                    id=uuid.uuid4(),
                    name=step_name,
                    run_type=step_type,
                    parent_run_id=run_uuid,
                    inputs=step.get("inputs", {}),
                    outputs=step.get("outputs", {}),
                    start_time=step_start,
                    end_time=step_end,
                    project_name=project_name,
                    extra={"metadata": step.get("metadata", {})},
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
