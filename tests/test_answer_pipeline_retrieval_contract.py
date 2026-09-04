from __future__ import annotations

import logging
from unittest.mock import Mock

from src.evaluation.suites import _run_pure_regulation_retrieval
from src.generation.answer_pipeline import AnswerPipeline


def _minimal_pipeline() -> AnswerPipeline:
    pipeline = AnswerPipeline.__new__(AnswerPipeline)
    pipeline.config = {
        "retrieval": {"default_top_k": 5},
    }
    pipeline.model = object()
    pipeline.scoring_tables = []
    pipeline.formula_rules = []
    pipeline.student_office_profiles = []
    pipeline.student_service_directory = []
    pipeline.student_faculty_profiles = []
    pipeline.foreign_language_tables = []
    pipeline.structured_tables_registry = []
    pipeline.program_directory = []

    class DummySlangNormalizer:
        def normalize_for_retrieval(self, value: str) -> str:
            return f"slang::{value}"

    pipeline.slang_normalizer = DummySlangNormalizer()
    return pipeline


def test_answer_output_propagates_query_handling() -> None:
    pipeline = AnswerPipeline.__new__(AnswerPipeline)
    handling = {
        "raw_query": "con K51 thi sao?",
        "effective_query": "K51 thời gian học tối đa là bao lâu?",
        "source": "grounded_follow_up",
    }
    output = pipeline._build_output(
        query="con K51 thi sao?",
        retrieval_result={
            "effective_query": handling["effective_query"],
            "query_handling": handling,
            "router_decision": {"query_handling": handling},
        },
        final_answer="test",
        context_used="",
        selected_citations=[],
        status="answered",
        error_type=None,
        error_message=None,
        llm_called=False,
        used_cache=False,
    )

    assert output["effective_query"] == handling["effective_query"]
    assert output["query_handling"] == handling
    assert output["router_decision"]["query_handling"] == handling


def test_prepare_answer_logs_retrieval_failure_with_trace_id(caplog) -> None:
    pipeline = _minimal_pipeline()

    def fail_retrieval(*args, **kwargs):
        raise RuntimeError("internal retrieval endpoint failed")

    pipeline._run_retrieval = fail_retrieval
    with caplog.at_level(
        logging.ERROR,
        logger="student_handbook_rag.generation.answer_pipeline",
    ):
        prepared = pipeline.prepare_answer(
            "test query",
            chat_history=[],
            cohort="K51",
            tracker=Mock(),
            router_started_at="",
            trace_id="trace-test",
        )

    record = next(
        item for item in caplog.records if item.message == "answer_retrieval_failed"
    )
    assert prepared.terminal_status == "retrieval_error"
    assert record.trace_id == "trace-test"
    assert "internal retrieval endpoint failed" in (record.exc_text or "")


def test_evaluation_pure_retrieval_bypasses_planner(monkeypatch) -> None:
    pipeline = _minimal_pipeline()

    class FailingRouter:
        def plan(self, query, chat_history=None, cohort=None):
            raise AssertionError("planner should not run in pure retrieval eval")

    captured = {}

    def fake_hybrid_pipeline(**kwargs):
        captured.update(kwargs)
        return {
            "query": kwargs["query"],
            "retrieval_query": kwargs["retrieval_query"],
            "retrieved_items": [],
            "related_items": [],
            "citations": [],
            "needs_llm_answer": True,
        }

    pipeline.router = FailingRouter()
    monkeypatch.setattr(
        "src.retrieval.core.hybrid_pipeline.run_hybrid_retrieval_pipeline",
        fake_hybrid_pipeline,
    )

    result = _run_pure_regulation_retrieval(
        pipeline,
        "K50 bao luu duoc bao lau?",
        cohort="K50",
    )

    assert captured["query"] == "K50 bao luu duoc bao lau?"
    assert captured["retrieval_query"] == "slang::K50 bao luu duoc bao lau?"
    assert result["router_decision"]["evaluation_scope"] == "pure_regulation"
    assert result["query_handling"]["source"] == "evaluation_pure_regulation"
