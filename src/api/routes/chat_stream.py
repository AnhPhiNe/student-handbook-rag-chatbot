"""Endpoint streaming Server-Sent Events (SSE) cho phản hồi chat thời gian thực.

Khác với endpoint đồng bộ POST /chat phải đợi đủ câu trả lời, endpoint này stream
token ngay khi LLM sinh ra, tạo trải nghiệm phản hồi tức thì giống ChatGPT.

Các loại sự kiện SSE:
    - metadata: Ý định, chiến lược, trích dẫn; gửi đầu tiên trước token.
    - token:    Một đoạn văn bản được sinh ra.
    - done:     Báo hiệu stream đã hoàn tất.
    - error:    Có lỗi xảy ra trong lúc xử lý.
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
    """Định dạng một sự kiện Server-Sent Event (SSE) thành chuỗi theo chuẩn.

    Hàm này nhận vào loại sự kiện và dữ liệu, sau đó chuyển đổi dữ liệu thành
    chuỗi JSON và định dạng nó theo chuẩn SSE để gửi về client.

    Args:
        event_type (str): Loại sự kiện (ví dụ: "metadata", "token", "done", "error").
        data (dict[str, Any]): Dữ liệu của sự kiện, sẽ được chuyển đổi thành JSON.

    Returns:
        str: Chuỗi đã định dạng của sự kiện SSE, sẵn sàng để gửi đi.
    """
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event_type}\ndata: {payload}\n\n"


@router.post("/chat/stream")
def chat_stream(
    request: ChatRequest,
    http_request: Request,
    answer_service: Any = Depends(get_answer_service),
) -> StreamingResponse:
    """Xử lý yêu cầu chat và trả về các phản hồi theo thời gian thực dưới dạng Server-Sent Events (SSE).

    Endpoint này cho phép client nhận từng phần của câu trả lời ngay khi chúng được tạo ra
    bởi mô hình ngôn ngữ lớn (LLM), mang lại trải nghiệm giống như ChatGPT với phản hồi
    trực quan tức thì.

    Client sẽ nhận được các loại sự kiện sau:
    1.  `event: metadata`: Chứa thông tin về ý định, nguồn và trạng thái;
        được gửi khi bắt đầu và cập nhật lại bằng trạng thái cuối.
    2.  `event: token`: Chứa các đoạn văn bản nhỏ (token) khi Gemini tạo ra chúng.
    3.  `event: done`: Tín hiệu cho biết luồng dữ liệu đã hoàn tất.
    4.  `event: error`: Tín hiệu cho biết có lỗi xảy ra trong quá trình xử lý.

    Args:
        request (ChatRequest): Dữ liệu yêu cầu chat từ client, bao gồm câu hỏi,
            lịch sử chat và nhóm người dùng (cohort).
        http_request (Request): Đối tượng yêu cầu HTTP từ FastAPI, được sử dụng
            để kiểm tra giới hạn tốc độ truy cập.
        answer_service (Any): Dịch vụ xử lý câu trả lời, được cung cấp thông qua
            hệ thống Dependency Injection của FastAPI.

    Returns:
        StreamingResponse: Một phản hồi streaming, gửi các sự kiện SSE về cho client
            theo thời gian thực.
    """
    query = validate_chat_query(request.query)
    enforce_chat_rate_limit(http_request)

    request_id = uuid4().hex
    include_debug = should_include_debug(request.include_debug)

    def event_generator():
        """Một hàm generator tạo ra các sự kiện Server-Sent Events (SSE) dựa trên luồng dữ liệu.

        Hàm này kết nối với dịch vụ trả lời (answer_service) để nhận các phần của câu trả lời
        theo thời gian thực. Mỗi phần sẽ được định dạng thành một sự kiện SSE và được gửi
        về client. Nó xử lý các loại chunk khác nhau như metadata, token, progress, done
        và cả các trường hợp lỗi.

        Yields:
            str: Một chuỗi đã định dạng theo chuẩn SSE, đại diện cho một phần của câu trả lời
                hoặc thông báo trạng thái (ví dụ: metadata, token, done, error).
        """
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
                            chunk.get("used_cache", final_metadata.get("used_cache", False))
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
                        done_latency = round((time.perf_counter() - started_at) * 1000, 2)
                        ttft_ms = round((first_token_at - started_at) * 1000, 2) if first_token_at else done_latency
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
