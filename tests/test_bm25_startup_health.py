from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.retrieval.core.hybrid_pipeline import ChildParentHybridRetriever
from src.retrieval.core.runtime_health import (
    get_bm25_runtime_status,
    set_bm25_runtime_status,
)


def _retriever_stub() -> ChildParentHybridRetriever:
    retriever = ChildParentHybridRetriever.__new__(ChildParentHybridRetriever)
    retriever.collection_name = "test-collection"
    retriever.qdrant_client = Mock()
    retriever.bm25 = Mock()
    return retriever


def test_bm25_startup_retries_qdrant_scroll_then_becomes_ready() -> None:
    retriever = _retriever_stub()
    point = SimpleNamespace(id="c1", payload={"chunk_id": "c1", "content": "text"})
    retriever.qdrant_client.scroll.side_effect = [
        TimeoutError("temporary timeout"),
        ([point], None),
    ]

    with patch("src.retrieval.core.hybrid_pipeline.time.sleep") as sleep:
        succeeded = retriever._build_bm25_index_with_retry(
            max_attempts=3,
            backoff_seconds=0.25,
        )

    assert succeeded is True
    assert retriever.qdrant_client.scroll.call_count == 2
    sleep.assert_called_once_with(0.25)
    retriever.bm25.build_bm25_index.assert_called_once()
    assert get_bm25_runtime_status() == {
        "status": "ready",
        "attempts": 2,
        "error_type": None,
    }


def test_bm25_startup_becomes_degraded_after_bounded_retries() -> None:
    retriever = _retriever_stub()
    retriever.qdrant_client.scroll.side_effect = TimeoutError("persistent timeout")

    with patch("src.retrieval.core.hybrid_pipeline.time.sleep") as sleep:
        succeeded = retriever._build_bm25_index_with_retry(
            max_attempts=3,
            backoff_seconds=0.25,
        )

    assert succeeded is False
    assert retriever.qdrant_client.scroll.call_count == 3
    assert [call.args[0] for call in sleep.call_args_list] == [0.25, 0.5]
    retriever.bm25.build_bm25_index.assert_not_called()
    assert get_bm25_runtime_status() == {
        "status": "degraded",
        "attempts": 3,
        "error_type": "TimeoutError",
    }


def test_bm25_runtime_status_snapshot_is_independent() -> None:
    set_bm25_runtime_status("initializing", attempts=0)
    snapshot = get_bm25_runtime_status()
    snapshot["status"] = "degraded"

    assert get_bm25_runtime_status()["status"] == "initializing"
