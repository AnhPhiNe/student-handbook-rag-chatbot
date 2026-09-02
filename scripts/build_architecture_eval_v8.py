from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from copy import deepcopy
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import build_architecture_eval_v7 as v7


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "eval" / "architecture_v8"
RUNTIME_COMMIT = "09b1d3da5206f8b16a7f6c10e34793c813ff4d30"
EVALUATOR_COMMIT = "b755a1ce40fe09d58ee8f64961d213d208f865e3"
COUNTS = {"deterministic": 140, "retrieval": 160, "answers": 150, "production": 60}
DETERMINISTIC_CONTRACT = "query-plan-grounded-outcome-v8"

MANUAL_PROMPTS = (
    "mấy điểm mới qua môn",
    "mức tiền học bổng xuất sắc nhận được là gì",
    "điều kiện để được xét học bổng khuyến khích học tập là gì",
    "đối tượng nào được giảm học phí",
    "phòng công tác sinh viên ở đâu",
    "sdt của pdt là gì",
    "các lý do dẫn đến cbht và nếu tôi dc 2 kỳ liên tiếp gpa và điểm rèn luyện xuất sắc thì dc gì",
)

QUERY_OVERRIDES = {
    "v8_det_118": (
        "Mình chỉ nhớ khóa của mình thuộc nhóm K5x; cần xác định K50 hay K51 "
        "trước khi tra quy định này?"
    ),
    "v8_ret_023": (
        "K48–K49: sau khi được thông báo chỉ tiêu, cơ sở đào tạo giáo viên "
        "có trách nhiệm tuyển sinh và đào tạo như thế nào?"
    ),
    "v8_ret_048": (
        "Việc chấm điểm rèn luyện cho sinh viên K51 phải bảo đảm những nguyên tắc nào?"
    ),
    "v8_ret_061": (
        "Ở K51, ai chịu trách nhiệm phổ biến và giám sát việc thực hiện Quy tắc ứng xử?"
    ),
    "v8_ret_081": (
        "Khi đã có chỉ tiêu hằng năm, cơ sở đào tạo phải thông báo gì cho thí sinh "
        "trúng tuyển ngành sư phạm K50?"
    ),
    "v8_ret_083": (
        "Cuối học kỳ chính, những ngưỡng tín chỉ và điểm nào khiến sinh viên chính quy "
        "K51 bị cảnh báo học tập?"
    ),
    "v8_ans_unanswerable_002": (
        "Ngân hàng đã ghi có khoản học bổng của riêng em vào chính xác lúc nào?"
    ),
    "v8_ans_ood_001": "Chỉ mình cách căn giữa một nút bằng CSS.",
}


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-zA-Z0-9\s]", " ", text.lower())).strip()


def no_diacritics(value: str) -> str:
    value = value.replace("Đ", "D").replace("đ", "d")
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()


def lower_sentence_start(value: str) -> str:
    if len(value) > 1 and value[0].isupper() and value[1].isupper():
        return value
    return value[:1].lower() + value[1:]


def _primary_judgments(case: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in case.get("relevance_judgments") or case.get("gold_evidence") or []
        if int(item.get("grade") or 2) == 2
    ]


def _compact_fields(value: dict[str, Any], *, limit: int = 8) -> dict[str, Any]:
    rows = value.get("rows")
    source = rows[0] if isinstance(rows, list) and len(rows) == 1 else value
    ignored = {
        "raw_text",
        "raw_excerpt",
        "summary",
        "source_provenance",
        "source_pages",
        "document_id",
        "content_type",
        "quality_status",
        "embedding_enabled",
        "retrieval_mode",
    }
    result: dict[str, Any] = {}
    for key, item in source.items():
        if (
            key in ignored
            or isinstance(item, (dict, list))
            or item is None
            or item == ""
        ):
            continue
        if len(str(item)) > 220:
            continue
        result[key] = item
        if len(result) == limit:
            break
    return result


def _first_scalar(values: Any, default: str) -> str:
    if isinstance(values, dict):
        values = values.values()
    for value in values:
        if isinstance(value, (dict, list)) or value is None or value == "":
            continue
        return str(value)
    return default


def _public_row_fact(row: dict[str, Any]) -> str:
    return "; ".join(
        f"{key}: {value}"
        for key, value in row.items()
        if not isinstance(value, (dict, list)) and value is not None and value != ""
    )


def _field_from_fact(fact: str) -> str:
    match = re.search(r"—\s*([a-z]+)\s*:", fact, flags=re.IGNORECASE)
    return match.group(1).lower() if match else "office"


