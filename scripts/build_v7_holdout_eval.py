from __future__ import annotations

import difflib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT / "data" / "eval"
REPORT_DIR = EVAL_DIR / "reports"
DOCSTORE_PATH = ROOT / "data" / "processed" / "chunks" / "all_docstore_items.json"

FINAL_SYSTEM_PATH = EVAL_DIR / "final_system_eval_holdout_v7.json"
FINAL_ROUTER_PATH = EVAL_DIR / "final_router_holdout_v7.json"
FINAL_STRUCTURED_PATH = EVAL_DIR / "final_structured_tool_holdout_v7.json"
FINAL_RAG_PATH = EVAL_DIR / "final_true_rag_holdout_v7.json"
RAGAS_HOLDOUT_PATH = EVAL_DIR / "ragas_judge_holdout_v7.json"
DUPLICATE_REPORT_PATH = REPORT_DIR / "final_holdout_duplicate_check_v7.json"

OUTPUT_NAMES = {
    FINAL_SYSTEM_PATH.name,
    FINAL_ROUTER_PATH.name,
    FINAL_STRUCTURED_PATH.name,
    FINAL_RAG_PATH.name,
    RAGAS_HOLDOUT_PATH.name,
    DUPLICATE_REPORT_PATH.name,
}


def normalize_query(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def iter_queries(value: Any) -> list[str]:
    queries: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "query" and isinstance(item, str):
                queries.append(item)
            elif key in {"cases", "results"} and isinstance(item, list):
                queries.extend(iter_queries(item))
            elif isinstance(item, (dict, list)):
                queries.extend(iter_queries(item))
    elif isinstance(value, list):
        for item in value:
            queries.extend(iter_queries(item))
    return queries


def collect_old_queries() -> list[dict[str, str]]:
    old: list[dict[str, str]] = []
    for path in sorted(EVAL_DIR.rglob("*.json")):
        if path.name in OUTPUT_NAMES or "holdout_v7" in path.name or "final_holdout" in path.name:
            continue
        try:
            data = load_json(path)
        except Exception:
            continue
        for query in iter_queries(data):
            normalized = normalize_query(query)
            if normalized:
                old.append({"path": str(path.relative_to(ROOT)), "query": query, "normalized": normalized})
    return old


def docstore_index() -> dict[str, list[dict[str, Any]]]:
    docs = load_json(DOCSTORE_PATH)
    by_cohort: dict[str, list[dict[str, Any]]] = {}
    for item in docs:
        metadata = item.get("metadata") or {}
        cohort = str(metadata.get("cohort") or item.get("cohort") or "")
        by_cohort.setdefault(cohort, []).append(item)
    return by_cohort


def find_section(
    index: dict[str, list[dict[str, Any]]],
    *,
    cohort: str,
    title_contains: str,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    cohorts = [cohort] if cohort not in {"general", "all"} else sorted(index)
    needle = normalize_query(title_contains)
    for current_cohort in cohorts:
        for item in index.get(current_cohort, []):
            metadata = item.get("metadata") or {}
            title = str(metadata.get("title") or "")
            if needle and needle in normalize_query(title):
                candidates.append(item)
    if not candidates:
        raise ValueError(f"Cannot resolve section: cohort={cohort} title_contains={title_contains!r}")
    item = candidates[0]
    metadata = item.get("metadata") or {}
    parent_section_ids = [
        str((candidate.get("metadata") or {}).get("parent_section_id") or "").strip()
        for candidate in candidates
    ]
    parent_section_ids = [item for item in parent_section_ids if item]
    return {
        "document_id": metadata.get("document_id") or item.get("document_id"),
        "parent_section_id": metadata.get("parent_section_id"),
        "parent_section_ids": parent_section_ids,
        "source_section": metadata.get("title") or metadata.get("source_section"),
        "source_pages": metadata.get("source_pages") or [],
        "cohort": metadata.get("cohort") or item.get("cohort"),
    }


def can_resolve_section(
    index: dict[str, list[dict[str, Any]]],
    *,
    cohort: str,
    title_contains: str,
) -> bool:
    try:
        find_section(index, cohort=cohort, title_contains=title_contains)
    except ValueError:
        return False
    return True


STRUCTURED_CASES: list[dict[str, Any]] = [
    {
        "id": "holdout_struct_program_cntt_k50",
        "category": "program_lookup",
        "query": "Ở khóa 50, khoa Công nghệ Thông tin đào tạo những ngành nào vậy?",
        "cohort": "K50",
        "expected_status": "answered",
        "expected_llm_called": False,
        "expected_intent": "faculty_query",
        "expected_strategy": "program_lookup",
        "expected_lookup_type": "program_directory",
        "expected_structured_items_include": ["Công nghệ Thông tin", "Sư phạm Tin học"],
        "expected_structured_items_exclude": ["Công nghệ Giáo dục"],
        "expected_citation_cohort": "K50",
        "expected_citation_content_types": ["program_directory"],
        "eval_type": "structured",
        "content_type": "program_directory",
    },
    {
        "id": "holdout_struct_program_cntt_k51",
        "category": "program_lookup",
        "query": "Khóa 51 bên CNTT có thêm ngành nào so với các khóa trước?",
        "cohort": "K51",
        "expected_status": "answered",
        "expected_llm_called": False,
        "expected_intent": "faculty_query",
        "expected_strategy": "program_lookup",
        "expected_lookup_type": "program_directory",
        "expected_structured_items_include": ["Công nghệ Giáo dục", "Công nghệ Thông tin", "Sư phạm Tin học"],
        "expected_citation_cohort": "K51",
        "expected_citation_content_types": ["program_directory"],
        "eval_type": "structured",
        "content_type": "program_directory",
    },
    {
        "id": "holdout_struct_program_school_k48_count",
        "category": "program_lookup",
        "query": "Danh mục ngành áp dụng cho K48-K49 gồm bao nhiêu ngành?",
        "cohort": "K48-K49",
        "expected_status": "answered",
        "expected_llm_called": False,
        "expected_intent": "faculty_query",
        "expected_strategy": "program_lookup",
        "expected_lookup_type": "program_directory",
        "min_structured_items": 42,
        "max_structured_items": 42,
        "expected_structured_items_exclude": ["Toán ứng dụng", "Công nghệ Giáo dục"],
        "expected_citation_cohort": "K48-K49",
        "eval_type": "structured",
        "content_type": "program_directory",
    },
    {
        "id": "holdout_struct_program_school_k51_count",
        "category": "program_lookup",
        "query": "Nếu chọn khóa 51 thì trường đang có tổng cộng mấy ngành đào tạo?",
        "cohort": "K51",
        "expected_status": "answered",
        "expected_llm_called": False,
        "expected_intent": "faculty_query",
        "expected_strategy": "program_lookup",
        "expected_lookup_type": "program_directory",
        "min_structured_items": 44,
        "max_structured_items": 44,
        "expected_structured_items_include": ["Toán ứng dụng", "Công nghệ Giáo dục"],
        "expected_citation_cohort": "K51",
        "eval_type": "structured",
        "content_type": "program_directory",
    },
    {
        "id": "holdout_struct_program_faculty_history_geo",
        "category": "program_lookup",
        "query": "Ai phụ trách ngành Sư phạm Lịch sử - Địa lý trong danh mục ngành?",
        "cohort": "K51",
        "expected_status": "answered",
        "expected_llm_called": False,
        "expected_intent": "faculty_query",
        "expected_strategy": "program_lookup",
        "expected_lookup_type": "program_directory",
        "expected_answer_contains": ["Khoa Địa lý"],
        "expected_structured_items_include": ["Sư phạm Lịch sử"],
        "expected_citation_content_types": ["program_directory"],
        "eval_type": "structured",
        "content_type": "program_directory",
    },
    {
        "id": "holdout_struct_program_faculty_sp_cong_nghe",
        "category": "program_lookup",
        "query": "Sư phạm Công nghệ do khoa nào phụ trách?",
        "cohort": "K51",
        "expected_status": "answered",
        "expected_llm_called": False,
        "expected_intent": "faculty_query",
        "expected_strategy": "program_lookup",
        "expected_lookup_type": "program_directory",
        "expected_answer_contains": ["Khoa Vật lý"],
        "expected_structured_items_include": ["Sư phạm Công nghệ"],
        "eval_type": "structured",
        "content_type": "program_directory",
    },
    {
        "id": "holdout_struct_score_k50_d",
        "category": "scoring_lookup",
        "query": "K50 bị điểm D thì môn đó có được tính là đạt không?",
        "cohort": "K50",
        "expected_status": "answered",
        "expected_llm_called": False,
        "expected_intent": "score_lookup_query",
        "expected_strategy": "structured_lookup",
        "expected_lookup_type": "grade_10_to_letter",
        "expected_answer_contains": ["D", "1.0"],
        "eval_type": "structured",
        "content_type": "scoring_tables",
    },
    {
        "id": "holdout_struct_score_k51_dplus",
        "category": "scoring_lookup",
        "query": "K51 điểm D+ có qua học phần không?",
        "cohort": "K51",
        "expected_status": "answered",
        "expected_llm_called": False,
        "expected_intent": "score_lookup_query",
        "expected_strategy": "structured_lookup",
        "expected_lookup_type": "grade_10_to_letter",
        "expected_answer_contains": ["D+", "1.5"],
        "eval_type": "structured",
        "content_type": "threshold_rules",
    },
    {
        "id": "holdout_struct_score_bplus",
        "category": "scoring_lookup",
        "query": "B+ quy đổi sang thang 4 là bao nhiêu?",
        "cohort": "K48-K49",
        "expected_status": "answered",
        "expected_llm_called": False,
        "expected_intent": "score_lookup_query",
        "expected_strategy": "structured_lookup",
        "expected_lookup_type": "letter_to_grade_4",
        "expected_answer_contains": ["B+", "3.5"],
        "eval_type": "structured",
        "content_type": "scoring_tables",
    },
    {
        "id": "holdout_struct_score_f_retake",
        "category": "scoring_lookup",
        "query": "Nếu học phần bị F thì hệ thống tính như thế nào?",
        "cohort": "K50",
        "expected_status": "answered",
        "expected_llm_called": False,
        "expected_intent": "score_lookup_query",
        "expected_strategy": "structured_lookup",
        "expected_lookup_type": "letter_to_grade_4",
        "expected_answer_contains": ["F", "0.0"],
        "eval_type": "structured",
        "content_type": "scoring_tables",
    },
    {
        "id": "holdout_struct_form_certificate",
        "category": "form_lookup",
        "query": "Nếu cần giấy xác nhận đang là sinh viên thì nên mở mục biểu mẫu nào?",
        "cohort": "K51",
        "expected_status": "answered",
        "expected_llm_called": False,
        "expected_intent": "form_query",
        "expected_strategy": "form_lookup",
        "expected_lookup_type": "form_template",
        "expected_answer_contains": ["Biểu mẫu"],
        "eval_type": "structured",
        "content_type": "form_templates",
    },
    {
        "id": "holdout_struct_office_ctcthssv_email",
        "category": "office_lookup",
        "query": "Email liên hệ Phòng CTCT&HSSV là gì?",
        "cohort": "K51",
        "expected_status": "answered",
        "expected_llm_called": False,
        "expected_intent": "office_query",
        "expected_strategy": "office_lookup",
        "expected_lookup_type": "office_directory",
        "expected_answer_contains": ["hopthusinhvien@hcmue.edu.vn"],
        "eval_type": "structured",
        "content_type": "office_directory",
    },
    {
        "id": "holdout_struct_office_khao_thi",
        "category": "office_lookup",
        "query": "Các việc liên quan đến khảo thí và đảm bảo chất lượng nên hỏi phòng nào?",
        "cohort": "K50",
        "expected_status": "answered",
        "expected_llm_called": False,
        "expected_intent": "office_query",
        "expected_strategy": "office_lookup",
        "expected_lookup_type": "office_directory",
        "expected_structured_items_include": ["Khảo thí"],
        "eval_type": "structured",
        "content_type": "office_directory",
    },
    {
        "id": "holdout_struct_office_ktx",
        "category": "office_lookup",
        "query": "Ký túc xá có thể hỏi thông tin ở đơn vị nào?",
        "cohort": "K48-K49",
        "expected_status": "answered",
        "expected_llm_called": False,
        "expected_intent": "office_query",
        "expected_strategy": "office_lookup",
        "expected_lookup_type": "office_directory",
        "expected_structured_items_include": ["Ký túc xá"],
        "eval_type": "structured",
        "content_type": "office_directory",
    },
    {
        "id": "holdout_struct_office_student_account",
        "category": "office_lookup",
        "query": "Tài khoản sinh viên trên hệ thống phần mềm bị lỗi thì nên hỏi đơn vị nào?",
        "cohort": "K48-K49",
        "expected_status": "answered",
        "expected_llm_called": False,
        "expected_intent": "office_query",
        "expected_strategy": "office_lookup",
        "expected_lookup_type": "office_directory",
        "expected_structured_items_include": ["Công nghệ Thông tin"],
        "eval_type": "structured",
        "content_type": "office_directory",
    },
    {
        "id": "holdout_struct_guardrail_weather",
        "category": "guardrail",
        "query": "Ngày mai ở quận 5 có mưa không?",
        "cohort": "K51",
        "expected_status": "out_of_domain",
        "expected_llm_called": False,
        "expected_intent": "out_of_domain",
        "expected_strategy": "none",
        "eval_type": "structured",
        "content_type": "guardrail",
    },
]


REGULATION_BLUEPRINTS: list[dict[str, Any]] = [
    {
        "key": "scholarship_standard",
        "title_contains": "Tiêu chuẩn, mức, quỹ học bổng khuyến khích học tập",
        "tags": ["numeric_fact", "table_heavy", "citation_required"],
        "ground_truth": "Học bổng khuyến khích học tập yêu cầu sinh viên chính quy trong kế hoạch khóa học, kết quả học tập và rèn luyện từ khá trở lên, không bị kỷ luật từ khiển trách trở lên; học kỳ phải tích lũy tối thiểu 15 tín chỉ theo kế hoạch và các tín chỉ đều đạt.",
        "queries": [
            "Để được xét học bổng khuyến khích học tập thì một học kỳ phải tích lũy điều kiện gì?",
            "Khi xét học bổng KKHT, mốc tín chỉ tối thiểu trong học kỳ được quy định ra sao?",
            "Sinh viên muốn xét học bổng khuyến khích học tập cần đáp ứng những tiêu chuẩn chính nào?",
            "Nếu học kỳ chỉ đăng ký ít tín chỉ thì điều kiện học bổng KKHT được hiểu ra sao?",
        ],
    },
    {
        "key": "scholarship_amount",
        "title_contains": "Tiêu chuẩn, mức, quỹ học bổng khuyến khích học tập",
        "tags": ["numeric_fact", "citation_required"],
        "ground_truth": "Mức học bổng được tính theo số tín chỉ, định mức học phí một tín chỉ và hệ số theo loại: khá 1.0, giỏi 1.25, xuất sắc 1.5; quỹ học bổng bố trí tối thiểu bằng 8% nguồn thu học phí và cấp bù học phí.",
        "queries": [
            "Mức học bổng loại khá, giỏi, xuất sắc được tính theo hệ số nào?",
            "Quỹ học bổng khuyến khích học tập tối thiểu được bố trí theo tỷ lệ bao nhiêu?",
            "Công thức mức học bổng KKHT trong sổ tay đang dựa trên những thành phần nào?",
        ],
    },
    {
        "key": "graduation_rounds",
        "title_contains": "Công nhận tốt nghiệp và cấp bằng tốt nghiệp",
        "tags": ["numeric_fact", "table_heavy", "citation_required"],
        "ground_truth": "Sinh viên chính quy có 03 đợt xét tốt nghiệp chính thức, thường vào tháng 5, tháng 8 và tháng 10. Sinh viên vừa làm vừa học có 05 đợt, thường vào tháng 3, 5, 8, 10 và 12.",
        "queries": [
            "Trong năm trường thường tổ chức xét tốt nghiệp chính quy vào các tháng nào?",
            "Sinh viên chính quy có bao nhiêu đợt xét tốt nghiệp chính thức?",
            "Hệ vừa làm vừa học được xét tốt nghiệp chính thức mấy đợt mỗi năm?",
            "Các mốc tháng xét tốt nghiệp của chính quy và vừa làm vừa học khác nhau thế nào?",
        ],
    },
    {
        "key": "graduation_conditions",
        "title_contains": "Công nhận tốt nghiệp và cấp bằng tốt nghiệp",
        "tags": ["citation_required"],
        "ground_truth": "Điều kiện công nhận tốt nghiệp gồm tích lũy đủ học phần/số tín chỉ và nội dung bắt buộc theo CTĐT, đạt chuẩn đầu ra, điểm trung bình tích lũy toàn khóa từ trung bình trở lên, và tại thời điểm xét không bị truy cứu trách nhiệm hình sự hoặc kỷ luật đình chỉ học tập.",
        "queries": [
            "Khi xét công nhận tốt nghiệp, sinh viên cần thỏa những nhóm điều kiện nào?",
            "Muốn được cấp bằng tốt nghiệp thì ngoài tín chỉ còn cần điều kiện gì?",
            "Điểm trung bình toàn khóa có vai trò gì trong điều kiện tốt nghiệp?",
        ],
    },
    {
        "key": "study_duration",
        "title_contains": "Chương trình đào tạo và thời gian học tập",
        "tags": ["numeric_fact", "table_heavy", "citation_required"],
        "ground_truth": "Đào tạo đại học cấp bằng thứ nhất hệ chính quy có thời gian chuẩn 4 năm học và tối đa 8 năm học; hình thức vừa làm vừa học có thời gian chuẩn 5 năm học và tối đa 9 năm học.",
        "queries": [
            "Học đại học chính quy cấp bằng thứ nhất được học tối đa bao lâu?",
            "Thời gian chuẩn và tối đa của chương trình đại học chính quy là mấy năm?",
            "Hệ vừa làm vừa học cấp bằng thứ nhất có thời gian học tối đa bao nhiêu năm?",
            "Bảng thời gian học tập quy định mốc tối đa thế nào cho hệ chính quy?",
        ],
    },
    {
        "key": "academic_warning_regular",
        "title_contains": "Xử lý kết quả học tập đối với hình thức đào tạo chính quy",
        "tags": ["numeric_fact", "cohort_sensitive", "citation_required"],
        "ground_truth": "Sinh viên chính quy bị cảnh báo học tập nếu tín chỉ không đạt vượt 50% khối lượng đăng ký hoặc nợ đọng vượt 24 tín chỉ; điểm trung bình học kỳ dưới 0,8 ở học kỳ đầu hoặc dưới 1,0 ở các học kỳ sau; hoặc điểm trung bình tích lũy dưới ngưỡng theo năm học.",
        "queries": [
            "Hệ chính quy bị cảnh báo học tập khi rơi vào các trường hợp nào?",
            "Nếu nợ tín chỉ quá nhiều thì điều kiện cảnh báo học tập được quy định ra sao?",
            "Ngưỡng điểm trung bình học kỳ nào khiến sinh viên chính quy bị cảnh báo?",
        ],
    },
    {
        "key": "forced_withdraw_regular",
        "title_contains": "Xử lý kết quả học tập đối với hình thức đào tạo chính quy",
        "tags": ["numeric_fact", "cohort_sensitive", "citation_required"],
        "ground_truth": "Sinh viên chính quy bị buộc thôi học nếu bị cảnh báo học tập 03 lần liên tiếp trong một khóa học, bị cảnh báo đến lần thứ tư tính từ đầu khóa, hoặc thời gian học tập vượt quá giới hạn tối đa.",
        "queries": [
            "Chính quy bị buộc thôi học sau bao nhiêu lần cảnh báo học tập?",
            "Cảnh báo học tập đến mức nào thì sinh viên chính quy có thể bị buộc thôi học?",
            "Ngoài cảnh báo học tập, trường hợp nào khác có thể dẫn đến buộc thôi học?",
        ],
    },
    {
        "key": "warning_part_time",
        "title_contains": "Xử lý kết quả học tập đối với hình thức đào tạo vừa làm",
        "tags": ["numeric_fact", "citation_required"],
        "ground_truth": "Hình thức vừa làm vừa học bị cảnh báo nếu điểm trung bình tích lũy dưới ngưỡng theo năm học hoặc tổng tín chỉ nợ đọng từ đầu khóa vượt quá 24; bị buộc thôi học nếu cảnh báo 02 lần liên tiếp hoặc 03 lần không liên tiếp trong một khóa học, hoặc vượt thời gian tối đa.",
        "queries": [
            "Hệ vừa làm vừa học bị cảnh báo hoặc buộc thôi học theo các mốc nào?",
            "Vừa làm vừa học bị buộc thôi học sau mấy lần cảnh báo?",
            "Tín chỉ nợ đọng của hệ vừa làm vừa học vượt mức nào thì bị cảnh báo?",
        ],
    },
    {
        "key": "temporary_leave",
        "title_contains": "Nghỉ học tạm thời, tiếp nhận trở lại học và cho thôi học",
        "tags": ["citation_required"],
        "ground_truth": "Sinh viên được xem xét nghỉ học tạm thời trong các trường hợp như được điều động vào lực lượng vũ trang, ốm đau/tai nạn/thai sản có xác nhận y tế, hoặc vì lý do cá nhân khi đã học tối thiểu một học kỳ và không thuộc diện buộc thôi học/cảnh báo ở mức cần xử lý theo quy định.",
        "queries": [
            "Trường hợp nào sinh viên được xin nghỉ học tạm thời?",
            "Nghỉ học tạm thời vì lý do cá nhân cần lưu ý điều kiện gì?",
            "Sau khi tạm nghỉ thì việc tiếp nhận trở lại học được căn cứ theo đâu?",
        ],
    },
    {
        "key": "transfer_major",
        "title_contains": "Chuyển ngành, chuyển nơi học, chuyển cơ sở đào tạo",
        "tags": ["citation_required"],
        "ground_truth": "Việc chuyển ngành, chuyển nơi học hoặc chuyển cơ sở đào tạo phải đáp ứng điều kiện theo quy chế, phụ thuộc chương trình, năng lực tiếp nhận và không thuộc các trường hợp không được phép; sinh viên cần thực hiện theo thủ tục do Trường quy định.",
        "queries": [
            "Muốn chuyển ngành thì sổ tay nêu những nguyên tắc điều kiện nào?",
            "Chuyển nơi học hoặc chuyển cơ sở đào tạo được xem xét theo các yếu tố nào?",
            "Sinh viên có thể tự ý chuyển ngành hay phải theo quy trình của trường?",
        ],
    },
    {
        "key": "two_programs",
        "title_contains": "Học cùng lúc hai chương trình",
        "tags": ["citation_required"],
        "ground_truth": "Sinh viên học cùng lúc hai chương trình phải đáp ứng điều kiện học lực và tiến độ theo quy định; nếu không đáp ứng điều kiện trong quá trình học thì phải dừng học chương trình thứ hai.",
        "queries": [
            "Học song song hai chương trình cần đáp ứng điều kiện gì?",
            "Khi nào sinh viên phải dừng học chương trình thứ hai?",
            "Quy định học cùng lúc hai chương trình nhấn mạnh những yêu cầu nào?",
        ],
    },
    {
        "key": "credit_transfer",
        "title_contains": "Công nhận kết quả học tập và chuyển đổi tín chỉ",
        "tags": ["citation_required"],
        "ground_truth": "Kết quả học tập và tín chỉ có thể được xem xét công nhận, chuyển đổi theo quy định của Trường trên cơ sở nội dung, khối lượng, chuẩn đầu ra và điều kiện tương đương của học phần/chương trình.",
        "queries": [
            "Chuyển đổi tín chỉ được xét dựa trên những yếu tố nào?",
            "Học phần đã tích lũy ở nơi khác có thể được công nhận ra sao?",
            "Công nhận kết quả học tập có phải tự động hay cần xét theo quy định?",
        ],
    },
    {
        "key": "student_duties",
        "title_contains": "Nhiệm vụ của sinh viên",
        "tags": ["citation_required"],
        "ground_truth": "Sinh viên có nhiệm vụ chấp hành chủ trương, pháp luật, quy chế của Bộ và Trường; học tập, rèn luyện; giữ gìn phẩm chất, đoàn kết; đóng học phí và thực hiện nghĩa vụ theo quy định.",
        "queries": [
            "Sổ tay quy định sinh viên có những nhiệm vụ chính nào?",
            "Ngoài học tập, sinh viên phải chấp hành những nghĩa vụ gì?",
            "Nhiệm vụ của sinh viên liên quan đến rèn luyện và nội quy được nêu thế nào?",
        ],
    },
    {
        "key": "student_rights",
        "title_contains": "Quyền của sinh viên",
        "tags": ["citation_required"],
        "ground_truth": "Sinh viên có các quyền liên quan đến học tập, nghiên cứu, tham gia hoạt động, được cung cấp thông tin, được hưởng chính sách, được góp ý/khiếu nại theo quy định và được bảo đảm quyền lợi hợp pháp.",
        "queries": [
            "Sinh viên có những quyền lợi chính nào trong sổ tay?",
            "Quyền của sinh viên về thông tin, chính sách và khiếu nại được hiểu thế nào?",
            "Sinh viên được tham gia và được hỗ trợ những hoạt động gì?",
        ],
    },
    {
        "key": "forbidden_behaviors",
        "title_contains": "Các hành vi sinh viên không được làm",
        "tags": ["citation_required"],
        "ground_truth": "Sinh viên không được có các hành vi vi phạm pháp luật, gian lận, gây rối, xúc phạm danh dự nhân phẩm, sử dụng chất cấm hoặc các hành vi bị cấm khác theo quy định của Trường và pháp luật.",
        "queries": [
            "Những hành vi nào sinh viên bị cấm trong sổ tay?",
            "Sổ tay nêu các nhóm việc sinh viên không được làm ra sao?",
            "Gian lận hoặc gây rối có nằm trong nhóm hành vi bị cấm không?",
        ],
    },
    {
        "key": "discipline_forms",
        "title_contains": "Hình thức kỷ luật và nội dung vi phạm",
        "tags": ["citation_required"],
        "ground_truth": "Kỷ luật sinh viên có các hình thức như khiển trách, cảnh cáo, đình chỉ học tập có thời hạn và buộc thôi học; nội dung vi phạm được xem xét theo mức độ và quy định liên quan.",
        "queries": [
            "Các hình thức kỷ luật sinh viên gồm những mức nào?",
            "Khi vi phạm nội quy, sinh viên có thể bị xử lý kỷ luật theo các hình thức nào?",
            "Đình chỉ học tập và buộc thôi học nằm trong nhóm xử lý kỷ luật nào?",
        ],
    },
    {
        "key": "discipline_process",
        "title_contains": "Trình tự, thủ tục và hồ sơ xét kỷ luật",
        "tags": ["citation_required"],
        "ground_truth": "Việc xét kỷ luật thực hiện theo trình tự, thủ tục và hồ sơ quy định; có xem xét hành vi vi phạm, báo cáo/biên bản, ý kiến của sinh viên và quyết định của cấp có thẩm quyền.",
        "queries": [
            "Quy trình xét kỷ luật sinh viên cần những bước/hồ sơ gì?",
            "Khi bị xem xét kỷ luật, hồ sơ xử lý thường dựa vào những tài liệu nào?",
            "Trình tự xét kỷ luật có phải do cá nhân tự quyết hay theo hội đồng/quy định?",
        ],
    },
    {
        "key": "discipline_appeal",
        "title_contains": "Quyền khiếu nại về khen thưởng, kỷ luật",
        "tags": ["citation_required"],
        "ground_truth": "Sinh viên có quyền khiếu nại về khen thưởng, kỷ luật theo quy định; việc khiếu nại được thực hiện đến cơ quan/đơn vị có thẩm quyền và theo trình tự được nêu trong quy định.",
        "queries": [
            "Nếu không đồng ý với quyết định kỷ luật thì sinh viên có quyền gì?",
            "Quyền khiếu nại về khen thưởng, kỷ luật được nêu như thế nào?",
            "Sinh viên có thể phản ánh quyết định khen thưởng hoặc kỷ luật không?",
        ],
    },
    {
        "key": "training_method",
        "title_contains": "Phương thức tổ chức đào tạo",
        "tags": ["citation_required"],
        "ground_truth": "Đào tạo được tổ chức theo tín chỉ, năm học gồm các học kỳ chính và có thể có học kỳ phụ; sinh viên đăng ký học tập theo kế hoạch và quy định của Trường.",
        "queries": [
            "Phương thức tổ chức đào tạo theo tín chỉ được mô tả thế nào?",
            "Năm học và học kỳ trong phương thức đào tạo được tổ chức ra sao?",
            "Sinh viên học theo tín chỉ thì việc học tập được quản lý theo nguyên tắc nào?",
        ],
    },
    {
        "key": "teaching_plan",
        "title_contains": "Kế hoạch giảng dạy và học tập",
        "tags": ["citation_required"],
        "ground_truth": "Kế hoạch giảng dạy và học tập được xây dựng, công bố để sinh viên đăng ký học phần, theo dõi tiến độ và thực hiện CTĐT theo quy định của Trường.",
        "queries": [
            "Kế hoạch giảng dạy và học tập có vai trò gì với sinh viên?",
            "Sinh viên dựa vào đâu để đăng ký học phần theo tiến độ?",
            "Kế hoạch học tập của trường được dùng để quản lý những việc gì?",
        ],
    },
    {
        "key": "register_learning",
        "title_contains": "Tổ chức đăng ký học tập",
        "tags": ["citation_required"],
        "ground_truth": "Đăng ký học tập được tổ chức theo kế hoạch của Trường; sinh viên phải đăng ký học phần đúng thời hạn, đúng điều kiện tiên quyết và chịu trách nhiệm với kết quả đăng ký.",
        "queries": [
            "Đăng ký học phần cần tuân thủ những nguyên tắc nào?",
            "Sinh viên có trách nhiệm gì khi đăng ký học tập?",
            "Việc đăng ký học tập có liên quan đến điều kiện học phần tiên quyết không?",
        ],
    },
    {
        "key": "course_assessment",
        "title_contains": "Đánh giá và tính điểm học phần",
        "tags": ["citation_required"],
        "ground_truth": "Đánh giá học phần gồm các điểm thành phần và điểm thi/kết thúc học phần theo đề cương; điểm học phần được tính từ các thành phần đánh giá và quy đổi theo thang điểm/chữ theo quy định.",
        "queries": [
            "Điểm học phần được đánh giá từ những thành phần nào?",
            "Việc tính điểm học phần căn cứ vào đâu?",
            "Đánh giá học phần có bao gồm điểm quá trình và điểm kết thúc học phần không?",
        ],
    },
    {
        "key": "semester_result",
        "title_contains": "Đánh giá kết quả học tập theo học kỳ, năm học",
        "tags": ["citation_required"],
        "ground_truth": "Kết quả học tập theo học kỳ/năm học được đánh giá bằng các chỉ số như số tín chỉ tích lũy, điểm trung bình học kỳ/năm học và điểm trung bình tích lũy theo quy định.",
        "queries": [
            "Kết quả học tập theo học kỳ được đánh giá bằng những chỉ số nào?",
            "Điểm trung bình học kỳ và tín chỉ tích lũy dùng để làm gì?",
            "Khi tổng kết năm học, sổ tay đánh giá kết quả học tập ra sao?",
        ],
    },
    {
        "key": "full_course_result",
        "title_contains": "Đánh giá kết quả học tập theo học kỳ",
        "tags": ["citation_required"],
        "ground_truth": "Kết quả học tập toàn khóa được đánh giá dựa trên điểm trung bình tích lũy toàn khóa, số tín chỉ tích lũy và các điều kiện theo chương trình đào tạo; kết quả này liên quan đến xếp loại và tốt nghiệp.",
        "queries": [
            "Đánh giá kết quả học tập toàn khóa dựa trên những căn cứ nào?",
            "Điểm trung bình tích lũy toàn khóa có ý nghĩa gì?",
            "Kết quả toàn khóa liên quan thế nào đến xếp loại tốt nghiệp?",
        ],
    },
    {
        "key": "graduate_rank_reduction",
        "title_contains": "Công nhận tốt nghiệp và cấp bằng tốt nghiệp",
        "tags": ["numeric_fact", "citation_required"],
        "ground_truth": "Hạng tốt nghiệp loại xuất sắc hoặc giỏi bị giảm một mức nếu khối lượng học phần phải học lại vượt quá 5% tổng số tín chỉ của chương trình hoặc sinh viên đã bị kỷ luật từ mức cảnh cáo trở lên trong thời gian học.",
        "queries": [
            "Trường hợp nào làm hạng tốt nghiệp xuất sắc hoặc giỏi bị giảm một mức?",
            "Nếu học lại quá nhiều tín chỉ thì hạng tốt nghiệp có bị ảnh hưởng không?",
            "Kỷ luật từ mức nào có thể làm giảm hạng tốt nghiệp?",
        ],
    },
    {
        "key": "student_management_system",
        "title_contains": "Hệ thống tổ chức, quản lý công tác sinh viên",
        "tags": ["citation_required"],
        "ground_truth": "Hệ thống tổ chức, quản lý công tác sinh viên gồm các đơn vị và cá nhân liên quan trong Trường như phòng ban, khoa, cố vấn học tập, lớp sinh viên/lớp học phần theo nhiệm vụ được phân công.",
        "queries": [
            "Công tác sinh viên được quản lý qua những cấp/đơn vị nào?",
            "Hệ thống quản lý công tác sinh viên gồm những thành phần chính nào?",
            "Khoa, phòng ban và cố vấn học tập tham gia quản lý sinh viên ra sao?",
        ],
    },
    {
        "key": "academic_advisor",
        "title_contains": "Cố vấn học tập",
        "tags": ["citation_required"],
        "ground_truth": "Cố vấn học tập có nhiệm vụ tư vấn, hướng dẫn sinh viên về học tập, rèn luyện, đăng ký học phần, kế hoạch học tập và phối hợp quản lý lớp sinh viên theo quy định.",
        "queries": [
            "Cố vấn học tập hỗ trợ sinh viên những việc gì?",
            "Khi cần tư vấn kế hoạch học tập thì cố vấn học tập có vai trò gì?",
            "Cố vấn học tập có liên quan đến đăng ký học phần và rèn luyện không?",
        ],
    },
    {
        "key": "conduct_classification",
        "title_contains": "Phân loại kết quả rèn luyện",
        "tags": ["numeric_fact", "citation_required"],
        "ground_truth": "Kết quả rèn luyện được phân loại theo các mức tương ứng với điểm rèn luyện; kết quả này được dùng trong xét học bổng, khen thưởng, kỷ luật và các quyền lợi liên quan.",
        "queries": [
            "Kết quả rèn luyện được phân loại thành những mức nào?",
            "Điểm rèn luyện ảnh hưởng đến các quyền lợi nào của sinh viên?",
            "Xếp loại rèn luyện có liên quan đến học bổng không?",
        ],
    },
    {
        "key": "conduct_process",
        "title_contains": "Quy trình đánh giá kết quả rèn luyện sinh viên",
        "tags": ["citation_required"],
        "ground_truth": "Quy trình đánh giá rèn luyện gồm các bước sinh viên tự đánh giá, lớp/khoa/đơn vị xem xét, hội đồng đánh giá và công bố/khiếu nại theo thời gian quy định.",
        "queries": [
            "Quy trình đánh giá điểm rèn luyện được thực hiện qua những bước nào?",
            "Sinh viên có tự đánh giá rèn luyện trước khi đơn vị xét không?",
            "Việc công bố và khiếu nại kết quả rèn luyện diễn ra theo quy trình nào?",
        ],
    },
    {
        "key": "research_rights",
        "title_contains": "Quyền lợi và trách nhiệm của sinh viên tham gia NCKH",
        "tags": ["citation_required"],
        "ground_truth": "Sinh viên tham gia nghiên cứu khoa học có quyền lợi và trách nhiệm theo quy định, bao gồm thực hiện đề tài nghiêm túc, tuân thủ yêu cầu chuyên môn, được hỗ trợ/hướng dẫn và được xem xét khen thưởng hoặc công nhận kết quả nếu đáp ứng điều kiện.",
        "queries": [
            "Sinh viên tham gia nghiên cứu khoa học có quyền lợi và trách nhiệm gì?",
            "Khi làm NCKH, sinh viên cần tuân thủ những yêu cầu nào?",
            "Kết quả NCKH của sinh viên có thể được công nhận hoặc khen thưởng không?",
        ],
    },
    {
        "key": "tuition_support_refund",
        "title_contains": "Bồi hoàn kinh phí hỗ trợ",
        "tags": ["citation_required"],
        "ground_truth": "Người học thuộc diện hỗ trợ chi phí đào tạo có thể phải bồi hoàn kinh phí nếu thuộc trường hợp phải hoàn trả theo quy định; việc bồi hoàn căn cứ vào thời gian, mức hỗ trợ và trách nhiệm của người học.",
        "queries": [
            "Khi nào người học phải bồi hoàn kinh phí hỗ trợ?",
            "Bồi hoàn kinh phí hỗ trợ được hiểu theo nguyên tắc nào?",
            "Nếu không thực hiện đúng cam kết hỗ trợ đào tạo thì trách nhiệm bồi hoàn ra sao?",
        ],
    },
]


def regulation_case(
    index: dict[str, list[dict[str, Any]]],
    *,
    case_id: str,
    blueprint: dict[str, Any],
    query: str,
    cohort: str,
    ragas: bool = False,
) -> dict[str, Any]:
    section = find_section(index, cohort=cohort, title_contains=blueprint["title_contains"])
    case = {
        "id": case_id,
        "query": f"{cohort}: {query}" if cohort != "general" else query,
        "cohort": cohort,
        "expected_cohort": None if cohort == "general" else cohort,
        "eval_type": "true_rag",
        "content_type": "regulation_sections",
        "expected_content_types": ["regulation"],
        "expected_intent": "regulation_query",
        "expected_strategy": "semantic_filtered",
        "expected_source_sections": [section["source_section"]],
        "expected_parent_section_ids": section["parent_section_ids"]
        if cohort == "general"
        else [section["parent_section_id"]],
        "tags": sorted(set(["true_rag", *blueprint.get("tags", [])])),
    }
    if cohort != "general":
        case["expected_document_id"] = section["document_id"]
        case["expected_source_pages"] = section["source_pages"]
    if ragas:
        case.update(
            {
                "eval_bucket": "true_rag",
                "ground_truth": blueprint["ground_truth"],
                "judge_metrics": [
                    "faithfulness",
                    "answer_relevancy",
                    "context_precision",
                    "context_recall",
                    "answer_correctness",
                    "citation_correctness",
                ],
            }
        )
    return case


def build_regulation_cases(
    index: dict[str, list[dict[str, Any]]],
    *,
    total: int,
    ragas: bool,
    prefix: str,
) -> list[dict[str, Any]]:
    cohorts = ["K48-K49", "K50", "K51", "general"]
    cases: list[dict[str, Any]] = []
    query_cursor = 0
    for blueprint in REGULATION_BLUEPRINTS:
        for query in blueprint["queries"]:
            start = (len(cases) + query_cursor) % len(cohorts)
            rotated_cohorts = cohorts[start:] + cohorts[:start]
            cohort = next(
                (
                    candidate
                    for candidate in rotated_cohorts
                    if can_resolve_section(
                        index,
                        cohort=candidate,
                        title_contains=blueprint["title_contains"],
                    )
                ),
                "general",
            )
            cases.append(
                regulation_case(
                    index,
                    case_id=f"{prefix}_{len(cases)+1:03d}",
                    blueprint=blueprint,
                    query=query,
                    cohort=cohort,
                    ragas=ragas,
                )
            )
            if len(cases) >= total:
                return cases
        query_cursor += 1

    # If the requested size is larger than the handcrafted query pool, create
    # conservative paraphrases from existing blueprints while keeping source
    # expectations tied to the same resolved section.
    while len(cases) < total:
        blueprint = REGULATION_BLUEPRINTS[len(cases) % len(REGULATION_BLUEPRINTS)]
        start = len(cases) % len(cohorts)
        rotated_cohorts = cohorts[start:] + cohorts[:start]
        cohort = next(
            (
                candidate
                for candidate in rotated_cohorts
                if can_resolve_section(
                    index,
                    cohort=candidate,
                    title_contains=blueprint["title_contains"],
                )
            ),
            "general",
        )
        query = f"Cho mình hỏi rõ hơn về quy định liên quan đến {blueprint['title_contains'].lower()} trong sổ tay?"
        cases.append(
            regulation_case(
                index,
                case_id=f"{prefix}_{len(cases)+1:03d}",
                blueprint=blueprint,
                query=query,
                cohort=cohort,
                ragas=ragas,
            )
        )
    return cases


def build_router_cases(structured: list[dict[str, Any]], rag: list[dict[str, Any]]) -> list[dict[str, Any]]:
    router_cases: list[dict[str, Any]] = []
    for case in structured[:16]:
        router_cases.append(
            {
                "id": f"router_{case['id']}",
                "category": case["category"],
                "query": case["query"],
                "cohort": case.get("cohort", "general"),
                "expected_intent": case["expected_intent"],
                "expected_strategy": case["expected_strategy"],
                "expected_target_chunk_types": None,
            }
        )
    for case in rag[:24]:
        router_cases.append(
            {
                "id": f"router_{case['id']}",
                "category": "regulation_query",
                "query": case["query"],
                "cohort": case.get("cohort", "general"),
                "expected_intent": "regulation_query",
                "expected_strategy": "semantic_filtered",
                "expected_target_chunk_types": ["regulation"],
            }
        )
    return router_cases


def duplicate_report(new_cases: list[dict[str, Any]], old_queries: list[dict[str, str]]) -> dict[str, Any]:
    old_norms = [(item["normalized"], item) for item in old_queries]
    new_norms: dict[str, str] = {}
    internal_duplicates: list[dict[str, Any]] = []
    exact_old_duplicates: list[dict[str, Any]] = []
    near_old_duplicates: list[dict[str, Any]] = []

    for case in new_cases:
        normalized = normalize_query(case["query"])
        if normalized in new_norms:
            internal_duplicates.append(
                {"id": case["id"], "query": case["query"], "duplicate_of": new_norms[normalized]}
            )
        else:
            new_norms[normalized] = case["id"]
        for old_norm, old in old_norms:
            if normalized == old_norm:
                exact_old_duplicates.append(
                    {
                        "id": case["id"],
                        "query": case["query"],
                        "old_path": old["path"],
                        "old_query": old["query"],
                    }
                )
                break
        best_ratio = 0.0
        best_old: dict[str, str] | None = None
        for old_norm, old in old_norms:
            ratio = difflib.SequenceMatcher(None, normalized, old_norm).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_old = old
        if best_old and best_ratio >= 0.92:
            near_old_duplicates.append(
                {
                    "id": case["id"],
                    "query": case["query"],
                    "similarity": round(best_ratio, 4),
                    "old_path": best_old["path"],
                    "old_query": best_old["query"],
                }
            )

    return {
        "new_cases": len(new_cases),
        "old_queries_scanned": len(old_queries),
        "internal_duplicate_count": len(internal_duplicates),
        "exact_old_duplicate_count": len(exact_old_duplicates),
        "near_old_duplicate_count_threshold_0_92": len(near_old_duplicates),
        "internal_duplicates": internal_duplicates,
        "exact_old_duplicates": exact_old_duplicates,
        "near_old_duplicates": near_old_duplicates[:100],
    }


def main() -> None:
    index = docstore_index()
    true_rag_cases = build_regulation_cases(index, total=84, ragas=False, prefix="holdout_rag")
    final_system = [*STRUCTURED_CASES, *true_rag_cases]
    final_system = final_system[:100]

    structured = [case for case in final_system if case.get("eval_type") == "structured"]
    true_rag = [case for case in final_system if case.get("eval_type") == "true_rag"]
    router_cases = build_router_cases(structured, true_rag)
    ragas_cases = build_regulation_cases(index, total=100, ragas=True, prefix="holdout_ragas")

    save_json(final_system, FINAL_SYSTEM_PATH)
    save_json(router_cases, FINAL_ROUTER_PATH)
    save_json(structured, FINAL_STRUCTURED_PATH)
    save_json(true_rag, FINAL_RAG_PATH)
    save_json(ragas_cases, RAGAS_HOLDOUT_PATH)

    old_queries = collect_old_queries()
    report = {
        "summary": {
            "final_system_cases": len(final_system),
            "router_cases": len(router_cases),
            "structured_cases": len(structured),
            "true_rag_cases": len(true_rag),
            "ragas_cases": len(ragas_cases),
        },
        "final_system_duplicate_check": duplicate_report(final_system, old_queries),
        "ragas_duplicate_check": duplicate_report(ragas_cases, old_queries),
    }
    save_json(report, DUPLICATE_REPORT_PATH)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Saved duplicate report: {DUPLICATE_REPORT_PATH}")


if __name__ == "__main__":
    main()
