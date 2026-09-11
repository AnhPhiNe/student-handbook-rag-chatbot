"""Cross-component contracts; no model calls or benchmark-answer matching."""
import json
from pathlib import Path

import pytest

from src.retrieval.core.slang_normalizer import SlangNormalizer
from src.retrieval.core.structured_dispatcher import resolve_structured_task
from src.retrieval.core.structured_routing import prepare_structured_task


@pytest.mark.parametrize("phrase", ["qua môn", "không qua môn", "pass môn", "rớt môn", "đậu môn"])
def test_pass_intent_survives_both_normalization_stages(phrase):
    query = SlangNormalizer().replace_for_router(f"Em được 6,1 thì có {phrase} không?")
    decision = prepare_structured_task(
        query,
        lookup_type="scoring",
        intent="direct_value",
        slots={"operation": "pass_threshold", "score_or_grade": "6.1"},
        slot_spans={"score_or_grade": "6,1"},
        cohort="K51",
    )
    assert decision["slots"]["operation"] == "pass_threshold"


def resolve(slots, cohort, *, registry=None, legacy=None, intent="direct_value", clarification=None):
    if registry is None:
        registry = json.loads(Path("data/processed/tables/structured_tables_registry.json").read_text(encoding="utf-8"))
    return resolve_structured_task(
        {"lookup_type": "scoring", "intent": intent, "slots": slots,
         "clarification_question": clarification,
         "slot_spans": {"score_or_grade": "6,1", "course_scope": "học phần còn lại" if slots.get("course_scope") == "remaining" else slots.get("course_scope")}},
        query="6,1 học phần còn lại foundation remaining pass_fail_ungraded", cohort=cohort,
        formula_rules=[], office_directory=[], student_service_directory=[],
        student_faculty_profiles=[], structured_tables_registry=registry,
        program_directory=[],
    )


@pytest.mark.parametrize("scope,expected", [("pass_fail_ungraded", False), ("remaining", True), (None, False)])
def test_grade_conversion_resolver_respects_selector_and_scope(scope, expected):
    resolution = resolve({"operation": "grade_10_to_letter", "score_or_grade": 6.1, "course_scope": scope}, "K51")
    result = resolution.result.get("resolved_result") if resolution else None
    assert (result is not None) is expected
    if result:
        assert result["result"][0]["row"]["letter_grade"] == "C"


@pytest.mark.parametrize("cohort", ["K48-K49", "K50", "K51"])
@pytest.mark.parametrize("operation", ["grade_10_to_letter", "pass_threshold", "academic_classification", "conduct_classification", "letter_to_grade_4"])
def test_real_catalog_selector_contract(cohort, operation):
    resolution = resolve({"operation": operation}, cohort)
    assert resolution is not None
    evidence = resolution.result.get("sub_lookups") or [resolution.result]
    if operation == "grade_10_to_letter":
        assert all(t["table_subtype"] == "grade_scale" for t in evidence)
    assert "resolved_result" not in resolution.result


@pytest.mark.parametrize("scope", ["foundation", "remaining", "pass_fail_ungraded"])
def test_explicit_scope_constrains_evidence_and_resolver(scope):
    slots = {"operation": "pass_threshold", "course_scope": scope}
    resolution = resolve(slots, "K51")
    assert resolution is not None
    assert not resolution.result.get("sub_lookups")
    assert resolution.result["table_id"].endswith(scope)


def test_legacy_catalog_cannot_supply_a_lock_without_canonical_evidence():
    legacy = [{"table_id": "academic_classification", "cohort": "K51",
               "rows": [{"range": "0 - 4", "label": "incorrect legacy value"}]}]
    assert resolve({"operation": "academic_classification", "score_or_grade": 6.1},
                   "K51", registry=[], legacy=legacy) is None


def test_lock_and_evidence_share_the_selected_source():
    slots = {"operation": "grade_10_to_letter", "score_or_grade": 6.1,
             "course_scope": "remaining"}
    resolution = resolve(slots, "K51", legacy=[{"table_id": "invalid"}])
    assert resolution.resolution_status == "resolved"
    assert resolution.result["table_id"] == resolution.result["resolved_result"]["table_id"]


@pytest.mark.parametrize("intent,expected", [
    ("direct_value", "needs_clarification"), ("list_items", "evidence_only"),
])
def test_explicit_missing_input_does_not_turn_list_requests_into_clarification(intent, expected):
    resolution = resolve({"operation": "academic_classification"}, "K51",
                         intent=intent, clarification="Điểm trung bình của bạn là bao nhiêu?")
    assert resolution.resolution_status == expected


def test_resolved_input_takes_precedence_over_stale_clarification():
    resolution = resolve({"operation": "grade_10_to_letter", "score_or_grade": 6.1,
                          "course_scope": "remaining"}, "K51", clarification="Bạn được bao nhiêu điểm?")
    assert resolution.resolution_status == "resolved"
