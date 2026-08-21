import json
from typing import Any

from src.common.cohort import COHORT_ADMISSION_YEARS

from .amendment_precedence import (
    collect_applicable_amendments,
    format_applicable_amendments,
)
from .context_allocation import ContextAllocationConfig, build_context_for_prompt
from .request_answer_contract import (
    REQUEST_COMPOSER_PROMPT_VERSION,
)


DEFAULT_MAX_CONTEXT_CHARS = 160000
ANSWER_PROMPT_VERSION = "single-cohort-answer-v3-request-focused"


def build_request_claim_prompt(
    *,
    request_id: str,
    request_kind: str,
    query_span: str,
    grounded_request_query: str,
    cohort: str | None,
    evidence_catalog: list[dict[str, Any]],
    fact_catalog: list[dict[str, Any]],
) -> str:
    """Build a request-isolated composer prompt with a typed claim contract."""

    evidence_json = _to_pretty_json(evidence_catalog)
    facts_json = _to_pretty_json(fact_catalog)
    allowed_ids = [str(item.get("evidence_id")) for item in evidence_catalog]
    allowed_fact_refs = [str(item.get("fact_ref")) for item in fact_catalog]
    return f"""Bạn là bộ soạn câu trả lời cho đúng một yêu cầu tra cứu Sổ tay sinh viên.
Phiên bản prompt: {REQUEST_COMPOSER_PROMPT_VERSION}

RÀNG BUỘC
- Chỉ xử lý request_id={request_id}; không suy đoán về yêu cầu khác.
- Loại request đã kiểm chứng: {request_kind}
- Câu chữ gốc của yêu cầu con: {query_span}
- Câu hỏi con đã được grounding bằng code: {grounded_request_query}
- Cohort đã được kiểm chứng: {cohort or "không xác định"}
- Chỉ dùng FACT_CATALOG và EVIDENCE_CATALOG bên dưới. Không dùng kiến thức ngoài nguồn.
- Mỗi claim phải là một khẳng định độc lập, ngắn gọn, giữ nguyên điều kiện, số liệu,
  đối tượng, phủ định, ngoại lệ và phạm vi áp dụng trong nguồn.
- Trả tối đa 6 claims cho request này; gộp câu chữ chỉ khi không làm thay đổi phạm vi.
- Không tự thêm lời khuyên, đơn vị liên hệ, thủ tục, thời hạn hoặc kết luận vắng mặt.
- citation_ids chỉ được lấy từ danh sách cho phép: {json.dumps(allowed_ids, ensure_ascii=False)}.
- Với structured, mỗi claim phải có fact_refs lấy từ: {json.dumps(allowed_fact_refs, ensure_ascii=False)}.
- Với RAG, fact_refs bắt buộc là []; mỗi claim phải được evidence hỗ trợ trực tiếp.
- Ưu tiên câu hỏi đã grounding khi câu chữ gốc là follow-up phụ thuộc lịch sử.
- Nếu dữ liệu không trực tiếp trả lời câu hỏi con đã grounding, trả claims=[] và nêu abstention_reason.
- Không xuất Markdown fence, giải thích hoặc văn bản ngoài JSON.

SCHEMA ĐẦU RA
{{
  "request_id": {json.dumps(request_id, ensure_ascii=False)},
  "claims": [
    {{
      "text": "khẳng định được nguồn hỗ trợ",
      "citation_ids": ["evidence_id"],
      "fact_refs": ["result.field"]
    }}
  ],
  "abstention_reason": null
}}

FACT_CATALOG
{facts_json or "(không áp dụng cho RAG)"}

EVIDENCE_CATALOG
{evidence_json}
"""


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
    request_results = _to_pretty_json(retrieval_result.get("request_results"))
    request_evidence_scope = _request_evidence_scope(retrieval_result)
    unresolved_requests = _to_pretty_json(
        retrieval_result.get("unresolved_lookup_requests")
    )
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
- Trả lời trực tiếp và bám sát đúng 100% phạm vi câu hỏi dựa trên tài liệu được cấp. Tuyệt đối KHÔNG suy đoán, không bổ sung quy định từ trí nhớ ngoài nguồn, và không tự ý đưa thêm lời khuyên mở rộng ngoài Sổ tay sinh viên.
- Bắt buộc nêu rõ tên **Điều X** (kèm tên văn bản quy chế) trực tiếp từ nguồn chính trong câu trả lời để làm anchor cốt lõi cho liên kết Đồ thị Tri thức (Knowledge Graph).
- Chỉ trích xuất và trình bày các điều kiện/thủ tục thực tế có trong văn bản của từng Điều trong CONTEXT; tuyệt đối KHÔNG tự thêm các con số, tỷ lệ phần trăm hoặc quy định ngoài CONTEXT.
- Khi câu hỏi hỏi về điểm học phần/học tập, chỉ trả lời phần quy định cho học phần/học tập; tuyệt đối không tự mở rộng sang điểm rèn luyện, khen thưởng hay kỷ luật nếu người dùng không hỏi.
- Chỉ trả lời đúng đối tượng, chính sách hoặc giá trị mà câu hỏi đang hỏi. Không tự mở rộng sang địa chỉ, email, thủ tục, hậu quả hoặc ngoại lệ nếu người dùng không hỏi và nguồn không nói trực tiếp.
- Dùng tiêu đề nguồn, source_section và loại nguồn làm anchor chủ đề. Không diễn giải một thuật ngữ trong quy định thành tên phòng/khoa/đơn vị chỉ vì gần chữ.
- Với câu hỏi về liên hệ/đơn vị, chỉ trả lời các trường có trong STRUCTURED_RESULT hoặc CONTEXT. Không suy ra phòng, email, số điện thoại, địa điểm hoặc đơn vị phụ trách từ tên gần giống.
- Với câu hỏi có/không, quyền, ngoại lệ, hậu quả, thay thế, miễn hoặc thời hạn, chỉ kết luận có hoặc không khi nguồn trực tiếp xác lập đúng quyền, nghĩa vụ hoặc điều cấm được hỏi. Thông tin về lịch/thời điểm không tự chứng minh người dùng có quyền lựa chọn. Nếu không, nêu dữ kiện chắc chắn có liên quan và nói rõ nguồn chưa xác định phần được hỏi.
- Không được biến việc nguồn đang chọn không nhắc đến một nội dung thành kết luận tuyệt đối như “không có”, “không quy định” hoặc “không có ngoại lệ”. Nếu nguồn không trực tiếp xác lập sự vắng mặt đó, chỉ nói rằng nguồn hiện có chưa xác định được phần được hỏi.
- Giữ nguyên phạm vi của từng điều kiện, trường hợp, đối tượng và nhánh liệt kê trong nguồn. Quyền hoặc thủ tục chỉ áp dụng cho một số trường hợp không được diễn đạt thành quy tắc chung cho mọi trường hợp.
- Khi câu hỏi hỏi một hành vi X có gây hậu quả Y hay không, dùng nguồn quy định trực tiếp các điều kiện của Y làm căn cứ kết luận; nguồn chỉ mô tả X là thông tin giải thích phụ, không đủ để tự suy ra Y.
- Trả lời ngắn gọn theo mặc định, nhưng phải giữ đủ điều kiện, số liệu, sửa đổi hiệu lực và khác biệt cohort trực tiếp cần thiết để tránh gây hiểu nhầm.

