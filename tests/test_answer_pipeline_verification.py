from __future__ import annotations

import unittest

from src.generation.answer_pipeline import AnswerPipeline, _normalize_retrieval_cohort
from src.generation.query_rewriter import QueryRewriteResult


def _result(intent: str, chunk_type: str, score: float) -> dict:
    return {
        "intent": intent,
        "strategy": "semantic_filtered_rerank",
        "target_chunk_types": [chunk_type],
        "context_for_llm": "context",
        "citations": [{"source": "student_handbook", "page": 1}],
        "retrieved_items": [
            {
                "metadata": {"chunk_type": chunk_type},
                "rerank": {"final_score": score},
            }
        ],
    }


class AnswerPipelineRetrievalVerificationTest(unittest.TestCase):
    def test_general_cohort_does_not_become_storage_filter(self) -> None:
        self.assertIsNone(_normalize_retrieval_cohort("general"))
        self.assertIsNone(_normalize_retrieval_cohort("GENERAL"))
        self.assertIsNone(_normalize_retrieval_cohort("all"))
        self.assertIsNone(_normalize_retrieval_cohort(""))
        self.assertEqual(_normalize_retrieval_cohort("K50"), "K50")

    def test_falls_back_to_original_when_qwen_router_query_has_no_context(self) -> None:
        class FakePipeline:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def _run_retrieval(
                self,
                query: str,
                cohort: str | None = None,
                chat_history: list[dict[str, str]] | None = None,
            ) -> dict:
                self.calls.append(query)
                if query == "router rewrite":
                    return {
                        "intent": "regulation_query",
                        "strategy": "semantic_filtered",
                        "retrieval_query": "router rewrite",
                        "router_model": "qwen/qwen3.6-27b",
                        "context_for_llm": "",
                        "citations": [],
                        "retrieved_items": [],
                    }
                return _result("regulation_query", "regulation", 0.91)

            _select_verified_retrieval = AnswerPipeline._select_verified_retrieval

        pipeline = FakePipeline()
        rewrite_result = QueryRewriteResult(
            original_query="original question",
            effective_query="router rewrite",
            rewritten_query="router rewrite",
            confidence="high",
            reason="qwen_structured_router",
        )

        result, selected_rewrite = AnswerPipeline._run_verified_retrieval(
            pipeline,
            "original question",
            rewrite_result,
        )

        self.assertEqual(pipeline.calls, ["router rewrite", "original question"])
        self.assertEqual(result["rewrite_verification"]["selected"], "original_query")
        self.assertEqual(selected_rewrite.effective_query, "original question")

    def test_context_ambiguity_can_clarify_before_retrieval(self) -> None:
        rewrite_result = QueryRewriteResult(
            original_query="bên đó thì sao?",
            effective_query="bên đó thì sao?",
            needs_clarification=True,
            clarification_question="Bạn muốn hỏi tiếp hay chuyển chủ đề mới?",
            context_resolution={
                "history_used": False,
                "decision": "ambiguous",
                "needs_clarification": True,
            },
        )

        should_clarify = AnswerPipeline._should_answer_rewrite_clarification(
            None,
            rewrite_result,
        )

        self.assertTrue(should_clarify)

    def test_selects_rewritten_query_when_original_is_not_answerable(self) -> None:
        selected = AnswerPipeline._select_verified_retrieval(
            None,
            original_result={
                "intent": "unknown",
                "needs_clarification": True,
                "context_for_llm": "",
                "citations": [],
                "retrieved_items": [],
            },
            rewritten_result=_result("scholarship_query", "regulation", 0.92),
        )

        self.assertEqual(selected, "rewritten_query")

    def test_asks_clarification_when_dual_retrieval_conflicts_without_winner(self) -> None:
        selected = AnswerPipeline._select_verified_retrieval(
            None,
            original_result=_result("office_query", "office_directory", 0.91),
            rewritten_result=_result("scholarship_query", "regulation", 0.90),
        )

        self.assertEqual(selected, "needs_clarification")


if __name__ == "__main__":
    unittest.main()
