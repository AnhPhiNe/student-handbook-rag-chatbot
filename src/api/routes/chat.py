from __future__ import annotations

import logging
import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.chat_controls import (
    ChatCapacityError,
    chat_capacity_slot,
    enforce_chat_rate_limit,
    should_include_debug,
    validate_chat_query,
)
from src.api.deps import get_answer_service
from src.api.schemas import ChatRequest, ChatResponse, ChatFeedbackRequest
from src.generation.structured_result_presenter import public_regulation_citations
from src.api.langsmith_helper import (
    build_trace_metadata,
    submit_feedback_to_langsmith,
    submit_trace_to_langsmith,
)


router = APIRouter(tags=["chat"])
logger = logging.getLogger("student_handbook_rag.api.chat")
PUBLIC_ERROR_MESSAGE = "Không thể hoàn tất yêu cầu. Vui lòng thử lại sau."


def _build_debug_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Project internal pipeline state into the bounded public debug payload."""
    context_used = str(result.get("context_used") or "")
    citations = result.get("citations") or []
    citations_used = result.get("citations_used") or []

    return {
        "intent": result.get("intent"),
        "strategy": result.get("strategy"),
        "effective_query": result.get("effective_query"),
        "query_handling": result.get("query_handling"),
        "router_decision": result.get("router_decision"),
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
        "evaluation_telemetry": result.get("evaluation_telemetry"),
        "query_plan": result.get("query_plan"),
        "task_results": result.get("task_results") or [],
        "coverage_by_task": result.get("coverage_by_task") or {},
        "planner_fallback": result.get("planner_fallback"),
        "supports_task_ids": result.get("supports_task_ids") or {},
    }


def _to_chat_response(
    result: dict[str, Any],
    *,
    include_debug: bool,
) -> ChatResponse:
    """Convert an internal answer result into the stable public API schema."""
    citations_used = public_regulation_citations(result.get("citations_used") or [])
    internal_error_message = result.get("error_message")
    if include_debug:
        public_error_message = internal_error_message
    elif internal_error_message:
        public_error_message = PUBLIC_ERROR_MESSAGE
    else:
        public_error_message = None
    if isinstance(citations_used, list) and not include_debug:
        citations_used = [
            {
                key: value
                for key, value in citation.items()
                if key not in {"task_id", "supports_task_ids"}
            }
            if isinstance(citation, dict)
            else citation
            for citation in citations_used
        ]

    return ChatResponse(
        answer=str(result.get("answer") or ""),
        status=str(result.get("status") or "unknown"),
        effective_query=result.get("effective_query"),
        query_handling=result.get("query_handling"),
        request_id=result.get("request_id"),
        run_id=result.get("run_id"),
        latency_ms=result.get("latency_ms"),
        citations_used=citations_used if isinstance(citations_used, list) else [],
        structured_results=result.get("structured_results") or [],
        related_references=result.get("related_references") or [],
        clarification_needed=bool(result.get("clarification_needed", False)),
        intent=result.get("intent"),
        strategy=result.get("strategy"),
        llm_called=bool(result.get("llm_called", False)),
        used_cache=bool(result.get("used_cache", False)),
        error_type=result.get("error_type"),
        error_message=public_error_message,
        debug=_build_debug_payload(result) if include_debug else None,
    )


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    http_request: Request,
    answer_service: Any = Depends(get_answer_service),
) -> ChatResponse:
    """Validate, rate-limit, execute, trace, and serialize a chat request."""
    request_id = uuid4().hex
    started_at = time.perf_counter()
    query = validate_chat_query(request.query)
    enforce_chat_rate_limit(http_request)
    try:
        with chat_capacity_slot():
            result = answer_service.answer(
                query,
                chat_history=request.chat_history,
                cohort=request.cohort,
                trace_id=request_id,
            )
            sync_latency = round((time.perf_counter() - started_at) * 1000, 2)
            trace_metadata = build_trace_metadata(
                result,
                query=query,
                cohort=request.cohort,
                chat_history=request.chat_history,
                latency_ms=sync_latency,
            )
            submit_trace_to_langsmith(
                request_id,
                "Chat (Sync)",
                request.cohort,
                query,
                str(result.get("answer") or ""),
                metadata=trace_metadata,
                latency_ms=sync_latency,
                model=trace_metadata.get("model"),
                tags=["sync"],
                tracker=result.get("tracker"),
            )
    except ChatCapacityError as exc:
        latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.warning(
            "chat_request_overloaded",
            extra={
                "request_id": request_id,
                "latency_ms": latency_ms,
                "reason": exc.reason,
            },
        )
        raise HTTPException(
            status_code=503,
            detail="Hệ thống đang bận, bạn thử lại sau vài giây nhé.",
        ) from exc
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
    result["run_id"] = request_id
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
    """Queue bounded user feedback for the corresponding LangSmith run."""
    if not request.run_id:
        raise HTTPException(status_code=400, detail="run_id is required")

    submit_feedback_to_langsmith(request.run_id, request.score, request.comment)
    return {"status": "success"}
