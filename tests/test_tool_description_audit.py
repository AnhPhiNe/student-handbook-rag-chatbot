"""Every answerable field is one the planner is told about, or a known gap listed here."""
from scripts.audit_tool_descriptions import audit

# No aspect returns all four scholarship reference tables. Advertising that
# path does not require a new enum, and does not promise an award decision.
# This lexical test complements, not replaces, runtime contract tests.
KNOWN_GAPS = set()


def test_no_unclassified_or_stale_field_and_no_new_advertising_gap() -> None:
    summary, findings = audit()

    assert summary["tools"] == 8
    unclassified = [f for f in findings if f["kind"] != "field_the_planner_is_not_told_about"]
    assert unclassified == [], unclassified
    gaps = {(f["tool"], f["field"]) for f in findings}
    assert gaps == KNOWN_GAPS, {"new": gaps - KNOWN_GAPS, "closed": KNOWN_GAPS - gaps}
