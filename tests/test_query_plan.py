from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import src.common.cohort as cohort_module
from src.common.cohort import is_validated_source_applicable
from src.generation.answer_pipeline import AnswerPipeline
from src.api.routes.chat import _to_chat_response
from src.retrieval.core.office_lookup import office_lookup
from src.retrieval.core.query_plan import (
    safe_rag_fallback_plan,
    normalize_query_plan,
    query_plan_json_schema,
    query_plan_response_schema,
)
from src.retrieval.core.slang_normalizer import SlangNormalizer
from src.retrieval.core.structured_dispatcher import StructuredResolution


def _rag_task(index: int, question: str | None = None) -> dict[str, Any]:
    return {
        "id": f"t{index}",
        "question": question or f"Câu hỏi quy định {index}",
        "mode": "rag",
        "intent": "open_question",
        "lookup_type": None,
        "slots": {},
        "slot_spans": {},
        "cohorts": [],
        "clarification_question": None,
    }


def _plan(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "v1",
        "context_mode": "standalone",
        "normalized_query": "Câu hỏi tổng hợp",
        "standalone_query": None,
        "referenced_turns": [],
        "out_of_domain": False,
        "tasks": tasks,
    }


def test_query_plan_accepts_one_and_three_tasks() -> None:
    one, errors = normalize_query_plan(_plan([_rag_task(1)]), query="q", selected_cohort="K51")
    assert errors == []
    assert len(one["tasks"]) == 1
    assert one["tasks"][0]["cohorts"] == ["K51"]

    three, errors = normalize_query_plan(
        _plan([_rag_task(1), _rag_task(2), _rag_task(3)]),
        query="q",
    )
    assert errors == []
    assert [task["id"] for task in three["tasks"]] == ["t1", "t2", "t3"]


@pytest.mark.parametrize(
    "query",
    [
        "Điều 16 quy định gì?",
        "K51 Điều 16 nói gì vậy?",
        "Điều 30 có nội dung gì?",
    ],
)


def test_bare_article_reference_requires_document_or_topic(query: str) -> None:
    plan, errors = normalize_query_plan(
        _plan([_rag_task(1, query)]),
        query=query,
        selected_cohort="K51",
    )

    assert errors == []
    assert plan["context_mode"] == "ambiguous"
    assert plan["planner_fallback"] == "bare_article_requires_document_or_topic"
    assert plan["tasks"][0]["mode"] == "clarify"
    assert "văn bản/quy chế nào" in plan["tasks"][0]["clarification_question"]


@pytest.mark.parametrize(
    "query",
    [
        "Điều 16 của Quy chế đào tạo quy định gì?",
        "Điều 16 quy định việc nghỉ học tạm thời như thế nào?",
    ],
)
def test_article_reference_with_document_or_topic_keeps_rag(query: str) -> None:
    plan, errors = normalize_query_plan(
        _plan([_rag_task(1, query)]),
        query=query,
        selected_cohort="K51",
    )

    assert errors == []
    assert plan["tasks"][0]["mode"] == "rag"
    assert plan["tasks"][0]["question"] == query


def test_cross_cohort_source_requires_validated_applicability() -> None:
    assert not is_validated_source_applicable(
        {"cohort": "K50", "applicable_cohorts": ["K51"]},
        "K51",
    )
    assert is_validated_source_applicable(
        {
            "cohort": "K50",
            "source_cohort": "K50",
            "applicable_cohorts": ["K48-K49", "K50", "K51"],
            "applicability_validated": True,
        },
        "K51",
    )
    assert is_validated_source_applicable({"cohort": "K51"}, "K51")
    assert not is_validated_source_applicable({"cohort": "K48-K49"}, "K51")


@pytest.mark.parametrize(
    ("query", "clarifies"),
    [
        ("Em thuộc K50 nhưng năm tuyển sinh là 2025", True),
        ("Em thuộc K50, năm tuyển sinh là 2024", False),
        ("So sánh K50 với sinh viên tuyển sinh năm 2025", False),
        ("K50 so với sinh viên tuyển sinh năm 2025", False),
        ("K50 hỏi quy định ban hành năm 2025", False),
    ],
)
def test_cohort_admission_year_conflict_is_conservative(
    query: str, clarifies: bool
) -> None:
    plan, errors = normalize_query_plan(
        _plan([_rag_task(1, query)]), query=query, selected_cohort="K51"
    )
    assert errors == []
    assert (plan["tasks"][0]["mode"] == "clarify") is clarifies
    if clarifies:
        assert plan["planner_fallback"] == "cohort_admission_year_conflict"


def test_cohort_year_guard_uses_registry_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        cohort_module.COHORT_REGISTRY,
        "K52",
        {"aliases": ("K52",), "admission_years": (2026,)},
    )
    query = "Em thuộc K52 nhưng năm tuyển sinh 2027"
    plan, _ = normalize_query_plan(_plan([_rag_task(1, query)]), query=query)
    assert plan["tasks"][0]["mode"] == "clarify"
    assert "2026" in plan["tasks"][0]["clarification_question"]


def test_selected_cohort_conflicting_with_explicit_admission_year_clarifies() -> None:
    query = "Em tuyển sinh năm 2025 và muốn tra thời gian đào tạo"
    plan, _ = normalize_query_plan(
        _plan([_rag_task(1, query)]), query=query, selected_cohort="K50"
    )
    assert plan["tasks"][0]["mode"] == "clarify"
    assert plan["planner_fallback"] == "cohort_admission_year_conflict"


def test_office_lookup_never_falls_back_to_another_cohort() -> None:
    record = {
        "record_id": "office-k50",
        "unit_name": "Phòng Đào tạo",
        "aliases": ["phòng đào tạo"],
        "cohort": "K50",
    }
    assert (
        office_lookup(
            "Phòng Đào tạo",
            [record],
            cohort="K51",
            candidate_text="Phòng Đào tạo",
            require_confident_match=True,
        )
        is None
    )


def test_office_lookup_accepts_only_validated_cross_cohort_source() -> None:
    base = {
        "record_id": "office-shared",
        "unit_name": "Phòng Đào tạo",
        "aliases": ["phòng đào tạo"],
        "cohort": "K50",
        "applicable_cohorts": ["K51"],
    }
    assert (
        office_lookup(
            "Phòng Đào tạo",
            [base],
            cohort="K51",
            candidate_text="Phòng Đào tạo",
            require_confident_match=True,
        )
        is None
    )
    result = office_lookup(
        "Phòng Đào tạo",
        [{**base, "applicability_validated": True}],
        cohort="K51",
        candidate_text="Phòng Đào tạo",
        require_confident_match=True,
    )
    assert result is not None
    assert result["result"][0]["unit_name"] == "Phòng Đào tạo"


def test_office_lookup_keeps_explicit_shared_source() -> None:
    result = office_lookup(
        "Trung tâm dùng chung",
        [
            {
                "record_id": "shared-office",
                "unit_name": "Trung tâm dùng chung",
                "aliases": ["trung tâm dùng chung"],
                "cohort": "shared",
            }
        ],
        cohort="K51",
        candidate_text="Trung tâm dùng chung",
        require_confident_match=True,
    )
    assert result is not None


