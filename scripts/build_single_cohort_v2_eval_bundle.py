"""Build the annotated single-cohort-v2 development and frozen hidden suites."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "eval" / "single_cohort_v2"
COUNTS = {
    "single_structured": (10, 4),
    "single_rag": (10, 4),
    "multi_entity": (15, 6),
    "two_structured": (18, 7),
    "mixed": (20, 8),
    "two_regulations": (15, 6),
    "three_to_six_requests": (12, 5),
    "robustness": (14, 6),
    "follow_up": (15, 6),
    "cohort_resolution": (11, 4),
    "failure_isolation": (10, 4),
}


def _request(
    index: int,
    kind: str,
    span: str,
    *,
    tool_name: str | None = None,
    intent: str,
    slots: dict[str, Any] | None = None,
    cohort: str | None = "K51",
    expected_status: str = "ok",
    source_contract: str | None = None,
) -> dict[str, Any]:
    return {
        "request_id": f"r{index}",
        "request_kind": kind,
        "tool_name": tool_name,
        "intent": intent,
        "query_span": span,
        "slots": slots or {},
        "cohort_refs": [cohort] if cohort else [],
        "expected_status": expected_status,
        "expected_source_contract": source_contract or (
            "request_scoped_rag" if kind == "rag" else "structured_record"
        ),
        "expected_evidence": (
            {"anchor_terms": [term for term in span.casefold().split() if len(term) >= 4][:4]}
            if kind == "rag"
            else None
        ),
        "citation_scope": f"r{index}",
    }


def _case(
    split: str,
    category: str,
    number: int,
    query: str,
    requests: list[dict[str, Any]],
    *,
    selected_cohort: str | None = "K51",
    history: list[dict[str, str]] | None = None,
    outcome: str = "execute",
    context_mode: str = "standalone",
    query_mode: str = "validated",
    effective_cohort: str | None = "K51",
    cohort_source: str = "raw_query",
    fault_injection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    notes = (
        [
            "Dùng để đối chiếu hồ sơ cá nhân.", "Cần câu trả lời tách từng ý.",
            "Vui lòng giữ nguyên thứ tự câu hỏi.", "Tôi cần kiểm tra trước khi nộp đơn.",
            "Hãy nêu rõ nguồn cho từng phần.", "Cần xác nhận theo đúng sổ tay.",
            "Tôi đang chuẩn bị giấy tờ liên quan.", "Xin trả lời từng nội dung độc lập.",
            "Mỗi kết luận cần nguồn riêng.", "Tôi cần biết trước hạn đăng ký.",
            "Hãy phân biệt các nội dung giúp tôi.", "Tôi cần kiểm tra quyền lợi của mình.",
            "Xin giữ đúng phạm vi câu hỏi.", "Cần dùng cho buổi tư vấn học vụ.",
            "Hãy cho biết nếu phần nào không tìm thấy.", "Tôi muốn xác minh thông tin này.",
            "Cần kết quả để trao đổi với cố vấn.", "Xin không gộp bằng chứng giữa các ý.",
            "Tôi cần chuẩn bị trước kỳ học tới.", "Hãy ghi nhận phần chưa giải quyết được.",
        ]
        if split == "hidden"
        else [
            "Xin trích đúng nguồn tương ứng.", "Tôi cần hoàn thiện biểu mẫu.",
            "Hãy trả lời theo từng yêu cầu.", "Cần kiểm tra trước khi đăng ký.",
            "Xin nêu phần nào chưa đủ dữ liệu.", "Tôi muốn xác nhận với cố vấn.",
            "Hãy giữ đúng thứ tự các ý.", "Cần dùng cho kế hoạch học tập.",
            "Mỗi ý cần bằng chứng riêng.", "Xin không suy đoán khi thiếu nguồn.",
            "Tôi đang chuẩn bị hồ sơ học vụ.", "Hãy tách rõ kết quả từng phần.",
            "Cần thông tin trước thời hạn xử lý.", "Tôi muốn đối chiếu với sổ tay.",
            "Xin ghi rõ nội dung chưa tìm thấy.", "Hãy giới hạn trong câu hỏi này.",
            "Tôi cần trao đổi lại với nhà trường.", "Xin giữ citation theo từng yêu cầu.",
            "Cần kết quả cho học kỳ sắp tới.", "Hãy báo rõ nếu công cụ gặp lỗi.",
        ]
    )
    query = f"{query.rstrip()} {notes[(number - 1) % len(notes)]}"
    successful = sum(item["expected_status"] == "ok" for item in requests)
    partial_status = (
        "not_applicable"
        if not requests
        else "complete"
        if successful == len(requests)
        else "partial"
        if successful
        else "failed"
    )
    signature = "|".join(
        f"{item.get('tool_name') or item['request_kind']}:{item['query_span'].casefold()}"
        for item in requests
    ) or f"{outcome}:{query.casefold()}"
    explicit_cohorts = set(re.findall(r"\bK(?:48-K49|50|51)\b", query, flags=re.IGNORECASE))
    return {
        "id": f"{split}-{category}-{number:02d}",
        "category": category,
        "template_id": f"{split}:{category}:{number:02d}",
        "entity_signature": f"{effective_cohort}:{signature}",
        "conversation_pattern": f"{split}:{context_mode}:{len(history or [])}",
        "query": query,
        "selected_cohort": selected_cohort,
        "chat_history": history or [],
        "fault_injection": fault_injection,
        "expected": {
            "outcome": outcome,
            "context_mode": context_mode,
            "query_mode": query_mode,
            "effective_cohort": effective_cohort,
            "effective_cohort_source": cohort_source,
            "atomic_requests": requests,
            "retrieval_executed": outcome == "execute" and bool(requests),
            "partial_status": partial_status,
            "citation_isolation": True,
            "multi_cohort_rejection": len(explicit_cohorts) >= 2,
        },
    }


def _structured_specs(hidden: bool) -> list[tuple[str, str, str, dict[str, Any]]]:
    if hidden:
        return [
            ("TOEFL iBT 72", "foreign_language", "direct_value", {"certificate_or_language": "TOEFL iBT", "score_or_level": 72}),
            ("thời gian tối đa hệ vừa làm vừa học", "study_duration", "direct_value", {"training_mode": "vua_lam_vua_hoc"}),
            ("điểm học bổng loại Khá", "scholarship_classification", "direct_value", {"score_or_label": "Khá"}),
            ("điểm chữ B+ đổi sang thang 4", "scoring", "direct_value", {"operation": "letter_to_grade_4", "score_or_grade": "B+"}),
            ("đơn vị hỗ trợ xác nhận sinh viên", "student_service", "contact", {"service": "xác nhận sinh viên", "requested_field": "unit"}),
            ("website Phòng Sau đại học", "office", "contact", {"office": "Phòng Sau đại học", "requested_field": "website"}),
            ("điện thoại Khoa Tiếng Anh", "faculty", "contact", {"faculty": "Khoa Tiếng Anh", "requested_field": "phone"}),
            ("ngành Tâm lý học thuộc khoa nào", "program", "direct_value", {"program_or_faculty": "Tâm lý học", "requested_field": "faculty"}),
            ("công thức GPA trung bình có trọng số", "formula", "formula", {"formula_type": "gpa_weighted_average"}),
        ]
    return [
        ("IELTS 6.0", "foreign_language", "direct_value", {"certificate_or_language": "IELTS", "score_or_level": "6.0"}),
        ("thời gian tối đa hệ chính quy", "study_duration", "direct_value", {"training_mode": "chinh_quy"}),
        ("điểm học bổng loại Giỏi", "scholarship_classification", "direct_value", {"score_or_label": "Giỏi"}),
        ("GPA 3.4 xếp loại học lực", "scoring", "direct_value", {"operation": "academic_classification", "score_or_grade": 3.4}),
        ("đơn vị hỗ trợ bảo hiểm y tế", "student_service", "contact", {"service": "bảo hiểm y tế", "requested_field": "unit"}),
        ("email Phòng Đào tạo", "office", "contact", {"office": "Phòng Đào tạo", "requested_field": "email"}),
        ("website Khoa Công nghệ Thông tin", "faculty", "contact", {"faculty": "Khoa Công nghệ Thông tin", "requested_field": "website"}),
        ("ngành Công nghệ Thông tin thuộc khoa nào", "program", "direct_value", {"program_or_faculty": "Công nghệ Thông tin", "requested_field": "faculty"}),
        ("công thức điểm trung bình chung theo tín chỉ", "formula", "formula", {"formula_type": "gpa_weighted_average"}),
        ("điểm rèn luyện 82 xếp loại gì", "scoring", "direct_value", {"operation": "conduct_classification", "score_or_grade": 82}),
    ]


def _single_structured(split: str, hidden: bool, count: int) -> list[dict[str, Any]]:
    cohort = "K50" if hidden else "K51"
    lead = "Cho biết theo sổ tay K50" if hidden else "Sinh viên K51 muốn biết"
    specs = _structured_specs(hidden)
    return [
        _case(split, "single_structured", index + 1, f"{lead} {span}?", [_request(1, "structured", span, tool_name=tool, intent=intent, slots=slots, cohort=cohort)], selected_cohort=cohort, effective_cohort=cohort)
        for index, (span, tool, intent, slots) in enumerate(specs[:count])
    ]


def _single_rag(split: str, hidden: bool, count: int) -> list[dict[str, Any]]:
    cohort = "K50" if hidden else "K51"
    topics = (
        ["điều kiện được xét tốt nghiệp", "quy trình xin học lại", "trường hợp bị cảnh báo học vụ", "thủ tục chuyển chương trình"]
        if hidden
        else ["thủ tục bảo lưu", "điều kiện tốt nghiệp", "quy định học cải thiện", "xử lý nghỉ học quá hạn", "đăng ký học phần", "rút học phần", "miễn giảm học phí", "khiếu nại điểm", "xét thôi học", "quyền nhận bằng và bảng điểm sau tốt nghiệp"]
    )
    phrase = "Sổ tay K50 quy định thế nào về" if hidden else "K51 cần tra cứu"
    return [_case(split, "single_rag", i + 1, f"{phrase} {topic}?", [_request(1, "rag", topic, intent="policy", cohort=cohort)], selected_cohort=cohort, effective_cohort=cohort) for i, topic in enumerate(topics[:count])]


def _multi_entity(split: str, hidden: bool, count: int) -> list[dict[str, Any]]:
    cohort = "K50" if hidden else "K51"
    entities = ["IELTS 5.5", "IELTS 6.0", "IELTS 6.5", "TOEFL iBT 60", "JLPT N3", "HSK 4", "TOPIK 3", "Cambridge B2"]
    cases = []
    for i in range(count):
        left, right = entities[i % len(entities)], entities[(i + 3) % len(entities)]
        query = (f"Đối chiếu chuẩn K50 cho {left}; đồng thời cho {right}." if hidden else f"K51: {left} và {right} lần lượt tương đương bậc nào?")
        requests = [_request(1, "structured", left, tool_name="foreign_language", intent="direct_value", slots={"certificate_or_language": left.rsplit(" ", 1)[0], "score_or_level": left.rsplit(" ", 1)[1]}, cohort=cohort), _request(2, "structured", right, tool_name="foreign_language", intent="direct_value", slots={"certificate_or_language": right.rsplit(" ", 1)[0], "score_or_level": right.rsplit(" ", 1)[1]}, cohort=cohort)]
        cases.append(_case(split, "multi_entity", i + 1, query, requests, selected_cohort=cohort, effective_cohort=cohort))
    return cases


def _two_structured(split: str, hidden: bool, count: int) -> list[dict[str, Any]]:
    cohort = "K50" if hidden else "K51"
    specs = _structured_specs(hidden)
    cases = []
    for i in range(count):
        first = specs[i % len(specs)]
        second = specs[(i + 2) % len(specs)]
        if i % 3 == 0:
            first = specs[3]
            second = ("GPA 2.8 xếp loại học lực", "scoring", "direct_value", {"operation": "academic_classification", "score_or_grade": 2.8})
        query = (f"Theo K50, tra riêng {first[0]}; kế đó tra {second[0]}." if hidden else f"K51 cho biết {first[0]} và {second[0]}?")
        requests = [_request(1, "structured", first[0], tool_name=first[1], intent=first[2], slots=first[3], cohort=cohort), _request(2, "structured", second[0], tool_name=second[1], intent=second[2], slots=second[3], cohort=cohort)]
        cases.append(_case(split, "two_structured", i + 1, query, requests, selected_cohort=cohort, effective_cohort=cohort))
    return cases


def _mixed(split: str, hidden: bool, count: int) -> list[dict[str, Any]]:
    cohort = "K50" if hidden else "K51"
    specs = _structured_specs(hidden)
    topics = ["thủ tục bảo lưu", "điều kiện tốt nghiệp", "quy định học lại", "hậu quả cảnh báo học vụ", "rút học phần", "tạm dừng học", "khiếu nại điểm", "miễn học phần"]
    cases = []
    for i in range(count):
        structured = specs[i % len(specs)]
        topic = topics[(i + (2 if hidden else 0)) % len(topics)]
        query = (f"Hồ sơ K50 cần hai ý: {structured[0]}; quy định về {topic}." if hidden else f"K51: {structured[0]}, còn {topic} thực hiện thế nào?")
        requests = [_request(1, "structured", structured[0], tool_name=structured[1], intent=structured[2], slots=structured[3], cohort=cohort), _request(2, "rag", topic, intent="procedure", cohort=cohort)]
        cases.append(_case(split, "mixed", i + 1, query, requests, selected_cohort=cohort, effective_cohort=cohort))
    return cases


def _two_regulations(split: str, hidden: bool, count: int) -> list[dict[str, Any]]:
    cohort = "K50" if hidden else "K51"
    topics = ["điều kiện tốt nghiệp", "nghỉ học tạm thời", "xét thôi học", "đăng ký học phần", "học cải thiện", "cảnh báo học vụ", "rút học phần", "chuyển ngành", "khiếu nại điểm", "miễn giảm học phí"]
    cases = []
    for i in range(count):
        left, right = topics[i % len(topics)], topics[(i + 4) % len(topics)]
        query = (f"Tách hai quy định K50: {left}; {right}." if hidden else f"K51 quy định {left} ra sao, và {right} ra sao?")
        requests = [_request(1, "rag", left, intent="policy", cohort=cohort), _request(2, "rag", right, intent="policy", cohort=cohort)]
        cases.append(_case(split, "two_regulations", i + 1, query, requests, selected_cohort=cohort, effective_cohort=cohort))
    return cases


def _three_to_six(split: str, hidden: bool, count: int) -> list[dict[str, Any]]:
    cohort = "K50" if hidden else "K51"
    sizes = ([3, 4, 5, 6, 4] if hidden else [3, 4, 5, 6] * 3)[:count]
    specs = _structured_specs(hidden)
    topics = ["bảo lưu", "tốt nghiệp", "học lại", "rút học phần", "cảnh báo học vụ", "khiếu nại điểm"]
    cases = []
    for i, size in enumerate(sizes):
        requests: list[dict[str, Any]] = []
        spans: list[str] = []
        for position in range(size):
            if position % 2 == 0:
                spec = specs[(i + position) % len(specs)]
                spans.append(spec[0])
                requests.append(_request(position + 1, "structured", spec[0], tool_name=spec[1], intent=spec[2], slots=spec[3], cohort=cohort))
            else:
                topic = topics[(i + position) % len(topics)]
                spans.append(topic)
                requests.append(_request(position + 1, "rag", topic, intent="policy", cohort=cohort))
        query = (f"Phiếu K50 gồm {size} ý: " if hidden else f"K51 hỏi {size} ý: ") + "; ".join(spans) + "."
        cases.append(_case(split, "three_to_six_requests", i + 1, query, requests, selected_cohort=cohort, effective_cohort=cohort))
    return cases


def _robustness(split: str, hidden: bool, count: int) -> list[dict[str, Any]]:
    cohort = "K50" if hidden else "K51"
    queries = (["k50 toefl ibt 72 doi ra bac nao", "thoi gian hoc toi da he vlvh", "web phong sau dh", "nganh tam ly thuoc khoa nao", "diem B+ ra he 4", "ct gpa co trong so"] if hidden else ["k51 ielts 6.0 tuong duong bac may", "thoi gian hoc toi da he chinh quy", "mail pdt", "web khoa cntt", "nganh cntt thuoc khoa nao", "diem hb loai gioi", "gpa 3.4 loai gi", "don vi lo bhyt", "cong thuc gpa co trong so", "điểm rèn luyên 82 loại gì", "IELST 6.0 đổi bậc", "phong dao tao email", "khoa cong nghe tt website", "ct tinh diem tbc"])
    specs = _structured_specs(hidden)
    spec_indexes = (
        [0, 1, 5, 7, 3, 8]
        if hidden
        else [0, 1, 5, 6, 7, 2, 3, 4, 8, 9, 0, 5, 6, 8]
    )
    cases = []
    for i, query in enumerate(queries[:count]):
        spec = specs[spec_indexes[i]]
        requests = [_request(1, "structured", query, tool_name=spec[1], intent=spec[2], slots=spec[3], cohort=cohort)]
        cases.append(_case(split, "robustness", i + 1, query, requests, selected_cohort=cohort, effective_cohort=cohort, query_mode="validated"))
    return cases


def _follow_up(split: str, hidden: bool, count: int) -> list[dict[str, Any]]:
    cohort = "K50" if hidden else "K51"
    cases = []
    grounded_count = count - max(2, count // 3)
    for i in range(count):
        if i < grounded_count:
            topic = ["bảo lưu", "tốt nghiệp", "học lại", "cảnh báo học vụ"][i % 4]
            history_text = (f"Theo sổ tay {cohort}, tôi cần xem quy định {topic}." if hidden else f"Tôi là sinh viên {cohort}, hãy tra quy định {topic}.")
            history = [{"role": "user", "content": history_text}, {"role": "assistant", "content": f"Đã xác định mục {topic}."}]
            query = "Trường hợp ngoại lệ của mục vừa nêu là gì?" if hidden else "Nội dung đó có ngoại lệ nào?"
            requests = [_request(1, "rag", query, intent="consequence_or_exception", cohort=cohort)]
            cases.append(_case(split, "follow_up", i + 1, query, requests, selected_cohort=None, history=history, context_mode="follow_up", effective_cohort=cohort, cohort_source="grounded_history"))
        else:
            query = "Còn trường hợp đó thì xử lý sao?" if hidden else "Cái đó có ngoại lệ không?"
            history = [{"role": "assistant", "content": "Bạn muốn hỏi thêm nội dung nào?"}]
            cases.append(_case(split, "follow_up", i + 1, query, [], selected_cohort=None, history=history, outcome="clarify", context_mode="ambiguous", effective_cohort=None, cohort_source="unresolved"))
    return cases


def _cohort_resolution(split: str, hidden: bool, count: int) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    patterns = ["missing", "multi", "raw_wins", "directory"]
    for i in range(count):
        kind = patterns[i % len(patterns)]
        if kind == "missing":
            query = "Khóa của tôi cần điều kiện nào để tốt nghiệp?" if hidden else "Điều kiện tốt nghiệp của khóa tôi là gì?"
            cases.append(_case(split, "cohort_resolution", i + 1, query, [], selected_cohort=None, outcome="clarify", context_mode="ambiguous", effective_cohort=None, cohort_source="unresolved"))
        elif kind == "multi":
            query = "Đối chiếu K48-K49 với K50 về điều kiện tốt nghiệp." if hidden else "So sánh K50 và K51 về điều kiện tốt nghiệp."
            cases.append(_case(split, "cohort_resolution", i + 1, query, [], selected_cohort="K50" if hidden else "K51", outcome="clarify", context_mode="standalone", effective_cohort=None, cohort_source="raw_query"))
        elif kind == "raw_wins":
            raw_cohort = "K48-K49" if hidden else "K50"
            span = f"điều kiện tốt nghiệp {raw_cohort}"
            cases.append(_case(split, "cohort_resolution", i + 1, f"Hãy tra {span}.", [_request(1, "rag", span, intent="policy", cohort=raw_cohort)], selected_cohort="K50" if hidden else "K51", effective_cohort=raw_cohort, cohort_source="raw_query"))
        else:
            office = "Phòng Sau đại học" if hidden else "Phòng Đào tạo"
            span = f"email {office}"
            cases.append(_case(split, "cohort_resolution", i + 1, f"Cho tôi {span}.", [_request(1, "structured", span, tool_name="office", intent="contact", slots={"office": office, "requested_field": "email"}, cohort=None)], selected_cohort=None, effective_cohort=None, cohort_source="unresolved"))
    return cases


def _failure_isolation(split: str, hidden: bool, count: int) -> list[dict[str, Any]]:
    cohort = "K50" if hidden else "K51"
    statuses = [("ok", "no_match"), ("ok", "error"), ("invalid", "ok"), ("ok", "unresolved"), ("error", "error")]
    cases = []
    for i in range(count):
        left_status, right_status = statuses[i % len(statuses)]
        if i % 5 == 4:
            cases.append(_case(split, "failure_isolation", i + 1, f"{cohort}: kế hoạch đã bị sửa tool_name sau validation.", [], selected_cohort=cohort, outcome="clarify", effective_cohort=cohort, fault_injection={"type": "plan_tampering", "request_id": "r1"}))
            continue
        left, right = "email Phòng Đào tạo", "thủ tục bảo lưu"
        requests = [_request(1, "structured", left, tool_name="office", intent="contact", slots={"office": "Phòng Đào tạo", "requested_field": "email"}, cohort=cohort, expected_status=left_status), _request(2, "rag", right, intent="procedure", cohort=cohort, expected_status=right_status)]
        cases.append(_case(split, "failure_isolation", i + 1, f"{cohort}: {left}; đồng thời {right}.", requests, selected_cohort=cohort, effective_cohort=cohort, fault_injection={"type": "request_status", "statuses": [left_status, right_status]}))
    return cases


BUILDERS = (_single_structured, _single_rag, _multi_entity, _two_structured, _mixed, _two_regulations, _three_to_six, _robustness, _follow_up, _cohort_resolution, _failure_isolation)


def build_suite(hidden: bool) -> list[dict[str, Any]]:
    split = "hidden" if hidden else "dev"
    cases: list[dict[str, Any]] = []
    for builder, (category, counts) in zip(BUILDERS, COUNTS.items(), strict=True):
        built = builder(split, hidden, counts[1 if hidden else 0])
        if any(case["category"] != category for case in built):
            raise ValueError(f"Builder/category mismatch: {category}")
        cases.extend(built)
    return cases


def _write_json(path: Path, value: Any) -> str:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--replace-hidden", action="store_true", help="Explicit one-time hidden-suite replacement.")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    existing_manifest_path = OUT / "manifest.json"
    if existing_manifest_path.exists() and not args.replace_hidden:
        existing_manifest = json.loads(existing_manifest_path.read_text(encoding="utf-8"))
        if existing_manifest.get("hidden_human_review_complete"):
            raise SystemExit(
                "Hidden is human-approved and frozen; use --replace-hidden for an explicit replacement."
            )
    dev = build_suite(False)
    dev_hash = _write_json(OUT / "dev.json", dev)
    hidden_path = OUT / "hidden.json"
    if hidden_path.exists() and not args.replace_hidden:
        hidden = json.loads(hidden_path.read_text(encoding="utf-8"))
        hidden_hash = hashlib.sha256(hidden_path.read_bytes()).hexdigest()
    else:
        hidden = build_suite(True)
        hidden_hash = _write_json(hidden_path, hidden)
    manifest = {
        "schema_version": "single-cohort-v2.2",
        "dataset_version": "single-cohort-gold-candidate-1",
        "frozen_at": datetime.now(UTC).isoformat(),
        "baseline_commit": "15f971d5",
        "prompt_version": "single-cohort-planner-v2.2",
        "registry_version": 3,
        "counts": {key: {"dev": value[0], "hidden": value[1]} for key, value in COUNTS.items()},
        "files": {"dev.json": dev_hash, "hidden.json": hidden_hash},
        "hidden_frozen": False,
        "hidden_human_review_required": True,
        "hidden_human_review_complete": False,
        "hidden_replacement_requires_flag": True,
        "legacy_final_holdout": {"commit": "e38bfef", "preserved": True},
    }
    _write_json(OUT / "manifest.json", manifest)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from src.evaluation.single_cohort_gold import (
        audit_bundle,
        legacy_compatibility_report,
    )
    from src.evaluation.single_cohort_v2 import validate_bundle

    audited = audit_bundle(OUT, root=ROOT)
    dev_hash = _write_json(OUT / "dev.json", audited.dev)
    hidden_hash = _write_json(OUT / "hidden.json", audited.hidden)
    manifest["files"] = {"dev.json": dev_hash, "hidden.json": hidden_hash}
    manifest["frozen_at"] = None
    manifest["gold_audit"] = {
        "commit": audited.report["commit"],
        "generated_at": audited.report["generated_at"],
        "data_versions": audited.report["data_versions"],
        "gold_ready": False,
    }
    _write_json(OUT / "manifest.json", manifest)
    _write_json(OUT / "gold_audit_report.json", audited.report)
    _write_json(OUT / "dev_review_queue.json", audited.dev_review_queue)
    _write_json(OUT / "hidden_review_queue.json", audited.review_queue)
    _write_json(OUT / "legacy_compatibility.json", legacy_compatibility_report(ROOT))

    validation = validate_bundle(OUT)
    report = {
        "valid": validation.valid,
        "errors": validation.errors,
        "generated_at": manifest["frozen_at"],
        "schema_version": manifest["schema_version"],
        "counts": validation.counts,
        "hashes": manifest["files"],
        "coverage": validation.coverage,
        "hidden_replaced": bool(args.replace_hidden),
    }
    _write_json(OUT / "validation_report.json", report)


if __name__ == "__main__":
    main()
