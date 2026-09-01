from __future__ import annotations

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


def test_answer_pipeline_pure_retrieval_bypasses_planner(monkeypatch) -> None:
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
    monkeypatch.setenv("STUDENT_RAG_EVAL_FORCE_REGULATION_RAG", "1")
    monkeypatch.setattr(
        "src.generation.answer_pipeline.run_hybrid_retrieval_pipeline",
        fake_hybrid_pipeline,
    )

    result = pipeline._run_retrieval("K50 bao luu duoc bao lau?", cohort="K50")

    assert captured["query"] == "K50 bao luu duoc bao lau?"
    assert captured["retrieval_query"] == "slang::K50 bao luu duoc bao lau?"
    assert result["router_decision"]["eval_force_regulation"] is True
    assert result["query_handling"]["source"] == "eval_force_regulation"
