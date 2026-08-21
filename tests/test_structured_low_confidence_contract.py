from __future__ import annotations

import json
from typing import Any

from src.generation.answer_pipeline import AnswerPipeline


class _FormulaClient:
    def __init__(self) -> None:
        self.sync_calls = 0
        self.stream_calls = 0

    def generate(self, _prompt: str) -> dict[str, Any]:
        self.sync_calls += 1
        return {
            "ok": True,
            "text": json.dumps(
                {
                    "request_id": "r1",
                    "claims": [
                        {
                            "text": "Điểm trung bình chung được tính theo công thức A = Σ(ai × ni) / Σ(ni).",
                            "citation_ids": [
                                "structured:formula:so_tay_sinh_vien_khoa_51:K51_QuyCheDaoTao_Chuong3_Dieu11"
                            ],
                            "fact_refs": ["result.formula_text"],
                        }
                    ],
                    "abstention_reason": None,
                }
            ),
            "model_used": "deterministic-formula",
            "usage": {},
            "attempts": 1,
        }

    def generate_stream(self, _prompt: str):
        self.stream_calls += 1
        yield "Điểm trung bình chung được tính theo công thức đã dẫn nguồn."


class _MemoryCache:
    def __init__(self) -> None:
        self.values: dict[str, dict[str, Any]] = {}

    def get(self, key: str) -> dict[str, Any] | None:
        value = self.values.get(key)
        return dict(value) if value is not None else None

    def set(self, key: str, value: dict[str, Any]) -> None:
        self.values[key] = dict(value)


def _formula_retrieval_result() -> dict[str, Any]:
    source_record = {
        "source_kind": "formula",
        "document_id": "so_tay_sinh_vien_khoa_51",
        "cohort": "K51",
        "source_record_id": "cumulative_average_formula",
        "parent_section_id": "K51_QuyCheDaoTao_Chuong3_Dieu11",
        "source_pages": [19, 20, 21],
    }
    return {
        "effective_query": "K51 công thức tính điểm trung bình chung là gì?",
        "selected_cohort": "K51",
        "intent": "formula_lookup",
        "strategy": "semantic_request_executor",
        "retrieval_executed": True,
        "needs_clarification": False,
        "out_of_domain": False,
        "retrieved_items": [],
        "structured_result": {
            "request_id": "r1",
            "request_index": 0,
            "lookup_type": "formula",
            "formula_text": "A = Σ(ai × ni) / Σ(ni)",
            "result": "A = Σ(ai × ni) / Σ(ni)",
            "source_records": [source_record],
        },
        "citations": [
            {
                "request_id": "r1",
                "request_index": 0,
                "request_kind": "structured",
                "chunk_id": (
                    "structured:formula:so_tay_sinh_vien_khoa_51:"
                    "K51_QuyCheDaoTao_Chuong3_Dieu11"
                ),
                "chunk_type": "formula",
                "title": "Công thức tính điểm trung bình chung",
                "content": "A = Σ(ai × ni) / Σ(ni)",
                **source_record,
            }
        ],
        "request_results": [
            {
                "request_id": "r1",
                "request_index": 0,
                "request_kind": "structured",
                "lookup_type": "formula",
                "status": "ok",
                "provenance": {
                    "source_contract": "regulation_table",
                    "source_bound": True,
                },
            }
        ],
        "request_execution_contexts": [],
        "router_decision": {
            "plan_version": "single-cohort-v2",
            "execution_mode": "structured",
            "cohort": "K51",
        },
    }


def _pipeline(client: _FormulaClient) -> AnswerPipeline:
    pipeline = AnswerPipeline.__new__(AnswerPipeline)
    pipeline.config = {
        "citations": {"max_sources": 2},
        "guardrails": {"skip_llm_on_low_confidence": True},
        "request_composition": {"max_concurrency": 3},
    }
    pipeline.llm_config = {"model_name": "deterministic-formula"}
    pipeline.max_context_chars = 2000
    pipeline.context_allocation = object()
    pipeline.request_sleep_seconds = 0
    pipeline._last_llm_call_at = 0.0
    pipeline.response_cache = _MemoryCache()
    pipeline._finalize_evaluation_telemetry = lambda **_kwargs: None
    pipeline._get_llm_client = lambda: client
    pipeline._make_response_cache_key = lambda **_kwargs: "formula-cache-key"
    pipeline._throttle_llm_call = lambda: None
    return pipeline


