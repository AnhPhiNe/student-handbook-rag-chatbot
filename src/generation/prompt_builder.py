import json
from typing import Any

from src.common.cohort import COHORT_ADMISSION_YEARS

from .amendment_precedence import (
    collect_applicable_amendments,
    format_applicable_amendments,
)
from .context_allocation import ContextAllocationConfig, build_context_for_prompt


DEFAULT_MAX_CONTEXT_CHARS = 160000


def build_answer_prompt(
    query: str,
    retrieval_result: dict[str, Any],
    selected_citations: list[dict[str, Any]] | None = None,
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    cohort: str | None = None,
    context_allocation: ContextAllocationConfig | dict[str, Any] | None = None,
) -> str:
    context = build_context_for_prompt(
        retrieval_result=retrieval_result,
        query=query,
        selected_citations=selected_citations or [],
        max_context_chars=max_context_chars,
        allocation_config=context_allocation,
    )
    structured_result = _to_pretty_json(retrieval_result.get("structured_result"))
    cohort_instruction = _cohort_instruction(cohort)
    source_usage_instruction = _source_usage_instruction(context)
    applicable_amendments = format_applicable_amendments(
        collect_applicable_amendments(
            retrieval_result,
            query=query,
            cohort=cohort,
        )
    )

    return f"""Bạn là chatbot tra cứu Sổ tay sinh viên. Trả lời bằng tiếng Việt tự nhiên, chính xác, bám nguồn.
{cohort_instruction}
{source_usage_instruction}

NHIỆM VỤ
- Chỉ sử dụng STRUCTURED_RESULT và CONTEXT; không dùng kiến thức ngoài nguồn.
- Trả lời trực tiếp phạm vi người dùng hỏi, sau đó nêu đủ điều kiện, số liệu, ngoại lệ hoặc bước thủ tục có trong nguồn trực tiếp.
- STRUCTURED_RESULT là nguồn chuẩn cho bảng và danh mục. CONTEXT là nguồn chuẩn cho quy định, điều kiện và thủ tục.
- PRIMARY SOURCES là căn cứ chính. RELATED SOURCES chỉ bổ sung khi trực tiếp làm rõ câu hỏi, không được tạo ra kết luận mới hoặc phủ định nguồn chính.
- Nếu có APPLICABLE AMENDMENTS, nội dung thay thế/bổ sung trong đó có thứ tự hiệu lực cao hơn câu chữ cũ bị sửa, nhưng chỉ trong đúng phạm vi điều/khoản/điểm và cohort được nêu.
- Chỉ dùng dữ liệu đúng cohort. Nếu thiếu cohort và các khóa có quy định khác nhau, hãy hỏi lại thay vì tự chọn.
- Giữ nguyên số liệu, tỷ lệ, thời hạn, Điều, khoản, điểm và thông tin liên hệ. Không suy rộng quy định cho đối tượng khác.
- Nếu nguồn chỉ hỗ trợ một phần, trả lời phần chắc chắn và nói rõ phần chưa xác định. Nếu không có căn cứ trực tiếp, nói rằng chưa tìm thấy trong Sổ tay.
- Với bảng, chỉ dùng record có `applicability` phù hợp với hình thức đào tạo, loại học phần hoặc đối tượng được hỏi; nếu chưa đủ thông tin để chọn, hãy hỏi lại.
- Câu hỏi danh sách hoặc quy trình phải trả đủ các mục có liên quan; câu hỏi đơn giản nên ngắn gọn. Không thêm chính sách phụ hoặc hướng dẫn người dùng không hỏi.
- Phân biệt đúng quan hệ mà người dùng hỏi. Lịch xét, thời hạn xử lý hoặc thời điểm cấp kết quả không tự chứng minh người dùng có quyền lựa chọn, được phép hay bị cấm một hành động khác.
- Với câu hỏi có/không, chỉ kết luận có hoặc không khi nguồn trực tiếp xác lập đúng quyền, nghĩa vụ hoặc điều cấm được hỏi. Nếu nguồn chỉ nêu thông tin gần nghĩa, hãy nói nguồn chưa xác định phần đó rồi mới nêu dữ kiện chắc chắn có liên quan.
- Không hiển thị quá trình suy luận, nhãn kỹ thuật hoặc tự thêm mục nguồn; UI sẽ hiển thị citation riêng.

CÂU HỎI CỦA SINH VIÊN
{query}

DỮ LIỆU

STRUCTURED_RESULT:
{structured_result if structured_result else "(không có)"}

{applicable_amendments if applicable_amendments else "APPLICABLE AMENDMENTS: (không có sửa đổi áp dụng trực tiếp được phát hiện)"}

CONTEXT:
{context if context else "(không có context)"}

RETRIEVAL_METADATA:
- intent: {retrieval_result.get("intent")}
- strategy: {retrieval_result.get("strategy")}
- execution_mode: {retrieval_result.get("execution_mode")}
- retrieval_query: {retrieval_result.get("retrieval_query")}

Chỉ xuất câu trả lời cuối cùng cho sinh viên."""


