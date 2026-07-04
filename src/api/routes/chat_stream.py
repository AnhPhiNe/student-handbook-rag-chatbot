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

import threading
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from langfuse import Langfuse
from src.api.langfuse_helper import push_trace_to_langfuse

from src.api.chat_controls import (
    ChatCapacityError,
    chat_capacity_slot,
    enforce_chat_rate_limit,
    validate_chat_query,
)
from src.api.deps import get_answer_service
from src.api.schemas import ChatRequest

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
    1.  `event: metadata`: Chứa thông tin về ý định, chiến lược và các trích dẫn (được gửi đầu tiên).
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
        full_text = ""
        
        try:
            with chat_capacity_slot():
                logger.debug(
                    "chat_stream_history_received",
                    extra={"history_count": len(request.chat_history or [])},
                )
                stream = answer_service.answer_stream(
                    query,
                    chat_history=request.chat_history,
                    cohort=request.cohort,
                    langfuse_trace_id=request_id,
                )
                for chunk in stream:
                    chunk_type = chunk.get("type", "")
                    if chunk_type == "metadata":
                        chunk["request_id"] = request_id
                        chunk["run_id"] = request_id
                        final_metadata = dict(chunk)
                        final_status = str(chunk.get("status") or final_status)
                        yield _sse_event("metadata", chunk)
                    elif chunk_type == "token":
                        full_text += chunk.get("text", "")
                        yield _sse_event("token", {"text": chunk.get("text", "")})
                    elif chunk_type == "progress":
                        yield _sse_event(
                            "progress",
                            {"message": chunk.get("message", "")},
                        )
                    elif chunk_type == "done":
                        done_latency = round((time.perf_counter() - started_at) * 1000, 2)
                        tracker = chunk.get("tracker")
                        threading.Thread(
                            target=push_trace_to_langfuse,
                            args=(
                                request_id, 
                                "Chat (Stream)", 
                                request.cohort, 
                                query, 
                                full_text, 
                            ),
                            kwargs={
                                "metadata": {
                                    "status": final_status,
                                    "intent": final_metadata.get("intent"),
                                    "strategy": final_metadata.get("strategy"),
                                    "model": final_metadata.get("model"),
                                },
                                "latency_ms": done_latency,
                                "model": final_metadata.get("model"),
                                "tags": ["stream"],
                                "tracker": tracker,
                            },
                            daemon=True
                        ).start()
                        
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
                            {"request_id": request_id, "latency_ms": latency_ms},
                        )
        except ChatCapacityError as exc:
            logger.warning(
                "chat_stream_overloaded",
                extra={"request_id": request_id, "reason": exc.reason},
            )
            yield _sse_event(
                "error",
                {
                    "request_id": request_id,
                    "error_type": "server_busy",
                    "error_message": (
                        "Hệ thống đang bận, bạn thử lại sau vài giây nhé."
                    ),
                },
            )
            yield _sse_event("done", {"request_id": request_id})
        except Exception:
            logger.exception(
                "chat_stream_error",
                extra={"request_id": request_id},
            )
            yield _sse_event(
                "error",
                {
                    "request_id": request_id,
                    "error_message": "Internal chatbot service error",
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
