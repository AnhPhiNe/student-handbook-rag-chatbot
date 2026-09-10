"""Focused regressions for task-local structured-plan normalization."""

from __future__ import annotations

from typing import Any

import pytest

from src.retrieval.core.query_plan import normalize_query_plan
from src.retrieval.core.structured_routing import (
    load_lookup_registry,
    normalize_router_decision,
    validate_router_decision,
)


def _plan(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "v1",
        "context_mode": "standalone",
        "normalized_query": None,
        "standalone_query": None,
        "referenced_turns": [],
        "out_of_domain": False,
        "tasks": tasks,
    }


def _structured(
    task_id: str,
    question: str,
    *,
    slots: dict[str, Any],
    slot_spans: dict[str, Any],
    lookup_type: str = "scoring",
    intent: str = "direct_value",
    cohorts: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": task_id,
        "question": question,
        "mode": "structured",
        "intent": intent,
        "lookup_type": lookup_type,
        "slots": slots,
        "slot_spans": slot_spans,
        "cohorts": cohorts or ["K51"],
    }


def _normalize(tasks: list[dict[str, Any]], query: str) -> dict[str, Any]:
    plan, errors = normalize_query_plan(
        _plan(tasks),
        query=query,
        selected_cohort="K51",
    )
    assert errors == []
    return plan


def test_registry_declares_slot_verification_roles_without_name_allowlist() -> None:
    registry = load_lookup_registry()

    assert registry["version"] == 7
    assert registry["tools"]["scholarship_classification"]["slot_schema"]["aspect"][
        "verification_role"
    ] == "reading_intent"
    assert registry["tools"]["scoring"]["slot_schema"]["score_or_grade"][
        "verification_role"
    ] == "result_input"
    assert registry["tools"]["student_service"]["slot_schema"]["service"][
        "verification_role"
    ] == "directory_entity"


@pytest.mark.parametrize(
    ("value", "error"),
    [(42, "invalid_slot_type:aspect"), ("invented_aspect", "invalid_slot_value:aspect")],
)
def test_reading_intent_selector_still_enforces_type_and_enum(
    value: Any, error: str,
) -> None:
    query = "Học bổng xuất sắc cần thông tin gì?"
    decision = normalize_router_decision(
        {
            "route": "structured",
            "execution_mode": "structured",
            "intent": "direct_value",
            "lookup_type": "scholarship_classification",
            "slots": {"aspect": value, "score_or_label": "xuất sắc"},
            "slot_spans": {"score_or_label": "xuất sắc"},
        },
        query=query,
        selected_cohort="K51",
    )

    assert error in validate_router_decision(
        decision,
        query=query,
        selected_cohort="K51",
    )


@pytest.mark.parametrize(
    ("value", "error"),
    [(42, "invalid_slot_type:aspect"), ("invented_aspect", "invalid_slot_value:aspect")],
)
def test_invalid_reading_intent_value_is_not_repaired_from_alias(
    value: Any, error: str,
) -> None:
    query = "Mức tiền học bổng xuất sắc là bao nhiêu?"
    decision = normalize_router_decision(
        {
            "route": "structured",
            "execution_mode": "structured",
            "intent": "direct_value",
            "lookup_type": "scholarship_classification",
            "slots": {"aspect": value, "score_or_label": "xuất sắc"},
            "slot_spans": {"score_or_label": "xuất sắc"},
        },
        query=query,
        selected_cohort="K51",
    )

    assert decision["slots"]["aspect"] == value
    assert error in validate_router_decision(
        decision,
        query=query,
        selected_cohort="K51",
    )


def test_present_result_input_repairs_only_same_value_span() -> None:
    query = "K51 học chương trình bằng thứ nhất tối đa bao lâu?"
    decision = normalize_router_decision(
        {
            "route": "structured",
            "execution_mode": "structured",
            "intent": "direct_value",
            "lookup_type": "study_duration",
            "slots": {"program_type": "first_degree"},
            "slot_spans": {},
        },
        query=query,
        selected_cohort="K51",
    )

    assert decision["slots"]["program_type"] == "first_degree"
    assert decision["slot_spans"]["program_type"] == "bằng thứ nhất"


