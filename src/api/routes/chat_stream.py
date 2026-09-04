"""Server-Sent Events endpoint for incremental chat responses.

The stream emits metadata, token, progress, done, and error events while keeping
the same answer contract as the synchronous endpoint.
"""

from __future__ import annotations

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
from src.api.sse_events import StreamEventBuilder

router = APIRouter(tags=["chat"])
logger = logging.getLogger("student_handbook_rag.api.chat_stream")


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
        """Coordinate capacity, pipeline streaming, tracing, and logging."""
        events = StreamEventBuilder(request_id, include_debug=include_debug)

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
                    yield events.queued(ticket.position)

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
                for chunk in stream:
                    chunk_type = chunk.get("type", "")
                    if chunk_type == "metadata":
                        yield events.metadata(chunk)
                    elif chunk_type == "token":
                        yield events.token(chunk)
                    elif chunk_type == "progress":
                        yield events.progress(chunk)
                    elif chunk_type == "done":
                        events.prepare_done(chunk)
                        done_latency = events.latency_ms
                        trace_metadata = build_trace_metadata(
                            events.trace_metadata,
                            query=query,
                            cohort=request.cohort,
                            chat_history=request.chat_history,
                            latency_ms=done_latency,
                            ttft_ms=events.ttft_ms,
                            status_override=events.final_status,
                        )
                        submit_trace_to_langsmith(
                            request_id,
                            "Chat (Stream)",
                            request.cohort,
                            query,
                            events.full_text,
                            metadata=trace_metadata,
                            latency_ms=done_latency,
                            model=trace_metadata.get("model"),
                            tags=["stream"],
                            tracker=events.tracker,
                        )

                        latency_ms = events.latency_ms
                        logger.info(
                            "chat_stream_completed",
                            extra={
                                "request_id": request_id,
                                "latency_ms": latency_ms,
                                "query_length": len(query),
                                "status": events.final_status,
                                "intent": events.final_metadata.get("intent"),
                                "strategy": events.final_metadata.get("strategy"),
                            },
                        )
                        yield events.done(latency_ms=latency_ms)
            finally:
                if ticket:
                    ticket.leave_queue()
                if acquired and limiter:
                    limiter.release()
        except ChatCapacityError as exc:
            logger.warning(
                "chat_stream_overloaded",
                extra={"request_id": request_id, "reason": exc.reason},
            )
            message = (
                "Trường đang đông quá, phòng chờ của AI đã đầy mất tiêu rồi! Bạn đợi 1 xíu nữa quay lại hỏi nha, xếp hàng cũng nhanh lắm! 🏃💨"
                if exc.reason == "queue_full"
                else "Quá thời gian xếp hàng, bạn thử hỏi lại giúp AI nhé!"
            )
            yield from events.failure(error_type="server_busy", error_message=message)
        except Exception as exc:
            logger.exception(
                "chat_stream_error",
                extra={"request_id": request_id},
            )
            yield from events.failure(
                error_type=type(exc).__name__,
                error_message="Internal chatbot service error",
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
