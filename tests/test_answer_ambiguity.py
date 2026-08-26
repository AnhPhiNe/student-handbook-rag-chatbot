import unittest

from src.generation.answer_guardrails import (
    build_clarification_question,
    detect_ambiguous_query,
    is_low_confidence,
)


class AnswerAmbiguityTest(unittest.TestCase):
    def test_needs_clarification_flag_triggers_guardrail(self) -> None:
        retrieval = {
            "needs_clarification": True,
            "clarification_question": "Bạn muốn hỏi về Phòng CNTT hay Khoa CNTT?",
            "retrieved_items": [],
        }
        self.assertTrue(detect_ambiguous_query("CNTT ở đâu?", retrieval))
        question = build_clarification_question("CNTT ở đâu?", retrieval)
        self.assertEqual(question, "Bạn muốn hỏi về Phòng CNTT hay Khoa CNTT?")

    def test_clear_query_does_not_trigger_clarification(self) -> None:
        retrieval = {
            "needs_clarification": False,
            "intent": "regulation_query",
            "retrieved_items": [{"metadata": {"chunk_type": "regulation"}}],
        }
        self.assertFalse(
            detect_ambiguous_query(
                "Có thể học vượt để ra trường sớm không?", retrieval
            )
        )

    def test_deterministic_result_never_needs_clarification(self) -> None:
        deterministic_score = {
            "needs_clarification": True,
            "deterministic_validated": True,
            "structured_result": {
                "lookup_type": "scoring",
                "table_name": "Điểm rèn luyện",
                "result": {"label": "Tốt"},
            },
        }
        self.assertFalse(
            detect_ambiguous_query(
                "Điểm rèn luyện 85 là loại gì?", deterministic_score
            )
        )

    def test_fallback_clarification_question(self) -> None:
        retrieval = {"needs_clarification": True}
        question = build_clarification_question("hỏi gì đó", retrieval)
        self.assertTrue("Bạn có thể nói rõ hơn" in question)

    def test_covered_query_plan_evidence_is_not_low_confidence(self) -> None:
        retrieval = {
            "query_plan": {"schema_version": "v1", "tasks": [{"id": "t1"}]},
            "coverage_by_task": {"t1": "covered"},
            "citations": [{"source_parent_id": "policy_source"}],
            "retrieved_items": [],
            "context_for_llm": "",
        }

        self.assertFalse(is_low_confidence(retrieval))


if __name__ == "__main__":
    unittest.main()

