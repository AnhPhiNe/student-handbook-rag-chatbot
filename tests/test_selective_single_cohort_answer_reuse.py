from __future__ import annotations

import copy

from scripts.selective_single_cohort_answer_reuse import (
    _digest,
    _stable,
    compare_snapshots,
)


def _snapshot() -> dict:
    return {
        "effective_query": "Quy định bảo lưu K51",
        "decision": {"outcome": "execute", "cohort": "K51"},
        "requests": [
            {
                "request_id": "r1",
                "request_kind": "rag",
                "query_span": "bảo lưu",
                "status": "ok",
                "qualified": True,
            }
        ],
        "structured_result": None,
        "formula_result": None,
        "context_used": "[Nguồn 1] Điều 12 về bảo lưu",
    }


def test_telemetry_does_not_change_stable_digest() -> None:
    left = {"content": "same", "score": 0.1, "semantic_score": 0.4}
    right = {
        "content": "same",
        "score": 0.9,
        "semantic_score": 0.8,
        "selection_method": "bm25",
    }
    assert _stable(left) == _stable(right)
    assert _digest(left) == _digest(right)


def test_context_or_contract_change_forces_regeneration() -> None:
    source = _snapshot()
    current = copy.deepcopy(source)
    current["context_used"] = "[Nguồn 1] Điều 13 khác nội dung"
    assert compare_snapshots(source, current) == (False, ["context_used"])

    current = copy.deepcopy(source)
    current["requests"][0]["status"] = "no_match"
    reusable, fields = compare_snapshots(source, current)
    assert not reusable
    assert fields == ["requests"]


def test_structured_number_and_cohort_changes_force_regeneration() -> None:
    source = _snapshot()
    source["structured_result"] = {"threshold": 80, "cohort": "K51"}
    current = copy.deepcopy(source)
    current["structured_result"]["threshold"] = 75
    reusable, fields = compare_snapshots(source, current)
    assert not reusable
    assert fields == ["structured_result"]

    current = copy.deepcopy(source)
    current["decision"]["cohort"] = "K50"
    reusable, fields = compare_snapshots(source, current)
    assert not reusable
    assert fields == ["decision"]


def test_identical_composer_inputs_are_reusable() -> None:
    snapshot = _snapshot()
    assert compare_snapshots(snapshot, copy.deepcopy(snapshot)) == (True, [])
