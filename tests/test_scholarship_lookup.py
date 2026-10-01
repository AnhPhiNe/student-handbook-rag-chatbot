"""Scholarship row locks use complete labels supplied by the student."""

import json
from pathlib import Path

import pytest

from src.retrieval.core.query_plan import QUERY_PLAN_SCHEMA_VERSION, normalize_query_plan
from src.retrieval.core.structured_dispatcher import resolve_structured_task


@pytest.fixture(scope="module")
def scholarship_tables():
    path = Path(__file__).resolve().parents[1] / "data/processed/tables/structured_tables_registry.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(tables, query, value, aspect):
    payload = {
        "schema_version": QUERY_PLAN_SCHEMA_VERSION,
        "context_mode": "standalone",
        "out_of_domain": False,
        "tasks": [{
            "id": "t1", "question": query, "mode": "structured",
            "lookup_type": "scholarship_classification", "intent": "direct_value",
            "cohorts": ["K50"],
            "slots": {"aspect": aspect, "score_or_label": value},
            "slot_spans": {"score_or_label": value},
        }],
    }
    plan, errors = normalize_query_plan(payload, query=query, selected_cohort="K50")
    assert errors == []
    return resolve_structured_task(
        plan["tasks"][0], query=query, cohort="K50",
        formula_rules=[], office_directory=[], student_service_directory=[],
        student_faculty_profiles=[], structured_tables_registry=tables, program_directory=[],
    )


@pytest.mark.parametrize("aspect", ["amount", "classification"])
def test_other_scholarships_does_not_lock_fair_label(scholarship_tables, aspect):
    resolution = _resolve(
        scholarship_tables, "Em muốn xem các mức học bổng khác của K50.", "khác", aspect,
    )

    assert resolution is not None
    assert resolution.resolution_status == "evidence_only"
    assert "resolved_result" not in resolution.result
    assert len(resolution.result["display_rows"]) == 3


@pytest.mark.parametrize("label", ["Khá", "gioi"])
def test_complete_scholarship_label_keeps_row_lock(scholarship_tables, label):
    resolution = _resolve(
        scholarship_tables, f"Cho em xem mức học bổng loại {label} của K50.", label, "amount",
    )

    assert resolution is not None
    assert resolution.resolution_status == "resolved"
    expected_label = "Giỏi" if label == "gioi" else label
    assert resolution.result["resolved_result"]["result"]["scholarship_level"] == expected_label


def test_multiple_labels_keep_complete_table_without_single_row_lock(scholarship_tables):
    resolution = _resolve(
        scholarship_tables, "So sánh mức học bổng loại Khá và Giỏi của K50.",
        ["Khá", "Giỏi"], "amount",
    )

    assert resolution is not None
    assert resolution.resolution_status == "evidence_only"
    assert "resolved_result" not in resolution.result
    assert len(resolution.result["display_rows"]) == 3


def test_numeric_scholarship_score_keeps_row_lock(scholarship_tables):
    resolution = _resolve(
        scholarship_tables, "Điểm học bổng 3,0 của K50 nằm trong khoảng của loại nào?",
        "3,0", "classification",
    )

    assert resolution is not None
    assert resolution.resolution_status == "resolved"
    assert resolution.result["resolved_result"]["result"]["label"] == "Khá"
