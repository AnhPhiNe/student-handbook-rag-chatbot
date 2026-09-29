import unittest

from src.generation.answer_guardrails import is_low_confidence


class AnswerAmbiguityTest(unittest.TestCase):
    def test_covered_query_plan_evidence_is_not_low_confidence(self) -> None:
        retrieval = {
            "query_plan": {"schema_version": "v1", "tasks": [{"id": "t1"}]},
            "coverage_by_task": {"t1": "covered"},
            "citations": [{"source_parent_id": "policy_source"}],
            "retrieved_items": [],
        }

        self.assertFalse(is_low_confidence(retrieval))


if __name__ == "__main__":
    unittest.main()