def test_native_plan_schema_matches_normalizer_contract() -> None:
    schema = query_plan_response_schema()
    tasks_schema = schema["properties"]["tasks"]
    task_schema = tasks_schema["items"]

    assert schema["properties"]["schema_version"]["enum"] == ["v1"]
    assert tasks_schema["minItems"] == 0
    assert tasks_schema["maxItems"] == 12
    assert "lookup_type" in task_schema["required"]
    assert "intent" in task_schema["required"]
    assert "slots" in task_schema["required"]
    assert "slot_spans" in task_schema["required"]


def test_query_plan_turns_more_than_three_requests_into_clarification() -> None:
    plan, errors = normalize_query_plan(
        _plan([_rag_task(1), _rag_task(2), _rag_task(3), _rag_task(4)]),
        query="bốn yêu cầu",
        selected_cohort="K50",
    )
    assert errors == []
    assert len(plan["tasks"]) == 1
    assert plan["tasks"][0]["mode"] == "clarify"
    assert "tối đa ba" in plan["tasks"][0]["clarification_question"]


def test_terminal_out_of_domain_does_not_require_executable_tasks() -> None:
    plan, errors = normalize_query_plan(
        {
            "schema_version": "v1",
            "context_mode": "standalone",
            "normalized_query": "Một câu ngoài phạm vi",
            "standalone_query": None,
            "referenced_turns": [],
            "out_of_domain": True,
            "tasks": [],
        },
        query="Một câu ngoài phạm vi",
        selected_cohort="K51",
    )

    assert errors == []
    assert plan["out_of_domain"] is True
    assert plan["tasks"] == []
    assert plan["planner_fallback"] is None


def test_handbook_domain_signal_overrides_false_out_of_domain() -> None:
    query = "K51 co duoc boi hoan hoc phi khi nghi hoc khong?"
    plan, errors = normalize_query_plan(
        {
            "schema_version": "v1",
            "context_mode": "standalone",
            "normalized_query": query,
            "standalone_query": None,
            "referenced_turns": [],
            "out_of_domain": True,
            "tasks": [],
        },
        query=query,
        selected_cohort="K51",
    )

    assert errors == []
    assert plan["out_of_domain"] is False
    assert plan["planner_fallback"] == "domain_signal_overrides_out_of_domain"
    assert plan["tasks"][0]["mode"] == "rag"
    assert plan["tasks"][0]["question"] == query
    assert plan["tasks"][0]["cohorts"] == ["K51"]


def test_unrelated_reimbursement_query_remains_out_of_domain() -> None:
    query = "Cửa hàng có bồi hoàn tiền mua sản phẩm cho tôi không?"
    plan, errors = normalize_query_plan(
        {
            "schema_version": "v1",
            "context_mode": "standalone",
            "normalized_query": query,
            "standalone_query": None,
            "referenced_turns": [],
            "out_of_domain": True,
            "tasks": [],
        },
        query=query,
        selected_cohort="K51",
    )

    assert errors == []
    assert plan["out_of_domain"] is True
    assert plan["tasks"] == []


def test_single_rag_task_preserves_original_subject_and_predicate() -> None:
    query = "Quy định về lớp sinh viên K50 là gì?"
    payload = _plan([_rag_task(1, "Quy định về điểm cho sinh viên K50 là gì?")])
    payload["normalized_query"] = "Quy định về diem cho sinh vien K50 là gì?"

    plan, errors = normalize_query_plan(
        payload,
        query=query,
        selected_cohort="K50",
    )

    assert errors == []
    assert plan["tasks"][0]["question"] == query


def test_single_structured_task_preserves_original_qualifiers() -> None:
    query = "Điểm học bổng loại Giỏi được tính như thế nào?"
    task = {
        **_rag_task(1, "Công thức tính điểm học bổng là gì?"),
        "mode": "structured",
        "intent": "formula",
        "lookup_type": "formula",
        "slots": {"formula_type": "scholarship_score"},
        "slot_spans": {"formula_type": "Điểm học bổng"},
    }

    plan, errors = normalize_query_plan(
        _plan([task]),
        query=query,
        selected_cohort="K50",
    )

    assert errors == []
    assert plan["tasks"][0]["question"] == query
    assert plan["tasks"][0]["slots"] == {"formula_type": "scholarship_score"}


def test_invalid_lookup_is_clarified_but_reference_table_slots_are_optional() -> None:
    invalid = {
        **_rag_task(1),
        "mode": "structured",
        "lookup_type": "unknown_tool",
        "intent": "direct_value",
    }
    plan, errors = normalize_query_plan(_plan([invalid]), query="tra dữ liệu")
    assert plan["tasks"][0]["mode"] == "clarify"
    assert any("unknown_lookup_type" in error for error in errors)

    missing = {
        **_rag_task(1, "IELTS tương đương bậc mấy?"),
        "mode": "structured",
        "lookup_type": "foreign_language",
        "intent": "direct_value",
    }
    plan, errors = normalize_query_plan(
        _plan([missing]),
        query=missing["question"],
        selected_cohort="K51",
    )
    assert errors == []
    assert plan["tasks"][0]["mode"] == "structured"
    assert plan["tasks"][0]["lookup_type"] == "foreign_language"
    assert plan["tasks"][0]["slots"] == {"certificate_or_language": "IELTS"}


def test_explicit_multi_cohort_is_preserved_over_ui_cohort() -> None:
    task = {**_rag_task(1), "cohorts": ["K50", "K51"]}
    plan, _ = normalize_query_plan(_plan([task]), query="so sánh K50 K51", selected_cohort="K48-K49")
    assert plan["tasks"][0]["cohorts"] == ["K50", "K51"]


def test_unknown_planner_cohort_uses_all_registered_cohorts_for_general_rag() -> None:
    task = {**_rag_task(1), "cohorts": ["UNKNOWN"]}

    plan, errors = normalize_query_plan(
        _plan([task]),
        query="Quy trình công nhận kết quả được quy định thế nào?",
        selected_cohort=None,
    )

    assert plan["tasks"][0]["cohorts"] == list(cohort_module.valid_cohorts())
    assert "t1:invalid_cohort" in errors


def test_unknown_planner_cohort_falls_back_to_selected_ui_cohort() -> None:
    task = {**_rag_task(1), "cohorts": ["UNKNOWN"]}

    plan, errors = normalize_query_plan(
        _plan([task]),
        query="Quy trình công nhận kết quả được quy định thế nào?",
        selected_cohort="K51",
    )

    assert plan["tasks"][0]["cohorts"] == ["K51"]
    assert "t1:invalid_cohort" in errors