def _structured_query(case: dict[str, Any], index: int) -> str:
    group = str(case.get("lookup_group") or "")
    cohort = str(case["cohort"])
    evidence = (case.get("gold_evidence") or [{}])[0]
    rows = evidence.get("rows") or []
    row = rows[0] if rows else evidence
    if group == "foreign_language":
        certificate = row.get("certificate") or row.get("level_or_scale")
        variants = (
            f"{certificate} tương ứng bậc 3 và bậc 4 ở bảng áp dụng cho {cohort} thế nào?",
            f"Em thuộc {cohort}, cho em hai mức quy đổi của chứng chỉ {certificate}.",
            f"Tra đúng dòng {certificate}: chuẩn bậc 3 và bậc 4 là bao nhiêu?",
        )
        return variants[index % len(variants)]
    if group == "study_duration":
        label = _first_scalar(row, "trường hợp này")
        scope_text = norm(
            f"{evidence.get('table_id') or ''} {evidence.get('applicability') or ''}"
        )
        mode = "vừa làm vừa học" if "vua lam vua hoc" in scope_text else "chính quy"
        subject = f"chương trình {label.lower()}"
        if norm(label) in {"chinh quy", "vua lam vua hoc"}:
            subject = "chương trình tương ứng"
        return f"Sinh viên {cohort} học hệ {mode}, {subject} có thời gian chuẩn và tối đa bao lâu?"
    if group == "scholarship_classification":
        subtype = str(evidence.get("table_subtype") or "")
        if subtype == "scholarship_amount":
            level = row.get("scholarship_level") or row.get("Mức học bổng")
            return f"Học bổng mức {level} của {cohort} được nhân hệ số nào và dựa trên mức học phí nào?"
        if subtype == "scholarship_classification":
            label = (
                row.get("scholarship_level")
                or row.get("Mức học bổng")
                or row.get("label")
            )
            return f"Bảng xếp loại học bổng {cohort} quy định mức {label} cần kết quả gì?"
        criterion = _first_scalar(row, "tiêu chí này")
        return f"Trong điều kiện xét học bổng của {cohort}, mục {criterion.lower()} yêu cầu cụ thể gì?"
    if group == "scoring":
        questions = (
            "Một học phần nền tảng K51 đạt 8,1 thì nhận điểm chữ gì?",
            "Môn còn lại của K51 được 5,0 thì quy ra chữ nào và có đạt không?",
            "Sinh viên K50 được 7,4 điểm học phần thì thuộc mức điểm chữ nào?",
            "Điểm môn học 4,3 ở K48–K49 được đổi sang điểm chữ gì?",
            "Trong thang điểm K51, B+ có giá trị hệ 4 là mấy?",
            "Ở bảng K50, điểm F tương ứng bao nhiêu điểm hệ 4?",
            "GPA 3,55 của K51 được xếp loại học lực nào?",
            "GPA 0,80 ở K48–K49 thuộc loại học lực gì?",
        )
        return questions[index % len(questions)]
    if group == "conduct":
        scores = (33, 51, 68, 82, 87, 97)
        return f"Nếu có {scores[index % len(scores)]} điểm rèn luyện ở {cohort} thì xếp loại gì?"
    if group == "formula":
        if evidence.get("rule_id") == "scholarship_score":
            return "Điểm dùng để xếp hạng học bổng được ghép từ điểm học tập và rèn luyện theo công thức nào?"
        return "Khi tính GPA có tín chỉ, tử số và mẫu số của công thức được lập ra sao?"
    if group in {"office", "faculty"}:
        name = str(
            evidence.get("unit_name")
            or evidence.get("faculty_name")
            or evidence.get("unit")
        )
        field = _field_from_fact(str((case.get("required_facts") or [""])[0]))
        labels = {
            "email": "email",
            "phone": "số điện thoại",
            "website": "website",
            "office": "địa chỉ làm việc",
        }
        return f"Cho em xin {labels.get(field, 'thông tin liên hệ')} của {name} theo danh bạ {cohort}."
    if group == "program":
        return f"Theo danh mục {cohort}, ngành {evidence['program_name']} do khoa nào quản lý?"
    if group == "student_service":
        service = str(evidence.get("service") or "dịch vụ này").rstrip(".;")
        return f"Em muốn {service[0].lower() + service[1:]}; bộ phận nào phụ trách việc này?"
    return f"Em cần tra cứu nội dung sau cho {cohort}: {case['query']}"


def _rag_question(case: dict[str, Any], index: int, *, answer: bool = False) -> str:
    def finish(query: str) -> str:
        if not answer:
            return query
        return f"Tóm tắt ngắn gọn cho em: {query[0].lower() + query[1:]}"

    primary = _primary_judgments(case)
    cohort = str(case.get("cohort") or "general")
    if not primary:
        return f"Xin giải đáp rõ giúp em: {case['query']}"
    sections = [str(item.get("source_section") or "quy định liên quan") for item in primary]
    articles = [str(item.get("article") or "Điều liên quan").rstrip(".") for item in primary]
    subtype = str(case.get("retrieval_subtype") or "")
    if subtype == "multi_cohort_equivalent" or cohort == "general":
        document = str(primary[0].get("document_title") or "văn bản tương ứng")
        document = re.sub(
            r"\s+(?:tại|của)\s+Trường Đại học Sư phạm.*$",
            "",
            document,
            flags=re.IGNORECASE,
        ).strip()
        return finish(
            f"Trong {document}, phần {sections[0].lower()} có điểm chung nào áp dụng từ K48 đến K51?"
        )
    if subtype == "graph_linked" and len((case.get("relevance_judgments") or [])) >= 2:
        support = (case.get("relevance_judgments") or [])[1]
        return finish(
            f"Ở {cohort}, khi đọc {articles[0]} về {sections[0].lower()}, "
            f"em cần đối chiếu thêm {str(support.get('article') or 'điều được dẫn').rstrip('.')} như thế nào?"
        )
    if subtype == "multi_source" and len(sections) >= 2:
        labels = [section.lower() for section in sections[:2]]
        if norm(labels[0]) == norm(labels[1]):
            labels = [
                f"{labels[item_index]} trong "
                f"{str(primary[item_index].get('document_title') or articles[item_index]).strip()}"
                for item_index in range(2)
            ]
        return finish(
            f"Em thuộc {cohort} và đang cần hai việc riêng: {labels[0]} và {labels[1]}. "
            "Mỗi việc được quy định ra sao?"
        )
    if subtype == "exact_article":
        return finish(
            f"Em đang xem {articles[0]} dành cho {cohort}; phần {sections[0].lower()} nói cụ thể điều gì?"
        )
    section = sections[0].lower()
    variants = (
        f"Sinh viên {cohort} cần hiểu gì về phần {section}?",
        f"Phần {section} dành cho {cohort} nêu những gì?",
        f"Ở {cohort}, {section} được quy định thế nào?",
        f"Ở {cohort}, phần {section} có những lưu ý nào?",
    )
    query = variants[index % len(variants)]
    if subtype == "typo_no_diacritics" and not answer:
        return no_diacritics(query)
    return finish(query)


