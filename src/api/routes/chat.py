from __future__ import annotations

import logging
import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.chat_controls import (
    enforce_chat_rate_limit,
    should_include_debug,
    validate_chat_query,
)
from src.api.deps import get_answer_service
from src.api.schemas import ChatRequest, ChatResponse, ChatFeedbackRequest
from langsmith import Client as LangSmithClient


router = APIRouter(tags=["chat"])
logger = logging.getLogger("student_handbook_rag.api.chat")


def _build_debug_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Xây dựng một payload (tải trọng) chứa thông tin gỡ lỗi (debug) từ kết quả xử lý chat.

    Hàm này lấy một từ điển chứa kết quả chi tiết của quá trình xử lý câu hỏi chat
    và định dạng lại thành một từ điển chỉ chứa các thông tin cần thiết cho việc gỡ lỗi,
    giúp dễ dàng kiểm tra và phân tích hoạt động của chatbot.

    Args:
        result (dict[str, Any]): Một từ điển chứa kết quả chi tiết của quá trình xử lý câu hỏi chat.
            Nó có thể bao gồm các thông tin như câu trả lời, ngữ cảnh sử dụng, trích dẫn,
            chiến lược, v.v.

    Returns:
        dict[str, Any]: Một từ điển chứa các thông tin gỡ lỗi đã được định dạng,
            bao gồm các trường như `intent`, `strategy`, `effective_query`,
            `llm_called`, `latency_ms`, v.v.
    """
    context_used = str(result.get("context_used") or "")
    citations = result.get("citations") or []
    citations_used = result.get("citations_used") or []

    return {
        "intent": result.get("intent"),
        "strategy": result.get("strategy"),
        "effective_query": result.get("effective_query"),
        "query_rewrite": result.get("query_rewrite"),
        "retrieval_query": result.get("retrieval_query"),
        "llm_called": bool(result.get("llm_called", False)),
        "used_cache": bool(result.get("used_cache", False)),
        "error_type": result.get("error_type"),
        "error_message": result.get("error_message"),
        "context_used_length": len(context_used),
        "citations_count": len(citations) if isinstance(citations, list) else 0,
        "citations_used_count": len(citations_used)
        if isinstance(citations_used, list)
        else 0,
        "request_id": result.get("request_id"),
        "latency_ms": result.get("latency_ms"),
    }


def _to_chat_response(
    result: dict[str, Any],
    *,
    include_debug: bool,
) -> ChatResponse:
    """Chuyển đổi kết quả xử lý chat từ dạng từ điển nội bộ sang đối tượng ChatResponse.

    Hàm này nhận một từ điển chứa kết quả chi tiết của quá trình xử lý câu hỏi chat
    và chuyển đổi nó thành một đối tượng `ChatResponse` theo định dạng API.
    Nó cũng có thể tùy chọn bao gồm thông tin gỡ lỗi nếu được yêu cầu.

    Args:
        result (dict[str, Any]): Một từ điển chứa kết quả chi tiết của quá trình xử lý câu hỏi chat.
            Ví dụ: câu trả lời, trạng thái, các trích dẫn được sử dụng, v.v.
        include_debug (bool): Một cờ (flag) cho biết có nên bao gồm thông tin gỡ lỗi
            trong phản hồi `ChatResponse` hay không. Nếu `True`, thông tin gỡ lỗi
            sẽ được tạo và thêm vào.

    Returns:
        ChatResponse: Một đối tượng phản hồi chat đã được định dạng, sẵn sàng
            để gửi về cho người dùng. Đối tượng này chứa câu trả lời, trạng thái,
            ID yêu cầu, và các thông tin khác.
    """
    citations_used = result.get("citations_used") or []

    return ChatResponse(
        answer=str(result.get("answer") or ""),
        status=str(result.get("status") or "unknown"),
        effective_query=result.get("effective_query"),
        query_rewrite=result.get("query_rewrite"),
        request_id=result.get("request_id"),
        run_id=result.get("run_id"),
        latency_ms=result.get("latency_ms"),
        citations_used=citations_used if isinstance(citations_used, list) else [],
        clarification_needed=bool(result.get("clarification_needed", False)),
        intent=result.get("intent"),
        strategy=result.get("strategy"),
        llm_called=bool(result.get("llm_called", False)),
        used_cache=bool(result.get("used_cache", False)),
        error_type=result.get("error_type"),
        error_message=result.get("error_message"),
        debug=_build_debug_payload(result) if include_debug else None,
    )


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    http_request: Request,
    answer_service: Any = Depends(get_answer_service),
) -> ChatResponse:
    """Xử lý yêu cầu chat từ người dùng và trả về câu trả lời.

    Đây là một API endpoint (điểm cuối API) nhận yêu cầu chat từ người dùng,
    xác thực câu hỏi, kiểm tra giới hạn tần suất (rate limit), sau đó gọi
    dịch vụ trả lời câu hỏi để nhận câu trả lời. Cuối cùng, nó định dạng
    câu trả lời và các thông tin liên quan thành một đối tượng `ChatResponse`
    để gửi về cho người dùng.

    Args:
        request (ChatRequest): Đối tượng chứa thông tin yêu cầu chat từ người dùng.
            Bao gồm `query` (câu hỏi), `chat_history` (lịch sử chat),
            `cohort` (nhóm người dùng) và `include_debug` (có muốn thông tin gỡ lỗi không).
        http_request (Request): Đối tượng yêu cầu HTTP từ FastAPI, được sử dụng
            để lấy thông tin như địa chỉ IP của người dùng để kiểm tra giới hạn tần suất.
        answer_service (Any): Dịch vụ dùng để xử lý và trả lời câu hỏi.
            Dịch vụ này được cung cấp thông qua Dependency Injection (tiêm phụ thuộc)
            bởi hàm `get_answer_service`.

    Returns:
        ChatResponse: Đối tượng phản hồi chat chứa câu trả lời, trạng thái,
            ID yêu cầu, độ trễ, các trích dẫn được sử dụng và tùy chọn thông tin gỡ lỗi.

    Raises:
        HTTPException: Nếu có lỗi xảy ra trong quá trình xử lý yêu cầu chat,
            ví dụ như lỗi nội bộ của dịch vụ chatbot, một ngoại lệ HTTP 500
            sẽ được trả về.
    """
    request_id = uuid4().hex
    started_at = time.perf_counter()
    query = validate_chat_query(request.query)
    enforce_chat_rate_limit(http_request)

    try:
        result = answer_service.answer(
            query, chat_history=request.chat_history, cohort=request.cohort
        )
    except Exception as exc:
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.exception(
            "chat_request_failed",
            extra={"request_id": request_id, "latency_ms": latency_ms},
        )
        raise HTTPException(
            status_code=500,
            detail="Internal chatbot service error",
        ) from exc

    latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
    result["request_id"] = request_id
    result["latency_ms"] = latency_ms
    logger.info(
        "chat_request_completed",
        extra={
            "request_id": request_id,
            "latency_ms": latency_ms,
            "query_length": len(query),
            "status": result.get("status"),
            "intent": result.get("intent"),
            "strategy": result.get("strategy"),
            "effective_query": result.get("effective_query"),
            "retrieval_query": result.get("retrieval_query"),
            "llm_called": bool(result.get("llm_called", False)),
            "used_cache": bool(result.get("used_cache", False)),
        },
    )

    return _to_chat_response(
        result,
        include_debug=should_include_debug(request.include_debug),
    )


@router.post("/chat/feedback")
def submit_feedback(request: ChatFeedbackRequest):
    """Gửi phản hồi (feedback) của người dùng về một câu trả lời cụ thể.

    Đây là một API endpoint nhận phản hồi từ người dùng về chất lượng của
    một câu trả lời đã được cung cấp. Phản hồi này (ví dụ: thích/không thích,
    điểm số, bình luận) sẽ được ghi lại vào LangSmith để theo dõi và cải thiện
    hiệu suất của chatbot.

    Args:
        request (ChatFeedbackRequest): Đối tượng chứa thông tin phản hồi từ người dùng.
            Bao gồm `run_id` (ID của lần chạy chatbot đã tạo ra câu trả lời),
            `score` (điểm đánh giá, ví dụ: 1 cho thích, 0 cho không thích),
            và `comment` (bình luận chi tiết của người dùng).

    Returns:
        dict: Một từ điển báo hiệu trạng thái thành công của việc gửi phản hồi,
            ví dụ: `{"status": "success"}`.

    Raises:
        HTTPException:
            - Nếu `run_id` không được cung cấp trong yêu cầu, một lỗi HTTP 400
              (Bad Request) sẽ được trả về.
            - Nếu có lỗi xảy ra trong quá trình gửi phản hồi đến LangSmith,
              một lỗi HTTP 500 (Internal Server Error) sẽ được trả về.
    """
    if not request.run_id:
        raise HTTPException(status_code=400, detail="run_id is required")

    try:
        client = LangSmithClient()
        client.create_feedback(
            request.run_id,
            key="user_score",
            score=request.score,
            comment=request.comment,
        )
        return {"status": "success"}
    except Exception as exc:
        logger.exception("feedback_submission_failed", extra={"run_id": request.run_id})
        raise HTTPException(
            status_code=500, detail="Failed to submit feedback"
        ) from exc