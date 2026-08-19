from __future__ import annotations

import json
import shutil

from src.evaluation.single_cohort_v2 import (
    BUNDLE_DIR,
    evaluate_release_gates,
    exact_plan_match,
    validate_bundle,
)


def test_frozen_bundle_has_required_counts_and_contract() -> None:
    result = validate_bundle()
    assert result.valid, result.errors
    assert result.counts == {"dev": 150, "hidden": 60}
    assert set(result.coverage["request_counts"]) >= {3, 4, 5, 6}
    assert set(result.coverage["statuses"]) == {
        "ok", "no_match", "invalid", "unresolved", "error"
    }
    assert result.coverage["same_tool_pair"]
    assert result.coverage["different_tool_pair"]


def test_exact_plan_requires_request_order_and_slots() -> None:
    expected = {"outcome": "execute", "context_mode": "standalone", "effective_cohort": "K51", "effective_cohort_source": "raw_query", "atomic_requests": [{"request_id": "r1", "request_kind": "structured", "tool_name": "scoring", "intent": "direct_value", "query_span": "GPA 3.2", "slots": {"score": "3.2"}, "cohort_refs": ["K51"]}]}
    assert exact_plan_match(expected, expected)
    changed = {**expected, "atomic_requests": [{**expected["atomic_requests"][0], "slots": {}}]}
    assert not exact_plan_match(expected, changed)


def test_manifest_hash_detects_hidden_or_dev_tampering(tmp_path) -> None:
    bundle = tmp_path / "single_cohort_v2"
    shutil.copytree(BUNDLE_DIR, bundle)
    dev_path = bundle / "dev.json"
    cases = json.loads(dev_path.read_text(encoding="utf-8"))
    cases[0]["query"] += " tampered"
    dev_path.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
    result = validate_bundle(bundle)
    assert not result.valid
    assert "frozen hash mismatch: dev.json" in result.errors


def test_release_gates_fail_closed_when_metrics_are_missing() -> None:
    result = evaluate_release_gates({"contract_invariants": 1.0})
    assert not result.passed
    assert "hidden_exact_plan" in result.missing_metrics
