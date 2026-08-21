from scripts.run_single_cohort_production_smoke import SMOKE_CASES


def test_production_smoke_has_twenty_unique_non_hidden_cases() -> None:
    ids = [case_id for case_id, _ in SMOKE_CASES]
    nodes = [node_id for _, node_id in SMOKE_CASES]
    assert len(ids) == 20
    assert len(ids) == len(set(ids))
    assert len(nodes) == len(set(nodes))
    assert all("hidden" not in value.lower() for value in ids + nodes)


def test_production_smoke_covers_runtime_boundaries() -> None:
    ids = set(case_id for case_id, _ in SMOKE_CASES)
    assert {
        "structured_two_requests",
        "mixed_independent_execution",
        "two_regulations",
        "grounded_follow_up",
        "multi_cohort_rejection",
        "sync_stream_cache_parity",
        "cache_fingerprint_isolation",
        "plan_tampering",
        "router_provider_failure",
        "cross_request_citation_rejection",
    } <= ids
