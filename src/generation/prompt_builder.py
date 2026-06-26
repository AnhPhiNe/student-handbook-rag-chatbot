import json
from typing import Any


DEFAULT_MAX_CONTEXT_CHARS = 12000


def build_answer_prompt(
    query: str,
    retrieval_result: dict[str, Any],
    selected_citations: list[dict[str, Any]] | None = None,
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    cohort: str | None = None,
) -> str:
    context = _selected_context_or_fallback(
        retrieval_result=retrieval_result,
        selected_citations=selected_citations or [],
        max_context_chars=max_context_chars,
    )
    structured_result = _to_pretty_json(retrieval_result.get("structured_result"))
    tool_result = _to_pretty_json(retrieval_result.get("tool_result"))
    cohort_str = ""
    if cohort:
        cohort_str = f" Sinh viên đang hỏi thuộc nhóm khóa: {cohort} (Lưu ý ánh xạ năm nhập học: K48=2022, K49=2023, K50=2024, K51=2025). NẾU TRONG TÀI LIỆU CÓ QUY ĐỊNH ÁP DỤNG THEO NĂM, HÃY ĐỐI CHIẾU NĂM ĐỂ TRẢ LỜI ĐÚNG CHO SINH VIÊN."
        
    return f"""Bạn là chatbot tra cứu Sổ tay sinh viên.{cohort_str}

Nguyên tắc bắt buộc:
- Chỉ trả lời dựa trên CONTEXT, STRUCTURED_RESULT, TOOL_RESULT và CITATIONS bên dưới.
- Đọc kỹ TOÀN BỘ các đoạn văn trong CONTEXT từ trên xuống dưới trước khi trả lời. ĐẶC BIỆT LƯU Ý các chú thích (footnote) hoặc dòng ghi chú sửa đổi (VD: "áp dụng từ khóa tuyển sinh năm 2025") để chọn đúng quy định áp dụng cho khóa của sinh viên. KHÔNG dùng quy định cũ nếu đã có chú thích sửa đổi cho khóa hiện tại.
- Không bịa, không suy đoán ngoài dữ liệu được cung cấp, không tự tạo nguồn ngoài context.
- ĐẶC BIỆT LƯU Ý: Nếu câu hỏi hỏi về một khái niệm (VD: học phí), nhưng CONTEXT chỉ chứa thông tin về khái niệm "tương tự" (VD: hỗ trợ chi phí, học bổng, tín chỉ), TUYỆT ĐỐI KHÔNG được dùng để trả lời. Bạn phải nói rõ: "Sổ tay sinh viên không đề cập cụ thể thông tin này." Tuy nhiên, đối với các TỪ LÓNG phổ biến của sinh viên (như "bảo lưu" tương đương với "nghỉ học tạm thời", "rớt môn" tương đương "học lại"), hãy linh hoạt cung cấp thông tin của thuật ngữ chính thức và giải thích nhẹ nhàng.
- Nếu dữ liệu không đủ rõ, nói rằng chưa tìm thấy thông tin rõ trong Sổ tay sinh viên.
- Nếu có nhiều nguồn liên quan, phân biệt rõ từng nguồn/trường hợp.
- Nếu có STRUCTURED_RESULT hoặc TOOL_RESULT, xem đó là kết quả đúng, không tự tính lại và không thay đổi kết quả.
- Trả lời bằng tiếng Việt, tự nhiên, thân thiện với sinh viên. TUYỆT ĐỐI KHÔNG xưng "chúng ta", không dùng văn phong máy móc kiểu "Để trả lời câu hỏi này, chúng ta cần xem xét...". Hãy đi thẳng vào vấn đề.
- TUYỆT ĐỐI KHÔNG ĐƯỢC nhắc đến các từ khóa kỹ thuật như "CONTEXT", "STRUCTURED_RESULT", "TOOL_RESULT", "CITATIONS" trong câu trả lời cho sinh viên.
- PHẢI trình bày ĐẦY ĐỦ, CHI TIẾT mọi thông tin có trong tài liệu. Không được tóm tắt, lược bỏ, hay rút gọn nội dung. Nếu có liệt kê điều kiện, quy trình, bước thực hiện thì PHẢI trình bày hết, giữ nguyên các con số, tỷ lệ, mức điểm.
- Tô đậm (in đậm) các ý quan trọng bằng Markdown (VD: **tên phòng ban**, **thời hạn**, **số điện thoại**, **chi phí**, **kết quả**) để sinh viên dễ đọc.
- Sử dụng bullet points, đánh số thứ tự, và tiêu đề phụ (nếu cần) để trình bày rõ ràng.
- TUYỆT ĐỐI KHÔNG TỰ VIẾT mục "Nguồn:", "Tham khảo:" hoặc liệt kê tài liệu ở cuối câu trả lời. Giao diện (UI) đã tự động thực hiện việc này.

Quy tắc theo loại câu hỏi:
- Câu hỏi về form: nêu đúng tên form/mẫu đơn và thông tin cần thiết nếu context có.
- Câu hỏi về phòng ban: nêu tên đơn vị, email/số điện thoại/địa chỉ/website nếu context có.
- Câu hỏi về quy định/thủ tục: PHẢI TỔNG HỢP toàn bộ quy trình từ TẤT CẢ các tài liệu. Phân biệt rõ nơi cấp giấy tờ và NƠI NỘP HỒ SƠ chính thức. Không bỏ sót nơi nộp hồ sơ. NẾU Sổ tay sinh viên KHÔNG GHI RÕ phòng ban nộp hồ sơ/thực hiện thủ tục, PHẢI TRẢ LỜI LÀ "Sổ tay sinh viên không quy định chi tiết phòng ban nộp đơn/thủ tục này", tuyệt đối KHÔNG tự ý suy diễn hoặc lấy thông tin từ danh bạ phòng ban để đoán bừa.
- Câu hỏi về điểm/range: dùng STRUCTURED_RESULT và trả kết quả trực tiếp.
- Câu hỏi tính điểm: dùng TOOL_RESULT, nêu kết quả và công thức/ghi chú có sẵn; không tự tính lại.

USER_QUESTION:
{query}

RETRIEVAL_METADATA:
- intent: {retrieval_result.get("intent")}
- strategy: {retrieval_result.get("strategy")}
- retrieval_query: {retrieval_result.get("retrieval_query")}

STRUCTURED_RESULT:
{structured_result if structured_result else "(không có)"}

TOOL_RESULT:
{tool_result if tool_result else "(không có)"}

CONTEXT:
{context if context else "(không có context)"}

Hãy viết câu trả lời cuối cùng cho sinh viên."""


def build_prompt(
    query: str,
    retrieval_result: dict[str, Any],
    max_context_chars: int = DEFAULT_MAX_CONTEXT_CHARS,
    cohort: str | None = None,
) -> str:
    return build_answer_prompt(
        query=query,
        retrieval_result=retrieval_result,
        selected_citations=retrieval_result.get("citations"),
        max_context_chars=max_context_chars,
        cohort=cohort,
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
        if not selected_chunk_ids and selected_titles and title.lower() not in selected_titles:
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
        return limit_context("\n\n---\n\n".join(blocks), max_context_chars=max_context_chars)

    return limit_context(
        str(retrieval_result.get("context_for_llm") or ""),
        max_context_chars=max_context_chars,
    )


def _to_pretty_json(data: Any) -> str:
    if not data:
        return ""

    return json.dumps(data, ensure_ascii=False, indent=2, default=str)
