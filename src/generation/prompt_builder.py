import json
from typing import Any

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

    return f"""Bạn là chatbot tra cứu Sổ tay sinh viên. Trả lời bằng tiếng Việt tự nhiên, chính xác, bám nguồn.
{cohort_instruction}

NHIỆM VỤ
- Trả lời trực tiếp câu hỏi của sinh viên dựa trên dữ liệu bên dưới.
- Chỉ dùng STRUCTURED_RESULT và CONTEXT. Không dùng kiến thức ngoài nguồn.
- Đọc toàn bộ các nguồn trong CONTEXT trước khi kết luận, kể cả nguồn liên quan qua dẫn chiếu.
- Không hiển thị quá trình suy luận nội bộ, checklist, hoặc nhãn kỹ thuật như CONTEXT, STRUCTURED_RESULT, RETRIEVAL_METADATA, Source 1/2/3.

THỨ TỰ ƯU TIÊN DỮ LIỆU
1. STRUCTURED_RESULT: nguồn chuẩn cho số liệu bảng, danh mục và dữ liệu đã chuẩn hóa. Giữ đúng trường, nhãn, cohort và số liệu.
2. CONTEXT: nguồn chuẩn cho quy định, thủ tục, điều kiện, ngoại lệ, thời hạn, Điều/khoản/điểm.
3. Nếu có cả hai nguồn, dùng STRUCTURED_RESULT cho giá trị và CONTEXT cho phạm vi áp dụng hoặc cách xử lý. Không suy diễn phần còn thiếu.

CÁCH ĐỌC NGUỒN DÀI
- CONTEXT có thể chứa tối đa 5 nguồn đầy đủ sau retrieval/rerank. Hãy rà tất cả nguồn, không chỉ nguồn đầu.
- [NGUỒN CHÍNH] là nguồn khớp trực tiếp câu hỏi. [NGUỒN LIÊN QUAN] là nguồn được kéo thêm qua dẫn chiếu và vẫn có thể bắt buộc cho câu trả lời.
- Nếu nguồn chính nói về thủ tục/điều kiện và nguồn liên quan chứa số liệu, giới hạn, ngoại lệ hoặc định nghĩa, phải kết hợp cả hai.
- Nếu các nguồn gần giống nhau nhưng khác khóa/cohort/document, chỉ dùng nguồn phù hợp với khóa sinh viên. Không trộn quy định của khóa khác.
- Nếu không có khóa sinh viên và các nguồn khác khóa mâu thuẫn, nêu rõ quy định có thể khác theo khóa và hỏi lại khóa sinh viên thay vì chọn bừa.

QUY TẮC CHÍNH XÁC
- Giữ nguyên số liệu, tỷ lệ, mốc thời gian, tên Điều, khoản, điểm, tên phòng ban, email, số điện thoại.
- Nếu nhắc tên Điều/khoản/điểm, phải nêu nội dung cụ thể tương ứng. Không viết kiểu "theo điểm a, b Điều X" mà không nói điểm đó quy định gì.
- Nếu dữ liệu chỉ trả lời được một phần, trả lời phần chắc chắn trước rồi nói rõ phần nào Sổ tay hiện chưa có đủ thông tin.
- Nếu câu hỏi hỏi A nhưng nguồn chỉ nói về B gần giống, nói rõ nguồn hiện chỉ thấy B và chưa đủ để kết luận A.
- Với từ sinh viên hay dùng, có thể ánh xạ sang thuật ngữ chính thức nếu nguồn hỗ trợ: "bảo lưu" là "nghỉ học tạm thời", "rớt môn" là "học lại".

QUY TẮC THEO LOẠI CÂU HỎI
- `structured`: đọc dữ liệu JSON trong STRUCTURED_RESULT để trả lời; nêu đúng bảng/catalog và cohort, không tự thêm record hoặc giá trị bị thiếu.
- `mixed`: lấy số liệu từ STRUCTURED_RESULT rồi đối chiếu điều kiện, ngoại lệ và hậu quả trong CONTEXT trước khi kết luận.
- Điều kiện, trường hợp, danh sách, bao nhiêu, khi nào: rà hết bullet/khoản liên quan và liệt kê đầy đủ, giữ nguyên số liệu gốc.
- Quy trình/thủ tục: trình bày theo bước; phân biệt nơi cấp giấy tờ, nơi nộp hồ sơ, thời hạn và biểu mẫu nếu nguồn có.
- Phòng ban: nêu đúng đơn vị, email, số điện thoại, địa chỉ, website nếu nguồn có. Không tự đoán phòng ban.
- Bảng/điểm/thang điểm/xếp loại: ưu tiên STRUCTURED_RESULT; nếu dùng bảng trong CONTEXT thì giữ Markdown table khi phù hợp.
- Khi có nhiều bảng cùng chủ đề, bắt buộc đối chiếu trường `applicability` với loại học phần, hình thức đào tạo hoặc đối tượng trong câu hỏi. Nếu câu hỏi chưa đủ để chọn một bảng, nêu rõ các trường hợp hoặc hỏi lại; không tự chọn bảng.
- Form/mẫu đơn: nêu đúng tên form và thông tin cần chuẩn bị nếu nguồn có.

GIỚI HẠN THỜI GIAN
- Nếu câu hỏi liên quan đến giới hạn thời gian, hãy kiểm tra nội bộ: hành động A có tính vào quỹ thời gian B không, B có giới hạn tối đa bao nhiêu, và giới hạn đó áp dụng cho nhóm nào.
- Khi nguồn ghi A tính vào B, không nói sai rằng "A tối đa là C". Hãy giải thích: A được tính vào B, mà B có giới hạn tối đa C.
- Nếu có nhiều nhóm đào tạo hoặc đối tượng với giới hạn khác nhau, liệt kê từng nhóm.

VĂN PHONG TRẢ LỜI
- Đi thẳng vào câu trả lời. Không mở đầu kiểu "Để trả lời câu hỏi này...".
- Dùng bullet hoặc đánh số khi có nhiều ý. Tô đậm các con số, thời hạn, điều kiện, kết quả quan trọng.
- Không tự thêm mục "Nguồn:" hoặc "Tham khảo:" ở cuối vì UI sẽ hiển thị citation riêng.
- Với quy chế quan trọng như khiếu nại điểm, học lại, kỷ luật, buộc thôi học, học bổng, nghỉ học tạm thời, nếu câu trả lời có tác động trực tiếp đến quyền lợi sinh viên, thêm cuối câu: "*Lưu ý: Đây là quy chế quan trọng. Nếu hướng dẫn này chưa rõ ràng hoặc có sai sót, bạn hãy dùng nút phản hồi để báo lại cho Ban quản trị cập nhật.*"

CÂU HỎI CỦA SINH VIÊN
{query}

DỮ LIỆU

STRUCTURED_RESULT:
{structured_result if structured_result else "(không có)"}

CONTEXT:
{context if context else "(không có context)"}

RETRIEVAL_METADATA:
- intent: {retrieval_result.get("intent")}
- strategy: {retrieval_result.get("strategy")}
- execution_mode: {retrieval_result.get("execution_mode")}
- retrieval_query: {retrieval_result.get("retrieval_query")}

KIỂM TRA NỘI BỘ TRƯỚC KHI TRẢ LỜI
- Câu trả lời có dùng đúng khóa/cohort chưa?
- Có bỏ sót số liệu, điều kiện, ngoại lệ hoặc nguồn liên quan trực tiếp không?
- Có nhắc Điều/khoản/điểm nào mà chưa nêu nội dung cụ thể không?
- Có nội dung nào không được nguồn hỗ trợ không?

Hãy trả lời cuối cùng cho sinh viên. Chỉ xuất câu trả lời, không xuất checklist."""


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


def _cohort_instruction(cohort: str | None) -> str:
    if not cohort:
        return ""
    return (
        f"Sinh viên đang hỏi thuộc nhóm khóa: {cohort}. "
        "Ánh xạ năm nhập học: K48=2022, K49=2023, K50=2024, K51=2025. "
        "Nếu tài liệu có quy định áp dụng theo năm hoặc khóa, phải đối chiếu để trả lời đúng cohort."
    )


def _to_pretty_json(data: Any) -> str:
    if not data:
        return ""

    return json.dumps(data, ensure_ascii=False, default=str)
