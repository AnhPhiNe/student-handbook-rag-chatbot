"""Focused regressions for task-local structured-plan normalization."""

from __future__ import annotations

from typing import Any

import pytest

from src.retrieval.core.query_plan import normalize_query_plan


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
) -> dict[str, Any]:
    return {
        "id": task_id,
        "question": question,
        "mode": "structured",
        "intent": "direct_value",
        "lookup_type": "scoring",
        "slots": slots,
        "slot_spans": slot_spans,
        "cohorts": ["K51"],
    }


def _normalize(tasks: list[dict[str, Any]], query: str) -> dict[str, Any]:
    plan, errors = normalize_query_plan(
        _plan(tasks),
        query=query,
        selected_cohort="K51",
    )
    assert errors == []
    return plan


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


def test_missing_operation_is_inferred_from_its_task_question_only() -> None:
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

    assert plan["tasks"][0]["slots"]["operation"] == "letter_to_grade_4"
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
