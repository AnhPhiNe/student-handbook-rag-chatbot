from typing import Any


def is_context_empty(retrieval_result: dict[str, Any]) -> bool:
    # Context rong nghia la retrieval khong co van ban, khong co lookup, cung khong co tool result.
    return not any(
        [
            bool(retrieval_result.get("retrieved_items")),
            _has_result(retrieval_result.get("structured_result")),
            _has_formula_result(retrieval_result.get("formula_result")),
            _has_result(retrieval_result.get("tool_result")),
        ]
    )


def is_low_confidence(retrieval_result: dict[str, Any]) -> bool:
    # Neu da co ket qua deterministic thi khong xem la low-confidence.
    if _has_validated_non_rag_outcome(retrieval_result):
        return False

    # QueryPlan coverage is computed after task-level source binding. A covered
    # task with citations is usable even when top-level retrieval context is empty.
    coverage = retrieval_result.get("coverage_by_task") or {}
    if (
        isinstance(coverage, dict)
        and "covered" in coverage.values()
        and bool(retrieval_result.get("citations"))
    ):
        return False

    # Khong co context nao thi LLM khong co nguon de dua vao.
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

    return any(
        (
            _has_result(retrieval_result.get("structured_result")),
            _has_formula_result(retrieval_result.get("formula_result")),
            _has_result(retrieval_result.get("tool_result")),
        )
    )


def build_fallback_answer(
    query: str,
    retrieval_result: dict[str, Any] | None = None,
    reason: str | None = None,
) -> str:
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

    if reason == "out_of_domain":
        return (
            "Mình chưa tìm thấy thông tin phù hợp trong Sổ tay sinh viên cho câu hỏi này. "
            "Sổ tay chủ yếu hỗ trợ các nội dung như quy định học vụ, "
            "điểm rèn luyện, học bổng, ký túc xá, phòng ban và khoa/ngành. "
            "Bạn có thể hỏi lại theo một nội dung liên quan đến sổ tay nhé."
        )

    return (
        "Mình chưa tìm thấy thông tin đủ rõ trong Sổ tay sinh viên cho câu hỏi này. "
        "Bạn có thể hỏi cụ thể hơn về phòng ban, quy định, mốc điểm "
        "hoặc thủ tục cần tra cứu."
    )


def detect_ambiguous_query(query: str, retrieval_result: dict[str, Any]) -> bool:
    """Check whether a query requires clarification before generating an answer."""
    if _has_result(retrieval_result.get("structured_result")) and retrieval_result.get("deterministic_validated"):
        return False
    if bool(retrieval_result.get("needs_clarification")):
        return True
    return False


def is_out_of_domain_query(query: str, retrieval_result: dict[str, Any]) -> bool:
    """Check if query is out of domain."""
    return bool(retrieval_result.get("out_of_domain"))


def build_clarification_question(query: str, retrieval_result: dict[str, Any]) -> str:
    """Return the Planner clarification or a clean default fallback."""
    clarification_q = retrieval_result.get("clarification_question")
    if clarification_q and str(clarification_q).strip():
        return str(clarification_q).strip()
    return "Bạn có thể nói rõ hơn bạn muốn tra cứu quy định, thủ tục hay đơn vị nào không?"


def _has_result(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    return value.get("result") is not None or bool(value.get("sub_lookups")) or bool(value.get("items"))


def _has_formula_result(value: Any) -> bool:
    return isinstance(value, dict) and bool(value.get("formula_text"))
