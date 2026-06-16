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
    request_id = uuid4().hex
    started_at = time.perf_counter()
    query = validate_chat_query(request.query)
    enforce_chat_rate_limit(http_request)

    try:
        result = answer_service.answer(query, chat_history=request.chat_history)
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
    """Gửi feedback (Like/Dislike) cho một câu trả lời vào LangSmith."""
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
        raise HTTPException(status_code=500, detail="Failed to submit feedback") from exc
