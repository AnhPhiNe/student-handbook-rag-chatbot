"""Server-Sent Events endpoint for incremental chat responses.

The stream emits metadata, token, progress, done, and error events while keeping
the same answer contract as the synchronous endpoint.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from src.api.langsmith_helper import build_trace_metadata, submit_trace_to_langsmith

from src.api.chat_controls import (
    ChatCapacityError,
    _chat_capacity_limiter,
    chat_capacity_settings,
    enforce_chat_rate_limit,
    should_include_debug,
    validate_chat_query,
)
from src.api.deps import get_answer_service
from src.api.schemas import ChatRequest
from src.generation.structured_result_presenter import public_regulation_citations

router = APIRouter(tags=["chat"])
logger = logging.getLogger("student_handbook_rag.api.chat_stream")


def _sse_event(event_type: str, data: dict[str, Any]) -> str:
    """Serialize one event and JSON payload using the SSE wire format."""
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event_type}\ndata: {payload}\n\n"


@router.post("/chat/stream")
def chat_stream(
    request: ChatRequest,
    http_request: Request,
    answer_service: Any = Depends(get_answer_service),
) -> StreamingResponse:
    """Validate a chat request and return its answer as an SSE stream."""
    query = validate_chat_query(request.query)
    enforce_chat_rate_limit(http_request)

    request_id = uuid4().hex
    include_debug = should_include_debug(request.include_debug)

    def event_generator():
        """Translate pipeline events into SSE packets and emit final telemetry."""
        started_at = time.perf_counter()
        final_status = "unknown"
        final_metadata: dict[str, Any] = {}
        trace_source_metadata: dict[str, Any] = {}
        full_text = ""

        try:
            settings = chat_capacity_settings()
            max_concurrent, _, timeout_seconds = settings

            acquired = False
            ticket = None
            limiter = None

            if max_concurrent > 0:
                limiter = _chat_capacity_limiter(settings)
                ticket = limiter.enter_queue()

                start_wait = time.monotonic()
                while time.monotonic() - start_wait < timeout_seconds:
                    if ticket.try_acquire(timeout=1.0):
                        acquired = True
                        break
                    yield _sse_event("queued", {"position": ticket.position})

                if not acquired:
                    raise ChatCapacityError("queue_timeout")

            try:
                logger.debug(
                    "chat_stream_history_received",
                    extra={"history_count": len(request.chat_history or [])},
                )
                stream = answer_service.answer_stream(
                    query,
                    chat_history=request.chat_history,
                    cohort=request.cohort,
                    trace_id=request_id,
                )
                first_token_at = None
                for chunk in stream:
                    chunk_type = chunk.get("type", "")
                    if chunk_type == "metadata":
                        # Preserve the internal QueryPlan packet for observability.
                        # Public SSE redaction below must not erase LangSmith task data.
                        trace_source_metadata = dict(chunk)
                        chunk["request_id"] = request_id
                        chunk["run_id"] = request_id
                        chunk["citations_used"] = public_regulation_citations(
                            chunk.get("citations_used") or []
                        )
                        if not include_debug:
                            for debug_key in (
                                "query_plan",
                                "task_results",
                                "coverage_by_task",
                                "planner_fallback",
                                "supports_task_ids",
                            ):
                                chunk.pop(debug_key, None)
                            citations = chunk.get("citations_used") or []
                            chunk["citations_used"] = [
                                {
                                    key: value
                                    for key, value in citation.items()
                                    if key not in {"task_id", "supports_task_ids"}
                                }
                                if isinstance(citation, dict)
                                else citation
                                for citation in citations
                            ]
                        final_metadata = dict(chunk)
                        final_status = str(chunk.get("status") or final_status)
                        yield _sse_event("metadata", chunk)
                    elif chunk_type == "token":
                        if first_token_at is None:
                            first_token_at = time.perf_counter()
                        full_text += chunk.get("text", "")
                        yield _sse_event("token", {"text": chunk.get("text", "")})
                    elif chunk_type == "progress":
                        yield _sse_event(
                            "progress",
                            {"message": chunk.get("message", "")},
                        )
                    elif chunk_type == "done":
                        final_status = str(chunk.get("status") or final_status)
                        final_metadata["status"] = final_status
                        final_metadata["used_cache"] = bool(
                            chunk.get(
                                "used_cache", final_metadata.get("used_cache", False)
                            )
                        )
                        if chunk.get("error_type"):
                            final_metadata["error_type"] = chunk["error_type"]
                        if trace_source_metadata:
                            trace_source_metadata.update(
                                {
                                    "status": final_status,
                                    "used_cache": final_metadata["used_cache"],
                                    "error_type": final_metadata.get("error_type"),
                                }
                            )
                        raw_done_citations = (
                            chunk.get("citations_used")
                            if "citations_used" in chunk
                            else final_metadata.get("citations_used", [])
                        )
                        final_citations = public_regulation_citations(
                            raw_done_citations or []
                        )
                        if not include_debug:
                            final_citations = [
                                {
                                    key: value
                                    for key, value in citation.items()
                                    if key not in {"task_id", "supports_task_ids"}
                                }
                                if isinstance(citation, dict)
                                else citation
                                for citation in final_citations
                            ]
                        final_metadata["citations_used"] = final_citations
                        if trace_source_metadata:
                            trace_source_metadata["citations_used"] = (
                                raw_done_citations or []
                            )
                        done_latency = round(
                            (time.perf_counter() - started_at) * 1000, 2
                        )
                        ttft_ms = (
                            round((first_token_at - started_at) * 1000, 2)
                            if first_token_at
                            else done_latency
                        )
                        tracker = chunk.get("tracker")
                        trace_metadata = build_trace_metadata(
                            trace_source_metadata or final_metadata,
                            query=query,
                            cohort=request.cohort,
                            chat_history=request.chat_history,
                            latency_ms=done_latency,
                            ttft_ms=ttft_ms,
                            status_override=final_status,
                        )
                        submit_trace_to_langsmith(
                            request_id,
                            "Chat (Stream)",
                            request.cohort,
                            query,
                            full_text,
                            metadata=trace_metadata,
                            latency_ms=done_latency,
                            model=trace_metadata.get("model"),
                            tags=["stream"],
                            tracker=tracker,
                        )

                        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
                        logger.info(
                            "chat_stream_completed",
                            extra={
                                "request_id": request_id,
                                "latency_ms": latency_ms,
                                "query_length": len(query),
                                "status": final_status,
                                "intent": final_metadata.get("intent"),
                                "strategy": final_metadata.get("strategy"),
                            },
                        )
                        yield _sse_event(
                            "done",
                            {
                                "request_id": request_id,
                                "latency_ms": latency_ms,
                                "status": final_status,
                                "error_type": final_metadata.get("error_type"),
                                "used_cache": final_metadata.get("used_cache", False),
                                "citations_used": final_citations,
                            },
                        )
            finally:
                if ticket:
                    ticket.leave_queue()
                if acquired and limiter:
                    limiter.release()
        except ChatCapacityError as exc:
            terminal_status = "api_error"
            terminal_error_type = "server_busy"
            logger.warning(
                "chat_stream_overloaded",
                extra={"request_id": request_id, "reason": exc.reason},
            )
            yield _sse_event(
                "error",
                {
                    "request_id": request_id,
                    "status": terminal_status,
                    "error_type": terminal_error_type,
                    "error_message": (
                        "Trường đang đông quá, phòng chờ của AI đã đầy mất tiêu rồi! Bạn đợi 1 xíu nữa quay lại hỏi nha, xếp hàng cũng nhanh lắm! 🏃💨"
                        if exc.reason == "queue_full"
                        else "Quá thời gian xếp hàng, bạn thử hỏi lại giúp AI nhé!"
                    ),
                },
            )
            yield _sse_event(
                "done",
                {
                    "request_id": request_id,
                    "status": terminal_status,
                    "error_type": terminal_error_type,
                },
            )
        except Exception as exc:
            terminal_status = "api_error"
            terminal_error_type = type(exc).__name__
            logger.exception(
                "chat_stream_error",
                extra={"request_id": request_id},
            )
            yield _sse_event(
                "error",
                {
                    "request_id": request_id,
                    "status": terminal_status,
                    "error_type": terminal_error_type,
                    "error_message": "Internal chatbot service error",
                },
            )
            yield _sse_event(
                "done",
                {
                    "request_id": request_id,
                    "status": terminal_status,
                    "error_type": terminal_error_type,
                },
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
