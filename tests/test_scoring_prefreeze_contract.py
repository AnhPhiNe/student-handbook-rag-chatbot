"""Cross-component contracts; no model calls or benchmark-answer matching."""
import json
from pathlib import Path

import pytest

from src.retrieval.core.slang_normalizer import SlangNormalizer
from src.retrieval.core.structured_dispatcher import _unique_reference_resolution, _select_reference_tables
from src.retrieval.core.structured_routing import normalize_router_decision


@pytest.mark.parametrize("phrase", ["qua môn", "không qua môn", "pass môn", "rớt môn", "đậu môn"])
def test_pass_intent_survives_both_normalization_stages(phrase):
    query = SlangNormalizer().replace_for_router(f"Em được 6,1 thì có {phrase} không?")
    decision = normalize_router_decision({
        "route": "structured", "lookup_type": "scoring", "intent": "direct_value",
        "slots": {"score_or_grade": "6.1"}, "slot_spans": {"score_or_grade": "6,1"},
    }, query=query, selected_cohort="K51")
    assert decision["slots"]["operation"] == "pass_threshold"


@pytest.mark.parametrize("scope,expected", [("pass_fail_ungraded", False), ("remaining", True), (None, False)])
def test_grade_conversion_resolver_respects_selector_and_scope(scope, expected):
    tables = json.loads(Path("data/processed/tables/scoring_tables.json").read_text(encoding="utf-8"))
    result = _unique_reference_resolution(
        "scoring", query="Tra bảng", slots={"operation": "grade_10_to_letter", "score_or_grade": 6.1, "course_scope": scope},
        cohort="K51", scoring_tables=tables, foreign_language_tables=[], structured_tables_registry=[],
    )
    assert (result is not None) is expected
    if result:
        assert result["result"][0]["row"]["letter_grade"] == "C"


@pytest.mark.parametrize("cohort", ["K48-K49", "K50", "K51"])
@pytest.mark.parametrize("operation", ["grade_10_to_letter", "pass_threshold", "academic_classification", "conduct_classification", "letter_to_grade_4"])
def test_real_catalog_selector_contract(cohort, operation):
    registry = json.loads(Path("data/processed/tables/structured_tables_registry.json").read_text(encoding="utf-8"))
    scoring = json.loads(Path("data/processed/tables/scoring_tables.json").read_text(encoding="utf-8"))
    evidence = _select_reference_tables("scoring", {"operation": operation}, [t for t in registry if t.get("cohort") == cohort])
    operands = _select_reference_tables("scoring", {"operation": operation}, [t for t in scoring if t.get("cohort") == cohort], resolver_catalog=True)
    assert evidence and operands
    if operation == "grade_10_to_letter":
        assert all(t["table_subtype"] == "grade_scale" for t in evidence)
        assert all(t.get("course_scope") != "pass_fail_ungraded" for t in operands)


@pytest.mark.parametrize("scope", ["foundation", "remaining", "pass_fail_ungraded"])
def test_explicit_scope_constrains_evidence_and_resolver(scope):
    registry = json.loads(Path("data/processed/tables/structured_tables_registry.json").read_text(encoding="utf-8"))
    scoring = json.loads(Path("data/processed/tables/scoring_tables.json").read_text(encoding="utf-8"))
    slots = {"operation": "pass_threshold", "course_scope": scope}
    evidence = _select_reference_tables("scoring", slots, [t for t in registry if t.get("cohort") == "K51"])
    operands = _select_reference_tables("scoring", slots, [t for t in scoring if t.get("cohort") == "K51"], resolver_catalog=True)
    assert len(evidence) == len(operands) == 1
    assert evidence[0]["table_id"].endswith(scope)
    assert operands[0]["course_scope"] == scope
