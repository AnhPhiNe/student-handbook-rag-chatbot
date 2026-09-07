"""Contract tests for the planner/normalizer structured-routing boundary."""

from __future__ import annotations

from typing import Any

import pytest

from src.retrieval.core.query_plan import normalize_query_plan
from src.retrieval.core.structured_routing import (
    normalize_router_decision,
    validate_router_decision,
)


def _decision(
    lookup_type: str,
    query: str,
    *,
    slots: dict[str, Any],
    slot_spans: dict[str, Any],
    intent: str = "direct_value",
) -> dict[str, Any]:
    return normalize_router_decision(
        {
            "route": "structured",
            "execution_mode": "structured",
            "intent": intent,
            "lookup_type": lookup_type,
            "slots": slots,
            "slot_spans": slot_spans,
        },
        query=query,
        selected_cohort="K51",
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


def _task(
    task_id: str,
    question: str,
    *,
    lookup_type: str,
    slots: dict[str, Any],
    slot_spans: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": task_id,
        "question": question,
        "mode": "structured",
        "intent": "direct_value",
        "lookup_type": lookup_type,
        "slots": slots,
        "slot_spans": slot_spans,
        "cohorts": ["K51"],
    }


def test_supplied_semantic_value_accepts_unseen_grounded_span() -> None:
    query = "K51 lộ trình đại học dành cho người mới kéo dài bao lâu?"
    decision = _decision(
        "study_duration",
        query,
        slots={"program_type": "first_degree"},
        slot_spans={"program_type": "lộ trình đại học dành cho người mới"},
    )

    assert decision["slots"]["program_type"] == "first_degree"
    assert decision["slot_spans"]["program_type"] == (
        "lộ trình đại học dành cho người mới"
    )
    assert validate_router_decision(
        decision,
        query=query,
        selected_cohort="K51",
    ) == []


def test_supplied_semantic_value_is_not_reinterpreted_from_conflicting_alias() -> None:
    query = "K51 văn bằng hai kéo dài bao lâu?"
    decision = _decision(
        "study_duration",
        query,
        slots={"program_type": "first_degree"},
        slot_spans={"program_type": "văn bằng hai"},
    )

    # The normalizer preserves the planner's meaning.  It does not decide
    # whether the planner chose the right meaning from the source phrase.
    assert decision["slots"]["program_type"] == "first_degree"
    assert validate_router_decision(
        decision,
        query=query,
        selected_cohort="K51",
    ) == []


def test_missing_enum_values_are_not_inferred_from_query_aliases() -> None:
    query = "K51 hệ chính quy văn bằng hai kéo dài bao lâu?"
    decision = _decision(
        "study_duration",
        query,
        slots={},
        slot_spans={},
    )

    assert decision["slots"] == {}
    assert decision["slot_spans"] == {}


def test_reading_intent_enum_does_not_require_a_registry_literal() -> None:
    query = "K51 quy đổi điểm số sang ký hiệu chữ trong bảng: 8,5"
    decision = _decision(
        "scoring",
        query,
        slots={
            "operation": "grade_10_to_letter",
            "score_or_grade": 8.5,
        },
        slot_spans={
            "operation": "quy đổi điểm số sang ký hiệu chữ trong bảng",
            "score_or_grade": "8,5",
        },
    )

    assert validate_router_decision(
        decision,
        query=query,
        selected_cohort="K51",
    ) == []


def test_invented_numeric_input_still_requires_matching_source_value() -> None:
    query = "K51 GPA 3,2 xếp loại học lực gì?"
    decision = _decision(
        "scoring",
        query,
        slots={
            "operation": "academic_classification",
            "score_or_grade": "4,0",
        },
        slot_spans={
            "operation": "xếp loại học lực",
            "score_or_grade": "3,2",
        },
    )

    assert "slot_span_mismatch:score_or_grade" in validate_router_decision(
        decision,
        query=query,
        selected_cohort="K51",
    )


@pytest.mark.parametrize(
    ("value", "span", "error"),
    [
        (42, "cấp bằng thứ nhất", "invalid_slot_type:program_type"),
        ("invented_program", "cấp bằng thứ nhất", "invalid_slot_value:program_type"),
    ],
)
def test_semantic_enum_type_and_domain_remain_strict(
    value: Any,
    span: str,
    error: str,
) -> None:
    query = "K51 cấp bằng thứ nhất kéo dài bao lâu?"
    decision = _decision(
        "study_duration",
        query,
        slots={"program_type": value},
        slot_spans={"program_type": span},
    )

    assert error in validate_router_decision(
        decision,
        query=query,
        selected_cohort="K51",
    )


@pytest.mark.parametrize(
    ("span", "error"),
    [
        (None, "missing_slot_span:program_type"),
        ("K51", "misgrounded_slot:program_type"),
        ("a phrase absent from the source", "ungrounded_slot:program_type"),
    ],
)
def test_semantic_enum_requires_a_real_non_cohort_source_span(
    span: str | None,
    error: str,
) -> None:
    query = "K51 chương trình đào tạo mới kéo dài bao lâu?"
    decision = _decision(
        "study_duration",
        query,
        slots={"program_type": "first_degree"},
        slot_spans={"program_type": span},
    )

    assert error in validate_router_decision(
        decision,
        query=query,
        selected_cohort="K51",
    )


def test_compound_tasks_do_not_cross_infer_missing_semantic_values() -> None:
    query = (
        "K51 hệ chính quy văn bằng hai kéo dài bao lâu; "
        "học phần còn lại được 5,2 thì đổi sang điểm chữ gì?"
    )
    plan, errors = normalize_query_plan(
        _plan(
            [
                _task(
                    "duration",
                    "K51 thời gian đào tạo tối đa bao lâu?",
                    lookup_type="study_duration",
                    slots={},
                    slot_spans={},
                ),
                _task(
                    "score",
                    "K51 được 5,2 thì đổi sang điểm chữ gì?",
                    lookup_type="scoring",
                    slots={
                        "operation": "grade_10_to_letter",
                        "score_or_grade": "5,2",
                    },
                    slot_spans={
                        "operation": "đổi sang điểm chữ gì",
                        "score_or_grade": "5,2",
                    },
                ),
            ]
        ),
        query=query,
        selected_cohort="K51",
    )

    assert errors == []
    duration_task, score_task = plan["tasks"]
    assert "training_mode" not in duration_task["slots"]
    assert "program_type" not in duration_task["slots"]
    assert "course_scope" not in score_task["slots"]
