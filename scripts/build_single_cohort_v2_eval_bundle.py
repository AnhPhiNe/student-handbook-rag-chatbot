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
    cohort_source: str | None = None,
    fault_injection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    notes = (
        [
            "Tôi đang lập danh sách việc cần làm cho học kỳ mới.",
            "Nếu có nhiều ý, hãy giữ từng kết quả ở đúng mục của nó.",
            "Thông tin này sẽ được dùng để kiểm tra lại với đơn vị phụ trách.",
            "Tôi cần biết phần nào có dữ liệu và phần nào chưa xác định được.",
            "Đừng dùng nguồn của yêu cầu trước để kết luận cho yêu cầu sau.",
            "Tôi muốn đối chiếu từng kết luận với đúng văn bản áp dụng.",
            "Hãy giữ nguyên các con số và điều kiện tôi đã nêu.",
            "Tôi cần câu trả lời theo cùng thứ tự với câu hỏi.",
            "Nếu một mục lỗi thì vẫn trả các mục còn kiểm chứng được.",
            "Xin tách thông tin liên hệ khỏi nội dung quy định.",
            "Tôi muốn kiểm tra nguồn trước khi trao đổi với cố vấn.",
            "Chỉ kết luận những phần có bằng chứng phù hợp.",
            "Hãy nêu rõ mục nào cần tôi bổ sung thông tin.",
            "Tôi đang chuẩn bị cho buổi tư vấn học tập sắp tới.",
            "Mỗi nội dung quy định cần citation của chính nội dung đó.",
            "Tôi cần xác minh độc lập từng yêu cầu trong câu này.",
            "Xin đừng suy ra thêm yêu cầu chỉ từ câu dặn cách trình bày.",
            "Nếu không có kết quả phù hợp thì hãy nói rõ là không tìm thấy.",
            "Tôi sẽ dùng kết quả để lập kế hoạch học vụ cá nhân.",
            "Hãy ưu tiên độ chính xác hơn việc trả lời đủ bằng mọi giá.",
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
    if cohort_source is None:
        cohort_source = (
            "raw_query"
            if effective_cohort and explicit_cohorts
            else "selected_cohort"
            if effective_cohort and selected_cohort
            else "grounded_history"
            if effective_cohort and context_mode == "follow_up" and history
            else "unresolved"
        )
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
        [
            "điều kiện để được công nhận tốt nghiệp",
            "điều kiện được nghỉ học tạm thời",
            "đăng ký học lại khi điểm học phần không đạt",
            "quy định công nhận kết quả học tập đã tích lũy",
        ]
        if hidden
        else ["thủ tục bảo lưu", "điều kiện tốt nghiệp", "quy định học cải thiện", "xử lý nghỉ học quá hạn", "đăng ký học phần", "rút học phần", "miễn giảm học phí", "khiếu nại điểm", "xét thôi học", "quyền nhận bằng và bảng điểm sau tốt nghiệp"]
    )
    phrase = "Trong phạm vi sổ tay K50, hãy xác minh" if hidden else "K51 cần tra cứu"
    return [_case(split, "single_rag", i + 1, f"{phrase} {topic}?", [_request(1, "rag", topic, intent="policy", cohort=cohort)], selected_cohort=cohort, effective_cohort=cohort) for i, topic in enumerate(topics[:count])]


def _multi_entity(split: str, hidden: bool, count: int) -> list[dict[str, Any]]:
    cohort = "K50" if hidden else "K51"
    entities = ["IELTS 5.5", "IELTS 6.0", "IELTS 6.5", "TOEFL iBT 60", "JLPT N3", "HSK 4", "TOPIK 3", "Cambridge B2"]
    cases = []
    for i in range(count):
        right_offset = 5 if hidden else 3
        left, right = entities[i % len(entities)], entities[(i + right_offset) % len(entities)]
        query = (f"Tách riêng hai chứng chỉ theo chuẩn K50: {left}, sau đó {right}." if hidden else f"K51: {left} và {right} lần lượt tương đương bậc nào?")
        requests = [_request(1, "structured", left, tool_name="foreign_language", intent="direct_value", slots={"certificate_or_language": left.rsplit(" ", 1)[0], "score_or_level": left.rsplit(" ", 1)[1]}, cohort=cohort), _request(2, "structured", right, tool_name="foreign_language", intent="direct_value", slots={"certificate_or_language": right.rsplit(" ", 1)[0], "score_or_level": right.rsplit(" ", 1)[1]}, cohort=cohort)]
        cases.append(_case(split, "multi_entity", i + 1, query, requests, selected_cohort=cohort, effective_cohort=cohort))
    return cases


def _two_structured(split: str, hidden: bool, count: int) -> list[dict[str, Any]]:
    cohort = "K50" if hidden else "K51"
    specs = _structured_specs(hidden)
    cases = []
    for i in range(count):
        first = specs[i % len(specs)]
        second = specs[(i + (4 if hidden else 2)) % len(specs)]
        if i % 3 == 0:
            first = specs[3]
            second = ("GPA 2.8 xếp loại học lực", "scoring", "direct_value", {"operation": "academic_classification", "score_or_grade": 2.8})
        query = (f"K50 có hai dữ kiện cần tra độc lập: {first[0]}; tiếp theo là {second[0]}." if hidden else f"K51 cho biết {first[0]} và {second[0]}?")
        requests = [_request(1, "structured", first[0], tool_name=first[1], intent=first[2], slots=first[3], cohort=cohort), _request(2, "structured", second[0], tool_name=second[1], intent=second[2], slots=second[3], cohort=cohort)]
        cases.append(_case(split, "two_structured", i + 1, query, requests, selected_cohort=cohort, effective_cohort=cohort))
    return cases


def _mixed(split: str, hidden: bool, count: int) -> list[dict[str, Any]]:
    cohort = "K50" if hidden else "K51"
    specs = _structured_specs(hidden)
    topics = (
        [
            "điều kiện nghỉ học tạm thời",
            "điều kiện công nhận tốt nghiệp",
            "công nhận kết quả học tập đã tích lũy",
            "phúc khảo điểm thi kết thúc học phần",
            "đăng ký học phần bổ sung",
            "điều kiện tiếp tục học sau cảnh báo",
            "chuyển ngành học",
            "chuyển đổi tín chỉ",
        ]
        if hidden
        else ["thủ tục bảo lưu", "điều kiện tốt nghiệp", "quy định học lại", "hậu quả cảnh báo học vụ", "rút học phần", "tạm dừng học", "khiếu nại điểm", "miễn học phần"]
    )
    cases = []
    for i in range(count):
        structured = specs[i % len(specs)]
        topic = topics[(i + (2 if hidden else 0)) % len(topics)]
        query = (f"Với K50, tra một dữ kiện là {structured[0]}; đồng thời xác minh nội dung {topic}." if hidden else f"K51: {structured[0]}, còn {topic} thực hiện thế nào?")
        requests = [_request(1, "structured", structured[0], tool_name=structured[1], intent=structured[2], slots=structured[3], cohort=cohort), _request(2, "rag", topic, intent="procedure", cohort=cohort)]
        cases.append(_case(split, "mixed", i + 1, query, requests, selected_cohort=cohort, effective_cohort=cohort))
    return cases


def _two_regulations(split: str, hidden: bool, count: int) -> list[dict[str, Any]]:
    cohort = "K50" if hidden else "K51"
    topics = (
        [
            "công nhận tốt nghiệp",
            "bảo lưu kết quả đã tích lũy",
            "đăng ký học lại học phần không đạt",
            "đăng ký học phần bổ sung",
            "điều kiện xét tốt nghiệp",
            "tiếp tục học sau cảnh báo",
            "chuyển đổi tín chỉ",
            "nghỉ học tạm thời",
            "công nhận kết quả học tập",
            "chuyển ngành học",
        ]
        if hidden
        else ["điều kiện tốt nghiệp", "nghỉ học tạm thời", "xét thôi học", "đăng ký học phần", "học cải thiện", "cảnh báo học vụ", "rút học phần", "chuyển ngành", "khiếu nại điểm", "miễn giảm học phí"]
    )
    cases = []
    for i in range(count):
        left, right = topics[i % len(topics)], topics[(i + 4) % len(topics)]
        query = (f"Đọc sổ tay K50 cho hai vấn đề không gộp nguồn: {left}; và {right}." if hidden else f"K51 quy định {left} ra sao, và {right} ra sao?")
        requests = [_request(1, "rag", left, intent="policy", cohort=cohort), _request(2, "rag", right, intent="policy", cohort=cohort)]
        cases.append(_case(split, "two_regulations", i + 1, query, requests, selected_cohort=cohort, effective_cohort=cohort))
    return cases


def _three_to_six(split: str, hidden: bool, count: int) -> list[dict[str, Any]]:
    cohort = "K50" if hidden else "K51"
    sizes = ([3, 4, 5, 6, 4] if hidden else [3, 4, 5, 6] * 3)[:count]
    specs = _structured_specs(hidden)
    topics = (
        [
            "nghỉ học tạm thời",
            "đăng ký học phần",
            "học lại học phần không đạt",
            "chuyển đổi tín chỉ",
            "tiếp tục học sau cảnh báo",
            "công nhận tốt nghiệp",
        ]
        if hidden
        else ["bảo lưu", "tốt nghiệp", "học lại", "rút học phần", "cảnh báo học vụ", "khiếu nại điểm"]
    )
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
        query = (f"Danh sách tra cứu K50 có {size} mục độc lập: " if hidden else f"K51 hỏi {size} ý: ") + "; ".join(spans) + "."
        cases.append(_case(split, "three_to_six_requests", i + 1, query, requests, selected_cohort=cohort, effective_cohort=cohort))
    return cases


def _robustness(split: str, hidden: bool, count: int) -> list[dict[str, Any]]:
    cohort = "K50" if hidden else "K51"
    queries = (["toefl 72 theo k50 thuoc muc nao", "he vua hoc vua lam duoc hoc toi da bao lau", "dia chi web cua p.sdh", "tam ly hoc do khoa nao quan ly", "B cong doi sang diem bon", "cong thuc tinh gpa theo trong so"] if hidden else ["k51 ielts 6.0 tuong duong bac may", "thoi gian hoc toi da he chinh quy", "mail pdt", "web khoa cntt", "nganh cntt thuoc khoa nao", "diem hb loai gioi", "gpa 3.4 loai gi", "don vi lo bhyt", "cong thuc gpa co trong so", "điểm rèn luyên 82 loại gì", "IELST 6.0 đổi bậc", "phong dao tao email", "khoa cong nghe tt website", "ct tinh diem tbc"])
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
            topic = (["nghỉ học tạm thời", "đăng ký học phần", "học lại học phần không đạt", "cảnh báo học vụ và ngưỡng áp dụng"] if hidden else ["bảo lưu", "tốt nghiệp", "học lại", "cảnh báo học vụ"])[i % 4]
            history_text = (f"Tôi thuộc {cohort}; chủ đề đã xác định là {topic} trong sổ tay." if hidden else f"Tôi là sinh viên {cohort}, hãy tra quy định {topic}.")
            history = [{"role": "user", "content": history_text}, {"role": "assistant", "content": f"Đã xác định mục {topic}."}]
            query = "Với chính chủ đề ở lượt trước, có điều kiện loại trừ nào không?" if hidden else "Nội dung đó có ngoại lệ nào?"
            requests = [_request(1, "rag", query, intent="consequence_or_exception", cohort=cohort)]
            cases.append(_case(split, "follow_up", i + 1, query, requests, selected_cohort=None, history=history, context_mode="follow_up", effective_cohort=cohort, cohort_source="grounded_history"))
        else:
            query = "Phần vừa nói có áp dụng cho tôi không?" if hidden else "Cái đó có ngoại lệ không?"
            history = [{"role": "assistant", "content": "Chưa có chủ đề hay khóa nào được xác định."}]
            cases.append(_case(split, "follow_up", i + 1, query, [], selected_cohort=None, history=history, outcome="clarify", context_mode="ambiguous", effective_cohort=None, cohort_source="unresolved"))
    return cases


def _cohort_resolution(split: str, hidden: bool, count: int) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    patterns = ["missing", "multi", "raw_wins", "directory"]
    for i in range(count):
        kind = patterns[i % len(patterns)]
        if kind == "missing":
            query = "Quy định công nhận tốt nghiệp áp dụng cho khóa của tôi ra sao?" if hidden else "Điều kiện tốt nghiệp của khóa tôi là gì?"
            cases.append(_case(split, "cohort_resolution", i + 1, query, [], selected_cohort=None, outcome="clarify", context_mode="ambiguous", effective_cohort=None, cohort_source="unresolved"))
        elif kind == "multi":
            query = "Trong cùng câu hỏi, hãy đối chiếu điều kiện nghỉ học của K48-K49 và K50." if hidden else "So sánh K50 và K51 về điều kiện tốt nghiệp."
            cases.append(_case(split, "cohort_resolution", i + 1, query, [], selected_cohort="K50" if hidden else "K51", outcome="clarify", context_mode="standalone", effective_cohort=None, cohort_source="raw_query"))
        elif kind == "raw_wins":
            raw_cohort = "K48-K49" if hidden else "K50"
            span = f"quy định nghỉ học tạm thời {raw_cohort}"
            cases.append(_case(split, "cohort_resolution", i + 1, f"Bỏ lựa chọn giao diện và dùng đúng khóa trong câu: {span}.", [_request(1, "rag", span, intent="policy", cohort=raw_cohort)], selected_cohort="K50" if hidden else "K51", effective_cohort=raw_cohort, cohort_source="raw_query"))
        else:
            office = "Phòng Sau đại học" if hidden else "Phòng Đào tạo"
            span = f"email {office}"
            cases.append(_case(split, "cohort_resolution", i + 1, f"Không chọn khóa, tôi chỉ cần dữ kiện danh bạ: {span}.", [_request(1, "structured", span, tool_name="office", intent="contact", slots={"office": office, "requested_field": "email"}, cohort=None)], selected_cohort=None, effective_cohort=None, cohort_source="unresolved"))
    return cases


def _failure_isolation(split: str, hidden: bool, count: int) -> list[dict[str, Any]]:
    cohort = "K50" if hidden else "K51"
    statuses = [("ok", "no_match"), ("ok", "error"), ("invalid", "ok"), ("ok", "unresolved"), ("error", "error")]
    cases = []
    for i in range(count):
        left_status, right_status = statuses[i % len(statuses)]
        if i % 5 == 4:
            cases.append(_case(split, "failure_isolation", i + 1, f"{cohort}: sau validation, một atomic request bị thay đổi source contract.", [], selected_cohort=cohort, outcome="clarify", effective_cohort=cohort, fault_injection={"type": "plan_tampering", "request_id": "r1"}))
            continue
        left, right = "email Phòng Đào tạo", "thủ tục bảo lưu"
        requests = [_request(1, "structured", left, tool_name="office", intent="contact", slots={"office": "Phòng Đào tạo", "requested_field": "email"}, cohort=cohort, expected_status=left_status), _request(2, "rag", right, intent="procedure", cohort=cohort, expected_status=right_status)]
        query = (
            f"Hai yêu cầu K50 phải độc lập khi một dependency lỗi: {left}; và {right}."
            if hidden
            else f"{cohort}: {left}; đồng thời {right}."
        )
        cases.append(_case(split, "failure_isolation", i + 1, query, requests, selected_cohort=cohort, effective_cohort=cohort, fault_injection={"type": "request_status", "statuses": [left_status, right_status]}))
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
    dev_path = OUT / "dev.json"
    if args.replace_hidden and dev_path.exists():
        dev = json.loads(dev_path.read_text(encoding="utf-8"))
        dev_hash = hashlib.sha256(dev_path.read_bytes()).hexdigest()
    else:
        dev = build_suite(False)
        dev_hash = _write_json(dev_path, dev)
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
        "baseline_commit": "839c27ba",
        "prompt_version": "single-cohort-planner-v2.4",
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
