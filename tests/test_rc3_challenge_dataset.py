from __future__ import annotations

import json
from collections import Counter

from src.evaluation.single_cohort_v2 import BUNDLE_DIR, _normalize
from scripts.run_single_cohort_rc3_challenge import _source_contract_bound


CHALLENGE_PATH = BUNDLE_DIR / "rc3_challenge.json"


def test_rc3_challenge_suite_has_exactly_the_bounded_coverage() -> None:
    payload = json.loads(CHALLENGE_PATH.read_text(encoding="utf-8"))
    cases = payload["cases"]

    assert payload["schema_version"] == "single-cohort-rc3-challenge-v1"
    assert payload["max_remediation_rounds"] == 2
    assert len(cases) == 24
    assert Counter(case["category"] for case in cases) == {
        "follow_up_cohort_provenance": 8,
        "metadata_vs_information_need": 6,
        "registry_capability": 6,
        "two_regulations_source_binding": 4,
    }
    assert len({case["id"] for case in cases}) == len(cases)


def test_rc3_challenge_queries_do_not_reuse_hidden_queries() -> None:
    hidden = json.loads((BUNDLE_DIR / "hidden.json").read_text(encoding="utf-8"))
    hidden_signatures = {_normalize(case["query"]) for case in hidden}
    challenge = json.loads(CHALLENGE_PATH.read_text(encoding="utf-8"))["cases"]

    assert all(_normalize(case["query"]) not in hidden_signatures for case in challenge)


def test_rc3_challenge_requests_keep_single_cohort_scope() -> None:
    challenge = json.loads(CHALLENGE_PATH.read_text(encoding="utf-8"))["cases"]

    for case in challenge:
        expected = case["expected"]
        requests = expected["atomic_requests"]
        if expected["outcome"] != "execute":
            assert requests == []
            continue
        for request in requests:
            assert request["request_kind"] in {"structured", "rag"}
            assert request["query_span"]
            assert len(request["cohort_refs"]) <= 1
            if request["request_kind"] == "structured":
                assert request.get("tool_name")
                assert request.get("slots")
            if case["category"] == "two_regulations_source_binding":
                assert request.get("expected_source_contract") == "regulation"


def test_rc3_source_contract_is_request_scoped_and_typed() -> None:
    request = {"request_id": "r2", "request_kind": "rag"}
    valid = {
        "request_id": "r2",
        "document_id": "handbook-k50",
        "parent_section_id": "dieu-1",
        "chunk_id": "chunk-1",
        "source_pages": [1],
    }

    assert _source_contract_bound([valid], request)
    assert not _source_contract_bound([{**valid, "request_id": "r1"}], request)
    assert not _source_contract_bound([{**valid, "chunk_id": None}], request)