def _manual_queries(case_type: str) -> tuple[str, ...]:
    values = {
        "missing_or_ambiguous": (
            "Em chọn K51 nhưng lại ghi mình tuyển sinh năm 2024, vậy phải tra theo khóa nào?",
            "TOEIC bốn kỹ năng của em mới có Nghe, Đọc và Nói; đã quy đổi bậc được chưa?",
            "Cho mình địa chỉ của đơn vị đó với.",
            "Khoản hỗ trợ vừa nhắc được tính theo tháng hay theo học kỳ vậy?",
            "Đổi số điểm vừa nói sang thang còn lại giúp mình.",
            "Mình muốn xem quy định này nhưng chưa xác định thuộc K50 hay K51.",
            "Gửi mình thông tin liên hệ của hai chỗ đó.",
            "Chứng chỉ ngoại ngữ còn hiệu lực không nếu chưa biết ngày cấp?",
            "Điều 12 em hỏi thuộc quy chế đào tạo hay quy chế công tác sinh viên?",
            "So sánh thời gian học giữa hai khóa, nhưng em chưa chọn khóa nào.",
            "Cho mình email Thư viện, khoa quản lý ngành Vật lý, bảng TOEFL và thủ tục bảo lưu.",
            "Mình cần điểm GPA, số điện thoại Khoa Toán, các ngành của Khoa Hóa và quy định thôi học.",
        ),
        "unsupported_in_domain": (
            "Hồ sơ miễn học phần ngoại ngữ của em hiện được duyệt tới bước nào rồi?",
            "Khoản học bổng cá nhân của em đã được chuyển chưa?",
            "Lớp học phần sáng mai còn bao nhiêu chỗ trống ngay lúc này?",
            "Bài thi của em đang do giảng viên nào chấm?",
            "Ca trực hiện tại của Trạm Y tế có những ai?",
            "Em có thể giữ ngay một chỗ trống trong ký túc xá không?",
            "Kiểm tra giúp giao dịch đóng học phí mới nhất của tài khoản em.",
            "Lớp em hiện có những bạn nào đang bị kỷ luật?",
        ),
        "out_of_domain": (
            "Viết cho mình một hàm Python sắp xếp danh sách.",
            "Tối nay nên nấu món gì nhanh và ít cay?",
            "Kể ngắn gọn nội dung một phim hoạt hình nổi tiếng.",
            "Xe máy hết bình giữa đường thì xử lý thế nào?",
            "Giá cổ phiếu công nghệ hôm nay tăng hay giảm?",
            "Giải phương trình x bình trừ 5x cộng 6 bằng 0.",
            "Viết caption khai trương tiệm cà phê.",
            "Tạo migration cho một bảng PostgreSQL như thế nào?",
        ),
    }
    return values[case_type]


def _answer_manual_queries(case_type: str) -> tuple[str, ...]:
    values = {
        "clarification": (
            "Em đang chọn K51 nhưng năm nhập học lại là 2024; cần dùng thông tin nào để tra?",
            "Chứng chỉ TOEIC của em mới có ba điểm Nghe, Đọc, Nói thì đã đủ dữ liệu quy đổi chưa?",
            "Mình muốn hỏi địa chỉ của đơn vị vừa được nhắc đến.",
            "Khoản hỗ trợ ở câu trước được tính theo tháng hay theo học kỳ?",
            "Hãy đổi mức điểm vừa nêu sang thang điểm tương ứng.",
            "Em chưa chắc mình thuộc K50 hay K51 nhưng muốn xem quy định đó.",
            "Cho mình thông tin liên hệ của cả hai đơn vị vừa nói.",
            "Em chưa nhớ ngày cấp chứng chỉ; có xác định được chứng chỉ còn hiệu lực không?",
        ),
        "unanswerable": (
            "Xem giúp hồ sơ xin miễn ngoại ngữ của riêng em đang ở công đoạn nào.",
            "Tiền học bổng của em đã chuyển vào tài khoản chưa?",
            "Hiện giờ lớp học phần sáng mai còn chính xác bao nhiêu chỗ?",
            "Cho em biết ai đang trực tiếp chấm bài thi của em.",
            "Danh sách nhân viên đang trực tại Trạm Y tế lúc này gồm những ai?",
            "Giữ ngay giúp em một chỗ còn trống trong ký túc xá.",
        ),
        "out_of_domain": (
            "Hướng dẫn mình viết hàm Python để sắp xếp một danh sách.",
            "Gợi ý một món ăn tối làm nhanh và không cay.",
            "Tóm tắt cốt truyện của một bộ phim hoạt hình nổi tiếng.",
            "Xe máy bị hết bình giữa đường thì nên làm gì trước?",
            "Thị trường cổ phiếu công nghệ hôm nay biến động ra sao?",
            "Giúp mình giải phương trình x² - 5x + 6 = 0.",
        ),
    }
    return values[case_type]


def _set_task_cohort(case: dict[str, Any], cohort: str) -> None:
    for outcome in case.get("accepted_outcomes") or []:
        for task in outcome.get("required_tasks") or []:
            task["cohorts"] = [cohort]


def _contact_value(record: dict[str, Any], field: str) -> Any:
    plural = {"phone": "phones", "email": "emails", "website": "websites"}.get(
        field
    )
    value = record.get(field)
    if value:
        return value
    values = record.get(plural) if plural else None
    return values[0] if isinstance(values, list) and values else None


def _balanced_records(
    records: list[dict[str, Any]],
    *,
    key: str,
    catalog: str,
    count: int,
    used_source_ids: set[str],
) -> list[dict[str, Any]]:
    by_cohort: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[str] = set()
    for record in sorted(
        records,
        key=lambda item: hashlib.sha256(
            f"v8:{item.get('cohort')}:{item.get(key)}".encode()
        ).hexdigest(),
    ):
        identity = norm(str(record.get(key) or ""))
        if not identity or identity in seen:
            continue
        if catalog == "service":
            source_id = str(record.get("service_id") or "")
            if not 18 <= len(str(record.get("service") or "")) <= 90:
                continue
        else:
            source_id = str(v7.structured_source(record, catalog)["source_id"])
        if not source_id or source_id in used_source_ids:
            continue
        seen.add(identity)
        by_cohort[str(record.get("cohort") or "general")].append(record)

    selected: list[dict[str, Any]] = []
    order = ("K51", "K50", "K48-K49")
    while len(selected) < count and any(by_cohort.values()):
        progressed = False
        for cohort in order:
            if by_cohort[cohort]:
                selected.append(by_cohort[cohort].pop(0))
                progressed = True
                if len(selected) == count:
                    break
        if not progressed:
            break
    if len(selected) != count:
        raise AssertionError(
            f"Not enough unseen {catalog} records: expected {count}, got {len(selected)}"
        )
    return selected


def _historical_structured_source_ids() -> set[str]:
    used: set[str] = set()
    for version in (
        "architecture_v4",
        "architecture_v5_holdout",
        "architecture_v6_holdout",
        "architecture_v7",
    ):
        path = ROOT / "data" / "eval" / version / "deterministic_tool_cases.json"
        if not path.exists():
            continue
        for case in load(path):
            used.update(
                str(source.get("source_id") or "")
                for source in case.get("expected_structured_sources") or []
            )
    used.discard("")
    return used


