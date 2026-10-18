"""A score the student wrote is kept as written; a number they did not write is not.

The planner sometimes quotes a score's span from its own task paraphrase or
writes the number differently from the question. Only numbers found in the
question (or visible history) are repaired; see repair_numeric_slot_spans.
"""
import pytest

from src.common.score import score_as_written
from src.retrieval.core.query_plan import normalize_query_plan


def _scoring_task(query, *, question, operation, score, span):
    raw = {
        "schema_version": "v1", "context_mode": "standalone",
        "normalized_query": query, "standalone_query": None,
        "referenced_turns": [], "out_of_domain": False,
        "tasks": [{
            "id": "t1", "question": question, "mode": "structured",
            "intent": "direct_value", "lookup_type": "scoring",
            "slots": {"operation": operation, "score_or_grade": score},
            "slot_spans": {"operation": "xếp loại", "score_or_grade": span},
            "cohorts": ["K51"], "clarification_question": None,
        }],
    }
    plan, _ = normalize_query_plan(raw, query=query, selected_cohort="K51")
    return plan["tasks"][0]


def test_span_quoted_from_the_task_paraphrase_is_repaired_from_the_question():
    task = _scoring_task(
        "Em được 78 điểm rèn luyện, bạn em 81 điểm thì mỗi người xếp loại gì?",
        question="Bạn em được 81 điểm rèn luyện thì xếp loại gì?",
        operation="conduct_classification", score=81, span="81 điểm rèn luyện",
    )
    assert task["mode"] == "structured"
    assert task["slots"]["score_or_grade"] == "81"
    assert task["slot_spans"]["score_or_grade"] == "81"
    assert task["normalization_warnings"] == ["numeric_span_repaired:score_or_grade"]


def test_a_number_the_student_did_not_write_is_still_dropped():
    task = _scoring_task(
        "Khung điểm rèn luyện từ 80 đến dưới 90 thì xếp loại gì?",
        question="85 điểm rèn luyện xếp loại gì?",
        operation="conduct_classification", score=85, span="85 điểm",
    )
    assert "score_or_grade" not in task["slots"]
    assert "numeric_span_repaired:score_or_grade" not in task["normalization_warnings"]
    assert "ungrounded_slot:score_or_grade" in task["normalization_warnings"]


@pytest.mark.parametrize(
    ("query", "score", "span", "expected"),
    [
        # Decimal dot for the student's comma.
        ("Còn GPA 2,83 thì xếp loại học lực gì?", "2.83", "GPA 2.83", "2,83"),
        # A scale written in words: the number as written, the lookup reads the scale.
        ("Em được 1.6 theo thang điểm 4 thì xếp loại học lực gì?", "1.6/4",
         "1.6 theo thang điểm 4", "1.6"),
        # The student's own denominator is kept.
        ("Điểm 3,6/4 xếp loại học lực gì?", "3,6", "3,6", "3,6/4"),
    ],
)
def test_decimal_mark_and_scale_follow_the_question(query, score, span, expected):
    task = _scoring_task(query, question=query, operation="academic_classification",
                         score=score, span=span)
    assert task["slots"]["score_or_grade"] == expected
    assert task["slot_spans"]["score_or_grade"] == expected


@pytest.mark.parametrize(
    ("query", "score"),
    [
        ("Em rớt 3 môn thì có bị cảnh báo học vụ không?", 3),
        ("Sinh viên năm 2 thì xếp loại học lực thế nào?", 2),
        ("Em được 91 điểm rèn luyện học kỳ 2 thì xếp loại gì?", 2),
    ],
)
def test_a_bare_number_that_is_not_written_as_a_score_grounds_nothing(query, score):
    assert score_as_written(score, query) is None
    task = _scoring_task(query, question=query, operation="conduct_classification",
                         score=score, span=f"{score} điểm")
    assert "score_or_grade" not in task["slots"]


def test_a_conflicting_scale_or_two_readings_is_not_repaired():
    assert score_as_written("3,6/10", "Điểm 3,6/4 xếp loại gì?") is None
    assert score_as_written("3,6", "Điểm 3,6/4 hay 3,6/10?") is None
    assert score_as_written("49", "Em khóa K49") is None
    task = _scoring_task(
        "Điểm 3,6/4 xếp loại học lực gì?", question="Điểm 3,6/10 xếp loại gì?",
        operation="academic_classification", score="3,6/10", span="3,6/10",
    )
    assert "score_or_grade" not in task["slots"]


def test_the_plan_logs_what_was_dropped_and_what_was_repaired():
    dropped = _scoring_task(
        "Khung điểm rèn luyện từ 80 đến dưới 90 thì xếp loại gì?",
        question="85 điểm rèn luyện xếp loại gì?",
        operation="conduct_classification", score=85, span="85 điểm",
    )
    assert {"slot": "score_or_grade", "warning": "ungrounded_slot",
            "value": 85, "span": "85 điểm"} in dropped["normalization_drops"]

    repaired = _scoring_task(
        "Em được 78 điểm rèn luyện, bạn em 81 điểm thì mỗi người xếp loại gì?",
        question="Bạn em được 81 điểm rèn luyện thì xếp loại gì?",
        operation="conduct_classification", score=81, span="81 điểm rèn luyện " * 10,
    )
    entry, = repaired["normalization_drops"]
    assert entry["warning"] == "numeric_span_repaired" and entry["kept"] == "81"
    # Long planner text is cut for the trace.
    assert len(entry["span"]) == 81 and entry["span"].endswith("…")