@pytest.mark.parametrize(
    ("lookup_type", "query", "slots", "slot_spans", "expected_intent"),
    [
        (
            "study_duration",
            "So sánh thời gian đào tạo hệ chính quy giữa K50 và K51.",
            {"training_mode": "chinh_quy", "program_type": "first_degree"},
            {
                "training_mode": "hệ chính quy",
                "program_type": "thời gian đào tạo",
            },
            "direct_value",
        ),
        (
            "foreign_language",
            "So sánh IELTS 6.0 giữa K50 và K51.",
            {"certificate_or_language": "IELTS", "score_or_level": "6.0"},
            {"certificate_or_language": "IELTS", "score_or_level": "6.0"},
            "direct_value",
        ),
        (
            "scholarship_classification",
            "So sánh học bổng loại Giỏi giữa K50 và K51.",
            {"score_or_label": "Giỏi"},
            {"score_or_label": "Giỏi"},
            "direct_value",
        ),
        (
            "scoring",
            "So sánh xếp loại điểm rèn luyện 85 giữa K50 và K51.",
            {"operation": "conduct_classification", "score_or_grade": 85},
            {"score_or_grade": "85"},
            "direct_value",
        ),
    ],
)
def test_structured_compare_uses_each_lookup_base_intent(
    lookup_type: str,
    query: str,
    slots: dict[str, Any],
    slot_spans: dict[str, Any],
    expected_intent: str,
) -> None:
    task = {
        **_rag_task(1, query),
        "mode": "structured",
        "intent": "compare",
        "lookup_type": lookup_type,
        "slots": slots,
        "slot_spans": slot_spans,
        "cohorts": ["K50", "K51"],
    }

    plan, errors = normalize_query_plan(
        _plan([task]),
        query=query,
        selected_cohort="K51",
    )

    assert errors == []
    assert len(plan["tasks"]) == 1
    assert plan["tasks"][0]["mode"] == "structured"
    assert plan["tasks"][0]["intent"] == expected_intent
    assert plan["tasks"][0]["cohorts"] == ["K50", "K51"]


def test_single_cohort_compare_is_also_presentation_only() -> None:
    query = "So sánh IELTS và TOEFL ở K51."
    task = {
        **_rag_task(1, query),
        "mode": "structured",
        "intent": "compare",
        "lookup_type": "foreign_language",
        "cohorts": ["K51"],
    }

    plan, errors = normalize_query_plan(_plan([task]), query=query)

    assert errors == []
    assert plan["tasks"][0]["intent"] == "direct_value"
    assert plan["tasks"][0]["question"] == query
    assert plan["tasks"][0]["cohorts"] == ["K51"]


def test_table_first_follow_up_drops_ungrounded_optional_row_hint() -> None:
    task = {
        **_rag_task(1, "Thời gian đào tạo tối đa hệ chính quy của K51 là bao lâu?"),
        "mode": "structured",
        "intent": "direct_value",
        "lookup_type": "study_duration",
        "slots": {
            "training_mode": "chinh_quy",
            "program_type": "first_degree",
        },
        "slot_spans": {
            "training_mode": "hệ chính quy",
            "program_type": "chương trình cấp bằng thứ nhất",
        },
        "cohorts": ["K51"],
    }

    plan, errors = normalize_query_plan(
        _plan([task]),
        query="Còn K51 thì sao?",
        selected_cohort="K51",
    )

    assert errors == []
    assert plan["tasks"][0]["mode"] == "structured"
    assert plan["tasks"][0]["lookup_type"] == "study_duration"
    assert plan["tasks"][0]["slots"] == {}
    assert plan["tasks"][0]["slot_spans"] == {}


def test_table_first_drops_invalid_optional_row_hint() -> None:
    query = "K51 thời gian học tối đa là bao lâu?"
    task = {
        **_rag_task(1, query),
        "mode": "structured",
        "intent": "direct_value",
        "lookup_type": "study_duration",
        "slots": {"training_mode": "K51"},
        "slot_spans": {"training_mode": "K51"},
        "cohorts": ["K51"],
    }

    plan, errors = normalize_query_plan(
        _plan([task]),
        query=query,
        selected_cohort="K51",
    )

    assert errors == []
    assert plan["tasks"][0]["mode"] == "structured"
    assert plan["tasks"][0]["slots"] == {}
    assert plan["tasks"][0]["slot_spans"] == {}


def test_table_first_drops_optional_slot_grounded_only_by_cohort() -> None:
    query = "K51 thời gian học tối đa là bao lâu?"
    task = {
        **_rag_task(1, query),
        "mode": "structured",
        "intent": "direct_value",
        "lookup_type": "study_duration",
        "slots": {"program_type": "first_degree"},
        "slot_spans": {"program_type": "K51"},
        "cohorts": ["K51"],
    }

    plan, errors = normalize_query_plan(
        _plan([task]),
        query=query,
        selected_cohort="K51",
    )

    assert errors == []
    assert plan["tasks"][0]["mode"] == "structured"
    assert plan["tasks"][0]["slots"] == {}
    assert plan["tasks"][0]["slot_spans"] == {}


def test_table_first_drops_optional_slot_whose_span_describes_another_value() -> None:
    query = "Điểm 7,9 quy đổi thành điểm chữ gì ở K51?"
    task = {
        **_rag_task(1, query),
        "mode": "structured",
        "intent": "direct_value",
        "lookup_type": "scoring",
        "slots": {
            "operation": "grade_10_to_letter",
            "score_or_grade": "8,5",
        },
        "slot_spans": {"score_or_grade": "7,9"},
        "cohorts": ["K51"],
    }

    plan, errors = normalize_query_plan(
        _plan([task]),
        query=query,
        selected_cohort="K51",
    )

    assert errors == []
    assert plan["tasks"][0]["mode"] == "structured"
    assert plan["tasks"][0]["slots"] == {"operation": "grade_10_to_letter"}
    assert plan["tasks"][0]["slot_spans"] == {}


def test_table_first_drops_optional_slot_outside_declared_domain() -> None:
    query = "K51 học chương trình không xác định trong bao lâu?"
    task = {
        **_rag_task(1, query),
        "mode": "structured",
        "intent": "direct_value",
        "lookup_type": "study_duration",
        "slots": {"program_type": "invented_program"},
        "slot_spans": {"program_type": "chương trình không xác định"},
        "cohorts": ["K51"],
    }

    plan, errors = normalize_query_plan(
        _plan([task]),
        query=query,
        selected_cohort="K51",
    )

    assert errors == []
    assert plan["tasks"][0]["mode"] == "structured"
    assert plan["tasks"][0]["slots"] == {}
    assert plan["tasks"][0]["slot_spans"] == {}


def test_table_first_drops_optional_slot_without_span() -> None:
    query = "K51 thời gian học tối đa là bao lâu?"
    task = {
        **_rag_task(1, query),
        "mode": "structured",
        "intent": "direct_value",
        "lookup_type": "study_duration",
        "slots": {"program_type": "second_degree"},
        "slot_spans": {},
        "cohorts": ["K51"],
    }

    plan, errors = normalize_query_plan(
        _plan([task]),
        query=query,
        selected_cohort="K51",
    )

    assert errors == []
    assert plan["tasks"][0]["mode"] == "structured"
    assert plan["tasks"][0]["slots"] == {}
    assert plan["tasks"][0]["slot_spans"] == {}


def test_table_first_drops_unknown_nested_slot() -> None:
    query = "K51 thời gian học tối đa là bao lâu?"
    task = {
        **_rag_task(1, query),
        "mode": "structured",
        "intent": "direct_value",
        "lookup_type": "study_duration",
        "slots": {"slot_spans": {"program_type": "second_degree"}},
        "slot_spans": {},
        "cohorts": ["K51"],
    }

    plan, errors = normalize_query_plan(
        _plan([task]),
        query=query,
        selected_cohort="K51",
    )

    assert errors == []
    assert plan["tasks"][0]["mode"] == "structured"
    assert plan["tasks"][0]["slots"] == {}
    assert plan["tasks"][0]["slot_spans"] == {}


