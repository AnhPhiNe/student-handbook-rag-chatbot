from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.retrieval.core.hybrid_pipeline import (
    ChildParentHybridRetriever,
    DEFAULT_RETRIEVAL_MODE,
    _build_related_references,
    _chunk_matches_regulation_scope,
    _is_supplemental_regulation_metadata,
    _v7_query_filter,
    select_graph_related_parent_candidates,
)


def test_retired_migration_parent_is_excluded_from_graph_context() -> None:
    assert (
        _is_supplemental_regulation_metadata(
            {
                "content_type": "regulation_text",
                "migration_status": "retired",
            }
        )
        is True
    )


def test_regulation_scope_accepts_source_declared_for_target_cohort() -> None:
    chunk = {
        "metadata": {
            "content_type": "regulation_text",
            "cohort": "K50",
            "source_cohort": "K50",
            "applicable_cohorts": ["K48-K49", "K50", "K51"],
        }
    }

    assert _chunk_matches_regulation_scope(chunk, "K51") is True
    assert _chunk_matches_regulation_scope(chunk, "K47") is False


def test_qdrant_scope_filter_matches_direct_or_applicable_cohort() -> None:
    query_filter = _v7_query_filter("K51")

    assert query_filter.should is not None
    keys = {condition.key for condition in query_filter.should}
    assert keys == {"cohort", "applicable_cohorts"}


def test_graph_supplement_skips_primary_dedupes_and_caps() -> None:
    primary = ["P1", "P2", "P3", "P4", "P5"]
    expanded = [
        {"id": "P1", "depth": 0, "seed_source": "P1"},
        {"id": "R2", "depth": 2, "seed_source": "P1"},
        {"id": "R1", "depth": 1, "seed_source": "P3"},
        {"id": "R1", "depth": 2, "seed_source": "P1"},
        {"id": "R3", "depth": 1, "seed_source": "P1"},
        {"id": "R4", "depth": 1, "seed_source": "P2"},
        {"id": "R5", "depth": 2, "seed_source": "P1"},
        {"id": "R6", "depth": 2, "seed_source": "P1"},
    ]

    selected = select_graph_related_parent_candidates(
        primary,
        expanded,
        max_related_total=5,
    )

    assert [item["parent_id"] for item in selected] == [
        "R3",
        "R4",
        "R1",
        "R2",
        "R5",
    ]
    assert all(item["parent_id"] not in primary for item in selected)


def test_graph_supplement_prefers_lower_depth_then_primary_rank() -> None:
    selected = select_graph_related_parent_candidates(
        ["P1", "P2"],
        [
            {"id": "late-depth-one", "depth": 1, "seed_source": "P2"},
            {"id": "early-depth-two", "depth": 2, "seed_source": "P1"},
            {"id": "early-depth-one", "depth": 1, "seed_source": "P1"},
        ],
        max_related_total=3,
    )

    assert [item["parent_id"] for item in selected] == [
        "early-depth-one",
        "late-depth-one",
        "early-depth-two",
    ]


def test_related_references_are_ui_metadata_not_answer_evidence() -> None:
    references = _build_related_references(
        [
            {
                "chunk_id": "K51_dieu_3",
                "content": "Nội dung đầy đủ của Điều 3. " * 40,
                "metadata": {
                    "title": "Điều 3 — Thời gian đào tạo",
                    "source_pages": [12],
                    "source_url": "https://example.edu/handbook.pdf",
                    "cohort": "K51",
                    "related_graph_depth": 1,
                    "related_source_primary_id": "K51_dieu_15",
                },
            }
        ]
    )

    assert len(references) == 1
    reference = references[0]
    assert reference["id"] == "R1"
    assert reference["primary_chunk_id"] == "K51_dieu_15"
    assert reference["related_chunk_id"] == "K51_dieu_3"
    assert reference["title"] == "Điều 3 — Thời gian đào tạo"
    assert reference["article_label"] == "Điều 3"
    assert reference["source_pages"] == [12]
    assert reference["source_url"] == "https://example.edu/handbook.pdf"
    assert reference["cohort"] == "K51"
    assert reference["graph_depth"] == 1
    assert reference["preview"].startswith("Nội dung đầy đủ của Điều 3.")
    assert reference["preview"].endswith("…")
    assert len(reference["preview"]) <= 480
    assert reference["content"] == ("Nội dung đầy đủ của Điều 3. " * 40).strip()


def _vector_hits(count: int = 24) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            score=1.0 - index / 100,
            payload={
                "chunk_id": f"c{index}",
                "parent_section_id": f"P{index}",
                "content": f"content {index}",
                "content_type": "regulation_text",
            },
        )
        for index in range(count)
    ]


