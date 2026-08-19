from __future__ import annotations

from types import SimpleNamespace

from src.generation.answer_pipeline import AnswerPipeline
from src.retrieval.core.structured_routing import (
    fallback_to_rag,
    normalize_router_decision,
    validate_router_decision,
)


def _pipeline() -> AnswerPipeline:
    pipeline = AnswerPipeline.__new__(AnswerPipeline)
    pipeline.config = {
        "retrieval": {"default_top_k": 5, "candidate_multiplier": 5, "min_candidates": 25},
        "embedding": {"normalize_embeddings": True},
        "input": {"structured_tables_registry": "test-registry"},
    }
    pipeline.model = object()
    pipeline.collection = object()
    pipeline.scoring_tables = []
    pipeline.formula_rules = []
    pipeline.entity_registry = []
    pipeline.expansion_rules = {}
    pipeline.student_office_profiles = []
    pipeline.student_service_directory = []
    pipeline.student_faculty_profiles = []
    pipeline.foreign_language_tables = []
    pipeline.structured_tables_registry = []
    pipeline.program_directory = []
    pipeline.parent_sources_by_id = {}
    pipeline.slang_normalizer = SimpleNamespace(
        normalize_for_retrieval=lambda value: f"search::{value}"
    )
    return pipeline


def test_invalid_plan_clarifies_without_creating_rag_request() -> None:
    decision = fallback_to_rag(
        {
            "route": "structured",
            "lookup_type": "program",
            "lookup_requests": [{"request_kind": "structured"}],
        },
        ["request:0:missing_slot:scope"],
        query="K50 học gì?",
    )

    assert decision["route"] == "clarify"
    assert decision["lookup_requests"] == []
    assert decision["retrieval_query"] is None
    assert decision["retrieval_executed"] is False


def test_multi_cohort_is_rejected_before_execution() -> None:
    decision = normalize_router_decision(
        {
            "outcome": "execute",
            "route": "rag",
            "lookup_requests": [
                {
                    "request_kind": "rag",
                    "lookup_type": None,
                    "intent": "open_question",
                    "query_span": "K50 và K51 khác nhau thế nào",
                    "slots": {},
                    "slot_spans": {},
                    "cohort_refs": ["K50", "K51"],
                }
            ],
        },
        query="K50 và K51 khác nhau thế nào?",
        selected_cohort=None,
    )

    assert decision["is_multi_cohort"] is True
    assert "multi_cohort_not_supported" in validate_router_decision(
        decision,
        query="K50 và K51 khác nhau thế nào?",
    )


def test_structured_no_match_never_falls_back_to_rag(monkeypatch) -> None:
    pipeline = _pipeline()
    hybrid_calls: list[dict] = []

    monkeypatch.setattr(
        "src.retrieval.core.structured_dispatcher.resolve_structured_decision",
        lambda *_args, **_kwargs: None,
    )

    def fake_hybrid(**kwargs):
        hybrid_calls.append(kwargs)
        return {
            "retrieved_items": [{"chunk_id": "regulation-1", "metadata": {}}],
            "citations": [{"chunk_id": "regulation-1", "title": "Điều 1"}],
            "related_items": [],
            "related_references": [],
        }

    monkeypatch.setattr(
        "src.generation.answer_pipeline.run_hybrid_retrieval_pipeline", fake_hybrid
    )
    decision = {
        "intent": "multi_request",
        "lookup_requests": [
            {
                "request_kind": "structured",
                "lookup_type": "program",
                "intent": "exists",
                "query_span": "ngành X có không",
                "slots": {"program_or_faculty": "ngành X"},
                "slot_spans": {"program_or_faculty": "ngành X"},
                "cohort_refs": ["K50"],
            },
            {
                "request_kind": "rag",
                "lookup_type": None,
                "intent": "open_question",
                "query_span": "quy định bảo lưu thế nào",
                "slots": {},
                "slot_spans": {},
                "cohort_refs": ["K50"],
            },
        ],
    }

    result = pipeline._execute_semantic_requests(
        query="ngành X có không và quy định bảo lưu thế nào",
        effective_query="ngành X có không và quy định bảo lưu thế nào",
        retrieval_query="unused-top-level-debug",
        cohort="K50",
        router_decision=decision,
        query_handling={},
    )

    assert len(hybrid_calls) == 1
    assert hybrid_calls[0]["query"] == "quy định bảo lưu thế nào"
    assert result["request_results"][0]["status"] == "unresolved"
    assert result["request_results"][1]["status"] == "ok"
    assert result["request_execution_contexts"][0]["retrieval_query"] == "search::ngành X có không"
    assert "retrieval_query" not in decision["lookup_requests"][0]
    assert result["citations"][0]["request_id"] == "r2"
