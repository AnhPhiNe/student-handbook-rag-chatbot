from __future__ import annotations

import json

from scripts.evaluate_cohere_answers import (
    CheckpointedCohereReranker,
    patched_group_method,
)


def _child(child: str, content: str = "content") -> dict:
    return {
        "_id": child,
        "content": content,
        "metadata": {"parent_section_id": child.split("-")[0]},
    }


def test_request_key_is_bound_to_ordered_ids_and_content() -> None:
    first = [_child("a-1"), _child("b-1")]
    assert CheckpointedCohereReranker.request_key("q", first) == (
        CheckpointedCohereReranker.request_key("q", list(first))
    )
    assert CheckpointedCohereReranker.request_key("q", first) != (
        CheckpointedCohereReranker.request_key("q", list(reversed(first)))
    )
    changed = [_child("a-1", "changed"), _child("b-1")]
    assert CheckpointedCohereReranker.request_key("q", first) != (
        CheckpointedCohereReranker.request_key("q", changed)
    )


def test_patched_group_only_replaces_scored_prefix() -> None:
    chunks = [(float(20 - index), _child(f"p{index}-c")) for index in range(20)]

    class Reranker:
        def rank(self, query, scored_chunks):
            assert query == "query"
            assert scored_chunks == chunks
            return list(reversed(scored_chunks[:16])), {
                "request_key": "key",
                "latency_ms": 12.0,
            }

    captured = {}

    def original(self, **kwargs):
        del self
        captured.update(kwargs)
        return ["result"]

    group = patched_group_method(Reranker(), original)
    telemetry = {"ranking_method": "rrf"}
    assert group(
        object(),
        query="query",
        scored_chunks=chunks,
        top_k_final=5,
        retrieval_telemetry=telemetry,
    ) == ["result"]
    assert len(captured["scored_chunks"]) == 16
    assert captured["scored_chunks"][0] == chunks[15]
    assert captured["retrieval_telemetry"]["ranking_method"] == (
        "cohere_rerank_v4_fast"
    )


def test_checkpoint_telemetry_distinguishes_fresh_and_cached_response(
    tmp_path, monkeypatch
) -> None:
    chunks = [(1.0 - index / 100, _child(f"p{index}-c")) for index in range(16)]
    checkpoint = tmp_path / "checkpoint.jsonl"
    reranker = CheckpointedCohereReranker(
        api_key="test-key",
        checkpoint_path=checkpoint,
        min_interval_seconds=0,
        timeout_seconds=1,
    )
    response = {
        "results": [
            {"index": index, "relevance_score": 1.0 - index / 100}
            for index in range(16)
        ],
        "meta": {"billed_units": {"search_units": 1}},
    }
    monkeypatch.setattr(
        "scripts.evaluate_cohere_answers.call_cohere",
        lambda *args, **kwargs: (json.loads(json.dumps(response)), 12.0),
    )

    _, fresh = reranker.rank("query", chunks)
    _, cached = reranker.rank("query", chunks)

    assert fresh["cache_hit"] is False
    assert cached["cache_hit"] is True
