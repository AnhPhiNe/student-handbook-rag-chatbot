from __future__ import annotations

from typing import Any

from src.generation.answer_pipeline import AnswerPipeline


class _FailingStreamClient:
    def generate_stream(self, _prompt: str):
        raise RuntimeError("provider unavailable")


def _stream_pipeline() -> AnswerPipeline:
    pipeline = AnswerPipeline.__new__(AnswerPipeline)
    pipeline.config = {
        "citations": {"max_sources": 2},
        "guardrails": {"skip_llm_on_low_confidence": False},
    }
    pipeline.max_context_chars = 2000
    pipeline.context_allocation = None
    pipeline.request_sleep_seconds = 0
    pipeline._last_llm_call_at = 0.0
    return pipeline


def test_stream_provider_failure_emits_final_api_error_metadata_with_scoped_citations(
    monkeypatch,
) -> None:
    """Streaming must converge to sync's api_error contract after generation fails."""
    pipeline = _stream_pipeline()
    query = "K51 quy định bảo lưu và điều kiện tốt nghiệp thế nào?"
    citations = [
        {
            "request_id": "r1",
            "request_index": 0,
            "request_kind": "rag",
            "request_intent": "policy",
            "request_cohort": "K51",
            "request_retrieval_rank": 1,
            "chunk_id": "retention-rule",
            "chunk_type": "regulation",
            "title": "Bảo lưu kết quả học tập",
        },
        {
            "request_id": "r2",
            "request_index": 1,
            "request_kind": "rag",
            "request_intent": "policy",
            "request_cohort": "K51",
            "request_retrieval_rank": 1,
            "chunk_id": "graduation-rule",
            "chunk_type": "regulation",
            "title": "Điều kiện tốt nghiệp",
        },
    ]
    retrieval_result: dict[str, Any] = {
        "effective_query": query,
        "cohort": "K51",
        "selected_cohort": "K51",
        "intent": "multi_request",
        "strategy": "semantic_request_executor",
        "execution_mode": "mixed",
        "retrieval_executed": True,
        "needs_clarification": False,
        "out_of_domain": False,
        "citations": citations,
        "related_references": [],
        "request_results": [
            {"request_id": "r1", "status": "ok"},
            {"request_id": "r2", "status": "ok"},
        ],
        "request_execution_contexts": [],
        "router_decision": {"plan_version": "single_cohort_v2"},
    }
    prompt_inputs: dict[str, Any] = {}

    monkeypatch.setattr(
        pipeline,
        "_run_retrieval",
        lambda *_args, **_kwargs: retrieval_result,
    )
    monkeypatch.setattr(pipeline, "_get_llm_client", lambda: _FailingStreamClient())
    monkeypatch.setattr(pipeline, "_throttle_llm_call", lambda: None)
    monkeypatch.setattr(
        "src.generation.answer_pipeline.detect_ambiguous_query",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "src.generation.answer_pipeline.is_out_of_domain_query",
        lambda *_args, **_kwargs: False,
    )

    def fake_build_answer_prompt(**kwargs: Any) -> str:
        prompt_inputs.update(kwargs)
        return "deterministic prompt"

    monkeypatch.setattr(
        "src.generation.answer_pipeline.build_answer_prompt",
        fake_build_answer_prompt,
    )

    events = list(pipeline.answer_stream(query, cohort="K51"))
    metadata_events = [event for event in events if event.get("type") == "metadata"]

    assert [citation["request_id"] for citation in prompt_inputs["selected_citations"]] == [
        "r1",
        "r2",
    ]
    assert metadata_events[-1]["status"] == "api_error"
    assert metadata_events[-1]["fallback_reason"] == "api_error"
    assert metadata_events[-1]["llm_called"] is True
    assert [
        citation["request_id"] for citation in metadata_events[-1]["citations_used"]
    ] == ["r1", "r2"]
    assert events[-1]["type"] == "done"
