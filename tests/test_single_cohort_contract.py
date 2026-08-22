from __future__ import annotations

import copy
from types import SimpleNamespace

from src.generation.context_allocation import ContextAllocationConfig
from src.generation.answer_pipeline import AnswerPipeline
from src.retrieval.core.structured_routing import (
    bind_effective_cohort,
    reject_invalid_plan,
    load_lookup_registry,
    normalize_router_decision,
    validate_router_decision,
)
from src.retrieval.core.query_context import CohortEvidence


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
    decision = reject_invalid_plan(
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


def test_post_validation_plan_tampering_clarifies_without_retrieval_or_cache(
    monkeypatch,
) -> None:
    """Runtime validation must catch mutations that occur after plan approval."""

    query = "K51 thủ tục bảo lưu thế nào?"
    registry = load_lookup_registry()
    valid_plan = normalize_router_decision(
        {
            "outcome": "execute",
            "context_mode": "standalone",
            "context_confidence": "high",
            "normalized_query": query,
            "normalization_confidence": "none",
            "corrections": [],
            "standalone_query": None,
            "referenced_turn_ids": [],
            "referenced_evidence": [],
            "route": "rag",
            "execution_mode": "regulation",
            "cohort": "K51",
            "lookup_requests": [
                {
                    "request_kind": "rag",
                    "lookup_type": None,
                    "intent": "procedure",
                    "query_span": "thủ tục bảo lưu",
                    "slots": {},
                    "slot_spans": {},
                    "cohort_refs": ["K51"],
                }
            ],
        },
        query=query,
        selected_cohort="K51",
    )
    valid_plan = bind_effective_cohort(
        valid_plan,
        raw_query=query,
        effective_query=query,
        selected_cohort="K51",
        registry=registry,
    )
    assert (
        validate_router_decision(
            valid_plan,
            query=query,
            selected_cohort="K51",
            grounding_context=query,
            registry=registry,
        )
        == []
    )

    # Simulate an untrusted mutation after the valid plan has been approved.
    tampered_plan = copy.deepcopy(valid_plan)
    tampered_plan["lookup_requests"][0]["lookup_type"] = "student_service"

    class _TamperedRouter:
        @staticmethod
        def route(*_args, **_kwargs):
            return copy.deepcopy(tampered_plan)

    class _NoCache:
        @staticmethod
        def make_cache_key(*_args, **_kwargs):
            raise AssertionError("clarification must not construct an answer cache key")

        @staticmethod
        def get(*_args, **_kwargs):
            raise AssertionError("clarification must not read the answer cache")

        @staticmethod
        def set(*_args, **_kwargs):
            raise AssertionError("clarification must not write the answer cache")

    def _retriever_called(**_kwargs):
        raise AssertionError("tampered plan must not invoke the retriever")

    monkeypatch.setattr(
        "src.generation.answer_pipeline.run_hybrid_retrieval_pipeline",
        _retriever_called,
    )
    pipeline = _pipeline()
    pipeline.router = _TamperedRouter()
    pipeline.response_cache = _NoCache()
    pipeline.max_context_chars = 1_000
    pipeline.context_allocation = ContextAllocationConfig()

    result = pipeline.answer(query, cohort="K51")

    assert result["status"] == "needs_clarification"
    assert result["retrieval_query"] is None
    assert result["debug"]["retrieval_executed"] is False
    assert result["router_decision"]["lookup_requests"] == []
    assert "request:0:rag_request_has_lookup_type" in result["router_decision"][
        "runtime_validation_errors"
    ]


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


def test_cohortless_rag_plan_is_rejected() -> None:
    query = "Thủ tục bảo lưu thế nào?"
    decision = normalize_router_decision(
        {
            "outcome": "execute",
            "route": "rag",
            "lookup_requests": [
                {
                    "request_kind": "rag",
                    "lookup_type": None,
                    "intent": "procedure",
                    "query_span": query,
                    "slots": {},
                    "slot_spans": {},
                    "cohort_refs": [],
                }
            ],
        },
        query=query,
        selected_cohort=None,
    )
    decision = bind_effective_cohort(
        decision,
        raw_query=query,
        effective_query=query,
        selected_cohort=None,
    )

    errors = validate_router_decision(decision, query=query)

    assert "request:0:missing_cohort" in errors


def test_history_grounded_cohort_is_bound_to_rag_request() -> None:
    raw_query = "Còn khóa đó thì sao?"
    effective_query = "K51 thủ tục bảo lưu thế nào?"
    decision = {
        "route": "rag",
        "execution_mode": "regulation",
        "cohort": None,
        "cohorts": [],
        "is_multi_cohort": False,
        "lookup_requests": [
            {
                "request_kind": "rag",
                "lookup_type": None,
                "intent": "procedure",
                "query_span": effective_query,
                "slots": {},
                "slot_spans": {},
                "cohort_refs": [],
            }
        ],
    }

    bound = bind_effective_cohort(
        decision,
        raw_query=raw_query,
        effective_query=effective_query,
        selected_cohort=None,
        cohort_evidence=(
            CohortEvidence(cohort="K51", turn_id=0, evidence_span="K51"),
        ),
        registry=load_lookup_registry(),
    )

    assert bound["cohort"] == "K51"
    assert bound["effective_cohort_source"] == "grounded_history"
    assert bound["lookup_requests"][0]["cohort_refs"] == ["K51"]
    assert validate_router_decision(bound, query=effective_query) == []


def test_bind_effective_cohort_rejects_untyped_cohort_evidence() -> None:
    bound = bind_effective_cohort(
        {"lookup_requests": []},
        raw_query="Còn khóa đó thì sao?",
        effective_query="K50 thủ tục bảo lưu thế nào?",
        selected_cohort=None,
        cohort_evidence=(
            {"cohort": "K50", "turn_id": 1, "evidence_span": "K50"},
            {"cohort": "K51", "turn_id": 1, "evidence_span": "K51"},
        ),  # type: ignore[arg-type]
    )

    assert bound["cohort"] is None
    assert bound["cohort_evidence"] == []


def test_selected_cohort_has_priority_over_history_cohort() -> None:
    bound = bind_effective_cohort(
        {"lookup_requests": []},
        raw_query="Còn trường hợp đó?",
        effective_query="K51 thủ tục bảo lưu thế nào?",
        selected_cohort="K50",
    )

    assert bound["cohort"] == "K50"
    assert bound["effective_cohort_source"] == "selected_cohort"


def test_selected_cohort_replaces_conflicting_model_request_refs() -> None:
    decision = {
        "route": "rag",
        "execution_mode": "regulation",
        "router_cohort": "K51",
        "lookup_requests": [
            {
                "request_kind": "rag",
                "lookup_type": None,
                "intent": "policy",
                "query_span": "điều kiện đó",
                "slots": {},
                "slot_spans": {},
                "cohort_refs": ["K51"],
            }
        ],
    }

    bound = bind_effective_cohort(
        decision,
        raw_query="Còn điều kiện đó?",
        effective_query="K51 có điều kiện xét tốt nghiệp nào?",
        selected_cohort="K50",
    )

    assert bound["cohort"] == "K50"
    assert bound["effective_cohort_source"] == "selected_cohort"
    assert bound["lookup_requests"][0]["cohort_refs"] == ["K50"]
    errors = validate_router_decision(
        bound,
        query="Còn điều kiện đó?",
        selected_cohort="K50",
        grounding_context="K51 có điều kiện xét tốt nghiệp nào?",
    )
    assert "cohort_conflict" not in errors
    assert "request_cohort_conflict" not in errors


def test_multiple_history_cohorts_are_rejected() -> None:
    effective_query = "K50 và K51 có quy định bảo lưu thế nào?"
    bound = bind_effective_cohort(
        {
            "route": "rag",
            "execution_mode": "regulation",
            "lookup_requests": [
                {
                    "request_kind": "rag",
                    "lookup_type": None,
                    "intent": "procedure",
                    "query_span": effective_query,
                    "slots": {},
                    "slot_spans": {},
                    "cohort_refs": [],
                }
            ],
        },
        raw_query="Còn hai khóa đó?",
        effective_query=effective_query,
        selected_cohort=None,
        cohort_evidence=(
            CohortEvidence(cohort="K50", turn_id=0, evidence_span="K50"),
            CohortEvidence(cohort="K51", turn_id=0, evidence_span="K51"),
        ),
    )

    assert bound["is_multi_cohort"] is True
    assert "multi_cohort_not_supported" in validate_router_decision(
        bound,
        query=effective_query,
    )


def test_router_provider_failure_is_not_reported_as_clarification() -> None:
    pipeline = _pipeline()

    class FailedRouter:
        @staticmethod
        def route(query, chat_history=None, cohort=None):
            return {
                "route": "clarify",
                "execution_mode": "regulation",
                "intent": "router_error",
                "normalized_query": query,
                "context_mode": "standalone",
                "context_confidence": "none",
                "normalization_confidence": "none",
                "referenced_turn_ids": [],
                "referenced_evidence": [],
                "lookup_requests": [],
                "clarification_question": "Thử hỏi lại.",
                "router_error_type": "timeout",
                "router_error": "provider timeout",
                "retrieval_query": None,
                "retrieval_executed": False,
            }

    pipeline.router = FailedRouter()

    result = pipeline._run_retrieval("K51 thủ tục bảo lưu?", cohort="K51")

    assert result["infrastructure_error"] is True
    assert result["needs_clarification"] is False
    assert result["retrieval_executed"] is False
    assert result["error_type"] == "timeout"


def test_clarify_and_out_of_domain_never_call_retriever(monkeypatch) -> None:
    def fail_if_called(**_kwargs):
        raise AssertionError("retriever must not run")

    monkeypatch.setattr(
        "src.generation.answer_pipeline.run_hybrid_retrieval_pipeline",
        fail_if_called,
    )
    for route in ("clarify", "out_of_domain"):
        pipeline = _pipeline()

        class Router:
            @staticmethod
            def route(query, chat_history=None, cohort=None):
                return {
                    "outcome": route,
                    "route": route,
                    "execution_mode": "regulation",
                    "intent": route,
                    "normalized_query": None,
                    "context_mode": "standalone",
                    "context_confidence": "none",
                    "normalization_confidence": "none",
                    "referenced_turn_ids": [],
                    "referenced_evidence": [],
                    "lookup_requests": [],
                    "clarification_question": (
                        "Bạn muốn hỏi nội dung nào?" if route == "clarify" else None
                    ),
                    "retrieval_query": None,
                    "retrieval_executed": False,
                }

        pipeline.router = Router()
        result = pipeline._run_retrieval("câu hỏi", cohort="K51")

        assert result["retrieval_query"] is None
        assert result["retrieval_executed"] is False
        assert result["retrieved_items"] == []

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
            "retrieved_items": [
                {
                    "chunk_id": "regulation-1",
                    "content": "Quy định bảo lưu.",
                    "metadata": {
                        "document_id": "handbook-k50",
                        "parent_section_id": "K50_Dieu1",
                        "source_pages": [1],
                        "cohort": "K50",
                    },
                }
            ],
            "citations": [
                {
                    "chunk_id": "regulation-1",
                    "title": "Điều 1",
                    "document_id": "handbook-k50",
                    "parent_section_id": "K50_Dieu1",
                    "source_pages": [1],
                    "cohort": "K50",
                    "content": "Quy định bảo lưu.",
                }
            ],
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
    assert result["request_results"][0]["status"] == "no_match"
    assert result["request_results"][1]["status"] == "ok"
    assert result["request_execution_contexts"][0]["retrieval_query"] == "search::ngành X có không"
    assert "retrieval_query" not in decision["lookup_requests"][0]
    assert result["citations"][0]["request_id"] == "r2"