def test_semantic_enum_meaning_is_not_reinterpreted_from_alias() -> None:
    query = "K51 học chương trình văn bằng hai tối đa bao lâu?"
    decision = normalize_router_decision(
        {
            "route": "structured",
            "execution_mode": "structured",
            "intent": "direct_value",
            "lookup_type": "study_duration",
            "slots": {"program_type": "first_degree"},
            "slot_spans": {"program_type": "văn bằng hai"},
        },
        query=query,
        selected_cohort="K51",
    )

    assert decision["slots"]["program_type"] == "first_degree"
    assert decision["slot_spans"]["program_type"] == "văn bằng hai"
    # Source/schema validation is not a second semantic classifier. A wrong
    # semantic interpretation remains a Planner error, not an alias repair.
    assert validate_router_decision(
        decision,
        query=query,
        selected_cohort="K51",
    ) == []


@pytest.mark.parametrize(
    ("query", "aspect", "aspect_span"),
    [
        (
            "Khoản hỗ trợ học bổng xuất sắc tính như thế nào?",
            "amount",
            "khoản hỗ trợ",
        ),
        (
            "Mức xếp hạng học bổng xuất sắc cần gì?",
            "classification",
            "mức xếp hạng",
        ),
    ],
)
def test_reading_intent_selector_preserves_unseen_paraphrase(
    query: str, aspect: str, aspect_span: str,
) -> None:
    task = {
        **_structured(
            "t1",
            query,
            lookup_type="scholarship_classification",
            slots={"aspect": aspect, "score_or_label": "xuất sắc"},
            slot_spans={
                "aspect": aspect_span,
                "score_or_label": "xuất sắc",
            },
        ),
    }

    plan, errors = normalize_query_plan(_plan([task]), query=query)

    assert errors == []
    assert plan["tasks"][0]["mode"] == "structured"
    assert plan["tasks"][0]["slots"] == {
        "aspect": aspect,
        "score_or_label": "xuất sắc",
    }
    assert plan["tasks"][0]["slot_spans"]["aspect"] == aspect_span


def test_undeclared_slot_role_defaults_to_source_grounding() -> None:
    registry = {
        "tools": {
            "custom": {
                "intents": ["direct_value"],
                "required_slots": {"direct_value": ["value"]},
                "slot_schema": {
                    "value": {
                        "type": "string",
                        "enum": ["known"],
                        "span_aliases": {"known": ["known"]},
                    }
                },
            }
        }
    }
    query = "A paraphrased request without the literal."
    decision = normalize_router_decision(
        {
            "route": "structured",
            "execution_mode": "structured",
            "intent": "direct_value",
            "lookup_type": "custom",
            "slots": {"value": "known"},
            "slot_spans": {},
        },
        query=query,
        registry=registry,
    )

    assert validate_router_decision(decision, query=query, registry=registry) == [
        "missing_slot_span:value"
    ]


def test_negated_selector_in_sibling_query_does_not_leak_into_task() -> None:
    query = "Không hỏi mức tiền học bổng; học bổng xuất sắc cần điều kiện gì?"
    task = {
        **_structured(
            "t1",
            "Học bổng xuất sắc cần điều kiện gì?",
            lookup_type="scholarship_classification",
            slots={"score_or_label": "xuất sắc"},
            slot_spans={"score_or_label": "xuất sắc"},
        ),
    }

    plan, errors = normalize_query_plan(_plan([task]), query=query)

    assert errors == []
    assert plan["tasks"][0]["mode"] == "structured"
    assert "aspect" not in plan["tasks"][0]["slots"]


def test_single_rewritten_service_task_defers_missing_entity_to_resolver() -> None:
    query = "Chưa biết sử dụng thư viện thì nhờ ai hướng dẫn?"
    task = _structured(
        "t1",
        "Đơn vị nào phụ trách hướng dẫn sử dụng thư viện cho sinh viên chưa biết sử dụng?",
        lookup_type="student_service",
        intent="contact",
        slots={
            "service": "Hướng dẫn sinh viên sử dụng thư viện",
            "requested_field": "unit",
        },
        slot_spans={},
        cohorts=["K50"],
    )

    plan, errors = normalize_query_plan(_plan([task]), query=query)

    assert errors == []
    normalized = plan["tasks"][0]
    assert normalized["mode"] == "structured"
    assert normalized["question"] == query
    assert "service" not in normalized["slots"]
    assert "service" not in normalized["slot_spans"]
    assert "missing_slot_span:service" in normalized["normalization_warnings"]
    assert normalized["slots"]["requested_field"] == "unit"