def test_required_entity_slot_without_span_requires_clarification() -> None:
    query = "Email Khoa Toán là gì?"
    task = {
        **_rag_task(1, query),
        "mode": "structured",
        "intent": "contact",
        "lookup_type": "faculty",
        "slots": {"faculty": "Khoa Toán", "requested_field": "email"},
        "slot_spans": {},
    }

    plan, errors = normalize_query_plan(_plan([task]), query=query)

    assert "t1:missing_slot_span:faculty" in errors
    assert plan["tasks"][0]["mode"] == "clarify"
    assert plan["tasks"][0]["lookup_type"] is None


def test_non_table_lookup_with_unknown_slot_degrades_to_safe_rag() -> None:
    query = "Email Khoa Toán là gì?"
    task = {
        **_rag_task(1, query),
        "mode": "structured",
        "intent": "contact",
        "lookup_type": "faculty",
        "slots": {
            "faculty": "Khoa Toán",
            "requested_field": "email",
            "unknown_hint": "không hợp lệ",
        },
        "slot_spans": {"faculty": "Khoa Toán"},
    }

    plan, errors = normalize_query_plan(_plan([task]), query=query)

    assert "t1:unknown_slot:unknown_hint" in errors
    assert plan["tasks"][0]["mode"] == "rag"
    assert plan["tasks"][0]["lookup_type"] is None
    assert plan["tasks"][0]["slots"] == {}
    assert plan["tasks"][0]["slot_spans"] == {}


def test_two_regulation_topics_keep_two_tasks_with_the_same_cohorts() -> None:
    first = {**_rag_task(1, "Quy định đăng ký học phần là gì?"), "cohorts": ["K50", "K51"]}
    second = {**_rag_task(2, "Quy định hoãn thi là gì?"), "cohorts": ["K50", "K51"]}

    plan, errors = normalize_query_plan(
        _plan([first, second]),
        query="So sánh K50 và K51 về đăng ký học phần và hoãn thi.",
    )

    assert errors == []
    assert len(plan["tasks"]) == 2
    assert [task["cohorts"] for task in plan["tasks"]] == [
        ["K50", "K51"],
        ["K50", "K51"],
    ]
    assert all(task["intent"] == "open_question" for task in plan["tasks"])


def test_single_query_cohort_fills_every_task_without_scope() -> None:
    plan, errors = normalize_query_plan(
        _plan([_rag_task(1), _rag_task(2)]),
        query="K51 cho biết quy định thứ nhất. Quy định thứ hai là gì?",
    )

    assert errors == []
    assert [task["cohorts"] for task in plan["tasks"]] == [["K51"], ["K51"]]


def test_rag_intent_is_canonicalized_to_open_question() -> None:
    task = {**_rag_task(1), "intent": "invented_regulation_taxonomy"}

    plan, errors = normalize_query_plan(_plan([task]), query="quy định học vụ")

    assert errors == []
    assert plan["tasks"][0]["intent"] == "open_question"
    assert plan["tasks"][0]["lookup_type"] is None


def test_offset_slot_spans_are_normalized_to_grounded_literals() -> None:
    query = "K51 IELTS 6.0 tương đương bậc mấy?"
    task = {
        **_rag_task(1, query),
        "mode": "structured",
        "intent": "direct_value",
        "lookup_type": "foreign_language",
        "slots": {"certificate_or_language": "IELTS", "score_or_level": "6.0"},
        "slot_spans": {
            "certificate_or_language": [{"start": 4, "end": 9}],
            "score_or_level": [{"start": 10, "end": 13}],
        },
        "cohorts": ["K51"],
    }
    plan, errors = normalize_query_plan(_plan([task]), query=query)
    assert errors == []
    assert plan["tasks"][0]["slot_spans"] == {
        "certificate_or_language": ["IELTS"],
        "score_or_level": ["6.0"],
    }


def test_per_cohort_rag_copies_merge_into_one_logical_task() -> None:
    first = {**_rag_task(1, "Thời gian học tối đa của K50 là bao lâu?"), "cohorts": ["K50"]}
    second = {**_rag_task(2, "Thời gian học tối đa của K51 là bao lâu?"), "cohorts": ["K51"]}
    plan, errors = normalize_query_plan(_plan([first, second]), query="So sánh K50 và K51")
    assert errors == []
    assert len(plan["tasks"]) == 1
    assert plan["tasks"][0]["cohorts"] == ["K50", "K51"]


def test_extended_cohort_registry_drives_schema_normalization_and_merging(
    monkeypatch,
) -> None:
    monkeypatch.setitem(
        cohort_module.COHORT_REGISTRY,
        "K52",
        {
            "aliases": ("K52", "K52+"),
            "admission_years": (2026,),
        },
    )

    assert cohort_module.normalize_cohort("k52+") == "K52"
    assert cohort_module.admission_years_for_cohort("K52") == (2026,)
    assert "K52" in query_plan_json_schema()["tasks"][0]["cohorts"]
    assert "K52" in query_plan_response_schema()["properties"]["tasks"]["items"][
        "properties"
    ]["cohorts"]["items"]["enum"]
    first = {
        **_rag_task(1, "Quy định đăng ký học phần của K51 là gì?"),
        "cohorts": ["K51"],
    }
    second = {
        **_rag_task(2, "Quy định đăng ký học phần của K52+ là gì?"),
        "cohorts": ["K52+"],
    }
    plan, errors = normalize_query_plan(
        _plan([first, second]),
        query="So sánh K51 và K52+ về quy định đăng ký học phần",
    )

    assert errors == []
    assert len(plan["tasks"]) == 1
    assert plan["tasks"][0]["cohorts"] == ["K51", "K52"]


def test_safe_fallback_is_one_regulation_rag_task() -> None:
    plan = safe_rag_fallback_plan("quy định học vụ", "K51", reason="safe_rag")
    assert plan["planner_fallback"] == "safe_rag"
    assert plan["tasks"] == [
        {
            "id": "t1",
            "question": "quy định học vụ",
            "mode": "rag",
            "intent": "open_question",
            "lookup_type": None,
            "slots": {},
            "slot_spans": {},
            "cohorts": ["K51"],
            "clarification_question": None,
            "validation_errors": [],
        }
    ]


def _pipeline(plan: dict[str, Any]) -> AnswerPipeline:
    pipeline = AnswerPipeline.__new__(AnswerPipeline)
    pipeline.router = type("Planner", (), {"plan": lambda self, *args, **kwargs: plan})()
    pipeline.slang_normalizer = SlangNormalizer()
    pipeline.config = {
        "planning": {"max_citations": 10},
    }
    pipeline.model = None
    pipeline.scoring_tables = []
    pipeline.formula_rules = []
    pipeline.student_office_profiles = []
    pipeline.student_service_directory = []
    pipeline.student_faculty_profiles = []
    pipeline.foreign_language_tables = []
    pipeline.structured_tables_registry = []
    pipeline.program_directory = []
    pipeline.parent_sources_by_id = {}
    return pipeline


