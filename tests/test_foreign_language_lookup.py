"""Textual certificate levels must match a complete code or phrase."""

import json
from pathlib import Path

import pytest

from src.retrieval.core.foreign_language_lookup import _level_from_text, normalize_text
from src.retrieval.core.query_plan import QUERY_PLAN_SCHEMA_VERSION, normalize_query_plan
from src.retrieval.core.structured_dispatcher import resolve_structured_task


@pytest.fixture(scope="module")
def language_tables():
    path = Path(__file__).resolve().parents[1] / "data/processed/tables/structured_tables_registry.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve(tables, certificate, level):
    query = f"Chứng chỉ {certificate} {level} của em tương đương bậc nào?"
    slots = {"certificate_or_language": certificate, "score_or_level": level}
    payload = {
        "schema_version": QUERY_PLAN_SCHEMA_VERSION,
        "context_mode": "standalone",
        "out_of_domain": False,
        "tasks": [{
            "id": "t1", "question": query, "mode": "structured",
            "lookup_type": "foreign_language", "intent": "direct_value",
            "cohorts": ["K50"], "slots": slots, "slot_spans": slots,
        }],
    }
    plan, errors = normalize_query_plan(payload, query=query, selected_cohort="K50")
    assert errors == []
    resolution = resolve_structured_task(
        plan["tasks"][0], query=query, cohort="K50",
        formula_rules=[], office_directory=[], student_service_directory=[],
        student_faculty_profiles=[], structured_tables_registry=tables, program_directory=[],
    )
    assert resolution is not None
    return resolution


@pytest.mark.parametrize("certificate,level", [
    ("JLPT", "N30"), ("JLPT", "N40"),
    ("Cambridge", "B10"), ("Cambridge", "B20"),
    ("HSK", "bậc 30"), ("HSK", "bậc 40"),
])
def test_longer_codes_do_not_match_a_level_prefix(language_tables, certificate, level):
    resolution = _resolve(language_tables, certificate, level)

    # An unmatched code must keep reference evidence, not an unresolved fact lock.
    assert resolution.resolution_status == "evidence_only"
    assert "resolved_result" not in resolution.result
    row = next(r for r in resolution.result["display_rows"]
               if certificate.casefold() in r["certificate"].casefold())
    assert row["equivalent_level_3"]
    assert row["equivalent_level_4"]


@pytest.mark.parametrize("certificate,level,expected", [
    ("JLPT", "N3", "bac_4"), ("JLPT", "n4.", "bac_3"),
    ("Cambridge", "B1", "bac_3"), ("Cambridge", "B2", "bac_4"),
    ("HSK", "bậc 3", "bac_3"), ("HSK", "bậc 4", "bac_4"),
    ("IELTS", "4,5", "bac_3"), ("IELTS", "6,0", "bac_4"),
    ("TOPIK II", "120", "bac_3"), ("TOPIK II", "150", "bac_4"),
])
def test_complete_levels_and_numeric_scores_still_resolve(
    language_tables, certificate, level, expected,
):
    result = _resolve(language_tables, certificate, level).result["resolved_result"]

    assert result["result"]["matched_level"] == expected


def test_a_named_level_is_answered_by_a_range_column() -> None:
    """Level columns hold score ranges as often as level names.

    Searching a range for the digit is wrong either way: a standalone "4" is
    absent from "46 - 93", and a substring "4" matches it only by accident.
    """
    row = {"certificate": "TOEFL iBT", "equivalent_level_3": "30 - 45", "equivalent_level_4": "46 - 93"}
    assert _level_from_text(row, normalize_text("TOEFL iBT bậc 4")) == "bac_4"
    assert _level_from_text(row, normalize_text("TOEFL iBT bậc 3")) == "bac_3"
    # A row that leaves the level unset must not be claimed for it.
    assert _level_from_text({"equivalent_level_3": "450 - 499", "equivalent_level_4": ""},
                            normalize_text("TOEFL ITP bậc 4")) is None
