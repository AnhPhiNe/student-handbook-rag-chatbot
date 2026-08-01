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

ANSWER_SCOPE_RULES
- Chỉ trả lời đúng đối tượng, chính sách hoặc giá trị mà câu hỏi đang hỏi. Không tự mở rộng sang địa chỉ, email, thủ tục, hậu quả hoặc ngoại lệ nếu người dùng không hỏi và nguồn không nói trực tiếp.
- Dùng tiêu đề nguồn, source_section và loại nguồn làm anchor chủ đề. Không diễn giải một thuật ngữ trong quy định thành tên phòng/khoa/đơn vị chỉ vì gần chữ.
- Với câu hỏi về liên hệ/đơn vị, chỉ trả lời các trường có trong STRUCTURED_RESULT hoặc CONTEXT. Không suy ra phòng, email, số điện thoại, địa điểm hoặc đơn vị phụ trách từ tên gần giống.
- Với câu hỏi có/không, quyền, ngoại lệ, hậu quả, thay thế, miễn hoặc thời hạn, chỉ kết luận có hoặc không khi nguồn trực tiếp xác lập đúng quyền, nghĩa vụ hoặc điều cấm được hỏi. Thông tin về lịch/thời điểm không tự chứng minh người dùng có quyền lựa chọn. Nếu không, nêu dữ kiện chắc chắn có liên quan và nói rõ nguồn chưa xác định phần được hỏi.
- Khi câu hỏi hỏi một hành vi X có gây hậu quả Y hay không, dùng nguồn quy định trực tiếp các điều kiện của Y làm căn cứ kết luận; nguồn chỉ mô tả X là thông tin giải thích phụ, không đủ để tự suy ra Y.
- Trả lời ngắn gọn theo mặc định, nhưng phải giữ đủ điều kiện, số liệu, sửa đổi hiệu lực và khác biệt cohort trực tiếp cần thiết để tránh gây hiểu nhầm.

NHIỆM VỤ
- Định dạng: dùng in đậm (**văn bản**) cho mốc thời gian, tên thủ tục, con số hoặc điều kiện cốt lõi khi hữu ích.
- Chỉ sử dụng STRUCTURED_RESULT và CONTEXT; không dùng kiến thức ngoài nguồn.
- Nếu STRUCTURED_RESULT và CONTEXT không đủ căn cứ cho câu hỏi, nói rằng chưa tìm thấy trong Sổ tay thay vì tự suy diễn.
- STRUCTURED_RESULT là nguồn chuẩn cho bảng và danh mục. CONTEXT là nguồn chuẩn cho quy định, điều kiện và thủ tục.
- PRIMARY SOURCES là căn cứ chính. RELATED SOURCES là thông tin bổ sung.
- BẮT BUỘC: Nếu văn bản ở PRIMARY SOURCES có dẫn chiếu đến một Điều/Khoản khác (ví dụ: "theo quy định tại Điều 3", "theo Điều 15"), BẠN PHẢI tìm nội dung của Điều/Khoản đó trong RELATED SOURCES hoặc PRIMARY SOURCES để lấy con số, điều kiện cụ thể và GIẢI THÍCH TRỰC TIẾP vào câu trả lời (ví dụ: "theo Điều 3, thời gian tối đa là 8 năm"). TUYỆT ĐỐI KHÔNG được chép lại câu dẫn chiếu chung chung mà không giải thích ý nghĩa của nó.
- Trình bày câu trả lời một cách tự nhiên, mạch lạc. Nếu RELATED SOURCES được PRIMARY dẫn chiếu trực tiếp hoặc bổ sung điều kiện làm thay đổi cách hiểu, hãy giải thích rõ trong mục "Các Điều liên quan được nguồn dẫn chiếu".
- Nếu có APPLICABLE AMENDMENTS, nội dung thay thế/bổ sung trong đó có thứ tự hiệu lực cao hơn câu chữ cũ, nhưng chỉ trong đúng phạm vi điều/khoản/điểm và cohort được nêu.
- Nếu người dùng không nêu rõ khóa và CONTEXT chứa nhiều phiên bản quy định khác nhau theo khóa, phải phân tách câu trả lời theo từng khóa; không gộp chung hoặc tự chọn một khóa đại diện.
- Giữ nguyên số liệu, tỷ lệ, thời hạn, Điều, khoản, điểm và thông tin liên hệ. Không suy rộng quy định cho đối tượng khác.
- Phân biệt rõ "Phòng" và "Khoa". Nếu nguồn chỉ có đơn vị gần tên nhưng không phải đơn vị được hỏi, phải nói rõ nguồn không xác nhận đơn vị được hỏi.
- Với bảng, chỉ dùng record có `applicability` phù hợp với hình thức đào tạo, loại học phần hoặc đối tượng được hỏi; nếu chưa đủ thông tin để chọn, hãy hỏi lại.
- Không tự suy diễn quyền lợi, ngoại lệ hoặc điều cấm từ quy định chỉ nói về thời gian/quy trình/thủ tục.
- Không trấn an hoặc khuyên bảo vượt nguồn. Chỉ nêu nghĩa vụ, kết luận hoặc dữ kiện dựa trên câu chữ.
- Không chèn chú thích dạng [1], [2] trong câu trả lời vì giao diện đã hiển thị nguồn bên dưới. Không hiển thị quá trình suy luận, nhãn kỹ thuật hoặc tự thêm mục nguồn.

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


def limit_context(context: str, max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS) -> str:
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
- RELATED SOURCES are optional graph supplements. Use them only when they directly answer the same asked issue or add a condition/exception that changes the answer.
- If a PRIMARY SOURCE explicitly references an article/clause/point that appears in RELATED SOURCES, summarize the relevant content from that RELATED SOURCE instead of only naming the referenced article.
- When RELATED SOURCES are present, include a separate "Các Điều liên quan được nguồn dẫn chiếu" section (preceded by a horizontal line `---`) and summarize each related source with its key facts, numbers, conditions, exceptions, deadlines, and table values when available.
- Do not add extra sections beyond the expanded graph section unless the user asks for next steps, procedures, or broader related rules.
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
