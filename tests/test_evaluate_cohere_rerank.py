from __future__ import annotations

import pytest

from scripts.evaluate_cohere_rerank import (
    CANDIDATE_COUNT,
    MODEL,
    EvaluationError,
    child_id,
    group_parent_ids,
    read_jsonl,
    sha256_text,
    validate_checkpoint_row,
    validate_response,
)


def _child(child: str, parent: str) -> dict:
    return {"child_id": child, "parent_id": parent, "content": child}


def test_group_parent_ids_uses_best_child_score_and_filters_missing_parents() -> None:
    ranked = [
        (0.95, _child("a1", "a")),
        (0.90, _child("a2", "a")),
        (0.85, _child("missing", "missing")),
        (0.80, _child("b1", "b")),
    ]

    assert group_parent_ids(ranked, {"a", "b"}) == ["a", "b"]


def test_validate_response_requires_complete_candidate_permutation() -> None:
    response = {
        "results": [
            {"index": 1, "relevance_score": 0.8},
            {"index": 0, "relevance_score": 0.5},
        ]
    }

    assert validate_response(response, 2) == [(1, 0.8), (0, 0.5)]
    with pytest.raises(Exception, match="changed or omitted"):
        validate_response({"results": response["results"][:1]}, 2)


def test_read_jsonl_returns_empty_for_missing_checkpoint(tmp_path) -> None:
    assert read_jsonl(tmp_path / "checkpoint.jsonl") == []


def test_checkpoint_row_is_bound_to_event_identity() -> None:
    children = [_child(f"c{index}", f"p{index}") for index in range(CANDIDATE_COUNT)]
    event = {
        "event_key": "case:0:K51",
        "case_id": "case",
        "event_index": 0,
        "cohort": "K51",
        "query": "query",
        "children": children,
    }
    candidate_ids = [child_id(child) for child in children]
    row = {
        "event_key": event["event_key"],
        "case_id": event["case_id"],
        "event_index": event["event_index"],
        "cohort": event["cohort"],
        "query_sha256": sha256_text(event["query"]),
        "candidate_child_ids": candidate_ids,
        "candidate_content_sha256": [
            sha256_text(str(child["content"])) for child in children
        ],
        "model": MODEL,
        "candidate_count": CANDIDATE_COUNT,
        "cohere_ranked_child_ids": list(reversed(candidate_ids)),
        "cohere_scores": [1.0 - index / 100 for index in range(CANDIDATE_COUNT)],
    }

    validate_checkpoint_row(row, event)
    row["query_sha256"] = "stale"
    with pytest.raises(EvaluationError, match="query_sha256"):
        validate_checkpoint_row(row, event)
