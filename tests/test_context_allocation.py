from __future__ import annotations

from src.generation.context_allocation import (
    ContextAllocationConfig,
    allocate_context_budget,
    build_context_for_prompt,
    prepare_content_for_prompt,
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
    assert "Section high" in context
    assert "high" in context


def test_full_sources_keeps_top_five_content_when_under_budget() -> None:
    retrieval_result = {
        "retrieved_items": [
            _item(str(index), f"full source body {index}. " * 50, 1.0 - index * 0.1)
            for index in range(5)
        ],
    }

    context = build_context_for_prompt(
        retrieval_result,
        max_context_chars=20000,
        allocation_config=ContextAllocationConfig(
            strategy="full_sources",
            min_chars_per_doc=0,
            max_chars_per_doc=50000,
            sentence_boundary=True,
        ),
    )

    for index in range(5):
        assert f"Section {index}" in context
        assert f"full source body {index}" in context
    assert "RELATED SNIPPET" not in context
    assert len(context) <= 20000


def test_full_sources_formats_related_sources_separately() -> None:
    retrieval_result = {
        "retrieved_items": [
            _item("primary-1", "primary body", 0.9),
        ],
        "related_items": [
            {
                "chunk_id": "related-1",
                "content": "related body",
                "metadata": {
                    "title": "Related section",
                    "chunk_type": "regulation",
                    "source_pages": [3],
                    "related_graph_depth": 1,
                    "related_source_primary_id": "primary-1",
                },
            }
        ],
    }

    context = build_context_for_prompt(
        retrieval_result,
        max_context_chars=4000,
        allocation_config=ContextAllocationConfig(
            strategy="full_sources",
            min_chars_per_doc=0,
            max_chars_per_doc=50000,
            sentence_boundary=True,
        ),
    )

    assert "PRIMARY SOURCES" in context
    assert "RELATED SOURCES" in context
    assert "[1]" in context
    assert "[R1]" in context
    assert "primary body" in context
    assert "related body" in context


def test_full_sources_truncates_only_when_global_budget_is_exceeded() -> None:
    retrieval_result = {
        "retrieved_items": [
            _item("high", "high source. " * 2000, 0.9),
            _item("low", "low source. " * 2000, 0.1),
        ],
    }

    context = build_context_for_prompt(
        retrieval_result,
        max_context_chars=1200,
        allocation_config=ContextAllocationConfig(
            strategy="full_sources",
            min_chars_per_doc=0,
            max_chars_per_doc=50000,
            sentence_boundary=True,
        ),
    )

    assert len(context) <= 1200
    assert "Section high" in context
    assert "Section low" in context
    assert "Content:" in context


def test_build_context_for_prompt_keeps_query_snippet_near_chunk_end() -> None:
    long_intro = "general unrelated policy text. " * 80
    content = (
        long_intro
        + "6. Students have 03 official graduation review rounds in May, August, and November."
    )
    retrieval_result = {
        "query": "graduation review rounds",
        "retrieved_items": [_item("graduation", content, 0.9)],
    }

    context = build_context_for_prompt(
        retrieval_result,
        query="graduation review rounds",
        max_context_chars=900,
        allocation_config=ContextAllocationConfig(
            strategy="score_weighted",
            min_chars_per_doc=400,
            max_chars_per_doc=700,
            sentence_boundary=True,
        ),
    )

    assert "03 official graduation review rounds" in context
    assert "May, August, and November" in context
    assert "RELATED SNIPPET" in context
    assert len(context) <= 900


def test_snippet_fallback_keeps_precise_match_when_sentence_boundary_drops_it() -> None:
    content = (
        "This section begins with a long general rule. " * 30
        + "6. Students have 03 official graduation review rounds in May, August, and November."
    )
    retrieval_result = {
        "query": "graduation review rounds",
        "retrieved_items": [_item("graduation", content, 0.9)],
    }

    context = build_context_for_prompt(
        retrieval_result,
        query="graduation review rounds",
        max_context_chars=900,
        allocation_config=ContextAllocationConfig(
            strategy="score_weighted",
            min_chars_per_doc=400,
            max_chars_per_doc=700,
            sentence_boundary=True,
        ),
    )

    assert "03 official graduation review rounds" in context
    assert "May, August, and November" in context


def test_prepare_content_for_prompt_keeps_table_like_context() -> None:
    content = (
        "Study duration table: program: first bachelor degree | standard: 4 years | max: 8 years\n"
        "program: college to university transfer | standard: 2 years | max: 4 years"
    )

    prepared = prepare_content_for_prompt(
        content,
        item={"metadata": {"chunk_type": "regulation", "has_table": True}},
        query="maximum study duration",
        budget=600,
    )

    assert "THONG TIN TRONG TAM" not in prepared
    assert "8 years" in prepared