@pytest.mark.parametrize(
    ("query", "task_question", "service", "service_span"),
    [
        (
            "Chưa biết sử dụng thư viện thì nhờ ai hướng dẫn?",
            "Đơn vị nào phụ trách hướng dẫn sử dụng thư viện cho sinh viên?",
            "Hướng dẫn sinh viên sử dụng thư viện",
            "Hướng dẫn sinh viên sử dụng thư viện",
        ),
        (
            "Mình muốn đăng ký mượn phòng học, hỏi đơn vị nào hỗ trợ?",
            "Đơn vị nào phụ trách đặt phòng học cho sinh viên?",
            "Đặt phòng học",
            "Đặt phòng học",
        ),
    ],
)
def test_single_rewritten_service_paraphrase_is_not_promoted_to_entity(
    query: str,
    task_question: str,
    service: str,
    service_span: str,
) -> None:
    task = _structured(
        "t1",
        task_question,
        lookup_type="student_service",
        intent="contact",
        slots={"service": service, "requested_field": "unit"},
        slot_spans={"service": service_span},
        cohorts=["K51"],
    )

    plan, errors = normalize_query_plan(_plan([task]), query=query)

    assert errors == []
    normalized = plan["tasks"][0]
    assert normalized["mode"] == "structured"
    assert normalized["question"] == query
    assert "service" not in normalized["slots"]
    assert "service" not in normalized["slot_spans"]
    assert "ungrounded_slot:service" in normalized["normalization_warnings"]


def test_single_rewritten_service_keeps_faithful_original_phrase_absent_from_task() -> None:
    query = "Mình muốn mượn phòng học, xin hỏi đơn vị nào hỗ trợ?"
    task = _structured(
        "t1",
        "Đơn vị nào phụ trách việc đặt chỗ cho sinh viên?",
        lookup_type="student_service",
        intent="contact",
        slots={"service": "mượn phòng học", "requested_field": "unit"},
        slot_spans={"service": "mượn phòng học"},
        cohorts=["K51"],
    )

    plan, errors = normalize_query_plan(_plan([task]), query=query)

    assert errors == []
    normalized = plan["tasks"][0]
    assert normalized["mode"] == "structured"
    assert normalized["slots"]["service"] == "mượn phòng học"
    assert normalized["slot_spans"]["service"] == "mượn phòng học"


def test_single_rewritten_service_hallucinated_span_is_removed() -> None:
    query = "Mình muốn mượn phòng học, xin hỏi đơn vị nào hỗ trợ?"
    task = _structured(
        "t1",
        "Đơn vị nào phụ trách việc đặt chỗ cho sinh viên?",
        lookup_type="student_service",
        intent="contact",
        slots={"service": "Cấp bảng điểm", "requested_field": "unit"},
        slot_spans={"service": "Cấp bảng điểm"},
        cohorts=["K51"],
    )

    plan, errors = normalize_query_plan(_plan([task]), query=query)

    assert errors == []
    normalized = plan["tasks"][0]
    assert normalized["mode"] == "structured"
    assert normalized["question"] == query
    assert "service" not in normalized["slots"]
    assert "service" not in normalized["slot_spans"]
    assert "ungrounded_slot:service" in normalized["normalization_warnings"]


def test_compound_rewritten_service_task_does_not_receive_whole_query() -> None:
    query = (
        "Chưa biết sử dụng thư viện thì nhờ ai hướng dẫn, còn muốn in giáo trình "
        "thì liên hệ đâu?"
    )
    first = _structured(
        "t1",
        "Đơn vị nào phụ trách hướng dẫn sử dụng thư viện cho sinh viên chưa biết sử dụng?",
        lookup_type="student_service",
        intent="contact",
        slots={
            "service": "Hướng dẫn sinh viên sử dụng thư viện",
            "requested_field": "unit",
        },
        slot_spans={"service": "Hướng dẫn sinh viên sử dụng thư viện"},
        cohorts=["K50"],
    )
    second = _structured(
        "t2",
        "Muốn in giáo trình thì liên hệ đâu?",
        lookup_type="student_service",
        intent="contact",
        slots={
            "service": "In ấn giáo trình",
            "requested_field": "unit",
        },
        slot_spans={},
        cohorts=["K50"],
    )

    plan, errors = normalize_query_plan(_plan([first, second]), query=query)

    assert errors == []
    assert [task["mode"] for task in plan["tasks"]] == ["structured", "structured"]
    assert [task["question"] for task in plan["tasks"]] == [
        first["question"],
        second["question"],
    ]
    assert all("service" not in task["slots"] for task in plan["tasks"])
    assert all(
        any(warning.endswith(":service") for warning in task["normalization_warnings"])
        for task in plan["tasks"]
    )