def _refresh_directory_targets(deterministic: list[dict[str, Any]]) -> None:
    used = _historical_structured_source_ids()
    configs = (
        ("office", v7.OFFICES, "unit_name", "office", 6),
        ("faculty", v7.FACULTIES, "faculty_name", "faculty", 6),
        ("program", v7.PROGRAMS, "program_name", "program", 8),
        ("student_service", v7.SERVICES, "service", "service", 6),
    )
    for lookup_type, path, key, catalog, expected_count in configs:
        cases = [
            case
            for case in deterministic
            if case.get("case_type") == "single_structured"
            and case.get("lookup_group") == lookup_type
        ]
        if len(cases) != expected_count:
            raise AssertionError(
                f"{lookup_type}: expected {expected_count} cases, got {len(cases)}"
            )
        records = _balanced_records(
            load(path),
            key=key,
            catalog=catalog,
            count=expected_count,
            used_source_ids=used,
        )
        for index, (case, record) in enumerate(zip(cases, records)):
            cohort = str(record["cohort"])
            case["cohort"] = cohort
            case["gold_evidence"] = [record]
            _set_task_cohort(case, cohort)
            if lookup_type in {"office", "faculty"}:
                name = str(
                    record.get("unit_name")
                    or record.get("faculty_name")
                    or record.get("unit")
                )
                available = [
                    field
                    for field in ("office", "phone", "email", "website")
                    if _contact_value(record, field)
                ]
                if not available:
                    raise AssertionError(f"No contact field for {name}")
                field = available[index % len(available)]
                value = _contact_value(record, field)
                case["required_facts"] = [f"{name} — {field}: {value}"]
                case["expected_structured_sources"] = [
                    v7.structured_source(record, catalog)
                ]
            elif lookup_type == "program":
                case["required_facts"] = [
                    f"{record['program_name']} thuộc {record['faculty_name']}."
                ]
                case["expected_structured_sources"] = [
                    v7.structured_source(record, "program")
                ]
            else:
                case["required_facts"] = [
                    f"Đơn vị phụ trách: {record['unit_name']}."
                ]
                case["expected_structured_sources"] = [
                    {"catalog": "service", "source_id": str(record["service_id"])}
                ]


def _refresh_foreign_language_rows(deterministic: list[dict[str, Any]]) -> None:
    records = [
        record
        for record in load(v7.TABLES)
        if record.get("table_type") == "foreign_language"
        and record.get("cohort") == "K50"
    ]
    if len(records) != 1:
        raise AssertionError("Expected one validated foreign-language reference table")
    record = records[0]
    rows = record.get("rows") or []
    # Prefer rows not exercised by V7, then retain two stable boundary rows so
    # English and Chinese coverage are not lost from the capability suite.
    row_indices = (4, 5, 8, 9, 0, 6)
    cases = [
        case
        for case in deterministic
        if case.get("case_type") == "single_structured"
        and case.get("lookup_group") == "foreign_language"
    ]
    if len(cases) != len(row_indices) or max(row_indices) >= len(rows):
        raise AssertionError("Foreign-language V8 row selection is incomplete")
    for case, row_index in zip(cases, row_indices):
        row = rows[row_index]
        case["gold_evidence"] = [{**record, "rows": [row]}]
        case["required_facts"] = [_public_row_fact(row)]
        case["expected_structured_sources"] = [
            v7.structured_source(record, "foreign_language")
        ]


def _refresh_compounds(deterministic: list[dict[str, Any]]) -> None:
    singles_by_cohort = {
        cohort: [
            case
            for case in deterministic
            if case.get("case_type") == "single_structured"
            and case.get("cohort") == cohort
        ]
        for cohort in ("K48-K49", "K50", "K51")
    }
    boundaries_by_cohort = {
        cohort: [
            case
            for case in deterministic
            if case.get("case_type") == "capability_boundary"
            and case.get("cohort") == cohort
        ]
        for cohort in ("K48-K49", "K50", "K51")
    }
    structured_index = 0
    mixed_index = 0
    for case in deterministic:
        if case.get("case_type") != "compound":
            continue
        is_mixed = case.get("expected_group") == "mixed"
        index = mixed_index if is_mixed else structured_index
        cohort = ("K51", "K50", "K48-K49")[index % 3]
        pool = singles_by_cohort[cohort]
        if is_mixed:
            structured = pool[(index * 7 + 3) % len(pool)]
            boundary_pool = boundaries_by_cohort[cohort]
            boundary = boundary_pool[(index * 5 + 2) % len(boundary_pool)]
            required_tasks = deepcopy(
                structured["accepted_outcomes"][0]["required_tasks"]
            ) + [v7.task_gold("rag", cohorts=[cohort])]
            case["accepted_outcomes"] = [v7.answer_outcome(required_tasks)]
            case["gold_evidence"] = deepcopy(structured["gold_evidence"]) + deepcopy(
                boundary["gold_evidence"]
            )
            case["rag_judgments"] = deepcopy(boundary["gold_evidence"])
            case["required_facts"] = list(structured["required_facts"]) + list(
                boundary["required_facts"]
            )
            case["expected_structured_sources"] = deepcopy(
                structured["expected_structured_sources"]
            )
            case["v8_component_ids"] = [structured["id"], boundary["id"]]
            mixed_index += 1
        else:
            task_count = len(
                case["accepted_outcomes"][0].get("required_tasks") or []
            )
            selected: list[dict[str, Any]] = []
            used_groups: set[str] = set()
            cursor = (index * 7 + 1) % len(pool)
            for offset in range(len(pool) * 2):
                candidate = pool[(cursor + offset * 5) % len(pool)]
                group = str(candidate.get("lookup_group") or "")
                if group in used_groups:
                    continue
                selected.append(candidate)
                used_groups.add(group)
                if len(selected) == task_count:
                    break
            if len(selected) != task_count:
                raise AssertionError("Unable to build distinct V8 compound")
            tasks = [
                deepcopy(item["accepted_outcomes"][0]["required_tasks"][0])
                for item in selected
            ]
            case["accepted_outcomes"] = [v7.answer_outcome(tasks)]
            case["gold_evidence"] = [
                deepcopy(evidence)
                for item in selected
                for evidence in item["gold_evidence"]
            ]
            case["required_facts"] = [
                fact for item in selected for fact in item["required_facts"]
            ]
            case["expected_structured_sources"] = [
                deepcopy(source)
                for item in selected
                for source in item["expected_structured_sources"]
            ]
            case["v8_component_ids"] = [item["id"] for item in selected]
            structured_index += 1
        case["cohort"] = cohort
        case["cohort_sensitivity"] = "single_cohort"


