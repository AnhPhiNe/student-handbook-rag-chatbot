from __future__ import annotations

from src.generation.context_allocation import (
    ContextAllocationConfig,
    allocate_context_budget,
    build_context_for_prompt,
    truncate_text,
)


def _item(
    chunk_id: str,
    content: str,
    score: float | None = None,
) -> dict[str, object]:
    item: dict[str, object] = {
        "chunk_id": chunk_id,
        "content": content,
        "metadata": {
            "title": f"Section {chunk_id}",
            "chunk_type": "regulation",
            "source_pages": [1, 2],
        },
    }
    if score is not None:
        item["score"] = score
    return item


def test_score_weighted_budget_stays_within_total_budget() -> None:
    items = [
        _item("a", "A" * 4000, 0.9),
        _item("b", "B" * 4000, 0.6),
        _item("c", "C" * 4000, 0.3),
        _item("d", "D" * 4000, 0.2),
        _item("e", "E" * 4000, 0.1),
    ]

    budgets = allocate_context_budget(
        items,
        total_budget=6000,
        min_chars_per_doc=400,
        max_chars_per_doc=1800,
        strategy="score_weighted",
    )

    assert sum(budgets) <= 6000
    assert max(budgets) <= 1800
    assert min(budgets) >= 400
    assert budgets[0] > budgets[-1]


def test_equal_score_budget_does_not_overflow_worst_case() -> None:
    items = [_item(str(index), "X" * 4000, 0.5) for index in range(5)]

    budgets = allocate_context_budget(
        items,
        total_budget=6000,
        min_chars_per_doc=400,
        max_chars_per_doc=1800,
        strategy="score_weighted",
    )

    assert budgets == [1200, 1200, 1200, 1200, 1200]
    assert sum(budgets) == 6000


def test_budget_smaller_than_minimum_is_split_without_overflow() -> None:
    items = [_item(str(index), "X" * 4000, 0.5) for index in range(5)]

    budgets = allocate_context_budget(
        items,
        total_budget=1000,
        min_chars_per_doc=400,
        max_chars_per_doc=1800,
        strategy="score_weighted",
    )

    assert budgets == [200, 200, 200, 200, 200]
    assert sum(budgets) == 1000


def test_high_score_document_is_capped() -> None:
    items = [
        _item("a", "A" * 4000, 0.99),
        _item("b", "B" * 4000, 0.01),
        _item("c", "C" * 4000, 0.01),
        _item("d", "D" * 4000, 0.01),
        _item("e", "E" * 4000, 0.01),
    ]

    budgets = allocate_context_budget(
        items,
        total_budget=6000,
        min_chars_per_doc=400,
        max_chars_per_doc=1800,
        strategy="score_weighted",
    )

    assert budgets[0] == 1800
    assert sum(budgets) <= 6000


def test_truncate_text_prefers_sentence_boundary() -> None:
    text = "First sentence is complete. Second sentence should not be partial."

    truncated = truncate_text(text, 35, sentence_boundary=True)

    assert truncated == "First sentence is complete."


def test_build_context_for_prompt_respects_total_budget() -> None:
    retrieval_result = {
        "retrieved_items": [
            _item("high", "high " * 1200, 0.9),
            _item("low", "low " * 1200, 0.1),
        ],
    }

    context = build_context_for_prompt(
        retrieval_result,
        max_context_chars=1000,
        allocation_config=ContextAllocationConfig(
            strategy="score_weighted",
            min_chars_per_doc=100,
            max_chars_per_doc=700,
            sentence_boundary=True,
        ),
    )

    assert len(context) <= 1000
    assert "[Ngu" in context
    assert "high" in context