def test_planned_rag_task_rejects_unvalidated_cross_cohort_sources(
    monkeypatch,
) -> None:
    task = _rag_task(1, "Điều kiện tốt nghiệp?")
    task["cohorts"] = ["K51"]

    def source(chunk_id: str, cohort: str, **metadata: Any) -> dict[str, Any]:
        return {
            "chunk_id": chunk_id,
            "content": chunk_id,
            "metadata": {"cohort": cohort, "chunk_type": "regulation", **metadata},
        }

    retrieved_items = [
        source("invalid-k50", "K50"),
        source(
            "validated-k50",
            "K50",
            source_cohort="K50",
            applicable_cohorts=["K48-K49", "K50", "K51"],
            applicability_validated=True,
        ),
        source("native-k51", "K51"),
    ]
    citations = [
        {
            "chunk_id": item["chunk_id"],
            "cohort": item["metadata"]["cohort"],
            "source_cohort": item["metadata"].get("source_cohort"),
            "applicable_cohorts": item["metadata"].get("applicable_cohorts", []),
            "applicability_validated": item["metadata"].get(
                "applicability_validated", False
            ),
        }
        for item in retrieved_items
    ]
    monkeypatch.setattr(
        "src.generation.answer_pipeline.run_hybrid_retrieval_pipeline",
        lambda **kwargs: {
            "retrieved_items": retrieved_items,
            "citations": citations,
            "related_references": [
                {
                    "id": "R1",
                    "primary_chunk_id": "native-k51",
                    "related_chunk_id": "related-k51",
                }
            ],
        },
    )

    result = _pipeline(_plan([task]))._execute_planned_rag_task(
        task=task,
        task_id="t1",
        cohort="K51",
    )

    assert [item["chunk_id"] for item in result["retrieved_items"]] == [
        "validated-k50",
        "native-k51",
    ]
    assert [citation["chunk_id"] for citation in result["citations"]] == [
        "validated-k50",
        "native-k51",
    ]
    assert result["related_references"][0]["related_chunk_id"] == "related-k51"


def test_two_structured_domains_execute_without_cross_domain_probing(monkeypatch) -> None:
    tasks = [
        {
            **_rag_task(1, "IELTS 6.0 tương đương bậc mấy?"),
            "mode": "structured",
            "lookup_type": "foreign_language",
            "intent": "direct_value",
            "cohorts": ["K51"],
        },
        {
            **_rag_task(2, "Điểm học bổng loại giỏi là bao nhiêu?"),
            "mode": "structured",
            "lookup_type": "scholarship_classification",
            "intent": "direct_value",
            "cohorts": ["K51"],
        },
    ]
    calls: list[str] = []

    def fake_resolve(decision, **kwargs):
        calls.append(decision["lookup_type"])
        lookup_type = decision["lookup_type"]
        return StructuredResolution(
            lookup_type=lookup_type,
            strategy=f"{lookup_type}_lookup",
            result_kind="lookup",
            result={
                "lookup_type": lookup_type,
                "result": [{"value": lookup_type}],
                "cohort": "K51",
                "document_id": f"doc-{lookup_type}",
                "source_parent_id": f"parent-{lookup_type}",
                "source_pages": [1],
                "table_name": lookup_type,
            },
            target_chunk_types=["structured_lookup"],
        )

    monkeypatch.setattr(
        "src.retrieval.core.structured_dispatcher.resolve_structured_decision",
        fake_resolve,
    )
    result = _pipeline(_plan(tasks))._run_query_plan(query="hai ý", cohort="K51", chat_history=[])
    assert calls == ["foreign_language", "scholarship_classification"]
    assert result["coverage_by_task"] == {"t1": "covered", "t2": "covered"}
    assert len(result["citations"]) == 2


def test_one_study_duration_task_executes_each_cohort_from_full_tables() -> None:
    task = {
        **_rag_task(
            1,
            "So sánh thời gian đào tạo tối đa hệ chính quy giữa K50 và K51.",
        ),
        "mode": "structured",
        "lookup_type": "study_duration",
        "intent": "direct_value",
        "cohorts": ["K50", "K51"],
    }
    pipeline = _pipeline(_plan([task]))
    pipeline.structured_tables_registry = json.loads(
        Path("data/processed/tables/structured_tables_registry.json").read_text(
            encoding="utf-8"
        )
    )

    result = pipeline._run_query_plan(
        query=task["question"],
        cohort="K51",
        chat_history=[],
    )

    assert result["coverage_by_task"] == {"t1": "covered"}
    assert result["task_results"][0]["coverage_by_cohort"] == {
        "K50": "covered",
        "K51": "covered",
    }
    assert len(result["structured_result"]["sub_lookups"]) == 2
    assert {citation["cohort"] for citation in result["citations"]} == {
        "K50",
        "K51",
    }


def test_rag_tasks_keep_top_five_and_deduplicate_shared_source(monkeypatch) -> None:
    calls: list[tuple[str, int]] = []

    def fake_retrieval(**kwargs):
        calls.append((kwargs["query"], kwargs["top_k"]))
        return {
            "retrieved_items": [
                {
                    "chunk_id": "shared-parent",
                    "content": f"Nguồn cho {kwargs['query']}",
                    "metadata": {"cohort": "K51", "chunk_type": "rule"},
                }
            ],
            "citations": [
                {
                    "chunk_id": "shared-parent",
                    "source_parent_id": "shared-parent",
                    "cohort": "K51",
                    "source_pages": [10],
                }
            ],
            "related_references": [
                {
                    "id": "R9",
                    "primary_chunk_id": "shared-parent",
                    "related_chunk_id": "related-parent",
                    "title": "Điều liên quan",
                }
            ],
        }

    monkeypatch.setattr("src.generation.answer_pipeline.run_hybrid_retrieval_pipeline", fake_retrieval)
    result = _pipeline(_plan([_rag_task(1, "quy định một"), _rag_task(2, "quy định hai")]))._run_query_plan(
        query="hai quy định", cohort="K51", chat_history=[]
    )
    assert calls == [("quy định một", 5), ("quy định hai", 5)]
    assert len(result["retrieved_items"]) == 1
    assert len(result["citations"]) == 1
    assert result["citations"][0]["supports_task_ids"] == ["t1", "t2"]
    assert result["coverage_by_task"] == {"t1": "covered", "t2": "covered"}
    assert result["related_references"] == [
        {
            "id": "R1",
            "primary_chunk_id": "shared-parent",
            "related_chunk_id": "related-parent",
            "title": "Điều liên quan",
        }
    ]


def test_covered_and_uncovered_tasks_keep_partial_answer_path(monkeypatch) -> None:
    def fake_retrieval(**kwargs):
        if "đủ nguồn" not in kwargs["query"]:
            return {"retrieved_items": [], "citations": []}
        return {
            "retrieved_items": [{"chunk_id": "p1", "content": "Có nguồn", "metadata": {"cohort": "K51"}}],
            "citations": [{"chunk_id": "p1", "source_parent_id": "p1", "cohort": "K51"}],
        }

    monkeypatch.setattr("src.generation.answer_pipeline.run_hybrid_retrieval_pipeline", fake_retrieval)
    result = _pipeline(_plan([_rag_task(1, "ý đủ nguồn"), _rag_task(2, "ý thiếu")]))._run_query_plan(
        query="hai ý", cohort="K51", chat_history=[]
    )
    assert result["coverage_by_task"] == {"t1": "covered", "t2": "uncovered"}
    assert result["needs_llm_answer"] is True
    assert result["needs_clarification"] is False