def _add_grounded_assertions(case: dict[str, Any]) -> None:
    sources = list(case.get("expected_structured_sources") or [])
    evidence = [
        item
        for item in case.get("gold_evidence") or []
        if not item.get("parent_section_id") or item.get("content_type") != "regulation_text"
    ]
    required_tasks = [
        task
        for outcome in case.get("accepted_outcomes") or []
        for task in outcome.get("required_tasks") or []
        if task.get("mode") == "structured"
    ]
    for index, task in enumerate(required_tasks):
        source = sources[index] if index < len(sources) else {}
        item = evidence[index] if index < len(evidence) else {}
        source_id = str(source.get("source_id") or "")
        if task.get("lookup_type") == "student_service" and item.get("service_id"):
            source_id = str(item["service_id"])
        if source_id:
            task["expected_source_ids"] = [source_id]
        fields = _compact_fields(item)
        if fields:
            task["expected_evidence_fields"] = fields
        subtype = str(item.get("table_subtype") or "")
        if task.get("lookup_type") in {
            "foreign_language",
            "scoring",
            "study_duration",
        } or subtype in {
            "scholarship_amount",
            "scholarship_classification",
        }:
            row_fields = _compact_fields(item)
            if row_fields:
                task["expected_resolved_fields"] = row_fields
                task["resolved_result_required"] = True


def _rekey_all(datasets: dict[str, list[dict[str, Any]]]) -> None:
    id_map = {
        case["id"]: str(case["id"]).replace("v7_", "v8_", 1)
        for cases in datasets.values()
        for case in cases
    }

    def replace(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: replace(item) for key, item in value.items()}
        if isinstance(value, list):
            return [replace(item) for item in value]
        if isinstance(value, str):
            if value in id_map:
                return id_map[value]
            return value.replace("v7_link_", "v8_link_").replace(
                "architecture_v7_draft", "architecture_v8_holdout"
            )
        return value

    for suite, cases in datasets.items():
        datasets[suite] = [replace(case) for case in cases]


def _rewrite_queries(
    datasets: dict[str, list[dict[str, Any]]], *, frozen: bool
) -> None:
    deterministic = datasets["deterministic"]
    deterministic_by_id = {case["id"]: case for case in deterministic}
    counters: Counter[str] = Counter()
    group_counters: Counter[str] = Counter()
    for case in deterministic:
        case_type = str(case["case_type"])
        index = counters[case_type]
        counters[case_type] += 1
        if case_type == "single_structured":
            group = str(case.get("lookup_group") or "")
            group_index = group_counters[group]
            group_counters[group] += 1
            case["query"] = _structured_query(case, group_index)
        elif case_type == "capability_boundary":
            source = (case.get("gold_evidence") or [{}])[0]
            article = str(source.get("article") or "Điều liên quan").rstrip(".")
            section = str(source.get("source_section") or "nội dung này").lower()
            case["query"] = f"Em thuộc {case['cohort']} và muốn đọc đúng {article}; phần {section} có các ý chính nào?"
        elif case_type == "compound":
            parts = [
                str(deterministic_by_id[case_id]["query"]).rstrip("?.")
                for case_id in case.get("v8_component_ids") or []
            ]
            labels = ("Thứ nhất", "Thứ hai", "Thứ ba")
            case["query"] = "Mình có các câu hỏi độc lập. " + " ".join(
                f"{labels[part_index]}: {lower_sentence_start(part)}?"
                for part_index, part in enumerate(parts)
            )
        elif case_type in {"missing_or_ambiguous", "unsupported_in_domain", "out_of_domain"}:
            case["query"] = _manual_queries(case_type)[index]
        case["query"] = QUERY_OVERRIDES.get(case["id"], case["query"])
        case["contract_version"] = DETERMINISTIC_CONTRACT
        case["author_review_state"] = (
            "reviewed_before_execution" if frozen else "draft_pending_review"
        )
        case["frozen"] = frozen
        _add_grounded_assertions(case)
        if case_type == "single_structured":
            case["near_duplicate_reviewed"] = True
            case["near_duplicate_rationale"] = (
                "Repeated capability wording is intentional; the grounded "
                "row, value, entity, cohort or structured source is distinct."
            )

    retrieval = datasets["retrieval"]
    for index, case in enumerate(retrieval):
        case["query"] = _rag_question(case, index)
        case["query"] = QUERY_OVERRIDES.get(case["id"], case["query"])
        case["contract_version"] = "regulation-retrieval-grounded-holdout-v8"
        case["query_origin"] = "v8_source_taxonomy_authoring"
        state = "reviewed_before_execution" if frozen else "draft_pending_review"
        case["annotation_status"] = state
        case["author_review_state"] = state
        case["frozen"] = frozen

    answers = datasets["answers"]
    manual_counters: Counter[str] = Counter()
    det_by_id = {case["id"]: case for case in deterministic}
    for index, case in enumerate(answers):
        case_type = str(case["case_type"])
        linked = (case.get("linked_source_case_ids") or [None])[0]
        source_case = det_by_id.get(linked)
        if case_type in {"structured_answer", "mixed_answer"} and source_case:
            case["cohort"] = source_case["cohort"]
            case["required_facts"] = deepcopy(source_case["required_facts"])
            case["ground_truth"] = "\n".join(
                f"- {fact}" for fact in case["required_facts"]
            )
            case["expected_structured_sources"] = deepcopy(
                source_case.get("expected_structured_sources") or []
            )
            if case_type == "mixed_answer":
                judgments = deepcopy(source_case.get("rag_judgments") or [])
                case["relevance_judgments"] = judgments
                case["expected_citations"] = deepcopy(judgments)
            else:
                case["lookup_group"] = source_case.get("lookup_group")
        if case_type == "regulation_true_rag":
            case["query"] = _rag_question(case, index, answer=True)
        elif case_type in {"structured_answer", "mixed_answer"} and linked in det_by_id:
            source_query = str(det_by_id[linked]["query"])
            if case_type == "mixed_answer":
                case["query"] = source_query.replace(
                    "Mình có các câu hỏi độc lập.",
                    "Giải đáp lần lượt giúp em.",
                    1,
                )
            else:
                case["query"] = (
                    "Tra cứu rồi trả lời ngắn gọn: "
                    + lower_sentence_start(source_query)
                )
        elif case_type == "clarification":
            idx = manual_counters[case_type]
            manual_counters[case_type] += 1
            case["query"] = _answer_manual_queries(case_type)[idx]
        elif case_type == "unanswerable":
            idx = manual_counters[case_type]
            manual_counters[case_type] += 1
            case["query"] = _answer_manual_queries(case_type)[idx]
        elif case_type == "out_of_domain":
            idx = manual_counters[case_type]
            manual_counters[case_type] += 1
            case["query"] = _answer_manual_queries(case_type)[idx]
        case["query"] = QUERY_OVERRIDES.get(case["id"], case["query"])
        case["contract_version"] = "answer-quality-grounded-holdout-v8"
        state = "reviewed_before_execution" if frozen else "draft_pending_review"
        case["annotation_status"] = state
        case["author_review_state"] = state
        case["frozen"] = frozen

    production = datasets["production"]
    answer_by_id = {case["id"]: case for case in answers}
    production_by_id: dict[str, dict[str, Any]] = {}
    for index, case in enumerate(production):
        source = answer_by_id.get(str(case.get("linked_answer_case_id") or ""))
        if case.get("repeat_of") in production_by_id:
            repeated = production_by_id[str(case["repeat_of"])]
            case["query"] = repeated["query"]
            case["cohort"] = repeated["cohort"]
        else:
            base = str(source["query"] if source else case["query"])
            for prefix in (
                "Tra cứu rồi trả lời ngắn gọn: ",
                "Tóm tắt ngắn gọn cho em: ",
                "Giải đáp lần lượt giúp em. ",
            ):
                if base.startswith(prefix):
                    base = base[len(prefix) :]
                    break
            prefixes = ("Mình cần hỏi: ", "Cho em tra nhanh: ", "Nhờ giải đáp: ")
            case["query"] = prefixes[index % len(prefixes)] + lower_sentence_start(base)
            if source:
                case["cohort"] = source["cohort"]
        case["contract_version"] = "production-contract-holdout-v8"
        case["author_review_state"] = (
            "reviewed_before_execution" if frozen else "draft_pending_review"
        )
        case["frozen"] = frozen
        production_by_id[str(case["id"])] = case

    stress_targets = {"deterministic": 28, "retrieval": 32, "answers": 30}
    priorities = {
        "deterministic": {"missing_or_ambiguous": 0, "compound": 1, "single_structured": 2},
        "retrieval": {"graph_linked": 0, "multi_source": 1},
        "answers": {"mixed_answer": 0, "clarification": 1, "unanswerable": 2, "out_of_domain": 3},
    }
    for suite, count in stress_targets.items():
        cases = datasets[suite]
        ranked = sorted(
            range(len(cases)),
            key=lambda idx: (
                priorities[suite].get(
                    str(cases[idx].get("case_type") or cases[idx].get("retrieval_subtype")),
                    9,
                ),
                idx,
            ),
        )
        stress_ids = {cases[idx]["id"] for idx in ranked[:count]}
        for case in cases:
            stress = case["id"] in stress_ids
            case["eval_split"] = "stress" if stress else "realistic"
            case["question_style"] = "stress" if stress else "realistic"


