from __future__ import annotations

import unittest

from src.generation.context_resolver import resolve_query_context


class ContextResolverTest(unittest.TestCase):
    def test_llm_follow_up_payload_uses_history(self) -> None:
        result = resolve_query_context(
            "còn loại giỏi thì sao?",
            [
                {"role": "user", "content": "Học bổng loại khá cần bao nhiêu điểm?"},
                {"role": "assistant", "content": "Loại khá cần đạt mức điểm theo quy định."},
            ],
            llm_payload={
                "decision": "follow_up",
                "confidence": "high",
                "referenced_turns": [0],
                "standalone_query": "Học bổng loại giỏi cần bao nhiêu điểm?",
                "reason": "current_query_depends_on_previous_scholarship_topic",
            },
        )

        self.assertTrue(result.history_used)
        self.assertEqual(result.decision, "follow_up")
        self.assertEqual(result.confidence, "high")

    def test_llm_standalone_payload_ignores_history(self) -> None:
        result = resolve_query_context(
            "Khoa CNTT ở đâu?",
            [
                {"role": "user", "content": "Học bổng loại khá cần bao nhiêu điểm?"},
                {"role": "assistant", "content": "Loại khá cần đạt mức điểm theo quy định."},
            ],
            llm_payload={
                "decision": "standalone_new_topic",
                "confidence": "high",
                "referenced_turns": [],
                "standalone_query": "Khoa CNTT ở đâu?",
                "reason": "current_query_has_own_subject",
            },
        )

        self.assertFalse(result.history_used)
        self.assertEqual(result.decision, "standalone_new_topic")
        self.assertEqual(result.reason, "current_query_has_own_subject")

    def test_low_confidence_payload_asks_for_clarification(self) -> None:
        result = resolve_query_context(
            "bên đó thì sao?",
            [
                {"role": "user", "content": "Khoa CNTT ở đâu?"},
                {"role": "assistant", "content": "Khoa CNTT có thông tin trong danh bạ khoa."},
            ],
            llm_payload={
                "decision": "ambiguous",
                "confidence": "low",
                "referenced_turns": [],
                "standalone_query": None,
                "clarification_question": "Bạn đang hỏi tiếp về Khoa CNTT hay một đơn vị khác?",
                "reason": "unclear_reference",
            },
        )

        self.assertFalse(result.history_used)
        self.assertTrue(result.needs_clarification)
        self.assertIn("Khoa CNTT", result.clarification_question or "")


if __name__ == "__main__":
    unittest.main()
