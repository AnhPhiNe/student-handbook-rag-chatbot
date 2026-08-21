from __future__ import annotations

import json
from typing import Any

from src.generation.answer_pipeline import AnswerPipeline


class _MemoryCache:
    def __init__(self) -> None:
        self.values: dict[str, dict[str, Any]] = {}

    def get(self, key: str) -> dict[str, Any] | None:
        value = self.values.get(key)
        return dict(value) if value is not None else None

    def set(self, key: str, value: dict[str, Any]) -> None:
        self.values[key] = dict(value)


class _VerifiedClient:
    def __init__(self) -> None:
        self.calls = 0

    def generate(self, prompt: str) -> dict[str, Any]:
        self.calls += 1
        if "bộ kiểm chứng claim" in prompt:
            payload = {
                "results": [
                    {
                        "request_id": "r1",
                        "claim_id": "r1.c1",
                        "verdict": "supported",
                        "supporting_evidence_ids": ["chunk-r1"],
                        "reason_code": "direct_support",
                    }
                ]
            }
        else:
            payload = {
                "request_id": "r1",
                "claims": [
                    {
                        "text": "Điều 5 quy định nội dung đã được kiểm chứng.",
                        "citation_ids": ["chunk-r1"],
                    }
                ],
                "abstention_reason": None,
            }
        return {
            "ok": True,
            "text": json.dumps(payload),
            "model_used": "deterministic-gemini",
            "usage": {"input": 1, "output": 1, "total": 2},
        }


def _retrieval_result() -> dict[str, Any]:
    citation = {
        "request_id": "r1",
        "request_index": 0,
        "request_kind": "rag",
        "request_cohort": "K51",
        "chunk_id": "chunk-r1",
        "document_id": "handbook-k51",
        "parent_section_id": "K51_Dieu5",
        "source_pages": [12],
        "title": "Điều 5",
        "content": "Điều 5 quy định nội dung đã được kiểm chứng.",
    }
    return {
        "effective_query": "K51 Điều 5 quy định gì?",
        "selected_cohort": "K51",
        "intent": "regulation_query",
        "strategy": "semantic_request_executor",
        "retrieval_executed": True,
        "needs_clarification": False,
        "out_of_domain": False,
        "citations": [citation],
        "retrieved_items": [dict(citation)],
        "related_references": [],
        "request_results": [
            {
                "request_id": "r1",
                "request_index": 0,
                "request_kind": "rag",
                "query_span": "Điều 5 quy định gì",
                "cohort": "K51",
                "status": "ok",
                "provenance": {"qualified": True},
            }
        ],
        "request_execution_contexts": [],
        "router_decision": {
            "plan_version": "single-cohort-v2",
            "execution_mode": "rag",
        },
    }


def _pipeline(client: _VerifiedClient) -> AnswerPipeline:
    pipeline = AnswerPipeline.__new__(AnswerPipeline)
    pipeline.config = {
        "citations": {"max_sources": 5},
        "guardrails": {"skip_llm_on_low_confidence": True},
        "request_composition": {"max_concurrency": 3},
        "claim_verifier": {"enabled": True, "max_chars_per_evidence": 5000},
    }
    pipeline.llm_config = {"model_name": "deterministic-gemini"}
    pipeline.max_context_chars = 5000
    pipeline.context_allocation = object()
    pipeline.request_sleep_seconds = 0
    pipeline._last_llm_call_at = 0.0
    pipeline.response_cache = _MemoryCache()
    pipeline._get_llm_client = lambda: client
    pipeline._make_response_cache_key = lambda **_kwargs: "verified-cache-key"
    return pipeline


def _patch_pipeline(monkeypatch, pipeline: AnswerPipeline) -> None:
    monkeypatch.setattr(
        pipeline, "_run_retrieval", lambda *_args, **_kwargs: _retrieval_result()
    )
    monkeypatch.setattr(
        "src.generation.answer_pipeline.detect_ambiguous_query",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "src.generation.answer_pipeline.is_out_of_domain_query",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "src.generation.answer_pipeline.build_context_for_prompt",
        lambda *_args, **_kwargs: "request-scoped context",
    )


def test_sync_then_stream_cache_have_verified_debug_parity(monkeypatch) -> None:
    client = _VerifiedClient()
    pipeline = _pipeline(client)
    _patch_pipeline(monkeypatch, pipeline)

    sync = pipeline.answer("K51 Điều 5 quy định gì?", cohort="K51")
    events = list(pipeline.answer_stream("K51 Điều 5 quy định gì?", cohort="K51"))
    stream_metadata = [event for event in events if event.get("type") == "metadata"][-1]
    stream_text = next(event["text"] for event in events if event.get("type") == "token")

    assert client.calls == 2
    assert sync["answer"] == stream_text
    assert sync["debug"]["verification_status"] == "passed"
    assert stream_metadata["debug"]["verification_status"] == "passed"
    assert stream_metadata["used_cache"] is True


def test_uncached_stream_buffers_until_verified_replacement(monkeypatch) -> None:
    client = _VerifiedClient()
    pipeline = _pipeline(client)
    _patch_pipeline(monkeypatch, pipeline)

    events = list(pipeline.answer_stream("K51 Điều 5 quy định gì?", cohort="K51"))

    assert client.calls == 2
    assert not any(event.get("type") == "token" for event in events)
    replacement = next(event for event in events if event.get("type") == "replace")
    metadata = [event for event in events if event.get("type") == "metadata"][-1]
    assert "Điều 5" in replacement["text"]
    assert metadata["debug"]["verification_executed"] is True
    assert metadata["debug"]["composer_call_count"] == 1
    assert metadata["debug"]["verifier_call_count"] == 1