def _source_ids(case: dict[str, Any]) -> set[str]:
    values = case.get("relevance_judgments") or case.get("gold_evidence") or []
    return {
        str(item.get("parent_section_id") or item.get("source_id") or "")
        for item in values
        if isinstance(item, dict)
    } - {""}


def _historical_queries() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    dataset_filenames = (
        "deterministic_tool_cases.json",
        "retrieval_cases.json",
        "generated_answer_cases.json",
        "production_cases.json",
    )
    paths = [
        ROOT / "data" / "eval" / version / filename
        for version in (
            "architecture_v4",
            "architecture_v5_holdout",
            "architecture_v6_holdout",
            "architecture_v7",
        )
        for filename in dataset_filenames
    ]
    paths.extend(
        ROOT / "data" / "eval" / suite / "cases.json"
        for suite in ("product_regression", "product_acceptance")
    )
    for path in paths:
        if not path.exists():
            continue
        try:
            value = load(path)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, dict) and str(item.get("query") or "").strip():
                rows.append(
                    {
                        "query": str(item["query"]),
                        "normalized": norm(str(item["query"])),
                        "id": str(item.get("id") or ""),
                        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                        "source_ids": sorted(_source_ids(item)),
                    }
                )
    smoke_path = ROOT / "scripts" / "evaluate_query_plan_smoke.py"
    smoke_tree = ast.parse(smoke_path.read_text(encoding="utf-8"))
    for node in smoke_tree.body:
        if not isinstance(node, ast.AnnAssign):
            continue
        if not isinstance(node.target, ast.Name) or node.target.id != "CASES":
            continue
        smoke_cases = ast.literal_eval(node.value)
        rows.extend(
            {
                "query": str(case["query"]),
                "normalized": norm(str(case["query"])),
                "id": f"smoke_{case['id']}",
                "path": "scripts/evaluate_query_plan_smoke.py",
                "source_ids": [],
            }
            for case in smoke_cases
        )
        break
    rows.extend(
        {
            "query": query,
            "normalized": norm(query),
            "id": f"manual_{index:02d}",
            "path": "manual_prompt_inventory",
            "source_ids": [],
        }
        for index, query in enumerate(MANUAL_PROMPTS, start=1)
    )
    return rows