def test_multi_cohort_service_fallback_keeps_task_query_and_cohorts() -> None:
    query = "K50 và K51 muốn mượn phòng học thì hỏi đơn vị nào?"
    task = _structured(
        "t1",
        "Đơn vị nào phụ trách cho mượn phòng học?",
        lookup_type="student_service",
        intent="contact",
        slots={"service": "Mượn phòng học", "requested_field": "unit"},
        slot_spans={},
        cohorts=["K50", "K51"],
    )

    plan, errors = normalize_query_plan(_plan([task]), query=query)

    assert errors == []
    normalized = plan["tasks"][0]
    assert normalized["mode"] == "structured"
    assert normalized["cohorts"] == ["K50", "K51"]
    assert normalized["question"] == query
    assert "service" not in normalized["slots"]


def test_unsupported_directory_entity_still_requires_grounded_source() -> None:
    query = "Email Khoa Toán là gì?"
    task = _structured(
        "t1",
        query,
        lookup_type="faculty",
        intent="contact",
        slots={"faculty": "Khoa Không tồn tại", "requested_field": "email"},
        slot_spans={"faculty": "Khoa Không tồn tại"},
    )

    plan, errors = normalize_query_plan(_plan([task]), query=query)

    assert "t1:ungrounded_slot:faculty" in errors
    assert plan["tasks"][0]["mode"] == "clarify"


def test_compound_scoring_tasks_keep_distinct_operations() -> None:
    query = "Điểm chữ C đổi ra hệ 4 là bao nhiêu, còn GPA 2,83 thì xếp loại học lực gì?"
    plan = _normalize(
        [
            _structured(
                "t1",
                "Điểm chữ C đổi ra hệ 4 là bao nhiêu?",
                slots={"operation": "letter_to_grade_4", "score_or_grade": "C"},
                slot_spans={"operation": "đổi ra hệ 4", "score_or_grade": "C"},
            ),
            _structured(
                "t2",
                "GPA 2,83 thì xếp loại học lực gì?",
                slots={
                    "operation": "academic_classification",
                    "score_or_grade": "2,83",
                },
                slot_spans={
                    "operation": "xếp loại học lực",
                    "score_or_grade": "2,83",
                },
            ),
        ],
        query,
    )

    assert [task["slots"]["operation"] for task in plan["tasks"]] == [
        "letter_to_grade_4",
        "academic_classification",
    ]


def test_reversed_compound_scoring_tasks_also_keep_distinct_operations() -> None:
    query = "GPA 2,83 thì xếp loại học lực gì, còn điểm chữ C đổi ra hệ 4 là bao nhiêu?"
    plan = _normalize(
        [
            _structured(
                "t1",
                "GPA 2,83 thì xếp loại học lực gì?",
                slots={
                    "operation": "academic_classification",
                    "score_or_grade": "2,83",
                },
                slot_spans={
                    "operation": "xếp loại học lực",
                    "score_or_grade": "2,83",
                },
            ),
            _structured(
                "t2",
                "Điểm chữ C đổi ra hệ 4 là bao nhiêu?",
                slots={"operation": "letter_to_grade_4", "score_or_grade": "C"},
                slot_spans={"operation": "đổi ra hệ 4", "score_or_grade": "C"},
            ),
        ],
        query,
    )

    assert [task["slots"]["operation"] for task in plan["tasks"]] == [
        "academic_classification",
        "letter_to_grade_4",
    ]


