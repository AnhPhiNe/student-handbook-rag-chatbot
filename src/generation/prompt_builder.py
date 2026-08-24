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
    query_plan = _to_pretty_json(retrieval_result.get("query_plan"))
    task_results = _to_pretty_json(retrieval_result.get("task_results"))
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
- Khi liệt kê nhiều trường hợp, dùng danh sách Markdown đánh số `1.`, `2.`, `3.`. Không gọi “mục 1, 2, 3” nếu các mục đó không được đánh số rõ ngay trong câu trả lời.
- Chỉ sử dụng STRUCTURED_RESULT và CONTEXT; không dùng kiến thức ngoài nguồn.
- Nếu STRUCTURED_RESULT và CONTEXT không đủ căn cứ cho câu hỏi, nói rằng chưa tìm thấy trong Sổ tay thay vì tự suy diễn.
- STRUCTURED_RESULT là nguồn chuẩn cho bảng và danh mục. CONTEXT là nguồn chuẩn cho quy định, điều kiện và thủ tục.
- PRIMARY SOURCES là căn cứ duy nhất để trả lời. Các điều khoản liên quan được giao diện liên kết riêng, không nằm trong CONTEXT.
- Không chèn mã trích dẫn dạng [1], [R1] hoặc chú thích nguồn vào câu trả lời; giao diện sẽ hiển thị nguồn và liên kết điều khoản liên quan.
- Nếu có APPLICABLE AMENDMENTS, nội dung thay thế/bổ sung trong đó có thứ tự hiệu lực cao hơn câu chữ cũ, nhưng chỉ trong đúng phạm vi điều/khoản/điểm và cohort được nêu. Hãy áp dụng trực tiếp nội dung mới nhất vào câu trả lời một cách tự nhiên; tuyệt đối KHÔNG ghi các nhãn hay chú thích như "AMENDMENT 1", "được bổ sung bởi AMENDMENT", "theo AMENDMENT", "[AMENDMENT]" vào câu trả lời.
- Nếu người dùng không nêu rõ khóa và CONTEXT chứa nhiều phiên bản quy định khác nhau theo khóa, phải phân tách câu trả lời theo từng khóa; không gộp chung hoặc tự chọn một khóa đại diện.
- Khi câu hỏi so sánh hoặc hỏi về từ 2 khóa trở lên (ví dụ K50 và K51), hãy trình bày rõ ràng theo từng khóa: "1. Đối với Khóa X: ..." và "2. Đối với Khóa Y: ...", sử dụng in đậm cho các con số, thang điểm và điều kiện cốt lõi; tuyệt đối không gộp chung hoặc lấy quy định của khóa này áp đặt cho khóa kia.
- Nếu câu hỏi chỉ định rõ một hình thức/hệ đào tạo (chính quy, vừa làm vừa học, liên thông, văn bằng 2), chỉ trả lời phần quy định cho hệ đó. Nếu câu hỏi không chỉ định rõ hệ đào tạo, hãy nêu rõ thông tin cho từng hệ đào tạo có trong nguồn để người dùng tự đối chiếu.
- Giữ nguyên số liệu, tỷ lệ, thời hạn, Điều, khoản, điểm và thông tin liên hệ. Không suy rộng quy định cho đối tượng khác.
- Phân biệt rõ "Phòng" và "Khoa". Nếu nguồn chỉ có đơn vị gần tên nhưng không phải đơn vị được hỏi, phải nói rõ nguồn không xác nhận đơn vị được hỏi.
- Với bảng, chỉ dùng record có `applicability` phù hợp với hình thức đào tạo, loại học phần hoặc đối tượng được hỏi; nếu chưa đủ thông tin để chọn, hãy hỏi lại.
- Không tự suy diễn quyền lợi, ngoại lệ hoặc điều cấm từ quy định chỉ nói về thời gian/quy trình/thủ tục.
- Không trấn an hoặc khuyên bảo vượt nguồn. Chỉ nêu nghĩa vụ, kết luận hoặc dữ kiện dựa trên câu chữ.
- Không hiển thị quá trình suy luận, nhãn kỹ thuật hoặc tự thêm mục nguồn.
- Khi có QUERY_PLAN, trả lời lần lượt mọi task theo thứ tự. Chỉ dùng STRUCTURED_RESULT hoặc PRIMARY SOURCE có `Supports tasks` chứa đúng task id tương ứng.
- Giữ nguyên số liệu, cohort và `applicability` trong structured JSON. Không dùng evidence của task này để lấp phần thiếu của task khác.
- Với task có coverage `uncovered`, nói rõ chưa tìm thấy nguồn cho riêng ý đó. Với task `needs_clarification`, nêu câu hỏi làm rõ; vẫn trả lời đầy đủ các task khác đã `covered`.
- Task `needs_clarification` tuyệt đối chỉ được xuất câu hỏi làm rõ tương ứng; không trả lời, suy đoán hoặc mượn evidence của task khác cho task đó, kể cả khi CONTEXT có đoạn nhìn có vẻ liên quan.

CÂU HỎI CỦA SINH VIÊN
{query}

DỮ LIỆU

QUERY_PLAN:
{query_plan if query_plan else "(không có; xử lý legacy một yêu cầu)"}

TASK_RESULTS:
{task_results if task_results else "(không có)"}

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


def _source_usage_instruction(context: str) -> str:
    normalized_context = str(context or "").upper()
    if (
        "PRIMARY SOURCES" not in normalized_context
        and "ROLE: PRIMARY" not in normalized_context
    ):
        return ""
    return """
SOURCE_USAGE_RULES
- PRIMARY SOURCES are the main evidence for the final answer.
- Only use facts contained in PRIMARY SOURCES. Do not infer facts from references to other articles.
- When a PRIMARY SOURCE header identifies an applicable Điều, retain the exact “Điều X” in the final answer; do not replace it with a generic reference.
- Do not output bracketed source markers; the client renders source and related-reference affordances separately.
"""


def _cohort_instruction(cohort: str | list[str] | None) -> str:
    if not cohort:
        return ""
    if isinstance(cohort, list):
        cohort_list = [str(c).strip() for c in cohort if str(c).strip()]
    else:
        cohort_list = [c.strip() for c in str(cohort).split(",") if c.strip()]

    year_mapping = ", ".join(
        f"{label}=" + "/".join(str(year) for year in years)
        for label, years in COHORT_ADMISSION_YEARS.items()
    )
    if len(cohort_list) >= 2:
        cohort_display = ", ".join(cohort_list)
        return (
            f"Câu hỏi đang yêu cầu so sánh/truy vấn giữa các nhóm khóa: {cohort_display}. "
            f"Ánh xạ năm nhập học: {year_mapping}. "
            "Hãy đối chiếu tài liệu và trả lời rành mạch theo từng khóa."
        )
    single_cohort = cohort_list[0] if cohort_list else str(cohort).strip()
    return (
        f"Sinh viên đang hỏi thuộc nhóm khóa: {single_cohort}. "
        f"Ánh xạ năm nhập học: {year_mapping}. "
        "Nếu tài liệu có quy định áp dụng theo năm hoặc khóa, phải đối chiếu để trả lời đúng cohort."
    )


def _to_pretty_json(data: Any) -> str:
    if not data:
        return ""

    return json.dumps(data, ensure_ascii=False, default=str)
