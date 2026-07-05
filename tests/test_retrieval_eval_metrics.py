import unittest

from scripts.evaluate_retrieval import (
    build_summary,
    evaluate_case,
    has_hit_at_k,
    reciprocal_rank,
)


class RetrievalEvalMetricsTest(unittest.TestCase):
    def test_hit_at_k_and_mrr(self) -> None:
        flags = [False, False, True]

        self.assertFalse(has_hit_at_k(flags, 1))
        self.assertTrue(has_hit_at_k(flags, 3))
        self.assertEqual(reciprocal_rank(flags), 1 / 3)

    def test_evaluate_case_supports_structured_and_tool_results(self) -> None:
        case = {
            "query": "Điểm rèn luyện 92 là loại gì?",
            "expected_intent": "score_lookup_query",
            "expected_strategy": "structured_lookup",
            "expected_lookup_type": "conduct_classification",
        }
        result = {
            "intent": "score_lookup_query",
            "strategy": "structured_lookup",
            "structured_result": {"lookup_type": "conduct_classification"},
            "retrieved_items": [],
        }

        evaluated = evaluate_case(case, result)

        self.assertTrue(evaluated["intent_match"])
        self.assertTrue(evaluated["strategy_match"])
        self.assertTrue(evaluated["lookup_match"])

    def test_build_summary_separates_retrieval_and_lookup_cases(self) -> None:
        summary = build_summary(
            [
                {
                    "is_retrieval_case": True,
                    "intent_match": True,
                    "strategy_match": True,
                    "expected_chunk_ids": ["a"],
                    "hit_at_1": True,
                    "hit_at_3": True,
                    "hit_at_5": True,
                    "reciprocal_rank": 1.0,
                },
                {
                    "intent_match": False,
                    "strategy_match": True,
                    "expected_lookup_type": "conduct_classification",
                    "lookup_match": True,
                    "reciprocal_rank": 0.0,
                },
            ]
        )

        self.assertEqual(summary["total_cases"], 2)
        self.assertEqual(summary["retrieval_cases"], 1)
        self.assertEqual(summary["intent_accuracy"], 0.5)
        self.assertEqual(summary["hit_at_3"], 1.0)
        self.assertEqual(summary["lookup_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
