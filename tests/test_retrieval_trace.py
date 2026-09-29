"""A retrieval is traced with its stage times, the rerank price and the top candidates' ranks."""
from unittest.mock import patch

from src.api.langsmith_helper import build_trace_metadata, push_trace_to_langsmith
from src.common.usage_tracker import UsageTracker, tracking
from src.retrieval.core.hybrid_pipeline import _RetrievalTrace


def _chunk(chunk_id: str) -> dict:
    return {"chunk_id": chunk_id, "metadata": {"parent_section_id": f"P_{chunk_id}"}}


DENSE = [(0.9, _chunk("a")), (0.8, _chunk("b"))]
BM25 = [(12.0, _chunk("c")), (11.0, _chunk("a"))]
FUSED = [(0.033, _chunk("a")), (0.016, _chunk("c")), (0.016, _chunk("b"))]
RERANKED = [(0.97, _chunk("c")), (0.51, _chunk("a")), (0.02, _chunk("b"))]
TELEMETRY = {"reranker_applied": True, "reranker_model": "Qwen/Qwen3-Reranker-8B",
             "reranker_latency_ms": 1800.0, "reranker_input_tokens": 11000, "reranker_cost": 0.00055}


def _trace() -> _RetrievalTrace:
    trace = _RetrievalTrace(query="email phòng đào tạo", cohort="K51", mode="default")
    trace.rerank_started = trace.started
    trace.stats.update({"embed_ms": 310.0, "embedding_tokens": 6, "bm25_ms": 40.0})
    return trace


def test_a_retrieval_records_ranks_from_every_list_and_the_rerank_call():
    tracker = UsageTracker()
    with tracking(tracker):
        _trace().record(TELEMETRY, RERANKED, DENSE, BM25, FUSED)

    retrieval, rerank = tracker.get_steps()
    assert retrieval["run_type"] == "retriever"
    assert retrieval["metadata"]["reranker_applied"] is True
    assert retrieval["metadata"]["embed_ms"] == 310.0
    first = retrieval["outputs"]["top_candidates"][0]
    assert first == {"rank": 1, "chunk_id": "c", "parent_section_id": "P_c", "score": 0.97,
                     "dense_rank": None, "bm25_rank": 1, "rrf_rank": 2}
    assert rerank["step_name"] == "Reranker"
    assert rerank["input_tokens"] == 11000
    assert rerank["total_cost"] == 0.00055


def test_nothing_is_recorded_outside_a_request():
    _trace().record(TELEMETRY, RERANKED, DENSE, BM25, FUSED)  # no tracker: no error, nothing kept


def test_langsmith_gets_a_retriever_run_and_the_rerank_price():
    tracker = UsageTracker()
    with tracking(tracker):
        _trace().record(TELEMETRY, RERANKED, DENSE, BM25, FUSED)
    runs = []

    class _Client:
        def create_run(self, **kwargs):
            runs.append(kwargs)

    with patch("src.api.langsmith_helper.get_langsmith_client", return_value=_Client()):
        push_trace_to_langsmith("trace-1", input_text="q", output_text="a",
                                metadata=build_trace_metadata({}, query="q"), tracker=tracker)

    _, retrieval, rerank = runs
    assert retrieval["run_type"] == "retriever"
    assert retrieval["outputs"]["top_candidates"][0]["chunk_id"] == "c"
    assert rerank["run_type"] == "llm"
    assert rerank["extra"]["metadata"]["ls_provider"] == "deepinfra"
    assert rerank["extra"]["metadata"]["usage_metadata"]["total_cost"] == 0.00055