def overlap_audit(
    datasets: dict[str, list[dict[str, Any]]], *, semantic: bool
) -> dict[str, Any]:
    history = _historical_queries()
    current = [
        {"id": case["id"], "suite": suite, "query": case["query"]}
        for suite, cases in datasets.items()
        for case in cases
    ]
    historical_tokens = [set(item["normalized"].split()) for item in history]
    rows: list[dict[str, Any]] = []
    for item in current:
        normalized = norm(item["query"])
        tokens = set(normalized.split())
        # Character matching is substantially more expensive than token overlap.
        # Compute it only for the strongest token candidates; exact matches are
        # still checked independently against the full historical inventory.
        token_candidates = sorted(
            (
                (
                    len(tokens & old_tokens) / max(1, len(tokens | old_tokens)),
                    old,
                )
                for old, old_tokens in zip(history, historical_tokens)
            ),
            key=lambda value: value[0],
            reverse=True,
        )[:30]
        scored = sorted(
            (
                (
                    jaccard,
                    SequenceMatcher(None, normalized, old["normalized"]).ratio(),
                    old,
                )
                for jaccard, old in token_candidates
            ),
            key=lambda value: max(value[0], value[1]),
            reverse=True,
        )[:3]
        rows.append(
            {
                **item,
                "exact_historical_matches": [
                    {"id": old["id"], "path": old["path"]}
                    for old in history
                    if old["normalized"] == normalized
                ],
                "nearest_lexical": [
                    {
                        "token_jaccard": round(jaccard, 4),
                        "sequence_ratio": round(sequence, 4),
                        "query": old["query"],
                        "id": old["id"],
                        "path": old["path"],
                    }
                    for jaccard, sequence, old in scored
                ],
            }
        )

    semantic_model = None
    if semantic:
        import numpy as np
        from huggingface_hub import snapshot_download
        from sentence_transformers import SentenceTransformer

        semantic_model = "BAAI/bge-m3"
        local_model_path = snapshot_download(semantic_model, local_files_only=True)
        model = SentenceTransformer(local_model_path, local_files_only=True)
        current_vectors = model.encode(
            [item["query"] for item in current], normalize_embeddings=True
        )
        history_vectors = model.encode(
            [item["query"] for item in history], normalize_embeddings=True
        )
        similarities = np.asarray(current_vectors) @ np.asarray(history_vectors).T
        for row, scores in zip(rows, similarities):
            indices = np.argsort(scores)[-3:][::-1]
            row["nearest_semantic"] = [
                {
                    "cosine": round(float(scores[index]), 4),
                    "query": history[int(index)]["query"],
                    "id": history[int(index)]["id"],
                    "path": history[int(index)]["path"],
                }
                for index in indices
            ]
            row["semantic_review_required"] = bool(scores[int(indices[0])] >= 0.90)
    else:
        for row in rows:
            row["nearest_semantic"] = []
            row["semantic_review_required"] = None

    by_normalized: dict[str, set[str]] = defaultdict(set)
    for item in current:
        by_normalized[norm(item["query"])].add(item["suite"])
    internal_cross_suite_exact_count = sum(
        len(suites) > 1 for suites in by_normalized.values()
    )

    return {
        "schema_version": "architecture-v8-overlap-audit-v1",
        "historical_query_count": len(history),
        "v8_case_count": len(current),
        "exact_historical_match_count": sum(bool(row["exact_historical_matches"]) for row in rows),
        "internal_cross_suite_exact_count": internal_cross_suite_exact_count,
        "lexical_review_count": sum(
            bool(row["nearest_lexical"])
            and max(
                row["nearest_lexical"][0]["token_jaccard"],
                row["nearest_lexical"][0]["sequence_ratio"],
            )
            >= 0.82
            for row in rows
        ),
        "semantic_model": semantic_model,
        "semantic_review_count": (
            sum(bool(row["semantic_review_required"]) for row in rows)
            if semantic
            else None
        ),
        "policy": "Exact historical matches are forbidden. Lexical and semantic similarity are review signals because the corpus and policy topics are finite.",
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
        selected.extend(
            sorted(
                by_type[case_type],
                key=lambda case: hashlib.sha256(case["id"].encode()).hexdigest(),
            )[:count]
        )
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
    lines = [
        "# Architecture V8 — Pre-run review casebook",
        "",
        "> Dataset mới cho runtime 09b1d3da; tài liệu này không chứa output của hệ thống.",
        "",
        "## Phân bố",
        "",
    ]
    for suite, cases in datasets.items():
        counts = Counter(case["eval_split"] for case in cases)
        lines.append(
            f"- `{suite}`: {len(cases)} case; realistic={counts['realistic']}; stress={counts['stress']}."
        )
    lines.extend(
        [
            "",
            "## Overlap",
            "",
            f"- Exact historical: {overlap['exact_historical_match_count']}",
            f"- Lexical review flags: {overlap['lexical_review_count']}",
            f"- Semantic review flags: {overlap['semantic_review_count']}",
            "",
            "## Toàn bộ câu hỏi và gold target",
            "",
            "| Suite | ID | Split | Cohort | Câu hỏi | Gold target |",
            "|---|---|---|---|---|---|",
        ]
    )
    for suite, cases in datasets.items():
        for case in cases:
            if suite == "retrieval":
                gold = ", ".join(
                    item["parent_section_id"]
                    for item in case.get("relevance_judgments") or []
                    if item.get("grade") == 2
                )
            elif suite == "deterministic":
                gold = ", ".join(
                    source.get("source_id", "")
                    for source in case.get("expected_structured_sources") or []
                ) or str(case.get("expected_group") or "")
            elif suite == "answers":
                gold = " / ".join(str(value) for value in case.get("required_facts") or [])
            else:
                gold = str(case.get("scenario") or "")
            query = re.sub(r"\s+", " ", str(case["query"])).replace("|", "\\|")
            gold = re.sub(r"\s+", " ", gold).replace("|", "\\|")
            if len(gold) > 220:
                gold = gold[:219].rstrip() + "…"
            lines.append(
                f"| `{suite}` | `{case['id']}` | `{case['eval_split']}` | "
                f"`{case['cohort']}` | {query} | {gold} |"
            )
    return "\n".join(lines) + "\n"


def build_manifest(
    datasets: dict[str, list[dict[str, Any]]],
    audit: list[dict[str, Any]],
    overlap: dict[str, Any],
    *,
    frozen: bool,
) -> dict[str, Any]:
    deterministic = datasets["deterministic"]
    retrieval = datasets["retrieval"]
    answers = datasets["answers"]
    production = datasets["production"]
    artifacts = (
        v7.TABLES,
        v7.FOREIGN,
        v7.FORMULAS,
        v7.OFFICES,
        v7.FACULTIES,
        v7.PROGRAMS,
        v7.SERVICES,
        v7.GRAPH,
    )
    return {
        "bundle": "architecture_v8",
        "schema_version": "architecture-evaluation-v8",
        "version": "8.0.0",
        "revision": 1,
        "frozen": frozen,
        "review_state": (
            "pre_run_codex_reviewed_owner_authorized"
            if frozen
            else "draft_pending_overlap_and_content_review"
        ),
        "authored_against_runtime_commit": RUNTIME_COMMIT,
        "evaluated_system_commit": RUNTIME_COMMIT,
        "evaluation_harness_commit": EVALUATOR_COMMIT,
        "benchmark_run_kind": "frozen_internal_holdout",
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
        "deterministic_lookup_group_counts": dict(
            Counter(
                case["lookup_group"]
                for case in deterministic
                if case["case_type"] == "single_structured"
            )
        ),
        "retrieval_contract": "regulation-rag-grounded-holdout-v8",
        "retrieval_cohort_counts": dict(Counter(case["cohort"] for case in retrieval)),
        "retrieval_eval_split_counts": dict(Counter(case["eval_split"] for case in retrieval)),
        "retrieval_forbidden_query_fragments": [],
        "evaluation_contract": "comprehensive-grounded-holdout-v8",
        "answer_case_type_counts": dict(Counter(case["case_type"] for case in answers)),
        "answer_eval_split_counts": dict(Counter(case["eval_split"] for case in answers)),
        "answer_path_counts": dict(Counter(case["expected_path"] for case in answers)),
        "answer_rag_cohort_counts": dict(
            Counter(
                case["cohort"]
                for case in answers
                if case["case_type"] == "regulation_true_rag"
            )
        ),
        "answer_structured_lookup_counts": dict(
            Counter(
                case["lookup_group"]
                for case in answers
                if case["case_type"] == "structured_answer"
            )
        ),
        "production_scenario_counts": dict(Counter(case["scenario"] for case in production)),
        "production_request_count": len(production),
        "production_unique_query_count": len({norm(case["query"]) for case in production}),
        "production_metric_scope": "availability, sync/stream payload contract, TTFT/latency, cache, fallback and bounded burst; semantic correctness is measured by answer judge and audit",
        "human_audit_required_n": len(audit),
        "human_audit_repeat_n": 0,
        "human_audit_selection_policy": "pre-output stratified by answer case type; stable SHA256 order; all automatic failures added after scoring",
        "dataset_hashes": {suite: stable_hash(cases) for suite, cases in datasets.items()},
        "auxiliary_hashes": {
            "human_audit_template": stable_hash(audit),
            "overlap_audit": stable_hash(overlap),
        },
        "docstore_path": str(v7.DOCSTORE.relative_to(ROOT)).replace("\\", "/"),
        "docstore_hash": file_hash(v7.DOCSTORE),
        "versions": {
            "query_plan_schema": "v1",
            "query_plan_normalizer": "v20-grounded-scoring-scope",
            "planner_prompt": "structured-regulation-v40-capability-boundaries",
            "composer_prompt": "student-handbook-answer-v3.22-answer-scope",
            "answer_pipeline": "v61-directory-alias-pools",
        },
        "config_hashes": {
            "ai_router": file_hash(ROOT / "configs" / "ai_router.yaml"),
            "structured_lookup_registry": file_hash(ROOT / "configs" / "structured_lookup_registry.yaml"),
            "retrieval": file_hash(ROOT / "configs" / "retrieval.yaml"),
            "answer_generation": file_hash(ROOT / "configs" / "answer_generation.yaml"),
            "slang_dictionary": file_hash(ROOT / "configs" / "hcmue_slang_dictionary.yaml"),
        },
        "artifact_hashes": {
            str(path.relative_to(ROOT)).replace("\\", "/"): file_hash(path)
            for path in artifacts
        },
        "dependency_hashes": {
            name: file_hash(ROOT / name)
            for name in ("requirements.txt", "requirements-eval.txt", "runtime.txt")
        },
        "cache_policy": {
            "router_cache": "disabled_for_evaluation",
            "answer_cache": "new_identity_bound_checkpoint_no_resume",
            "production_warm_cache": "only_declared_repeat_of_pairs",
        },
        "overlap_policy": {
            "exact_historical_query_matches_required": 0,
            "internal_cross_suite_exact_matches_required": 0,
            "lexical_threshold": 0.82,
            "semantic_threshold": 0.90,
            "semantic_similarity_is_review_signal_not_filter": True,
            "same_fixed_corpus_reuse_allowed": True,
        },
        "overlap_summary": {
            "exact": overlap["exact_historical_match_count"],
            "internal_cross_suite_exact": overlap["internal_cross_suite_exact_count"],
            "lexical_review": overlap["lexical_review_count"],
            "semantic_review": overlap["semantic_review_count"],
            "semantic_model": overlap["semantic_model"],
        },
        "system_executed_on_dataset": False,
        "user_review_approved": frozen,
        "limitations": [
            "V8 is an internal frozen holdout over the same three handbooks, not an external public benchmark.",
            "Similarity to historical questions is reviewed rather than automatically rejected because the source corpus and policy targets are finite.",
            "Production 60 is a bounded contract and burst smoke, not a capacity, security or soak benchmark.",
            "For a paper, V8 still needs baselines, ablations, uncertainty intervals and independent reviewer agreement.",
        ],
    }


def build(
    *, semantic_overlap: bool, frozen: bool
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    deterministic, mixed = v7.build_deterministic()
    print("[v8] deterministic gold built", flush=True)
    retrieval = v7.build_retrieval()
    print("[v8] retrieval gold built", flush=True)
    answers = v7.build_answers(deterministic, retrieval, mixed)
    print("[v8] answer gold built", flush=True)
    production = v7.build_production(answers)
    print("[v8] production contract built", flush=True)
    datasets = deepcopy(
        {
            "deterministic": deterministic,
            "retrieval": retrieval,
            "answers": answers,
            "production": production,
        }
    )
    _rekey_all(datasets)
    _refresh_foreign_language_rows(datasets["deterministic"])
    _refresh_directory_targets(datasets["deterministic"])
    _refresh_compounds(datasets["deterministic"])
    _rewrite_queries(datasets, frozen=frozen)
    print("[v8] queries rewritten", flush=True)
    for suite, expected in COUNTS.items():
        if len(datasets[suite]) != expected:
            raise AssertionError(f"{suite}: expected {expected}, got {len(datasets[suite])}")
    overlap = overlap_audit(datasets, semantic=semantic_overlap)
    print("[v8] overlap audit completed", flush=True)
    return datasets, overlap


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-semantic-overlap", action="store_true")
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    if args.freeze and not args.with_semantic_overlap:
        parser.error("--freeze requires --with-semantic-overlap")
    datasets, overlap = build(
        semantic_overlap=args.with_semantic_overlap,
        frozen=args.freeze,
    )
    if args.freeze and (
        overlap["exact_historical_match_count"]
        or overlap["internal_cross_suite_exact_count"]
    ):
        raise SystemExit("Cannot freeze V8 while exact overlap remains")
    audit = audit_template(datasets["answers"])
    manifest = build_manifest(datasets, audit, overlap, frozen=args.freeze)
    filenames = {
        "deterministic": "deterministic_tool_cases.json",
        "retrieval": "retrieval_cases.json",
        "answers": "generated_answer_cases.json",
        "production": "production_cases.json",
    }
    for suite, filename in filenames.items():
        write(OUT / filename, datasets[suite])
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
                "internal_cross_suite_exact_matches": overlap[
                    "internal_cross_suite_exact_count"
                ],
                "lexical_review": overlap["lexical_review_count"],
                "semantic_review": overlap["semantic_review_count"],
                "frozen": args.freeze,
                "system_executed_on_dataset": False,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
