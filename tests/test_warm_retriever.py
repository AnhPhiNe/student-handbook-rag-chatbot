"""warm() must build the retriever singleton and wait out BM25 initialization.

The first RAG question otherwise pays ~15s to create the retriever and scroll
Qdrant for the BM25 index; warm() moves that to boot.
"""

from __future__ import annotations

import src.retrieval.core.runtime_health as runtime_health
import src.services.answer_service as answer_service_module
from src.services.answer_service import AnswerService


class _FakePipeline:
    def __init__(self, **kwargs):
        self.calls: list[str] = []

    def _get_router(self):
        self.calls.append("router")

    @property
    def plan_executor(self):
        self.calls.append("plan_executor")
        return object()

    def _get_llm_client(self):
        self.calls.append("llm")


def _patch(monkeypatch, *, status_sequence):
    monkeypatch.setattr(answer_service_module, "AnswerPipeline", _FakePipeline)
    calls = {"init": 0}

    def _fake_init():
        calls["init"] += 1

    monkeypatch.setattr(
        "src.retrieval.core.hybrid_pipeline.initialize_hybrid_retriever",
        _fake_init,
    )
    seq = iter(status_sequence)
    last = {"v": status_sequence[-1]}

    def _fake_status():
        try:
            last["v"] = next(seq)
        except StopIteration:
            pass
        return {"status": last["v"], "attempts": 1, "error_type": None}

    monkeypatch.setattr(runtime_health, "get_bm25_runtime_status", _fake_status)
    monkeypatch.setattr(
        "src.retrieval.core.runtime_health.get_bm25_runtime_status", _fake_status
    )
    return calls


def test_warm_builds_the_retriever_and_waits_for_bm25(monkeypatch):
    calls = _patch(monkeypatch, status_sequence=["initializing", "initializing", "ready"])
    service = AnswerService()
    service.warm(bm25_wait_seconds=5.0)
    assert calls["init"] == 1
    assert service._get_pipeline().calls == ["router", "plan_executor", "llm"]


def test_warm_stops_waiting_at_the_deadline_when_bm25_never_finishes(monkeypatch):
    _patch(monkeypatch, status_sequence=["initializing"])
    service = AnswerService()
    # A zero budget means the loop must not block even while BM25 is stuck.
    service.warm(bm25_wait_seconds=0.0)


def test_warm_returns_immediately_when_bm25_is_already_degraded(monkeypatch):
    _patch(monkeypatch, status_sequence=["degraded"])
    service = AnswerService()
    service.warm(bm25_wait_seconds=30.0)  # must not wait: degraded is terminal