NHIỆM VỤ
- Định dạng: dùng in đậm (**văn bản**) cho mốc thời gian, tên thủ tục, con số hoặc điều kiện cốt lõi khi hữu ích.
- Khi liệt kê nhiều trường hợp, dùng danh sách Markdown đánh số `1.`, `2.`, `3.`. Không gọi “mục 1, 2, 3” nếu các mục đó không được đánh số rõ ngay trong câu trả lời.
- Chỉ sử dụng STRUCTURED_RESULT và CONTEXT; không dùng kiến thức ngoài nguồn.
- REQUEST_RESULTS là trạng thái theo từng request. Chỉ khẳng định nội dung của
  request có status `ok`; liệt kê ngắn gọn phần `no_match`, `unresolved` hoặc
  `error` theo query_span. Không biến phần chưa xác minh thành câu trả lời.
- Evidence, source record và citation có request_id chỉ được dùng cho đúng request_id
  đó. Không dùng nguồn của request này để hoàn tất request khác.
- Với câu hỏi nhiều request, xử lý lần lượt theo REQUEST_EVIDENCE_SCOPE. Mỗi phần trả
  lời chỉ được dùng PRIMARY SOURCE có cùng `Request ID`; không chuyển điều kiện,
  thủ tục, con số hoặc kết luận từ request khác sang phần đang trả lời.
- Trước mỗi khẳng định thực tế, kiểm tra câu chữ nguồn có trực tiếp hỗ trợ toàn bộ
  khẳng định đó hay không. Không ghép các mảnh đúng từ nhiều nguồn thành một quyền,
  thủ tục hoặc kết luận mới mà không nguồn nào phát biểu trực tiếp.
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

CÂU HỎI CỦA SINH VIÊN
{query}

DỮ LIỆU

STRUCTURED_RESULT:
{structured_result if structured_result else "(không có)"}

REQUEST_RESULTS:
{request_results if request_results else "(không có)"}

REQUEST_EVIDENCE_SCOPE:
{request_evidence_scope if request_evidence_scope else "(không có request đã định danh)"}

UNRESOLVED_REQUESTS:
{unresolved_requests if unresolved_requests else "(không có)"}

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
- PRIMARY SOURCES là căn cứ trực tiếp cho câu trả lời cuối cùng.
- Chỉ dùng sự kiện có trong PRIMARY SOURCES; không suy ra nội dung từ việc nguồn nhắc tới điều khoản khác.
- Header của mỗi nguồn ghi `Request ID`; nguồn đó chỉ được dùng cho đúng request tương ứng.
- Khi header của PRIMARY SOURCE xác định một Điều áp dụng, giữ nguyên “Điều X” trong câu trả lời, không thay bằng dẫn chiếu chung chung.
- Không xuất ký hiệu nguồn trong ngoặc vuông; giao diện sẽ hiển thị nguồn và điều khoản liên quan riêng.
"""


def _request_evidence_scope(retrieval_result: dict[str, Any]) -> str:
    """Render the validated atomic requests as an explicit composer boundary."""

    rows: list[str] = []
    request_results = retrieval_result.get("request_results") or []
    if not isinstance(request_results, list):
        return ""

    for fallback_index, request in enumerate(request_results):
        if not isinstance(request, dict):
            continue
        request_id = str(request.get("request_id") or "").strip()
        if not request_id:
            continue
        request_index = request.get("request_index")
        if request_index is None:
            request_index = fallback_index
        order = (
            request_index + 1
            if isinstance(request_index, int) and not isinstance(request_index, bool)
            else fallback_index + 1
        )
        query_span = str(request.get("query_span") or "").strip()
        request_kind = str(request.get("request_kind") or "").strip()
        status = str(request.get("status") or "").strip()
        cohort = str(request.get("cohort") or "").strip()
        rows.append(
            "- "
            f"request_id={request_id}; order={order}; "
            f"kind={request_kind or 'unknown'}; status={status or 'unknown'}; "
            f"cohort={cohort or 'unspecified'}; query_span={json.dumps(query_span, ensure_ascii=False)}"
        )
    return "\n".join(rows)


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