@pytest.mark.parametrize("intent", ["list_items", "direct_value"])
@pytest.mark.parametrize("question", [
    "Bảng quy đổi điểm TOEIC 4 kỹ năng sang bậc tương đương",
    "Bậc 3 tương ứng ngưỡng IELTS nào?",
    "Bảng quy đổi TOEFL áp dụng từ năm 2022",
])
def test_normalizer_does_not_invent_score_from_untyped_query_number(
    intent: str, question: str,
) -> None:
    task = {
        **_rag_task(1, question),
        "mode": "structured",
        "lookup_type": "foreign_language",
        "intent": intent,
    }
    plan, errors = normalize_query_plan(
        _plan([task]), query=question, selected_cohort="K51",
    )
    assert not errors
    assert plan["tasks"][0]["mode"] == "structured"
    assert "score_or_level" not in plan["tasks"][0]["slots"]
    assert "score_or_level" not in plan["tasks"][0]["slot_spans"]


def test_normalizer_preserves_grounded_score_and_component_guard() -> None:
    from src.retrieval.core.structured_dispatcher import resolve_structured_decision

    question = "TOEIC tổng 650 tương đương bậc nào?"
    task = {
        **_rag_task(1, question),
        "mode": "structured",
        "lookup_type": "foreign_language",
        "intent": "direct_value",
        "slots": {"certificate_or_language": "TOEIC", "score_or_level": 650},
        "slot_spans": {"certificate_or_language": "TOEIC", "score_or_level": "650"},
    }
    plan, errors = normalize_query_plan(
        _plan([task]), query=question, selected_cohort="K51",
    )
    assert not errors
    normalized_task = plan["tasks"][0]
    assert normalized_task["slots"]["score_or_level"] == 650
    registry = json.loads(Path(
        "data/processed/tables/structured_tables_registry.json"
    ).read_text(encoding="utf-8"))
    resolution = resolve_structured_decision(
        normalized_task, query=question, cohort="K51", scoring_tables=[],
        formula_rules=[], office_directory=[], student_service_directory=[],
        student_faculty_profiles=[], foreign_language_tables=[],
        structured_tables_registry=registry, program_directory=[],
    )
    assert resolution.result_kind == "clarification"
    assert set(resolution.result["missing_slots"]) == {
        "listening_score", "reading_score", "speaking_score", "writing_score",
    }


def test_runtime_clarification_stays_on_its_task_and_cohort(monkeypatch) -> None:
    from src.generation.prompt_builder import build_authorized_evidence_packet

    structured_task = {
        **_rag_task(1, "Yêu cầu cần dữ kiện bổ sung"),
        "mode": "structured",
        "lookup_type": "foreign_language",
        "intent": "direct_value",
        "cohorts": ["K50", "K51"],
    }
    rag_task = {**_rag_task(2, "Yêu cầu về quy định"), "cohorts": ["K51"]}
    pipeline = _pipeline(_plan([structured_task, rag_task]))
    clarification = "Vui lòng cung cấp các thành phần còn thiếu của kết quả."

    def fake_execute(*, task, task_id, cohort, **kwargs):
        if task_id == "t1" and cohort == "K50":
            return {
                "coverage": "needs_clarification",
                "clarification_question": clarification,
                "evidence": [], "citations": [], "retrieved_items": [],
            }
        citation = {
            "chunk_id": f"{task_id}-{cohort}", "cohort": cohort,
            "content": "Nội dung đủ căn cứ.", "supports_task_ids": [task_id],
        }
        return {
            "coverage": "covered", "evidence": [],
            "citations": [citation], "retrieved_items": [],
        }

    monkeypatch.setattr(pipeline, "_execute_planned_structured_task", fake_execute)
    monkeypatch.setattr(pipeline, "_execute_planned_rag_task", fake_execute)
    result = pipeline._run_query_plan(query="hai ý", cohort=None, chat_history=[])
    assert result["needs_llm_answer"] is True
    assert result["needs_clarification"] is False
    assert result["task_results"][0]["clarification_by_cohort"] == {"K50": clarification}
    assert result["task_results"][1]["clarification_by_cohort"] == {}

    packet = build_authorized_evidence_packet(
        query="hai ý", retrieval_result=result, selected_citations=None,
        fallback_cohort=None, max_context_chars=10000,
    )
    units = {(unit["task_id"], unit["cohort"]): unit for unit in packet["units"]}
    assert units[("t1", "K50")]["clarification_question"] == clarification
    assert units[("t1", "K50")]["allowed_source_refs"] == []
    for key in [("t1", "K51"), ("t2", "K51")]:
        assert units[key]["clarification_question"] is None
        assert units[key]["allowed_source_refs"]


def test_sync_and_stream_metadata_share_plan_coverage_and_fallback() -> None:
    pipeline = _pipeline(_plan([_rag_task(1)]))
    retrieval_result = {
        "query_plan": _plan([_rag_task(1)]),
        "task_results": [{"task_id": "t1", "coverage": "covered"}],
        "coverage_by_task": {"t1": "covered"},
        "planner_fallback": "safe_rag",
        "supports_task_ids": {"p1": ["t1"]},
        "citations": [{"chunk_id": "p1", "supports_task_ids": ["t1"]}],
        "effective_query": "q",
        "selected_cohort": "K51",
    }
    output = pipeline._build_output(
        query="q",
        retrieval_result=retrieval_result,
        final_answer="a",
        context_used="",
        selected_citations=retrieval_result["citations"],
        status="answered",
        error_type=None,
        error_message=None,
        llm_called=True,
        used_cache=False,
    )
    metadata = pipeline._build_stream_metadata(
        retrieval_result,
        status="answered",
        effective_query="q",
        citations_used=retrieval_result["citations"],
        llm_called=True,
    )
    for key in (
        "query_plan",
        "task_results",
        "coverage_by_task",
        "planner_fallback",
        "supports_task_ids",
    ):
        assert output[key] == metadata[key]