def _retriever_stub() -> ChildParentHybridRetriever:
    retriever = ChildParentHybridRetriever.__new__(ChildParentHybridRetriever)
    retriever.collection_name = "test"
    retriever.qdrant_client = object()
    retriever.embed_model = Mock()
    retriever.embed_model.encode.return_value = SimpleNamespace(
        tolist=lambda: [0.1, 0.2]
    )
    retriever._rerank_chunks = Mock(
        side_effect=lambda _query, chunks: [
            (1.0 - index / 100, chunk)
            for index, chunk in enumerate(chunks)
        ]
    )
    primary = [{"chunk_id": "P0", "metadata": {}}]
    retriever._group_parent_results = Mock(return_value=primary)
    retriever._graph_related_parent_results = Mock(
        return_value=([], {"graph_related_parents_selected": 0})
    )
    retriever.bm25 = Mock()
    retriever.bm25.sparse_search.return_value = []
    return retriever


def test_default_retrieval_groups_twenty_four_vector_chunks_before_graph() -> None:
    hits = _vector_hits()
    retriever = _retriever_stub()

    with (
        patch.dict(
            os.environ,
            {"STUDENT_RAG_EVAL_RETRIEVAL_MODE": DEFAULT_RETRIEVAL_MODE},
        ),
        patch(
            "src.retrieval.core.hybrid_pipeline._query_points_with_retry",
            return_value=hits,
        ),
    ):
        result = ChildParentHybridRetriever.retrieve(
            retriever,
            "dieu kien hoc bong",
            top_k_vector=12,
            top_k_final=5,
            graph_depth=2,
            cohort="K50",
        )

    retriever._rerank_chunks.assert_not_called()
    scored_chunks = retriever._group_parent_results.call_args.kwargs["scored_chunks"]
    assert len(scored_chunks) == 24
    assert [chunk["chunk_id"] for _, chunk in scored_chunks] == [
        f"c{index}" for index in range(24)
    ]
    telemetry = retriever._group_parent_results.call_args.kwargs[
        "retrieval_telemetry"
    ]
    assert telemetry["ranking_method"] == "rrf"
    assert telemetry["phoranker_used"] is False
    retriever._graph_related_parent_results.assert_called_once()
    assert result == retriever._group_parent_results.return_value


def test_full_ablation_reranks_the_same_twenty_four_vector_chunks() -> None:
    hits = _vector_hits()
    retriever = _retriever_stub()

    with (
        patch.dict(
            os.environ,
            {"STUDENT_RAG_EVAL_RETRIEVAL_MODE": "full"},
        ),
        patch(
            "src.retrieval.core.hybrid_pipeline._query_points_with_retry",
            return_value=hits,
        ),
    ):
        ChildParentHybridRetriever.retrieve(
            retriever,
            "dieu kien hoc bong",
            top_k_vector=12,
            top_k_final=5,
            graph_depth=2,
            cohort="K50",
        )

    reranked_chunks = retriever._rerank_chunks.call_args.args[1]
    assert len(reranked_chunks) == 24
    assert [chunk["chunk_id"] for chunk in reranked_chunks] == [
        f"c{index}" for index in range(24)
    ]
    telemetry = retriever._group_parent_results.call_args.kwargs[
        "retrieval_telemetry"
    ]
    assert telemetry["ranking_method"] == "phoranker"
    assert telemetry["phoranker_used"] is True


def test_parent_grouping_keeps_phoranker_order_and_top_k() -> None:
    retriever = ChildParentHybridRetriever.__new__(ChildParentHybridRetriever)
    retriever.collection_name = "test"
    retriever.parent_cache = {}
    retriever.mongo_store = Mock()
    retriever.mongo_store.get_document_by_id.side_effect = lambda parent_id: {
        "_id": parent_id,
        "content": f"full {parent_id}",
        "metadata": {"cohort": "K50", "title": parent_id},
    }
    scored = [
        (
            0.95,
            {
                "chunk_id": "c1",
                "content": "a",
                "metadata": {
                    "parent_section_id": "P2",
                    "chunk_granularity": "child",
                },
            },
        ),
        (
            0.90,
            {
                "chunk_id": "c2",
                "content": "b",
                "metadata": {
                    "parent_section_id": "P1",
                    "chunk_granularity": "child",
                },
            },
        ),
        (
            0.80,
            {
                "chunk_id": "c3",
                "content": "c",
                "metadata": {
                    "parent_section_id": "P3",
                    "chunk_granularity": "child",
                },
            },
        ),
    ]

    results = ChildParentHybridRetriever._group_parent_results(
        retriever,
        query="query",
        scored_chunks=scored,
        top_k_final=2,
        retrieval_telemetry={},
    )

    assert [item["chunk_id"] for item in results] == ["P2", "P1"]
    assert all(item["metadata"]["retrieval_role"] == "primary" for item in results)
    assert [item["content"] for item in results] == ["a", "b"]
    assert [item["document"] for item in results] == ["full P2", "full P1"]
