"""Every reference-table row stays reachable, and a shared value stays unpinned."""

from scripts.audit_structured_lookups import audit


def test_every_reference_table_row_is_pinned_by_its_own_key() -> None:
    summary, findings = audit()

    assert findings == [], findings
    # Guard the sweep itself: a registry change that stopped producing probes
    # would otherwise pass silently.
    assert summary["probes_with_a_unique_row"] >= 110
