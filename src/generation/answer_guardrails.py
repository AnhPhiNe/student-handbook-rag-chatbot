from typing import Any


def is_context_empty(retrieval_result: dict[str, Any]) -> bool:
    """Return whether neither retrieval nor structured lookup produced evidence."""

    return not (
        bool(retrieval_result.get("retrieved_items"))
        or _has_result(retrieval_result.get("structured_result"))
    )


def is_low_confidence(retrieval_result: dict[str, Any]) -> bool:
    # Deterministic structured evidence is never treated as low confidence.
    """Return whether available evidence is too weak for generation."""

    if _has_validated_non_rag_outcome(retrieval_result):
        return False

    # QueryPlan coverage is computed after source binding. The executor's
    # needs_llm_answer also includes covered units within a partially covered
    # multi-cohort task; their citations remain usable for composition.
    coverage = retrieval_result.get("coverage_by_task") or {}
    if (
        isinstance(coverage, dict)
        and (
            "covered" in coverage.values()
            or retrieval_result.get("needs_llm_answer") is True
        )
        and bool(retrieval_result.get("citations"))
    ):
        return False

    # Without context, the LLM has no grounded source to use.
    if is_context_empty(retrieval_result):
        return True

    retrieved_items = retrieval_result.get("retrieved_items") or []
    citations = retrieval_result.get("citations") or []
    return not retrieved_items and not citations


def _has_validated_non_rag_outcome(retrieval_result: dict[str, Any]) -> bool:
    if retrieval_result.get("out_of_domain") or retrieval_result.get(
        "needs_clarification"
    ):
        return True

    # Retrieved synthetic candidates may be useful context, but they are not
    # a validated structured result.
    if retrieval_result.get("deterministic_validated") is not True:
        return False

    return _has_result(retrieval_result.get("structured_result"))


def build_fallback_answer(
    query: str,
    retrieval_result: dict[str, Any] | None = None,
    reason: str | None = None,
) -> str:
    """Build the safe user-facing response for ungrounded requests."""

    if reason in {"api_error", "rate_limit", "timeout"}:
        return (
            "Hiện tại mình chưa gọi được mô hình AI để diễn giải câu trả lời. "
            "Bạn có thể thử lại sau; nếu hệ thống đã tìm được nguồn liên quan, "
            "mình vẫn hiển thị nguồn bên dưới để bạn tra nhanh."
        )

    if reason == "retrieval_error":
        return (
            "Mình gặp lỗi khi tra cứu dữ liệu sổ tay cho câu hỏi này. "
            "Bạn thử lại sau hoặc hỏi hẹp hơn theo phòng ban, "
            "quy định hay mốc điểm cần tra nhé."
        )

    return (
        "Mình chưa tìm thấy thông tin đủ rõ trong Sổ tay sinh viên cho câu hỏi này. "
        "Bạn có thể hỏi cụ thể hơn về phòng ban, quy định, mốc điểm "
        "hoặc thủ tục cần tra cứu."
    )


def _has_result(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return (
        value.get("result") is not None
        or bool(value.get("sub_lookups"))
        or bool(value.get("items"))
    )


