from typing import Any


def build_scoped_score_answer(packet: dict[str, Any], query_plan: dict[str, Any]) -> str | None:
    """Present complete conditional grade rows for pure direct lookup requests.

    Return None for policy questions, mixed plans or incomplete resolutions.
    Every conditional scope stays separate; no global fact lock is created.
    """
    tasks = {task.get("id"): task for task in query_plan.get("tasks") or []}
    units = packet.get("units") or []
    if not units or {unit.get("task_id") for unit in units} != set(tasks):
        return None
    sections = []
    for unit in units:
        task = tasks[unit["task_id"]]
        slots = task.get("slots") or {}
        sources = unit.get("primary_evidence") or []
        if (unit.get("mode") != "structured" or unit.get("coverage") != "covered"
                or task.get("lookup_type") != "scoring" or task.get("intent") != "direct_value"
                or slots.get("operation") not in ("grade_10_to_letter", "pass_threshold")
                or unit.get("applicable_amendments") or len(sources) != 1):
            return None
        source = sources[0]
        rows = source.get("resolved_rows")
        operand = slots.get("score_or_grade")
        if (not isinstance(rows, list) or not rows or source.get("resolved_result")
                or isinstance(operand, (bool, list, dict)) or operand is None
                or not source.get("printed_in") or not source.get("article_label")):
            return None
        lines = []
        for item in rows:
            row = item.get("row") or {}
            if not all(isinstance(value, str) and value.strip() for value in (
                    item.get("table_name"), item.get("applicability"),
                    row.get("letter_grade"), row.get("status"), row.get("score_10_range"))):
                return None
            lines.append(
                f"- **{item['table_name']}** ({item['applicability']}): "
                f"điểm chữ **{row['letter_grade']}**, xếp loại **{row['status']}** "
                f"(khoảng điểm **{row['score_10_range']}**)."
            )
        text = (f"Theo **{source['printed_in']}**, với điểm **{operand}**, "
                f"kết quả theo **{source['article_label']}** cho từng phạm vi là:\n\n"
                + "\n".join(lines)
                + "\n\nĐối chiếu nhóm học phần của bạn với trường hợp tương ứng ở trên để xác định kết quả áp dụng.")
        if source.get("currency_note"):
            text += f"\n\nLưu ý: {source['currency_note']}"
        if len(units) > 1:
            text = f"**Khóa {unit['cohort']} — {unit['question']}**\n\n{text}"
        sections.append(text)
    return "\n\n".join(sections)


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


