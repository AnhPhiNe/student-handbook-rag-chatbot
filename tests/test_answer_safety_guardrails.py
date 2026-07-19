from __future__ import annotations

from src.generation import answer_guardrails
from src.generation.answer_guardrails import is_context_empty


def test_empty_retrieval_has_no_answer_context() -> None:
    assert is_context_empty(
        {
            "retrieved_items": [],
            "context_for_llm": "",
            "structured_result": None,
            "formula_result": None,
            "tool_result": None,
        }
    )


def test_structured_result_is_valid_answer_context() -> None:
    assert not is_context_empty(
        {
            "retrieved_items": [],
            "context_for_llm": "",
            "structured_result": {"result": [{"value": "8 nam"}]},
        }
    )


def test_scope_abstention_is_not_part_of_runtime_guardrails() -> None:
    assert not hasattr(answer_guardrails, "build_scope_abstention_answer")
