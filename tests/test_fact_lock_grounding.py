"""A fact lock is grounded in the student's words, not in the planner's rewording of a task."""
import json
from pathlib import Path

from src.retrieval.core.query_plan import grounding_text
from src.retrieval.core.structured_dispatcher import resolve_structured_task

REGISTRY = json.loads(Path("data/processed/tables/structured_tables_registry.json").read_text(encoding="utf-8"))

# official_v2 case 091 (2026-09-29): the span quotes the student, the task question rewords it.
QUESTION = "Rèn luyện 82 điểm được loại gì, học bổng giỏi cần rèn luyện bao nhiêu điểm?"
TASK = {
    "lookup_type": "scoring", "intent": "direct_value",
    "question": "Điểm rèn luyện 82 được xếp loại gì?",
    "slots": {"operation": "conduct_classification", "score_or_grade": 82},
    "slot_spans": {"operation": "rèn luyện", "score_or_grade": "82 điểm"},
}


def _resolve(grounding: str | None):
    return resolve_structured_task(
        TASK, query=TASK["question"], grounding=grounding, cohort="K50",
        formula_rules=[], office_directory=[], student_service_directory=[],
        student_faculty_profiles=[], structured_tables_registry=REGISTRY, program_directory=[],
    )


def test_a_span_quoted_from_the_student_locks_the_row():
    locked = _resolve(QUESTION).result["resolved_result"]
    assert locked["result"]["label"] == "Tốt"


def test_the_task_question_alone_does_not_ground_a_span_it_does_not_contain():
    assert "resolved_result" not in _resolve(None).result


def test_grounding_text_is_the_question_plus_the_referenced_turns():
    history = [
        {"role": "user", "content": "GPA 3,2 xếp loại gì?"},
        {"role": "assistant", "content": "Loại Giỏi."},
        {"role": "user", "content": "Còn điểm rèn luyện 82?"},
    ]
    follow_up = {"context_mode": "follow_up", "referenced_turns": [0, 7]}
    assert grounding_text("Thế còn K50?", follow_up, history) == "Thế còn K50?\nGPA 3,2 xếp loại gì?"
    assert grounding_text("Thế còn K50?", {"context_mode": "standalone", "referenced_turns": [0]}, history) == (
        "Thế còn K50?"
    )
