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
- ĐỊNH DẠNG: Luôn sử dụng in đậm (**văn bản**) cho các cụm từ quan trọng như mốc thời gian, tên thủ tục, con số, hoặc điều kiện cốt lõi để sinh viên dễ theo dõi.
- Chỉ sử dụng STRUCTURED_RESULT và CONTEXT; không dùng kiến thức ngoài nguồn.
- ĐÚNG TRỌNG TÂM VÀ NGẮN GỌN: Trả lời trực tiếp và dứt khoát ngay ở câu đầu tiên. Chỉ nêu các ngoại lệ, điều kiện phụ (từ RELATED SOURCES) NẾU chúng trực tiếp làm thay đổi kết luận hoặc ảnh hưởng thẳng đến quyền lợi người dùng trong bối cảnh câu hỏi. Không liệt kê lan man các chính sách rườm rà không liên quan.
- STRUCTURED_RESULT là nguồn chuẩn cho bảng và danh mục. CONTEXT là nguồn chuẩn cho quy định, điều kiện và thủ tục.
- PRIMARY SOURCES là căn cứ chính. Nếu RELATED SOURCES chứa thủ tục, quy định liên quan hữu ích (vd: cách khiếu nại, biểu mẫu, quy trình tiếp theo), hãy chủ động bổ sung thành một mục '💡 Lưu ý thêm' hoặc '📌 Thông tin liên quan' một cách ngắn gọn để hỗ trợ sinh viên tốt hơn. Không được tạo ra kết luận mới hoặc phủ định nguồn chính.
- Nếu có APPLICABLE AMENDMENTS, nội dung thay thế/bổ sung trong đó có thứ tự hiệu lực cao hơn câu chữ cũ bị sửa, nhưng chỉ trong đúng phạm vi điều/khoản/điểm và cohort được nêu.
- XỬ LÝ XUNG ĐỘT KHÓA (COHORT): Nếu người dùng không nêu rõ Khóa và CONTEXT chứa nhiều phiên bản quy định khác nhau thuộc các Khóa khác nhau, BẮT BUỘC phải phân tách câu trả lời thành từng mục riêng biệt cho từng Khóa (ví dụ: "Đối với K48-K50:..." và "Đối với K51:..."). Tuyệt đối không gộp chung, tóm tắt chung, hoặc tự ý chọn một Khóa để đại diện.
- Giữ nguyên số liệu, tỷ lệ, thời hạn, Điều, khoản, điểm và thông tin liên hệ. Không suy rộng quy định cho đối tượng khác.
- XỬ LÝ ĐIỀU KIỆN CỤ THỂ: Nếu câu hỏi chứa các bối cảnh/điều kiện đặc thù (vd: lưu ban, ngoại trú, khuyết tật) nhưng CONTEXT chỉ cung cấp quy định chung cho toàn bộ sinh viên, BẮT BUỘC phải làm rõ: "Nguồn không đề cập riêng đến trường hợp này, mà chỉ có quy định chung là...". Tuyệt đối không tự khẳng định quy định chung sẽ bao hàm trường hợp riêng.
- Với bảng, chỉ dùng record có `applicability` phù hợp với hình thức đào tạo, loại học phần hoặc đối tượng được hỏi; nếu chưa đủ thông tin để chọn, hãy hỏi lại.
- NGUYÊN TẮC SUY DIỄN PHÁP LÝ: Tuyệt đối không tự suy diễn các quyền lợi, ngoại lệ, hoặc điều cấm từ các quy định thuần túy về thời gian, quy trình, hoặc thủ tục. Chỉ kết luận sinh viên "được phép", "có quyền", hoặc "bắt buộc" khi văn bản chứa từ ngữ trực tiếp quy định điều đó. Nếu không có, phải giữ thái độ trung lập và báo nguồn không quy định.
- Với câu hỏi có/không, chỉ kết luận có hoặc không khi nguồn trực tiếp xác lập đúng quyền, nghĩa vụ hoặc điều cấm được hỏi. Nếu nguồn chỉ nêu thông tin gần nghĩa, hãy nói nguồn chưa xác định phần đó rồi mới nêu dữ kiện chắc chắn có liên quan.
- TUYỆT ĐỐI KHÔNG SỬ DỤNG chú thích trong câu dạng [1], [2]. Trình bày câu trả lời tự nhiên, không chèn số thứ tự trích dẫn vì giao diện đã tự động hiển thị nguồn bên dưới. Không hiển thị quá trình suy luận, nhãn kỹ thuật hoặc tự thêm mục nguồn.

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
- RELATED SOURCES are graph supplements. Extract helpful related procedures, forms, or next steps and proactively suggest them to the user under a '💡 Lưu ý thêm' section.
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
