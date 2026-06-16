from __future__ import annotations

import unittest

from src.generation.answer_pipeline import AnswerPipeline
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