def build_prompt(
    query: str,
    retrieval_result: dict[str, Any],
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    cohort: str | None = None,
    context_allocation: ContextAllocationConfig | dict[str, Any] | None = None,
) -> str:
    return build_answer_prompt(
        query=query,
        retrieval_result=retrieval_result,
        selected_citations=retrieval_result.get("citations"),
        max_context_chars=max_context_chars,
        cohort=cohort,
        context_allocation=context_allocation,
    )


def limit_context(
    context: str, max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS
) -> str:
    context = (context or "").strip()
    if len(context) <= max_context_chars:
        return context

    return (
        context[:max_context_chars].rstrip()
        + "\n\n[Context đã được rút gọn để tránh prompt quá dài.]"
    )


def _selected_context_or_fallback(
    retrieval_result: dict[str, Any],
    selected_citations: list[dict[str, Any]],
    max_context_chars: int,
) -> str:
    selected_chunk_ids = {
        str(citation.get("chunk_id"))
        for citation in selected_citations
        if citation.get("chunk_id")
    }
    selected_titles = {
        str(citation.get("title") or "").strip().lower()
        for citation in selected_citations
        if citation.get("title")
    }

    blocks: list[str] = []
    for item in retrieval_result.get("retrieved_items", []) or []:
        metadata = item.get("metadata", {}) or {}
        chunk_id = str(item.get("chunk_id") or "")
        title = str(
            metadata.get("title")
            or metadata.get("form_name")
            or metadata.get("unit_name")
            or metadata.get("faculty_or_unit_name")
            or metadata.get("procedure_name")
            or chunk_id
        ).strip()

        if selected_chunk_ids and chunk_id not in selected_chunk_ids:
            continue
        if (
            not selected_chunk_ids
            and selected_titles
            and title.lower() not in selected_titles
        ):
            continue

        blocks.append(
            "\n".join(
                [
                    f"Tiêu đề: {title}",
                    f"Loại: {metadata.get('chunk_type')}",
                    f"Trang: {metadata.get('source_pages')}",
                    f"Nội dung: {item.get('content')}",
                ]
            )
        )

    if blocks:
        return limit_context(
            "\n\n---\n\n".join(blocks), max_context_chars=max_context_chars
        )

    return limit_context(
        str(retrieval_result.get("context_for_llm") or ""),
        max_context_chars=max_context_chars,
    )


def _source_usage_instruction(context: str) -> str:
    if "PRIMARY SOURCES" not in str(context or ""):
        return ""
    return """
SOURCE_USAGE_RULES
- PRIMARY SOURCES are the main evidence for the final answer and citations.
- RELATED SOURCES are graph supplements. Use them only to add context, explain a direct reference, or clarify a relationship.
- Do not let RELATED SOURCES replace, reorder, or override PRIMARY SOURCES.
- Prefer citations from PRIMARY SOURCES. Use a RELATED SOURCE only when it directly supports an extra contextual point.
- If a RELATED SOURCE appears to conflict with PRIMARY SOURCES, do not use it to negate the answer unless a PRIMARY SOURCE also supports that conclusion.
"""


def _cohort_instruction(cohort: str | None) -> str:
    if not cohort:
        return ""
    year_mapping = ", ".join(
        f"{label}=" + "/".join(str(year) for year in years)
        for label, years in COHORT_ADMISSION_YEARS.items()
    )
    return (
        f"Sinh viên đang hỏi thuộc nhóm khóa: {cohort}. "
        f"Ánh xạ năm nhập học: {year_mapping}. "
        "Nếu tài liệu có quy định áp dụng theo năm hoặc khóa, phải đối chiếu để trả lời đúng cohort."
    )


def _to_pretty_json(data: Any) -> str:
    if not data:
        return ""

    return json.dumps(data, ensure_ascii=False, default=str)
