from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "eval" / "architecture_v7"
DOCSTORE = ROOT / "data" / "processed" / "chunks" / "all_docstore_items.json"
TABLES = ROOT / "data" / "processed" / "tables" / "structured_tables_registry.json"
FOREIGN = ROOT / "data" / "processed" / "tables" / "foreign_language_equivalency_table.json"
FORMULAS = ROOT / "data" / "processed" / "tables" / "formula_rules.json"
OFFICES = ROOT / "data" / "processed" / "directories" / "student_office_profiles.json"
FACULTIES = ROOT / "data" / "processed" / "directories" / "student_faculty_profiles.json"
PROGRAMS = ROOT / "data" / "processed" / "directories" / "program_directory.json"
SERVICES = ROOT / "data" / "processed" / "directories" / "student_service_directory.json"
GRAPH = ROOT / "data" / "processed" / "graphs" / "document_edges.json"
V6_RETRIEVAL = ROOT / "data" / "eval" / "architecture_v6_holdout" / "retrieval_cases.json"

COUNTS = {"deterministic": 140, "retrieval": 160, "answers": 150, "production": 60}
COHORTS = ("K48-K49", "K50", "K51")
DETERMINISTIC_CONTRACT = "query-plan-outcome-equivalent-v7"

RETRIEVAL_TARGET_OVERRIDES = {
    "K50_QuyCheCongTacSinhVien_Chuong4_Dieu15": (
        "Ở K50, đơn vị nào phối hợp với các khoa và phân hiệu để định kỳ thu thập ý kiến sinh viên nhằm nâng cao chất lượng đào tạo và phục vụ?",
        "Phòng Khảo thí và Đảm bảo chất lượng phối hợp các khoa và phân hiệu định kỳ tổ chức thu thập ý kiến sinh viên nhằm nâng cao chất lượng đào tạo và phục vụ của Trường.",
    ),
    "K48-K49_K48_49_QuyDinhNghienCuuKhoaHocSinhVien_Chuong1_Dieu4": (
        "Sinh viên K48–K49 công bố kết quả nghiên cứu hoặc đưa kết quả đó vào thực tiễn có được tính là hoạt động nghiên cứu khoa học không?",
        "Có. Công bố kết quả nghiên cứu và ứng dụng kết quả nghiên cứu vào thực tiễn kinh tế – xã hội dưới dạng được công nhận chính thức là một nội dung hoạt động NCKH của sinh viên.",
    ),
    "K50_QuyCheCongTacSinhVien_Chuong6_Dieu38": (
        "Nếu Hiệu trưởng đã xem xét lại quyết định khen thưởng hoặc kỷ luật nhưng sinh viên K50 vẫn thấy chưa thỏa đáng thì còn có thể khiếu nại ở đâu?",
        "Sinh viên có thể khiếu nại lên cấp có thẩm quyền theo quy định của pháp luật về khiếu nại, tố cáo.",
    ),
    "K50_QuyCheDanhGiaKetQuaRenLuyen_Chuong2_Dieu8": (
        "Nhóm tiêu chí rèn luyện về phụ trách lớp, đoàn thể hoặc thành tích đặc biệt của K50 có khung điểm tối đa bao nhiêu?",
        "Khung điểm đánh giá của nhóm tiêu chí này từ 0 đến 10 điểm.",
    ),
    "K48-K49_K48_49_QuyCheCongTacSinhVien_Chuong5_Dieu30": (
        "Sinh viên K48–K49 thuộc diện miễn, giảm học phí hoặc hỗ trợ chi phí học tập phải nộp hồ sơ cho đơn vị nào và vào thời điểm nào?",
        "Sinh viên phải nộp hồ sơ về Phòng Công tác chính trị và Học sinh, sinh viên đúng thời gian được quy định theo từng học kỳ.",
    ),
    "K51_QuyCheCongTacSinhVien_Chuong5_Dieu29": (
        "Chính sách cấp học bổng và hỗ trợ phương tiện học tập cho sinh viên khuyết tật K51 được thực hiện theo những văn bản nào?",
        "Chính sách được thực hiện theo Nghị định 28/2012/NĐ-CP và Thông tư liên tịch 42/2013/TTLT-BGDĐT-BLĐTBXH-BTC.",
    ),
    "K48-K49_K48_49_QuyDinhNghienCuuKhoaHocSinhVien_Chuong2_Dieu9": (
        "K48–K49: kết quả nghiên cứu khoa học của sinh viên được phổ biến và lưu giữ qua những hình thức nào?",
        "Các hình thức gồm xuất bản tập san, thông báo khoa học hoặc kỷ yếu; quản lý và lưu giữ đề tài tại Thư viện; đăng tải kết quả trên trang thông tin điện tử của Trường và các phương tiện thông tin đại chúng khác.",
    ),
}

EQUIVALENT_TARGET_OVERRIDES = {
    "K48-K49_K48_49_QuyCheDanhGiaKetQuaRenLuyen_Chuong2_Dieu6": (
        "Trong cả ba nhóm khóa, hoạt động công ích hoặc tình nguyện có được tính vào nhóm điểm rèn luyện về hoạt động xã hội không, và khung điểm của nhóm này là bao nhiêu?",
        "Có. Ý thức tham gia hoạt động công ích, tình nguyện và công tác xã hội là một tiêu chí của nhóm này; khung điểm đánh giá từ 0 đến 20 điểm.",
    ),
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def stable_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())).strip()


def no_diacritics(value: str) -> str:
    return (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
    )