def test_compound_plan_calls_answer_llm_once(monkeypatch) -> None:
    retrieval_result = {
        "query_plan": _plan([_rag_task(1), _rag_task(2)]),
        "task_results": [
            {"task_id": "t1", "coverage": "covered"},
            {"task_id": "t2", "coverage": "uncovered"},
        ],
        "coverage_by_task": {"t1": "covered", "t2": "uncovered"},
        "planner_fallback": None,
        "supports_task_ids": {"p1": ["t1"]},
        "query": "hai ý",
        "effective_query": "hai ý",
        "intent": "multi_task",
        "strategy": "query_plan_execution",
        "execution_mode": "rag",
        "selected_cohort": "K51",
        "retrieved_items": [
            {
                "chunk_id": "p1",
                "content": "Nguồn trực tiếp",
                "supports_task_ids": ["t1"],
                "metadata": {"cohort": "K51", "chunk_type": "rule", "supports_task_ids": ["t1"]},
            }
        ],
        "citations": [{"chunk_id": "p1", "source_parent_id": "p1", "cohort": "K51", "supports_task_ids": ["t1"]}],
        "structured_result": None,
        "needs_clarification": False,
        "out_of_domain": False,
    }
    pipeline = _pipeline(retrieval_result["query_plan"])
    pipeline.max_context_chars = 10000
    pipeline.llm_config = {"model_name": "fake"}
    pipeline.config.update({"citations": {"max_sources": 5}, "guardrails": {"skip_llm_on_low_confidence": True}})
    pipeline._run_retrieval = lambda *args, **kwargs: retrieval_result
    pipeline._throttle_llm_call = lambda: None

    class Cache:
        def make_cache_key(self, **kwargs):
            return "key"

        def get(self, key):
            return None

        def set(self, key, value):
            return None

    class LLM:
        calls = 0

        def generate(self, prompt):
            self.calls += 1
            assert "coverage" in prompt
            return {"ok": True, "text": "Trả lời phần đủ nguồn", "model_used": "fake", "usage": {}}

    llm = LLM()
    pipeline.response_cache = Cache()
    pipeline._get_llm_client = lambda: llm
    monkeypatch.setattr("src.generation.answer_pipeline.resolve_cohort_from_query", lambda query, cohort: cohort)

    output = pipeline.answer("hai ý", cohort="K51")
    assert output["status"] == "answered"
    assert output["llm_called"] is True
    assert llm.calls == 1


def test_sync_and_stream_send_the_same_selected_evidence_to_composer(monkeypatch) -> None:
    task = _rag_task(1, "Điều kiện cảnh báo học tập?")
    task["cohorts"] = ["K51"]
    plan = _plan([task])
    citation = {
        "chunk_id": "p1",
        "source_parent_id": "p1",
        "cohort": "K51",
        "article_label": "Điều 16",
        "content": "Điều 16. Nguồn trực tiếp về cảnh báo học tập.",
        "supports_task_ids": ["t1"],
    }
    unanchored_citation = {
        "chunk_id": "p2",
        "source_parent_id": "p2",
        "cohort": "K51",
        "article_label": "Điều 8",
        "content": "Điều 8. Nguồn liên quan được retrieval xếp trước.",
        "supports_task_ids": ["t1"],
    }
    later_citations = [
        {
            "chunk_id": f"p{index}",
            "source_parent_id": f"p{index}",
            "cohort": "K51",
            "article_label": f"Điều {index}",
            "content": f"Điều {index}. Nguồn hợp lệ xuất hiện muộn.",
            "supports_task_ids": ["t1"],
        }
        for index in range(3, 13)
    ]
    retrieval_result = {
        "query_plan": plan,
        "task_results": [
            {
                "task_id": "t1",
                "question": task["question"],
                "coverage": "covered",
                "coverage_by_cohort": {"K51": "covered"},
            }
        ],
        "coverage_by_task": {"t1": "covered"},
        "query": task["question"],
        "effective_query": task["question"],
        "intent": "open_question",
        "strategy": "query_plan_execution",
        "execution_mode": "rag",
        "selected_cohort": "K51",
        "retrieved_items": [
            {
                "chunk_id": "p1",
                "content": citation["content"],
                "supports_task_ids": ["t1"],
                "metadata": {"cohort": "K51", "supports_task_ids": ["t1"]},
            }
        ],
        "evidence_citations": [unanchored_citation, citation, *later_citations],
        "citations": [unanchored_citation, citation],
        "needs_clarification": False,
        "out_of_domain": False,
    }
    pipeline = _pipeline(plan)
    pipeline.max_context_chars = 10000
    pipeline._run_retrieval = lambda *args, **kwargs: retrieval_result
    pipeline._throttle_llm_call = lambda: None
    pipeline.config.update(
        {
            "citations": {"max_sources": 5},
            "guardrails": {"skip_llm_on_low_confidence": True},
        }
    )

    class Cache:
        def __init__(self):
            self.value = None

        def make_cache_key(self, **kwargs):
            return "key"

        def get(self, key):
            return self.value

        def set(self, key, value):
            self.value = value

    class LLM:
        def generate(self, prompt):
            return {
                "ok": True,
                "text": "**Kết luận:** Theo Điều 16, sinh viên cần đối chiếu điều kiện.",
                "model_used": "fake",
                "usage": {},
            }

        def generate_stream(self, prompt):
            yield "**Kết luận:** Theo Điều 16, "
            yield "sinh viên cần đối chiếu điều kiện."

    captured: list[list[dict[str, Any]]] = []

    def capture_prompt(**kwargs):
        captured.append(kwargs["selected_citations"])
        return "prompt", '{"units": []}'

    pipeline.response_cache = Cache()
    pipeline._get_llm_client = lambda: LLM()
    monkeypatch.setattr(
        "src.generation.answer_pipeline.build_answer_prompt_bundle",
        capture_prompt,
    )
    monkeypatch.setattr(
        "src.generation.answer_pipeline.resolve_cohort_from_query",
        lambda query, cohort: cohort,
    )

    sync_output = pipeline.answer(task["question"], cohort="K51")
    cached_output = pipeline.answer(task["question"], cohort="K51")
    pipeline.response_cache.value = None
    stream_events = list(pipeline.answer_stream(task["question"], cohort="K51"))
    stream_answer = "".join(
        event["text"] for event in stream_events if event.get("type") == "token"
    )

    assert captured == [
        [unanchored_citation, citation, *later_citations],
        [unanchored_citation, citation, *later_citations],
        [unanchored_citation, citation, *later_citations],
    ]
    assert stream_answer == sync_output["answer"]
    assert len(sync_output["citations_used"]) == 10
    assert [item["source_parent_id"] for item in sync_output["citations_used"][:2]] == [
        "p1",
        "p2",
    ]
    assert cached_output["used_cache"] is True
    assert cached_output["citations_used"] == sync_output["citations_used"]
    stream_done = next(
        event for event in stream_events if event.get("type") == "done"
    )
    assert stream_done["citations_used"] == sync_output["citations_used"]
    assert "**Kết luận:**" in stream_answer
    assert "Điều 16" in stream_answer


