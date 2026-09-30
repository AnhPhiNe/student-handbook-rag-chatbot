"""Every answerable field is one the planner is told about, or a known gap listed here."""
from scripts.audit_tool_descriptions import audit

# The scholarship tool reads four table subtypes but its `table_selector` maps
# only two of them to a value of `aspect`, so the eligibility table (criterion,
# requirement) and the score-formula table (the two scales) cannot be selected
# at all. Advertising them would promise what the tool cannot deliver; reaching
# them needs a third `aspect` value and the code behind it. A gap outside this
# list is a new one and fails, which is how the audit stops the
# `scholarship_score_range` mistake (V4-148, V4-150) from recurring.
KNOWN_GAPS = {
    ("scholarship_classification", "criterion"),
    ("scholarship_classification", "requirement"),
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