def _patch_answer_dependencies(monkeypatch, pipeline: AnswerPipeline) -> None:
    retrieval_result = _formula_retrieval_result()
    monkeypatch.setattr(
        pipeline,
        "_run_retrieval",
        lambda *_args, **_kwargs: dict(retrieval_result),
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
        lambda *_args, **_kwargs: "formula context",
    )
    monkeypatch.setattr(
        "src.generation.answer_pipeline.build_answer_prompt",
        lambda **_kwargs: "formula prompt",
    )


def test_source_bound_formula_bypasses_rag_low_confidence_in_sync_and_cache(
    monkeypatch,
) -> None:
    client = _FormulaClient()
    pipeline = _pipeline(client)
    _patch_answer_dependencies(monkeypatch, pipeline)

    first = pipeline.answer(
        "K51 công thức tính điểm trung bình chung là gì?",
        cohort="K51",
    )
    cached = pipeline.answer(
        "K51 công thức tính điểm trung bình chung là gì?",
        cohort="K51",
    )

    assert first["status"] == "answered"
    assert first["llm_called"] is True
    assert first["used_cache"] is False
    assert cached["status"] == "answered"
    assert cached["used_cache"] is True
    assert cached["answer"] == first["answer"]
    assert client.sync_calls == 1
    assert first["debug"]["answer_composition"]["contract_passed"] is True


def test_source_bound_formula_bypasses_rag_low_confidence_in_stream_and_cache(
    monkeypatch,
) -> None:
    client = _FormulaClient()
    pipeline = _pipeline(client)
    _patch_answer_dependencies(monkeypatch, pipeline)

    first_events = list(
        pipeline.answer_stream(
            "K51 công thức tính điểm trung bình chung là gì?",
            cohort="K51",
        )
    )
    cached_events = list(
        pipeline.answer_stream(
            "K51 công thức tính điểm trung bình chung là gì?",
            cohort="K51",
        )
    )

    first_metadata = [
        event for event in first_events if event.get("type") == "metadata"
    ][-1]
    cached_metadata = [
        event for event in cached_events if event.get("type") == "metadata"
    ][-1]
    assert first_metadata["status"] == "answered"
    assert first_metadata["llm_called"] is True
    assert first_metadata["used_cache"] is False
    assert cached_metadata["status"] == "answered"
    assert cached_metadata["used_cache"] is True
    assert client.sync_calls == 1
    assert client.stream_calls == 0
    assert not any(
        event.get("status") == "low_confidence" for event in first_events
    )


def test_unqualified_rag_still_uses_low_confidence_guardrail() -> None:
    retrieval_result = {
        "retrieved_items": [],
        "citations": [],
        "request_results": [
            {
                "request_id": "r1",
                "request_kind": "rag",
                "status": "no_match",
                "provenance": {"qualified": False},
            }
        ],
    }

    assert AnswerPipeline._should_apply_low_confidence_guardrail(retrieval_result)


def test_legacy_rag_without_atomic_metadata_keeps_low_confidence_guardrail() -> None:
    retrieval_result = {
        "strategy": "hybrid_graph_retrieval",
        "retrieved_items": [],
        "citations": [],
    }

    assert AnswerPipeline._should_apply_low_confidence_guardrail(retrieval_result)


def test_structured_ok_without_source_bound_provenance_cannot_bypass() -> None:
    retrieval_result = _formula_retrieval_result()
    retrieval_result["request_results"][0]["provenance"]["source_bound"] = False

    assert not AnswerPipeline._has_source_bound_structured_success(retrieval_result)