def test_stream_cleans_internal_labels_sources_and_reports_terminal_status(
    monkeypatch,
) -> None:
    task = _rag_task(1, "Điều kiện học tập?")
    task["cohorts"] = ["K51"]
    plan = _plan([task])
    citation = {
        "chunk_id": "p1",
        "source_parent_id": "p1",
        "cohort": "K51",
        "content": "Nguồn hợp lệ.",
        "supports_task_ids": ["t1"],
    }
    retrieval_result = {
        "query_plan": plan,
        "task_results": [{"task_id": "t1", "coverage": "covered"}],
        "coverage_by_task": {"t1": "covered"},
        "effective_query": task["question"],
        "execution_mode": "rag",
        "selected_cohort": "K51",
        "evidence_citations": [citation],
        "citations": [citation],
        "retrieved_items": [{"chunk_id": "p1", "content": "Nguồn hợp lệ."}],
        "needs_clarification": False,
        "out_of_domain": False,
    }
    pipeline = _pipeline(plan)
    pipeline.max_context_chars = 10000
    pipeline.llm_config = {"model_name": "fake"}
    pipeline.request_sleep_seconds = 0
    pipeline._last_llm_call_at = 0
    pipeline._run_retrieval = lambda *args, **kwargs: retrieval_result

    class Cache:
        value = None

        def make_cache_key(self, **kwargs):
            return "key"

        def get(self, key):
            return self.value

        def set(self, key, value):
            self.value = value

    class DirtyLLM:
        calls = 0

        def generate_stream(self, prompt):
            self.calls += 1
            yield "```markdown\nTheo Điều 16 (S1), sinh viên đủ điều kiện "
            yield "(được bổ sung bởi AMENDMENT 2).\n\nNguồn:\n- S1"

    pipeline.response_cache = Cache()
    llm = DirtyLLM()
    pipeline._get_llm_client = lambda: llm
    monkeypatch.setattr(
        "src.generation.answer_pipeline.resolve_cohort_from_query",
        lambda query, cohort: cohort,
    )

    events = list(pipeline.answer_stream(task["question"], cohort="K51"))
    answer = "".join(event["text"] for event in events if event["type"] == "token")
    statuses = [event["status"] for event in events if event["type"] == "metadata"]
    done = next(event for event in events if event["type"] == "done")

    assert statuses == ["streaming", "answered"]
    assert done["status"] == "answered"
    assert "Theo Điều 16" in answer
    assert "S1" not in answer
    assert "AMENDMENT" not in answer
    assert "Nguồn:" not in answer
    assert "```" not in answer
    assert pipeline.response_cache.value["answer"] == answer

    cached_events = list(pipeline.answer_stream(task["question"], cohort="K51"))
    cached_metadata = next(
        event for event in cached_events if event["type"] == "metadata"
    )
    cached_done = next(event for event in cached_events if event["type"] == "done")
    assert llm.calls == 1
    assert cached_metadata["used_cache"] is True
    assert cached_done["used_cache"] is True


def test_stream_failure_finishes_with_api_error_metadata(monkeypatch) -> None:
    task = _rag_task(1, "Điều kiện học tập?")
    task["cohorts"] = ["K51"]
    plan = _plan([task])
    citation = {
        "chunk_id": "p1",
        "source_parent_id": "p1",
        "cohort": "K51",
        "content": "Nguồn hợp lệ.",
        "supports_task_ids": ["t1"],
    }
    retrieval_result = {
        "query_plan": plan,
        "task_results": [{"task_id": "t1", "coverage": "covered"}],
        "coverage_by_task": {"t1": "covered"},
        "effective_query": task["question"],
        "execution_mode": "rag",
        "selected_cohort": "K51",
        "evidence_citations": [citation],
        "citations": [citation],
        "retrieved_items": [{"chunk_id": "p1", "content": "Nguồn hợp lệ."}],
        "needs_clarification": False,
        "out_of_domain": False,
    }
    pipeline = _pipeline(plan)
    pipeline.max_context_chars = 10000
    pipeline.llm_config = {"model_name": "fake"}
    pipeline.request_sleep_seconds = 0
    pipeline._last_llm_call_at = 0
    pipeline._run_retrieval = lambda *args, **kwargs: retrieval_result

    class Cache:
        def make_cache_key(self, **kwargs):
            return "key"

        def get(self, key):
            return None

        def set(self, key, value):
            raise AssertionError("failed streams must not be cached")

    class FailingLLM:
        def generate_stream(self, prompt):
            yield "Một phần chưa hoàn chỉnh"
            raise RuntimeError("stream failed")

    pipeline.response_cache = Cache()
    pipeline._get_llm_client = lambda: FailingLLM()
    monkeypatch.setattr(
        "src.generation.answer_pipeline.resolve_cohort_from_query",
        lambda query, cohort: cohort,
    )

    events = list(pipeline.answer_stream(task["question"], cohort="K51"))
    statuses = [event["status"] for event in events if event["type"] == "metadata"]
    done = next(event for event in events if event["type"] == "done")

    assert statuses == ["streaming", "api_error"]
    assert done["status"] == "api_error"
    assert done["error_type"] == "RuntimeError"


def test_execution_mode_ignores_clarification_when_one_task_executes() -> None:
    structured = {
        **_rag_task(1, "Tra bảng"),
        "mode": "structured",
        "lookup_type": "scoring",
        "intent": "direct_value",
        "cohorts": ["K51"],
    }
    clarify = {
        **_rag_task(2, "Yêu cầu chưa rõ"),
        "mode": "clarify",
        "clarification_question": "Bạn muốn tra nội dung nào?",
        "cohorts": ["K51"],
    }
    pipeline = _pipeline(_plan([structured, clarify]))
    pipeline._execute_planned_structured_task = lambda **kwargs: {
        "coverage": "covered",
        "evidence": [],
        "citations": [],
        "retrieved_items": [],
        "structured_result": {"lookup_type": "scoring", "result": []},
    }

    result = pipeline._run_query_plan(
        query="hai yêu cầu",
        cohort="K51",
        chat_history=[],
    )

    assert result["execution_mode"] == "structured"


def test_query_plan_telemetry_is_hidden_without_api_debug() -> None:
    result = {
        "answer": "a",
        "status": "answered",
        "query_plan": _plan([_rag_task(1)]),
        "task_results": [{"task_id": "t1", "coverage": "covered"}],
        "coverage_by_task": {"t1": "covered"},
        "planner_fallback": None,
        "supports_task_ids": {"p1": ["t1"]},
        "citations_used": [{"chunk_id": "p1", "task_id": "t1", "supports_task_ids": ["t1"]}],
    }
    production = _to_chat_response(result, include_debug=False)
    debug = _to_chat_response(result, include_debug=True)
    assert production.debug is None
    assert "task_id" not in production.citations_used[0]
    assert debug.debug["query_plan"]["schema_version"] == "v1"
    assert debug.debug["coverage_by_task"] == {"t1": "covered"}
    assert debug.citations_used[0]["supports_task_ids"] == ["t1"]


def test_structured_citation_dedup_preserves_sibling_tables_and_applicability() -> None:
    common = {
        "chunk_id": "K51_Dieu10",
        "source_parent_id": "K51_Dieu10",
        "cohort": "K51",
        "evidence_kind": "structured_result",
        "supports_task_ids": ["t1"],
        "source_pages": [18],
    }
    citations = [
        {
            **common,
            "title": "Thang điểm học phần nền tảng",
            "applicability": "Học phần giáo dục đại cương",
            "content": json.dumps(
                {"table_id": "foundation", "rows": [{"Điểm": "5,0", "Loại": "Đạt"}]},
                ensure_ascii=False,
            ),
        },
        {
            **common,
            "title": "Thang điểm các học phần còn lại",
            "applicability": "Các học phần còn lại",
            "content": json.dumps(
                {"table_id": "remaining", "rows": [{"Điểm": "5,0", "Loại": "Không đạt"}]},
                ensure_ascii=False,
            ),
        },
    ]

    merged = AnswerPipeline._merge_task_citations(citations)

    assert len(merged) == 1
    tables = json.loads(merged[0]["content"])["tables"]
    assert [table["table_id"] for table in tables] == ["foundation", "remaining"]
    assert [table["applicability"] for table in tables] == [
        "Học phần giáo dục đại cương",
        "Các học phần còn lại",
    ]