def test_missing_operation_is_not_inferred_from_either_task_question() -> None:
    query = "GPA 2,83 thì xếp loại học lực gì, còn điểm chữ C đổi sang thang 4 là bao nhiêu?"
    plan = _normalize(
        [
            _structured(
                "t1",
                "Điểm chữ C đổi sang thang 4 là bao nhiêu?",
                slots={"score_or_grade": "C"},
                slot_spans={"score_or_grade": "C"},
            ),
            _structured(
                "t2",
                "GPA 2,83 thì xếp loại học lực gì?",
                slots={
                    "operation": "academic_classification",
                    "score_or_grade": "2,83",
                },
                slot_spans={
                    "operation": "xếp loại học lực",
                    "score_or_grade": "2,83",
                },
            ),
        ],
        query,
    )

    assert "operation" not in plan["tasks"][0]["slots"]
    assert plan["tasks"][1]["slots"]["operation"] == "academic_classification"


def test_valid_control_with_unregistered_paraphrase_is_preserved() -> None:
    query = "Điểm chữ C đổi ra hệ 4 là bao nhiêu, còn GPA 2,83 thì xếp loại học lực gì?"
    plan = _normalize(
        [
            _structured(
                "t1",
                "Điểm chữ C đổi ra hệ 4 là bao nhiêu?",
                slots={"operation": "letter_to_grade_4", "score_or_grade": "C"},
                slot_spans={"operation": "đổi ra hệ 4", "score_or_grade": "C"},
            )
        ],
        query,
    )

    assert plan["tasks"][0]["slots"]["operation"] == "letter_to_grade_4"


def test_invalid_numeric_input_is_dropped_with_a_normalization_warning() -> None:
    query = "K51 GPA 3,2 xếp loại học lực?"
    plan = _normalize(
        [
            _structured(
                "t1",
                query,
                slots={
                    "operation": "academic_classification",
                    "score_or_grade": "2.83",
                },
                slot_spans={
                    "operation": "xếp loại học lực",
                    "score_or_grade": "3,2",
                },
            )
        ],
        query,
    )

    task = plan["tasks"][0]
    assert task["mode"] == "structured"
    assert task["slots"] == {"operation": "academic_classification"}
    assert task["normalization_warnings"] == [
        "slot_span_mismatch:score_or_grade"
    ]
    assert task["validation_errors"] == []


def test_valid_control_without_grounded_span_is_not_overwritten_by_sibling_alias() -> None:
    query = "Điểm chữ C đổi ra hệ 4 là bao nhiêu, còn GPA 2,83 thì xếp loại học lực gì?"
    plan = _normalize(
        [
            _structured(
                "t1",
                "Điểm chữ C đổi ra hệ 4 là bao nhiêu?",
                slots={"operation": "letter_to_grade_4", "score_or_grade": "C"},
                slot_spans={"operation": "", "score_or_grade": "C"},
            )
        ],
        query,
    )

    assert plan["tasks"][0]["slots"]["operation"] == "letter_to_grade_4"


@pytest.mark.parametrize("grade,gpa", [("B+", "3,17"), ("D", "2,19")])
@pytest.mark.parametrize("reverse", [False, True])
def test_operation_isolation_with_other_values(grade, gpa, reverse):
    first = _structured("t1", f"Đổi {grade} sang hệ bốn?",
                        slots={"operation": "letter_to_grade_4", "score_or_grade": grade},
                        slot_spans={"operation": "sang hệ bốn", "score_or_grade": grade})
    second = _structured("t2", f"GPA {gpa} xếp loại học lực gì?",
                         slots={"operation": "academic_classification", "score_or_grade": gpa},
                         slot_spans={"operation": "xếp loại học lực", "score_or_grade": gpa})
    tasks = [second, first] if reverse else [first, second]
    plan = _normalize(tasks, " và ".join(t["question"] for t in tasks))
    assert [t["slots"]["operation"] for t in plan["tasks"]] == [
        t["slots"]["operation"] for t in tasks]


def test_paraphrase_cannot_introduce_number_absent_from_user_context():
    task = _structured("t1", "GPA 3,17 xếp loại học lực gì?",
                       slots={"operation": "academic_classification", "score_or_grade": "3,17"},
                       slot_spans={"score_or_grade": "3,17"})
    plan = _normalize([task], "GPA của em xếp loại gì?")
    assert "score_or_grade" not in plan["tasks"][0]["slots"]
    assert "ungrounded_slot:score_or_grade" in plan["tasks"][0]["normalization_warnings"]
