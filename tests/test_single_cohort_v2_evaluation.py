from __future__ import annotations

from src.evaluation.single_cohort_v2 import exact_plan_match, validate_bundle


def test_frozen_bundle_has_required_counts_and_contract() -> None:
    result = validate_bundle()
    assert result.valid, result.errors
    assert result.counts == {"dev.json": 150, "hidden.json": 60}


def test_exact_plan_requires_request_order_and_slots() -> None:
    expected = {"outcome": "execute", "context_mode": "validated", "effective_cohort": "K51", "effective_cohort_source": "raw_query", "atomic_requests": [{"request_id": "r1", "request_kind": "structured", "lookup_type": "scoring", "intent": "direct_value", "query_span": "GPA 3.2", "slots": {"score": "3.2"}, "cohort_refs": ["K51"]}]}
    assert exact_plan_match(expected, expected)
    changed = {**expected, "atomic_requests": [{**expected["atomic_requests"][0], "slots": {}}]}
    assert not exact_plan_match(expected, changed)