def slug(value: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", norm(value))).strip("_")


def common_case(
    *,
    case_id: str,
    suite: str,
    query: str,
    cohort: str,
    topic: str,
    expected_path: str,
    case_type: str,
    stress: bool = False,
) -> dict[str, Any]:
    return {
        "id": case_id,
        "suite": suite,
        "case_type": case_type,
        "query": query,
        "cohort": cohort,
        "history": [],
        "tags": ["architecture_v7_draft", case_type, "stress" if stress else "realistic"],
        "topic": topic,
        "question_style": "stress" if stress else "realistic",
        "expected_path": expected_path,
        "expected_intent": "query_plan" if suite == "deterministic" else "regulation_query",
        "expected_strategy": "query_plan_execution" if suite == "deterministic" else "semantic_filtered",
        "cohort_sensitivity": "none" if cohort == "general" else "single_cohort",
        "question_specificity": "specific",
        "expected_answer_behavior": "direct_answer" if expected_path == "structured" else "scoped_summary",
        "eval_split": "stress" if stress else "realistic",
        "near_duplicate_reviewed": False,
        "frozen": False,
        "author_review_state": "draft_pending_owner_review",
    }


def task_gold(
    mode: str,
    *,
    lookup_type: str | None = None,
    required_slot_keys: list[str] | None = None,
    cohorts: list[str] | None = None,
) -> dict[str, Any]:
    value: dict[str, Any] = {"mode": mode}
    if lookup_type:
        value["lookup_type"] = lookup_type
    if required_slot_keys:
        value["required_slot_keys"] = required_slot_keys
    if cohorts:
        value["cohorts"] = cohorts
    return value


def answer_outcome(
    required_tasks: list[dict[str, Any]],
    *,
    name: str = "answer-with-authorized-evidence",
    minimum: int | None = None,
    maximum: int | None = None,
) -> dict[str, Any]:
    modes = sorted({str(task["mode"]) for task in required_tasks})
    task_n = len(required_tasks)
    outcome: dict[str, Any] = {
        "name": name,
        "state": "answer",
        "allowed_modes": modes,
        "task_count": {
            "min": task_n if minimum is None else minimum,
            "max": task_n if maximum is None else maximum,
        },
        "required_tasks": required_tasks,
    }
    if any(task.get("mode") == "structured" for task in required_tasks):
        outcome["structured_evidence"] = "required"
    if any(task.get("mode") == "rag" for task in required_tasks):
        outcome["rag_evidence"] = "required"
    return outcome


def structured_source(record: dict[str, Any], catalog: str) -> dict[str, str]:
    if catalog == "foreign_language":
        source_id = str(record["table_id"])
    elif catalog in {"scoring", "study_duration", "scholarship"}:
        table_id = str(record.get("table_id") or "")
        source_id = (
            f"{record['source_parent_id']}_{record['table_subtype']}"
            if table_id in {"scholarship_amount", "scholarship_classification", "scholarship_eligibility", "scholarship_score_formula"}
            else table_id
        )
        source_id = source_id.replace("K48-K49_K48_49_", "K48_49_")
    elif catalog == "office":
        source_id = str(record["office_profile_id"])
    elif catalog == "faculty":
        source_id = str(record["faculty_profile_id"])
    elif catalog == "program":
        source_id = f"{record['cohort']}_{record['record_id']}"
    elif catalog == "formula":
        source_id = str(record.get("record_id") or record.get("rule_id"))
    else:
        raise ValueError(f"Unsupported structured catalog: {catalog}")
    return {"catalog": catalog, "source_id": source_id}


def row_fact(row: dict[str, Any]) -> str:
    return "; ".join(f"{key}: {value}" for key, value in row.items())


def table_record(
    tables: list[dict[str, Any]],
    cohort: str,
    subtype: str,
    *,
    id_contains: str | None = None,
) -> dict[str, Any]:
    matches = [
        item
        for item in tables
        if item.get("cohort") == cohort
        and item.get("table_subtype") == subtype
        and (not id_contains or id_contains in str(item.get("table_id") or ""))
    ]
    if not matches:
        raise KeyError((cohort, subtype, id_contains))
    return matches[0]


def build_deterministic() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tables: list[dict[str, Any]] = load(TABLES)
    formulas: list[dict[str, Any]] = load(FORMULAS)
    offices: list[dict[str, Any]] = load(OFFICES)
    faculties: list[dict[str, Any]] = load(FACULTIES)
    programs: list[dict[str, Any]] = load(PROGRAMS)
    services: list[dict[str, Any]] = load(SERVICES)
    cases: list[dict[str, Any]] = []
    structured_singles: list[dict[str, Any]] = []

    def add_structured(
        query: str,
        cohort: str,
        lookup_type: str,
        required_slots: list[str],
        evidence: dict[str, Any],
        fact: str,
        source: dict[str, str],
        topic: str,
        *,
        stress: bool = False,
    ) -> None:
        case_id = f"v7_det_{len(cases) + 1:03d}"
        task = task_gold(
            "structured",
            lookup_type=lookup_type,
            required_slot_keys=required_slots,
            cohorts=[cohort],
        )
        case = common_case(
            case_id=case_id,
            suite="deterministic",
            query=query,
            cohort=cohort,
            topic=topic,
            expected_path="structured",
            case_type="single_structured",
            stress=stress,
        )
        case.update(
            {
                "lookup_group": lookup_type,
                "expected_group": "structured",
                "expected_llm_called": True,
                "accepted_outcomes": [answer_outcome([task])],
                "gold_evidence": [evidence],
                "required_facts": [fact],
                "expected_structured_sources": [source],
                "contract_version": DETERMINISTIC_CONTRACT,
            }
        )
        cases.append(case)
        structured_singles.append(case)

    foreign_record = next(
        item
        for item in tables
        if item.get("table_type") == "foreign_language"
        and item.get("cohort") == "K50"
    )
    foreign_rows = foreign_record["rows"]
    foreign_specs = [
        ("K51", "TOEFL iBT", "Trong bảng K51, TOEFL iBT được ghi các khoảng nào cho bậc 3 và bậc 4?", 0),
        ("K50", "TOEFL ITP", "Tra giúp em riêng dòng TOEFL ITP: hai cột bậc 3 và bậc 4 ghi gì?", 1),
        ("K48-K49", "IELTS", "IELTS trong bảng tham chiếu của khóa em có hai khoảng tương đương nào?", 2),
        ("K51", "Cambridge", "Bảng quy đổi Cambridge/Linguaskill phân biệt bậc 3 với bậc 4 ra sao?", 3),
        ("K50", "HSK", "Chỉ xem bảng: HSK bậc 3 và bậc 4 tương ứng cấp nào?", 6),
        ("K51", "JLPT", "Dòng JLPT trong bảng ngoại ngữ xếp N4 và N3 vào bậc nào?", 7),
    ]
    for cohort, entity, query, index in foreign_specs:
        add_structured(
            query,
            cohort,
            "foreign_language",
            ["certificate_or_language"],
            {**foreign_record, "rows": [foreign_rows[index]]},
            row_fact(foreign_rows[index]),
            structured_source(foreign_record, "foreign_language"),
            "ngoai_ngu",
        )

    duration_specs = [
        ("K51", "chinh_quy", 0, "Khóa K51 hệ chính quy có thời gian chuẩn và thời gian tối đa bao nhiêu?", "chinh_quy"),
        ("K51", "vua_lam_vua_hoc", 0, "K51 vừa làm vừa học: bảng ghi cả mốc chuẩn lẫn mốc tối đa thế nào?", "vua_lam_vua_hoc"),
        ("K50", "chinh_quy", 0, "Bằng đại học thứ nhất hệ chính quy K50 được thiết kế bao lâu và trần hoàn thành là mấy năm?", "chinh_quy"),
        ("K50", "vua_lam_vua_hoc", 0, "Với K50 vừa làm vừa học cấp bằng thứ nhất, hai mốc thời gian trong bảng là gì?", "vua_lam_vua_hoc"),
        ("K48-K49", "chinh_quy", 1, "Liên thông từ cao đẳng hệ chính quy của K48–K49 có hai mốc thời gian nào?", "chinh_quy"),
        ("K48-K49", "vua_lam_vua_hoc", 3, "Người đã có một bằng đại học học liên thông vừa làm vừa học thì bảng K48–K49 ghi bao lâu?", "vua_lam_vua_hoc"),
    ]
    for cohort, mode, row_index, query, table_hint in duration_specs:
        record = table_record(tables, cohort, "study_duration", id_contains=table_hint)
        row = record["rows"][row_index]
        add_structured(
            query,
            cohort,
            "study_duration",
            ["training_mode"],
            {**record, "rows": [row]},
            row_fact(row),
            structured_source(record, "study_duration"),
            "khac",
        )

    scholarship_specs = [
        ("K51", "scholarship_amount", 1, "Mức học bổng loại Giỏi K51 dùng hệ số và căn cứ học phí nào?"),
        ("K51", "scholarship_classification", 2, "Học lực Giỏi và rèn luyện Tốt trở lên được xếp học bổng mức nào ở K51?"),
        ("K51", "scholarship_eligibility", 0, "Đối tượng nào nằm trong bảng điều kiện xét học bổng K51?"),
        ("K50", "scholarship_amount", 2, "Học bổng Xuất sắc K50 nhân hệ số bao nhiêu và theo cơ sở nào?"),
        ("K50", "scholarship_classification", 1, "Khoảng điểm học bổng của loại Giỏi K50 được ghi thế nào?"),
        ("K48-K49", "scholarship_eligibility", 1, "Bảng K48–K49 yêu cầu gì về học tập, rèn luyện và kỷ luật khi xét học bổng?"),
    ]
    for cohort, subtype, row_index, query in scholarship_specs:
        record = table_record(tables, cohort, subtype)
        row = record["rows"][row_index]
        add_structured(
            query,
            cohort,
            "scholarship_classification",
            [],
            {**record, "rows": [row]},
            row_fact(row),
            structured_source(record, "scholarship"),
            "hoc_bong",
        )

    scoring_specs = [
        ("K51", "grade_scale", "foundation", 1, "Học phần nền tảng được 8,4 thì bảng K51 đổi thành điểm chữ nào?"),
        ("K51", "grade_scale", "remaining", 5, "Học phần còn lại được 5,2: bảng K51 ghi D+ và trạng thái đạt hay không đạt?"),
        ("K50", "grade_scale", None, 2, "Điểm học phần 7,7 của K50 nằm ở hàng điểm chữ nào?"),
        ("K48-K49", "grade_scale", None, 6, "K48–K49: 4,6 điểm học phần được quy thành chữ gì?"),
        ("K51", "letter_to_grade4", None, 1, "Điểm chữ B+ tương ứng chính xác bao nhiêu trên thang 4?"),
        ("K50", "letter_to_grade4", None, 8, "Điểm chữ F trong bảng K50 đổi sang hệ 4 bằng bao nhiêu?"),
        ("K51", "academic_classification", None, 1, "GPA 3,59 theo bảng K51 vẫn thuộc xếp loại học lực nào?"),
        ("K48-K49", "academic_classification", None, 5, "Điểm trung bình 0,95 được bảng học lực K48–K49 xếp mức nào?"),
    ]
    for cohort, subtype, hint, row_index, query in scoring_specs:
        record = table_record(tables, cohort, subtype, id_contains=hint)
        row = record["rows"][row_index]
        add_structured(
            query,
            cohort,
            "scoring",
            ["operation", "score_or_grade"],
            {**record, "rows": [row]},
            row_fact(row),
            structured_source(record, "scoring"),
            "diem",
            stress=True,
        )

    conduct_specs = [
        ("K51", 34, 5, "K51 có 34 điểm rèn luyện thì thuộc mức nào?"),
        ("K51", 50, 3, "Đúng 50 điểm rèn luyện đã vào loại Trung bình chưa?"),
        ("K50", 65, 2, "Mốc 65 điểm rèn luyện của K50 được xếp loại gì?"),
        ("K50", 80, 1, "80 điểm rèn luyện thuộc Tốt hay Khá?"),
        ("K48-K49", 89, 1, "Điểm rèn luyện 89 của K48–K49 được phân loại thế nào?"),
        ("K48-K49", 99, 0, "99 điểm rèn luyện có thuộc Xuất sắc theo bảng không?"),
    ]
    for cohort, _score, row_index, query in conduct_specs:
        record = table_record(tables, cohort, "conduct_classification")
        row = record["rows"][row_index]
        add_structured(
            query,
            cohort,
            "scoring",
            ["operation", "score_or_grade"],
            {**record, "rows": [row]},
            row_fact(row),
            structured_source(record, "scoring"),
            "ren_luyen",
        )
        structured_singles[-1]["lookup_group"] = "conduct"

    formula_specs = [
        ("K51", "gpa_weighted_average", "Trong công thức GPA, mẫu số và trọng số của từng học phần được xác định thế nào?"),
        ("K50", "scholarship_score", "Công thức điểm xếp hạng học bổng kết hợp điểm học tập và rèn luyện theo tỷ trọng nào?"),
    ]
    for cohort, rule_id, query in formula_specs:
        candidates = [
            item
            for item in formulas
            if item.get("rule_id") == rule_id and item.get("cohort") == cohort
        ]
        record = candidates[0] if candidates else next(item for item in formulas if item.get("rule_id") == rule_id)
        add_structured(
            query,
            cohort,
            "formula",
            ["formula_type"],
            record,
            str(record.get("formula_text") or record.get("formula") or record.get("raw_excerpt"))[:600],
            structured_source(record, "formula"),
            "diem" if rule_id == "gpa_weighted_average" else "hoc_bong",
        )

    def choose_distinct(records: list[dict[str, Any]], key: str, n: int) -> list[dict[str, Any]]:
        seen: set[str] = set()
        selected: list[dict[str, Any]] = []
        for item in sorted(records, key=lambda value: (value.get("cohort", ""), norm(str(value.get(key) or "")))):
            identity = norm(str(item.get(key) or ""))
            if not identity or identity in seen:
                continue
            seen.add(identity)
            selected.append(item)
            if len(selected) == n:
                break
        return selected

    field_cycle = ("email", "phone", "website", "office", "email", "phone")
    for record, field in zip(choose_distinct(offices, "unit_name", 6), field_cycle):
        plural = {"email": "emails", "phone": "phones", "website": "websites"}.get(field)
        value = record.get(field) or (record.get(plural) or [""])[0] if plural else record.get(field)
        if not value:
            field = "office" if record.get("office") else "email"
            value = record.get(field) or "Không được ghi trong danh bạ"
        unit = str(record.get("unit_name") or record.get("unit"))
        query = f"Danh bạ {record['cohort']} ghi {field} của {unit} là gì?"
        add_structured(
            query,
            record["cohort"],
            "office",
            ["requested_field"],
            record,
            f"{unit} — {field}: {value}",
            structured_source(record, "office"),
            "phong_ban",
        )

    for record, field in zip(choose_distinct(faculties, "faculty_name", 6), field_cycle):
        plural = {"email": "emails", "phone": "phones", "website": "websites"}.get(field)
        value = record.get(field) or (record.get(plural) or [""])[0] if plural else record.get(field)
        if not value:
            field = "office"
            value = record.get("office") or "Không được ghi trong danh bạ"
        name = str(record.get("faculty_name") or record.get("unit_name"))
        add_structured(
            f"Em cần tra {field} của {name} trong danh bạ {record['cohort']}.",
            record["cohort"],
            "faculty",
            ["requested_field"],
            record,
            f"{name} — {field}: {value}",
            structured_source(record, "faculty"),
            "phong_ban",
        )

    for record in choose_distinct(programs, "program_name", 8):
        add_structured(
            f"Ngành {record['program_name']} thuộc khoa nào theo danh mục {record['cohort']}?",
            record["cohort"],
            "program",
            ["requested_field"],
            record,
            f"{record['program_name']} thuộc {record['faculty_name']}.",
            structured_source(record, "program"),
            "nganh_hoc",
        )

    for record in choose_distinct(services, "service", 6):
        office = next(
            item
            for item in offices
            if item.get("cohort") == record.get("cohort")
            and norm(str(item.get("unit_name") or "")) == norm(str(record.get("unit_name") or record.get("unit") or ""))
        )
        add_structured(
            f"Nếu cần {str(record['service']).lower()}, em phải liên hệ đơn vị nào?",
            record["cohort"],
            "student_service",
            ["requested_field"],
            record,
            f"Đơn vị phụ trách: {record['unit_name']}.",
            structured_source(office, "office"),
            "phong_ban",
        )

    if len(cases) != 60:
        raise AssertionError(f"Expected 60 structured cases, got {len(cases)}")

    docs = load(DOCSTORE)
    v6_used = {
        judgment["parent_section_id"]
        for case in load(V6_RETRIEVAL)
        for judgment in case.get("relevance_judgments") or []
    }
    boundary_docs = [
        doc
        for doc in docs
        if doc.get("_id") not in v6_used
        and len(str(doc.get("content") or "")) >= 350
    ]
    boundary_docs.sort(key=lambda item: hashlib.sha256(str(item["_id"]).encode()).hexdigest())
    boundary_cases: list[dict[str, Any]] = []
    for doc in boundary_docs[:24]:
        case_id = f"v7_det_{len(cases) + 1:03d}"
        cohort = str((doc.get("metadata") or {}).get("cohort") or "general")
        title = extract_title(doc)
        article = str((doc.get("metadata") or {}).get("article") or "Điều liên quan").rstrip(".")
        query = f"Theo {article} dành cho {cohort}, nội dung về {title.lower()} được quy định thế nào?"
        case = common_case(
            case_id=case_id,
            suite="deterministic",
            query=query,
            cohort=cohort,
            topic=topic_for(doc),
            expected_path="regulation_rag",
            case_type="capability_boundary",
        )
        case.update(
            {
                "lookup_group": "rag_boundary",
                "expected_group": "rag",
                "expected_llm_called": True,
                "accepted_outcomes": [
                    answer_outcome([task_gold("rag", cohorts=[cohort])])
                ],
                "gold_evidence": [judgment(doc, grade=2)],
                "required_facts": [first_fact(doc)],
                "contract_version": DETERMINISTIC_CONTRACT,
                "near_duplicate_reviewed": True,
                "near_duplicate_rationale": "Distinct canonical parent target; shared question template is intentional source-first coverage.",
            }
        )
        cases.append(case)
        boundary_cases.append(case)

    singles_by_cohort = {
        cohort: [case for case in structured_singles if case["cohort"] == cohort]
        for cohort in COHORTS
    }

    # Eighteen structured compositions and ten structured + regulation targets.
    for index in range(18):
        cohort = COHORTS[index % len(COHORTS)]
        pool = singles_by_cohort[cohort]
        selected = [pool[index % len(pool)], pool[(index + 5) % len(pool)]]
        if index >= 12:
            selected.append(pool[(index + 9) % len(pool)])
        required = [
            outcome_task
            for item in selected
            for outcome_task in item["accepted_outcomes"][0]["required_tasks"]
        ]
        query_parts = [item["query"].rstrip("?.") for item in selected]
        query = query_parts[0] + ". Đồng thời, " + "; đồng thời, ".join(
            part[0].lower() + part[1:] for part in query_parts[1:]
        ) + "?"
        case = common_case(
            case_id=f"v7_det_{len(cases) + 1:03d}",
            suite="deterministic",
            query=query,
            cohort=selected[0]["cohort"],
            topic="khac",
            expected_path="structured",
            case_type="compound",
            stress=len(required) == 3,
        )
        case.update(
            {
                "lookup_group": "compound_structured",
                "expected_group": "structured",
                "expected_llm_called": True,
                "accepted_outcomes": [answer_outcome(required)],
                "gold_evidence": [e for item in selected for e in item["gold_evidence"]],
                "required_facts": [f for item in selected for f in item["required_facts"]],
                "expected_structured_sources": [s for item in selected for s in item["expected_structured_sources"]],
                "contract_version": DETERMINISTIC_CONTRACT,
                "near_duplicate_reviewed": True,
                "near_duplicate_rationale": "Distinct structured capability composition with separately identified evidence targets.",
            }
        )
        cases.append(case)

    mixed_compounds: list[dict[str, Any]] = []
    for index in range(10):
        structured_case = structured_singles[(index * 5 + 2) % 60]
        matching_boundaries = [
            case for case in boundary_cases if case["cohort"] == structured_case["cohort"]
        ]
        rag_case = matching_boundaries[index % len(matching_boundaries)]
        required = [
            structured_case["accepted_outcomes"][0]["required_tasks"][0],
            task_gold("rag", cohorts=[rag_case["cohort"]]),
        ]
        query = f"{structured_case['query'].rstrip('?.')}; ngoài ra {rag_case['query'][0].lower() + rag_case['query'][1:]}"
        case = common_case(
            case_id=f"v7_det_{len(cases) + 1:03d}",
            suite="deterministic",
            query=query,
            cohort=structured_case["cohort"],
            topic="khac",
            expected_path="mixed",
            case_type="compound",
            stress=index >= 7,
        )
        case.update(
            {
                "lookup_group": "compound_mixed",
                "expected_group": "mixed",
                "expected_llm_called": True,
                "accepted_outcomes": [answer_outcome(required)],
                "gold_evidence": structured_case["gold_evidence"] + rag_case["gold_evidence"],
                "rag_judgments": rag_case["gold_evidence"],
                "required_facts": structured_case["required_facts"] + rag_case["required_facts"],
                "expected_structured_sources": structured_case["expected_structured_sources"],
                "contract_version": DETERMINISTIC_CONTRACT,
                "near_duplicate_reviewed": True,
                "near_duplicate_rationale": "Mixed composition links one canonical structured source and one canonical parent source.",
            }
        )
        cases.append(case)
        mixed_compounds.append(case)

    clarify_queries = [
        "Em học K50 nhưng năm tuyển sinh em lại ghi 2025; tra bảng thời gian chính quy giúp em.",
        "TOEIC bốn kỹ năng của em thiếu điểm Viết, vậy đã kết luận được bậc chưa?",
        "Tra giúp em địa chỉ của khoa đó.",
        "Mức hỗ trợ này áp dụng theo tháng hay học kỳ?",
        "Chuyển điểm này sang hệ còn lại giúp em.",
        "Em cần tra quy định vừa nói nhưng chưa rõ là K50 hay K51.",
        "Cho em liên hệ của hai đơn vị kia.",
        "Chứng chỉ của em có còn hạn không nếu em chưa nhớ ngày cấp?",
        "Em muốn hỏi Điều 16 nhưng không nhớ thuộc quy chế nào.",
        "So sánh thời gian học của hai khóa, nhưng em chưa ghi hai khóa nào.",
        "Cho em email Thư viện, khoa quản lý ngành Hóa học, bảng IELTS và thủ tục chuyển trường.",
        "Em cần GPA, số Khoa Lịch sử, danh sách ngành Khoa Ngữ văn và quy định nghỉ học.",
    ]
    for query in clarify_queries:
        case = common_case(
            case_id=f"v7_det_{len(cases) + 1:03d}",
            suite="deterministic",
            query=query,
            cohort="K51",
            topic="khac",
            expected_path="clarify",
            case_type="missing_or_ambiguous",
            stress=True,
        )
        case.update(
            {
                "lookup_group": "clarification",
                "expected_group": "clarification",
                "expected_llm_called": True,
                "accepted_outcomes": [
                    {
                        "name": "planner-or-task-clarification",
                        "state": "clarify",
                        "allowed_modes": ["clarify", "structured", "rag"],
                        "task_count": {"min": 1, "max": 3},
                        "required_tasks": [],
                    }
                ],
                "gold_evidence": [],
                "required_facts": ["Yêu cầu làm rõ dữ kiện còn thiếu hoặc mâu thuẫn; không tự đoán."],
                "contract_version": DETERMINISTIC_CONTRACT,
            }
        )
        cases.append(case)

    unsupported = [
        "Hồ sơ công nhận ngoại ngữ em gửi sáng nay đã được duyệt chưa?",
        "Tiền học bổng kỳ này đã vào đúng tài khoản cá nhân của em chưa?",
        "Lớp học phần chiều mai hiện còn chính xác bao nhiêu chỗ?",
        "Ai đang trực tiếp chấm bài thi của em ở thời điểm này?",
        "Tối nay Trạm Y tế có ai trực không?",
        "Ký túc xá còn giường trống để đặt ngay không?",
        "Đọc giúp em mã giao dịch học phí gần nhất trong tài khoản.",
        "Cho em danh sách sinh viên đang bị kỷ luật trong lớp.",
    ]
    for query in unsupported:
        case = common_case(
            case_id=f"v7_det_{len(cases) + 1:03d}",
            suite="deterministic",
            query=query,
            cohort="K51",
            topic="khac",
            expected_path="regulation_rag",
            case_type="unsupported_in_domain",
            stress=True,
        )
        case.update(
            {
                "lookup_group": "safe_unavailable",
                "expected_group": "safe_unavailable",
                "expected_llm_called": True,
                "accepted_outcomes": [
                    {
                        "name": "safe-unavailable",
                        "state": "safe_unavailable",
                        "allowed_modes": ["rag", "structured", "clarify"],
                        "task_count": {"min": 0, "max": 3},
                        "required_tasks": [],
                    },
                    {
                        "name": "clarify-without-fabrication",
                        "state": "clarify",
                        "allowed_modes": ["rag", "structured", "clarify"],
                        "task_count": {"min": 0, "max": 3},
                        "required_tasks": [],
                    },
                    {
                        "name": "out-of-domain-data-boundary",
                        "state": "out_of_domain",
                        "allowed_modes": [],
                        "task_count": {"min": 0, "max": 0},
                        "required_tasks": [],
                    },
                ],
                "gold_evidence": [],
                "required_facts": ["Không bịa hoặc tuyên bố đã truy cập dữ liệu live/cá nhân."],
                "contract_version": DETERMINISTIC_CONTRACT,
            }
        )
        cases.append(case)

    ood_queries = [
        "Viết hàm JavaScript đảo ngược một chuỗi.",
        "Gợi ý thực đơn ăn tối ít dầu mỡ cho gia đình.",
        "Tóm tắt cốt truyện một bộ phim khoa học viễn tưởng.",
        "Cách thay lốp xe máy bị thủng giữa đường?",
        "So sánh giá vàng và Bitcoin hôm nay.",
        "Giải phương trình bậc hai x bình cộng 3x trừ 4 bằng 0.",
        "Viết lời quảng cáo cho quán trà sữa.",
        "Hướng dẫn tạo index trong PostgreSQL.",
    ]
    for query in ood_queries:
        case = common_case(
            case_id=f"v7_det_{len(cases) + 1:03d}",
            suite="deterministic",
            query=query,
            cohort="general",
            topic="khac",
            expected_path="out_of_domain",
            case_type="out_of_domain",
            stress=True,
        )
        case.update(
            {
                "lookup_group": "out_of_domain",
                "expected_group": "out_of_domain",
                "expected_llm_called": False,
                "accepted_outcomes": [
                    {
                        "name": "out-of-domain",
                        "state": "out_of_domain",
                        "allowed_modes": [],
                        "task_count": {"min": 0, "max": 0},
                        "required_tasks": [],
                    }
                ],
                "gold_evidence": [],
                "required_facts": ["Từ chối ngắn gọn vì ngoài phạm vi Sổ tay sinh viên."],
                "contract_version": DETERMINISTIC_CONTRACT,
            }
        )
        cases.append(case)

    if len(cases) != COUNTS["deterministic"]:
        raise AssertionError(f"Expected 140 deterministic cases, got {len(cases)}")
    return cases, mixed_compounds


def extract_title(doc: dict[str, Any]) -> str:
    for line in str(doc.get("content") or "").splitlines():
        if line.startswith("Tiêu đề:"):
            return line.split(":", 1)[1].strip()
    return str((doc.get("metadata") or {}).get("source_section") or "quy định liên quan")


def body_text(doc: dict[str, Any]) -> str:
    content = str(doc.get("content") or "")
    return content.split("Nội dung:", 1)[-1].strip()


def first_fact(doc: dict[str, Any]) -> str:
    title = extract_title(doc)
    article = str((doc.get("metadata") or {}).get("article") or "").strip()
    flat = re.sub(r"\s+", " ", body_text(doc)).strip()
    heading = re.sub(r"\s+", " ", f"{article} {title}").strip()
    if flat.casefold().startswith(heading.casefold()):
        flat = flat[len(heading) :].strip()
    # Prefer the complete first numbered clause instead of an arbitrary line
    # slice. This keeps answer gold readable and avoids cutting a sentence in
    # the middle merely because the PDF wrapped it onto another line.
    if re.match(r"^1\.\s", flat):
        next_clause = re.search(r"\s2\.\s", flat)
        fact = flat[: next_clause.start()].strip() if next_clause else flat
    else:
        fact = flat
    if len(fact) > 700:
        boundary = max(fact.rfind(". ", 0, 700), fact.rfind("; ", 0, 700))
        fact = fact[: boundary + 1 if boundary >= 120 else 700].rstrip()
    return fact or f"Nội dung nguồn về {title}."


def document_title(doc: dict[str, Any]) -> str:
    metadata_title = str((doc.get("metadata") or {}).get("document_title") or "").strip()
    if metadata_title:
        return metadata_title
    for line in str(doc.get("content") or "").splitlines():
        if line.startswith("Tài liệu:"):
            return line.split(":", 1)[1].strip()
    return ""


def short_document(doc: dict[str, Any]) -> str:
    title = norm(document_title(doc))
    for needle, label in (
        ("ngoai ngu", "quy định ngoại ngữ"),
        ("co van hoc tap", "quy định cố vấn học tập"),
        ("nghien cuu khoa hoc", "quy định nghiên cứu khoa học"),
        ("ngoai tru", "quy định ngoại trú"),
        ("quy tac ung xu", "quy định quy tắc ứng xử"),
        ("thu vien", "quy định thư viện"),
        ("ren luyen", "quy chế rèn luyện"),
        ("cong tac sinh vien", "quy chế công tác sinh viên"),
        ("ho tro tien dong hoc phi", "nghị định hỗ trợ sinh viên sư phạm"),
        ("dao tao", "quy chế đào tạo"),
    ):
        if needle in title:
            return label
    return "văn bản trong Sổ tay"


def topic_for(doc: dict[str, Any]) -> str:
    text = norm(f"{extract_title(doc)} {document_title(doc)}")
    for needle, topic in (
        ("hoc bong", "hoc_bong"),
        ("hoc phi", "hoc_phi"),
        ("nghi hoc", "nghi_hoc"),
        ("ren luyen", "ren_luyen"),
        ("tot nghiep", "tot_nghiep"),
        ("ngoai ngu", "ngoai_ngu"),
        ("diem", "diem"),
    ):
        if needle in text:
            return topic
    return "khac"


def judgment(doc: dict[str, Any], *, grade: int) -> dict[str, Any]:
    metadata = doc.get("metadata") or {}
    return {
        "parent_section_id": doc["_id"],
        "grade": grade,
        "cohort": metadata.get("cohort"),
        "document_id": metadata.get("document_id"),
        "document_title": document_title(doc),
        "content_type": metadata.get("content_type"),
        "source_section": extract_title(doc),
        "source_pages": metadata.get("source_pages") or [],
        "article": metadata.get("article"),
        "anchor_source": "v7_local_docstore_authoring",
        "source_excerpt": body_text(doc)[:1400],
        "expected_fact": first_fact(doc),
    }


def build_retrieval() -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = load(DOCSTORE)
    docs_by_id = {doc["_id"]: doc for doc in docs}
    v6_used = {
        item["parent_section_id"]
        for case in load(V6_RETRIEVAL)
        for item in case.get("relevance_judgments") or []
    }
    eligible = [
        doc
        for doc in docs
        if doc["_id"] not in v6_used
        and len(body_text(doc)) >= 220
        and extract_title(doc)
    ]
    eligible.sort(key=lambda item: hashlib.sha256(str(item["_id"]).encode()).hexdigest())
    remaining = {doc["_id"]: doc for doc in eligible}
    cases: list[dict[str, Any]] = []

    def add_case(
        query: str,
        cohort: str,
        judgments: list[dict[str, Any]],
        subtype: str,
        tags: list[str],
        *,
        stress: bool,
    ) -> None:
        case = common_case(
            case_id=f"v7_ret_{len(cases) + 1:03d}",
            suite="retrieval",
            query=query,
            cohort=cohort,
            topic=topic_for(docs_by_id[judgments[0]["parent_section_id"]]),
            expected_path="regulation_rag",
            case_type="regulation_true_rag",
            stress=stress,
        )
        case.update(
            {
                "expected_intent": "regulation_query",
                "expected_strategy": "semantic_filtered",
                "expected_content_types": ["regulation_text"],
                "relevance_judgments": judgments,
                "retrieval_subtype": subtype,
                "query_style": "student_scenario",
                "query_origin": "v7_local_source_first_draft",
                "contract_version": "regulation-retrieval-outcome-draft-v7",
                "relevance_scope": "per_cohort_execution_unit",
                "annotation_status": "draft_pending_owner_review",
                "required_evidence_groups": [
                    [item["parent_section_id"]] for item in judgments if item["grade"] == 2
                ],
                "relevance_judgment_policy": "Grade 2 directly answers a requested target; grade 1 is supporting context. Unlisted sources remain unjudged.",
                "near_duplicate_reviewed": True,
                "near_duplicate_rationale": "Canonical relevance targets differ even when a source-first query template is shared.",
            }
        )
        case["tags"].extend(["true_rag", "citation_required", *tags])
        cases.append(case)

    # Twelve cohort-neutral questions use equivalent editions only when all
    # three cohorts contain the same document/article/title identity.
    equivalent: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for doc in eligible:
        metadata = doc.get("metadata") or {}
        key = (
            norm(str(metadata.get("document_title") or "")),
            norm(str(metadata.get("article") or "")),
            norm(extract_title(doc)),
        )
        equivalent[key].append(doc)
    groups = [
        group
        for group in equivalent.values()
        if {str((doc.get("metadata") or {}).get("cohort")) for doc in group} == set(COHORTS)
    ]
    groups.sort(key=lambda group: hashlib.sha256(group[0]["_id"].encode()).hexdigest())
    for group in groups[:12]:
        group = sorted(group, key=lambda doc: COHORTS.index((doc.get("metadata") or {})["cohort"]))
        first = group[0]
        override = EQUIVALENT_TARGET_OVERRIDES.get(str(first["_id"]))
        if override:
            query, expected_fact = override
            judgments = [judgment(doc, grade=2) for doc in group]
            for item in judgments:
                item["expected_fact"] = expected_fact
        else:
            query = (
                f"Trong Sổ tay sinh viên, {extract_title(first).lower()} được "
                f"{short_document(first)} quy định như thế nào?"
            )
            judgments = [judgment(doc, grade=2) for doc in group]
        add_case(
            query,
            "general",
            judgments,
            "multi_cohort_equivalent",
            ["paraphrase", "student_style", "cohort_sensitive"],
            stress=False,
        )
        for doc in group:
            remaining.pop(doc["_id"], None)

    by_cohort: dict[str, list[dict[str, Any]]] = {
        cohort: [
            doc
            for doc in remaining.values()
            if (doc.get("metadata") or {}).get("cohort") == cohort
        ]
        for cohort in COHORTS
    }
    selected_singles: list[dict[str, Any]] = []
    for cohort in COHORTS:
        selected_singles.extend(by_cohort[cohort][:36])
    selected_singles.sort(key=lambda doc: hashlib.sha256(doc["_id"].encode()).hexdigest())
    for index, doc in enumerate(selected_singles):
        metadata = doc.get("metadata") or {}
        cohort = str(metadata.get("cohort"))
        title = extract_title(doc)
        article = str(metadata.get("article") or "Điều liên quan").rstrip(".")
        if index < 30:
            query = f"{article} của {short_document(doc)} áp dụng cho {cohort} quy định gì về {title.lower()}?"
            subtype = "exact_article"
            tags = ["keyword", "exact_article"]
            stress = False
        elif index < 98:
            query = (
                f"Em thuộc {cohort}; cho em hỏi {title.lower()} được "
                f"{short_document(doc)} quy định thế nào?"
                if index % 3 == 0
                else f"Với {cohort}, nội dung chính của {article} về {title.lower()} là gì?"
                if index % 3 == 1
                else f"Sinh viên {cohort} cần lưu ý gì trong quy định về {title.lower()}?"
            )
            subtype = "semantic"
            tags = ["paraphrase", "student_style"]
            stress = index % 5 == 0
        else:
            query = no_diacritics(
                f"Em hoc {cohort}, cho em hoi quy dinh ve {title.lower()} trong {short_document(doc)}."
            )
            subtype = "typo_no_diacritics"
            tags = ["typo_no_diacritics", "student_style"]
            stress = True
        if re.search(r"\d", first_fact(doc)):
            tags.append("numeric_fact")
        if index % 9 == 0:
            tags.append("condition_procedure")
        source_judgment = judgment(doc, grade=2)
        if doc["_id"] in RETRIEVAL_TARGET_OVERRIDES:
            query, expected_fact = RETRIEVAL_TARGET_OVERRIDES[doc["_id"]]
            source_judgment["expected_fact"] = expected_fact
        add_case(query, cohort, [source_judgment], subtype, tags, stress=stress)
        remaining.pop(doc["_id"], None)

    graph_edges: list[dict[str, Any]] = load(GRAPH)
    graph_selected = [
        edge
        for edge in graph_edges
        if edge.get("source") in docs_by_id
        and edge.get("target") in docs_by_id
    ]
    graph_selected.sort(
        key=lambda edge: (
            edge.get("source") in v6_used or edge.get("target") in v6_used,
            hashlib.sha256(f"{edge['source']}->{edge['target']}".encode()).hexdigest(),
        )
    )
    for edge in graph_selected[:20]:
        source = docs_by_id[edge["source"]]
        target = docs_by_id[edge["target"]]
        cohort = str((source.get("metadata") or {}).get("cohort"))
        query = (
            f"Ở {cohort}, {extract_title(source).lower()} có dẫn chiếu "
            f"{edge.get('reference_text')}; cần đọc thêm nội dung nào từ điều được dẫn chiếu?"
        )
        add_case(
            query,
            cohort,
            [judgment(source, grade=2), judgment(target, grade=1)],
            "graph_linked",
            ["graph_reference", "condition_procedure", "student_style"],
            stress=True,
        )
        remaining.pop(source["_id"], None)
        remaining.pop(target["_id"], None)

    if len(cases) < 140:
        raise AssertionError(f"Insufficient graph cases: only {len(cases)} before multi-source")

    remaining_by_cohort = {
        cohort: [
            doc
            for doc in remaining.values()
            if (doc.get("metadata") or {}).get("cohort") == cohort
        ]
        for cohort in COHORTS
    }
    for index in range(20):
        cohort = COHORTS[index % len(COHORTS)]
        pool = remaining_by_cohort[cohort]
        first, second = pool.pop(0), pool.pop(0)
        query = (
            f"Em thuộc {cohort} và cần biết hai nội dung: "
            f"(1) {extract_title(first).lower()}; "
            f"(2) {extract_title(second).lower()}. "
            "Mỗi nội dung có những điểm chính nào?"
        )
        add_case(
            query,
            cohort,
            [judgment(first, grade=2), judgment(second, grade=2)],
            "multi_source",
            ["multi_source", "paraphrase", "cohort_sensitive"],
            stress=index >= 12,
        )

    if len(cases) != COUNTS["retrieval"]:
        raise AssertionError(f"Expected 160 retrieval cases, got {len(cases)}")
    return cases


def build_answers(
    deterministic: list[dict[str, Any]],
    retrieval: list[dict[str, Any]],
    mixed_compounds: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    answers: list[dict[str, Any]] = []

    def add_answer(
        *,
        case_type: str,
        query: str,
        cohort: str,
        expected_path: str,
        required_facts: list[str],
        judgments: list[dict[str, Any]],
        structured_sources: list[dict[str, str]],
        linked_ids: list[str],
        stress: bool,
        topic: str,
        answerability: str = "answerable",
    ) -> None:
        prefix = {
            "regulation_true_rag": "rag",
            "structured_answer": "struct",
            "mixed_answer": "mixed",
            "clarification": "clarify",
            "unanswerable": "unanswerable",
            "out_of_domain": "ood",
        }[case_type]
        case = common_case(
            case_id=f"v7_ans_{prefix}_{sum(1 for item in answers if item['case_type'] == case_type) + 1:03d}",
            suite="answers",
            query=query,
            cohort=cohort,
            topic=topic,
            expected_path=expected_path,
            case_type=case_type,
            stress=stress,
        )
        behavior = (
            "clarify_or_scope"
            if case_type == "clarification"
            else "abstain"
            if case_type in {"unanswerable", "out_of_domain"}
            else "scoped_summary"
        )
        case.update(
            {
                "expected_intent": "answer_composition",
                "expected_strategy": expected_path,
                "expected_answer_behavior": behavior,
                "answerability": answerability,
                "relevance_judgments": judgments,
                "expected_citations": judgments,
                "expected_structured_sources": structured_sources,
                "required_facts": required_facts,
                "ground_truth": "\n".join(f"- {fact}" for fact in required_facts),
                "forbidden_claims": [
                    "Không thêm con số, điều kiện, đối tượng hoặc ngoại lệ ngoài evidence của case.",
                    "Không dùng nguồn sai cohort nếu metadata không xác nhận phạm vi áp dụng.",
                ],
                "linked_source_case_ids": linked_ids,
                "generation_model": "gemini-3.1-flash-lite",
                "judge_model": "openai/gpt-oss-120b",
                "contract_version": "answer-quality-outcome-draft-v7",
                "annotation_status": "draft_pending_owner_review",
                "near_duplicate_reviewed": True,
                "near_duplicate_rationale": "Intentional cross-suite link to immutable V7 source case IDs.",
            }
        )
        answers.append(case)

    rag_candidates = (
        [case for case in retrieval if case.get("retrieval_subtype") == "semantic"][:55]
        + [case for case in retrieval if case.get("retrieval_subtype") == "exact_article"][:15]
        + [case for case in retrieval if case.get("retrieval_subtype") == "multi_cohort_equivalent"][:8]
        + [case for case in retrieval if case.get("retrieval_subtype") == "graph_linked"][:6]
        + [case for case in retrieval if case.get("retrieval_subtype") == "multi_source"][:6]
    )
    for source in rag_candidates:
        facts = [
            str(item.get("expected_fact") or "")
            for item in source["relevance_judgments"]
            if item.get("grade") == 2
        ]
        add_answer(
            case_type="regulation_true_rag",
            query=source["query"],
            cohort=source["cohort"],
            expected_path="regulation_rag",
            required_facts=facts,
            judgments=source["relevance_judgments"],
            structured_sources=[],
            linked_ids=[source["id"]],
            stress=source["eval_split"] == "stress",
            topic=source["topic"],
        )
        answers[-1]["duplicate_group"] = f"v7_link_{source['id']}"
        source["duplicate_group"] = answers[-1]["duplicate_group"]

    structured_candidates = [
        case for case in deterministic if case.get("case_type") == "single_structured"
    ][:30]
    for source in structured_candidates:
        add_answer(
            case_type="structured_answer",
            query=source["query"],
            cohort=source["cohort"],
            expected_path="structured",
            required_facts=source["required_facts"],
            judgments=[],
            structured_sources=source["expected_structured_sources"],
            linked_ids=[source["id"]],
            stress=source["eval_split"] == "stress",
            topic=source["topic"],
        )
        answers[-1]["lookup_group"] = source["lookup_group"]
        answers[-1]["duplicate_group"] = f"v7_link_{source['id']}"
        source["duplicate_group"] = answers[-1]["duplicate_group"]

    for source in mixed_compounds:
        add_answer(
            case_type="mixed_answer",
            query=source["query"],
            cohort=source["cohort"],
            expected_path="mixed",
            required_facts=source["required_facts"],
            judgments=source["rag_judgments"],
            structured_sources=source["expected_structured_sources"],
            linked_ids=[source["id"]],
            stress=source["eval_split"] == "stress",
            topic=source["topic"],
        )
        answers[-1]["duplicate_group"] = f"v7_link_{source['id']}"
        source["duplicate_group"] = answers[-1]["duplicate_group"]

    clarifications = [case for case in deterministic if case["case_type"] == "missing_or_ambiguous"][:8]
    for source in clarifications:
        add_answer(
            case_type="clarification",
            query=source["query"],
            cohort=source["cohort"],
            expected_path="clarify",
            required_facts=source["required_facts"],
            judgments=[],
            structured_sources=[],
            linked_ids=[source["id"]],
            stress=True,
            topic=source["topic"],
            answerability="needs_clarification",
        )
        answers[-1]["duplicate_group"] = f"v7_link_{source['id']}"
        source["duplicate_group"] = answers[-1]["duplicate_group"]

    unavailable = [case for case in deterministic if case["case_type"] == "unsupported_in_domain"][:6]
    for source in unavailable:
        add_answer(
            case_type="unanswerable",
            query=source["query"],
            cohort=source["cohort"],
            expected_path="regulation_rag",
            required_facts=source["required_facts"],
            judgments=[],
            structured_sources=[],
            linked_ids=[source["id"]],
            stress=True,
            topic="khac",
            answerability="unanswerable",
        )
        answers[-1]["duplicate_group"] = f"v7_link_{source['id']}"
        source["duplicate_group"] = answers[-1]["duplicate_group"]

    ood = [case for case in deterministic if case["case_type"] == "out_of_domain"][:6]
    for source in ood:
        add_answer(
            case_type="out_of_domain",
            query=source["query"],
            cohort=source["cohort"],
            expected_path="out_of_domain",
            required_facts=source["required_facts"],
            judgments=[],
            structured_sources=[],
            linked_ids=[source["id"]],
            stress=True,
            topic="khac",
            answerability="unanswerable",
        )
        answers[-1]["duplicate_group"] = f"v7_link_{source['id']}"
        source["duplicate_group"] = answers[-1]["duplicate_group"]

    if len(answers) != COUNTS["answers"]:
        raise AssertionError(f"Expected 150 answer cases, got {len(answers)}")
    return answers


def build_production(answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    production: list[dict[str, Any]] = []

    def add(source: dict[str, Any], scenario: str, *, stream: bool, concurrency: int, repeat_of: str | None = None) -> None:
        index = sum(1 for item in production if item["scenario"] == scenario) + 1
        case = common_case(
            case_id=f"v7_prod_{scenario}_{index:02d}",
            suite="production",
            query=source["query"],
            cohort=source["cohort"],
            topic=source["topic"],
            expected_path=source["expected_path"],
            case_type="production_contract",
            stress=scenario in {"streaming", "burst"},
        )
        case.update(
            {
                "scenario": scenario,
                "expected_intent": source["expected_intent"],
                "expected_strategy": source["expected_strategy"],
                "expected_response_status": "answered",
                "concurrency": concurrency,
                "stream": stream,
                "repeat_of": repeat_of,
                "linked_answer_case_id": source["id"],
                "duplicate_group": source.get("duplicate_group") or f"v7_link_{source['id']}",
                "near_duplicate_reviewed": True,
                "near_duplicate_rationale": "Intentional production reuse of an answer-quality case.",
            }
        )
        production.append(case)

    rag = [case for case in answers if case["case_type"] == "regulation_true_rag"]
    structured = [case for case in answers if case["case_type"] == "structured_answer"]
    mixed = [case for case in answers if case["case_type"] == "mixed_answer"]
    for source in rag[:20]:
        add(source, "cold_rag", stream=False, concurrency=1)
    cold = list(production)
    for source in structured[:10]:
        add(source, "structured", stream=False, concurrency=1)
    for source, original in zip(rag[:10], cold[:10]):
        add(source, "warm_cache", stream=False, concurrency=1, repeat_of=original["id"])
    for source in (rag[20:25] + structured[10:13] + mixed[:2]):
        add(source, "streaming", stream=True, concurrency=1)
    burst_sources = rag[25:30] + mixed[2:7]
    for index, source in enumerate(burst_sources):
        add(source, "burst", stream=index % 2 == 0, concurrency=3 if index < 5 else 5)
    if len(production) != COUNTS["production"]:
        raise AssertionError(f"Expected 60 production cases, got {len(production)}")
    return production


def historical_queries() -> dict[str, list[dict[str, str]]]:
    result: dict[str, list[dict[str, str]]] = defaultdict(list)
    for path in sorted((ROOT / "data" / "eval").glob("**/*.json")):
        if OUT in path.parents:
            continue
        try:
            value = load(path)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, dict) or not str(item.get("query") or "").strip():
                continue
            result[norm(str(item["query"]))].append(
                {"id": str(item.get("id") or ""), "path": str(path.relative_to(ROOT))}
            )
    return result


def overlap_audit(datasets: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    history = historical_queries()
    historical_token_sets = [(query, set(query.split()), refs) for query, refs in history.items()]
    rows: list[dict[str, Any]] = []
    for suite, cases in datasets.items():
        for case in cases:
            query = norm(case["query"])
            tokens = set(query.split())
            candidates = sorted(
                (
                    (len(tokens & old_tokens) / max(1, len(tokens | old_tokens)), old_query, refs)
                    for old_query, old_tokens, refs in historical_token_sets
                ),
                reverse=True,
            )[:3]
            rows.append(
                {
                    "id": case["id"],
                    "suite": suite,
                    "query": case["query"],
                    "exact_historical_matches": history.get(query, []),
                    "nearest_historical": [
                        {"token_jaccard": round(score, 4), "query": old, "references": refs}
                        for score, old, refs in candidates
                    ],
                    "review_required": bool(history.get(query))
                    or bool(candidates and candidates[0][0] >= 0.72),
                }
            )
    return {
        "schema_version": "architecture-v7-overlap-audit-v1",
        "historical_unique_query_count": len(history),
        "v7_case_count": sum(len(cases) for cases in datasets.values()),
        "exact_historical_match_count": sum(bool(row["exact_historical_matches"]) for row in rows),
        "high_similarity_review_count": sum(bool(row["review_required"]) for row in rows),
        "policy": "Similarity is a review signal, not an automatic rejection. Exact historical duplicates must be replaced unless they are declared cross-suite links inside V7.",
        "cases": rows,
    }


def audit_template(answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for case in answers:
        by_type[case["case_type"]].append(case)
    quota = {
        "regulation_true_rag": 18,
        "structured_answer": 8,
        "mixed_answer": 5,
        "clarification": 3,
        "unanswerable": 3,
        "out_of_domain": 3,
    }
    selected: list[dict[str, Any]] = []
    for case_type, count in quota.items():
        ranked = sorted(
            by_type[case_type],
            key=lambda case: hashlib.sha256(case["id"].encode()).hexdigest(),
        )
        selected.extend(ranked[:count])
    return [
        {
            "id": case["id"],
            "case_type": case["case_type"],
            "cohort": case["cohort"],
            "query": case["query"],
            "correctness": None,
            "faithfulness": None,
            "completeness": None,
            "citation_quality": None,
            "safe_behavior": None,
            "review_label": None,
            "notes": "",
            "repeat_for_consistency": False,
        }
        for case in selected
    ]


def casebook(datasets: dict[str, list[dict[str, Any]]], overlap: dict[str, Any]) -> str:
    def _counter_table(title: str, values: Counter[str]) -> list[str]:
        rows = ["", f"### {title}", "", "| Nhóm | Số case |", "|---|---:|"]
        rows.extend(
            f"| `{name}` | {count} |"
            for name, count in sorted(values.items(), key=lambda item: (-item[1], item[0]))
        )
        return rows

    def _clean_cell(value: Any, *, limit: int = 180) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip().replace("|", "\\|")
        if len(text) <= limit:
            return text
        return text[: limit - 1].rstrip() + "…"

    def _representative_cases(
        cases: list[dict[str, Any]], group_key: str, *, per_group: int = 2
    ) -> list[dict[str, Any]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for case in cases:
            grouped[str(case.get(group_key) or "khác")].append(case)
        selected: list[dict[str, Any]] = []
        for group in sorted(grouped):
            selected.extend(grouped[group][:per_group])
        return selected

    deterministic = datasets["deterministic"]
    retrieval = datasets["retrieval"]
    answers = datasets["answers"]
    production = datasets["production"]
    lines = [
        "# Architecture V7 — Draft review casebook",
        "",
        "> V7 is mutable and has not been run against the system. Review source targets and questions before any execution.",
        "",
        "## Distribution",
        "",
    ]
    for suite, cases in datasets.items():
        lines.append(f"- `{suite}`: {len(cases)} cases; realistic={sum(c['eval_split']=='realistic' for c in cases)}, stress={sum(c['eval_split']=='stress' for c in cases)}")
    lines.extend(
        _counter_table(
            "Deterministic theo case type",
            Counter(str(case["case_type"]) for case in deterministic),
        )
    )
    lines.extend(
        _counter_table(
            "Deterministic structured theo capability",
            Counter(
                str(case["lookup_group"])
                for case in deterministic
                if case["case_type"] == "single_structured"
            ),
        )
    )
    lines.extend(
        _counter_table(
            "Retrieval theo subtype",
            Counter(str(case["retrieval_subtype"]) for case in retrieval),
        )
    )
    lines.extend(
        _counter_table(
            "Generate + Judge theo case type",
            Counter(str(case["case_type"]) for case in answers),
        )
    )
    lines.extend(
        _counter_table(
            "Production theo scenario",
            Counter(str(case["scenario"]) for case in production),
        )
    )
    lines.extend(
        [
            "",
            "## Overlap review",
            "",
            f"- Exact historical matches: {overlap['exact_historical_match_count']}",
            f"- Cases flagged at token Jaccard >= 0.72: {overlap['high_similarity_review_count']}",
            "- Flags are review signals; do not edit gold merely to lower similarity.",
            "",
            "## Deterministic contract",
            "",
            "- Each case declares one or more `accepted_outcomes`.",
            "- Task order, task IDs and undeclared optional slots are not scored.",
            "- Mode/lookup/slot keys are constrained only when architecturally material.",
            "- Planner-level and task-level clarification can both be valid.",
            "- Live/private requests accept safe unavailable, clarification or out-of-domain handling without fabricated evidence.",
            "",
            "## Mẫu đại diện để review nhanh",
            "",
            "Các bảng dưới đây là lát cắt cố định theo từng nhóm, không phải kết quả chạy hệ thống.",
            "",
            "### Deterministic",
            "",
            "| ID | Nhóm | Cohort | Câu hỏi |",
            "|---|---|---|---|",
        ]
    )
    for case in _representative_cases(deterministic, "case_type"):
        lines.append(
            f"| `{case['id']}` | `{case['case_type']}` | `{case['cohort']}` | {_clean_cell(case['query'])} |"
        )
    lines.extend(
        [
            "",
            "### Retrieval",
            "",
            "| ID | Subtype | Cohort | Câu hỏi | Gold chính |",
            "|---|---|---|---|---|",
        ]
    )
    for case in _representative_cases(retrieval, "retrieval_subtype"):
        primary = [
            item["parent_section_id"]
            for item in case.get("relevance_judgments", [])
            if item.get("grade") == 2
        ]
        lines.append(
            f"| `{case['id']}` | `{case['retrieval_subtype']}` | `{case['cohort']}` | "
            f"{_clean_cell(case['query'])} | {_clean_cell(', '.join(primary), limit=120)} |"
        )
    lines.extend(
        [
            "",
            "### Generate + Judge",
            "",
            "| ID | Nhóm | Cohort | Câu hỏi |",
            "|---|---|---|---|",
        ]
    )
    for case in _representative_cases(answers, "case_type"):
        lines.append(
            f"| `{case['id']}` | `{case['case_type']}` | `{case['cohort']}` | {_clean_cell(case['query'])} |"
        )
    lines.extend(
        [
            "",
            "### Production",
            "",
            "| ID | Scenario | Cohort | Path | Câu hỏi |",
            "|---|---|---|---|---|",
        ]
    )
    for case in _representative_cases(production, "scenario"):
        lines.append(
            f"| `{case['id']}` | `{case['scenario']}` | `{case['cohort']}` | "
            f"`{case['expected_path']}` | {_clean_cell(case['query'])} |"
        )
    lines.extend(
        [
            "",
            "## Owner review checklist",
            "",
            "1. Review every overlap-flagged case.",
            "2. Spot-check at least 20 structured records and all 20 graph cases against artifacts.",
            "3. Review all multi-source and mixed cases for independent answer targets.",
            "4. Review all clarification/unanswerable cases for realistic user intent.",
            "5. Only after approval, run with `--allow-draft-dataset`; results remain draft and not CV headline metrics.",
        ]
    )
    return "\n".join(lines) + "\n"


def build_manifest(
    datasets: dict[str, list[dict[str, Any]]],
    audit: list[dict[str, Any]],
) -> dict[str, Any]:
    deterministic = datasets["deterministic"]
    retrieval = datasets["retrieval"]
    answers = datasets["answers"]
    production = datasets["production"]
    return {
        "bundle": "architecture_v7",
        "schema_version": "architecture-evaluation-v7",
        "version": "7.0-draft.1",
        "revision": 1,
        "frozen": False,
        "review_state": "draft_not_system_executed",
        "authored_against_runtime_commit": git_head(),
        "evaluated_system_commit": git_head(),
        "evaluation_harness_commit": "pending_commit_after_owner_review",
        "planner_model": "qwen/qwen3.8-27b",
        "planner_reasoning_effort": "low",
        "generation_model": "gemini-3.1-flash-lite",
        "judge_model": "openai/gpt-oss-120b",
        "retrieval_mode": "vector_primary_graph_supplement",
        "reranker_enabled": False,
        "hybrid_collection": "student_handbook_semantic_v32",
        "mongodb_parent_collection": "parent_docs_v32",
        "counts": COUNTS,
        "strict_structured_sources": True,
        "strict_cohort_conflicts": True,
        "strict_query_duplicates": True,
        "max_parent_query_usage": 5,
        "deterministic_contract": DETERMINISTIC_CONTRACT,
        "deterministic_case_type_counts": dict(Counter(case["case_type"] for case in deterministic)),
        "deterministic_lookup_case_types": ["single_structured"],
        "deterministic_lookup_group_counts": dict(Counter(case["lookup_group"] for case in deterministic if case["case_type"] == "single_structured")),
        "retrieval_contract": "regulation-rag-outcome-draft-v7",
        "retrieval_cohort_counts": dict(Counter(case["cohort"] for case in retrieval)),
        "retrieval_eval_split_counts": dict(Counter(case["eval_split"] for case in retrieval)),
        "retrieval_forbidden_query_fragments": [],
        "evaluation_contract": "comprehensive-outcome-draft-v7",
        "answer_case_type_counts": dict(Counter(case["case_type"] for case in answers)),
        "answer_eval_split_counts": dict(Counter(case["eval_split"] for case in answers)),
        "answer_path_counts": dict(Counter(case["expected_path"] for case in answers)),
        "answer_rag_cohort_counts": dict(Counter(case["cohort"] for case in answers if case["case_type"] == "regulation_true_rag")),
        "answer_structured_lookup_counts": dict(Counter(case["lookup_group"] for case in answers if case["case_type"] == "structured_answer")),
        "production_scenario_counts": dict(Counter(case["scenario"] for case in production)),
        "production_request_count": len(production),
        "production_unique_query_count": len({norm(case["query"]) for case in production}),
        "production_metric_scope": "availability, sync/stream payload contract, bounded latency, cache and burst scenarios; semantic correctness remains in answer judge/human audit",
        "human_audit_required_n": len(audit),
        "human_audit_repeat_n": 0,
        "human_audit_selection_policy": "pre-output stratified by answer case type; stable SHA256 order",
        "dataset_hashes": {suite: stable_hash(cases) for suite, cases in datasets.items()},
        "auxiliary_hashes": {"human_audit_template": stable_hash(audit)},
        "docstore_path": str(DOCSTORE.relative_to(ROOT)).replace("\\", "/"),
        "docstore_hash": file_hash(DOCSTORE),
        "config_hashes": {
            "ai_router": file_hash(ROOT / "configs" / "ai_router.yaml"),
            "structured_lookup_registry": file_hash(ROOT / "configs" / "structured_lookup_registry.yaml"),
            "retrieval": file_hash(ROOT / "configs" / "retrieval.yaml"),
            "answer_generation": file_hash(ROOT / "configs" / "answer_generation.yaml"),
        },
        "artifact_hashes": {
            str(path.relative_to(ROOT)).replace("\\", "/"): file_hash(path)
            for path in (TABLES, FOREIGN, OFFICES, FACULTIES, PROGRAMS, SERVICES, GRAPH)
        },
        "overlap_policy": {
            "exact_historical_query_matches_required": 0,
            "semantic_similarity_is_review_signal_not_filter": True,
            "same_fixed_corpus_reuse_allowed": True,
            "cross_suite_reuse_requires_linked_ids_and_duplicate_group": True,
        },
        "system_executed_on_dataset": False,
        "user_review_approved": False,
        "limitations": [
            "V7 is a mutable draft benchmark and cannot produce final CV or paper headline metrics.",
            "It uses the same three-handbook corpus; novelty concerns question/target composition, not unseen documents.",
            "Source-first automatic authoring requires owner review of phrasing and gold scope before execution.",
            "Production 60 is a bounded contract/load smoke, not a capacity or security benchmark.",
        ],
    }


def main() -> None:
    deterministic, mixed = build_deterministic()
    retrieval = build_retrieval()
    answers = build_answers(deterministic, retrieval, mixed)
    production = build_production(answers)
    datasets = {
        "deterministic": deterministic,
        "retrieval": retrieval,
        "answers": answers,
        "production": production,
    }
    overlap = overlap_audit(datasets)
    audit = audit_template(answers)
    manifest = build_manifest(datasets, audit)
    write(OUT / "deterministic_tool_cases.json", deterministic)
    write(OUT / "retrieval_cases.json", retrieval)
    write(OUT / "generated_answer_cases.json", answers)
    write(OUT / "production_cases.json", production)
    write(OUT / "human_audit_template.json", audit)
    write(OUT / "overlap_audit.json", overlap)
    write(OUT / "manifest.json", manifest)
    (OUT / "CASEBOOK_VI.md").write_text(
        casebook(datasets, overlap), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "output": str(OUT),
                "counts": {suite: len(cases) for suite, cases in datasets.items()},
                "exact_historical_matches": overlap["exact_historical_match_count"],
                "high_similarity_review": overlap["high_similarity_review_count"],
                "frozen": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
