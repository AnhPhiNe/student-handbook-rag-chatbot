"""Every answerable field is one the planner is told about, or a known gap listed here."""
from scripts.audit_tool_descriptions import audit

# Fields the data holds and no registry description names, found on 2026-10-01 by
# reading the official_v4 failures. Until each description is rewritten the
# planner cannot route a question to them; `scholarship_score_range` is the one
# that cost V4-148 and V4-150. A gap outside this list is a new one and fails.
KNOWN_GAPS = {
    ("faculty", "internal_numbers"),
    ("office", "internal_numbers"),
    ("student_service", "internal_numbers"),
    ("foreign_language", "input_requirements"),
    ("scholarship_classification", "scholarship_score_range"),
    ("scholarship_classification", "criterion"),
    ("scholarship_classification", "requirement"),
    ("scholarship_classification", "academic_classification"),
    ("scholarship_classification", "conduct_classification_condition"),
    ("scholarship_classification", "academic_score_scale"),
    ("scholarship_classification", "conduct_score_scale"),
}


def test_no_unclassified_or_stale_field_and_no_new_advertising_gap() -> None:
    summary, findings = audit()

    assert summary["tools"] == 8
    unclassified = [f for f in findings if f["kind"] != "field_the_planner_is_not_told_about"]
    assert unclassified == [], unclassified
    gaps = {(f["tool"], f["field"]) for f in findings}
    assert gaps == KNOWN_GAPS, {"new": gaps - KNOWN_GAPS, "closed": KNOWN_GAPS - gaps}
