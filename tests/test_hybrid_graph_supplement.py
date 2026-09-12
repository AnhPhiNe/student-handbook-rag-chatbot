from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.generation.plan_executor import PlanExecutor, StructuredCatalogs


def _executor(**kwargs) -> PlanExecutor:
    """A plan executor with empty catalogs, for graph-only assertions."""
    return PlanExecutor(
        router=None,
        slang_normalizer=None,
        catalogs=StructuredCatalogs([], [], [], [], [], []),
        parent_sources_by_id=kwargs.get("parent_sources_by_id", {}),
        top_k=5,
        public_source_limit=10,
        graph=kwargs.get("graph"),
    )
from src.retrieval.core.hybrid_pipeline import (
    ChildParentHybridRetriever,
    _is_supplemental_regulation_metadata,
    _regulation_query_filter,
    build_related_references,
    reciprocal_rank_fusion,
    select_graph_related_parent_candidates,
)
from src.retrieval.core.retrieval_mode import DEFAULT_RETRIEVAL_MODE


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


def test_qdrant_scope_filter_matches_direct_or_applicable_cohort() -> None:
    query_filter = _regulation_query_filter("K51")

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
    references = build_related_references(
        [
            {
                "chunk_id": "K51_dieu_3",
                "content": "Nội dung đầy đủ của Điều 3. " * 40,
                "metadata": {
                    "title": "Điều 3 — Thời gian đào tạo",
                    "source_pages": [12],
                    "source_url": "https://example.edu/handbook.pdf",
                    "cohort": "K51",
                    "document_title": "Quy chế đào tạo",
                    "document_id": "handbook-k51",
                    "related_graph_depth": 1,
                    "related_source_primary_id": "K51_dieu_15",
                },
            }
        ]
    )

    assert len(references) == 1
    reference = references[0]
    assert reference["id"] == reference["canonical_source_id"]
    assert reference["display_label"] == "R1"
    assert reference["document_identity"] == "Quy chế đào tạo"
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


def test_structured_source_exposes_direct_graph_neighbor_for_ui() -> None:
    graph = SimpleNamespace(
        expand_context=lambda seed_ids, max_depth: [
            {
                "id": "K50_Dieu3",
                "depth": 1,
                "seed_source": seed_ids[0],
            }
        ]
    )
    parent_sources_by_id = {
        "K50_Dieu3": {
            "_id": "K50_Dieu3",
            "content": "Điều 3. Giải thích từ ngữ.",
            "metadata": {
                "cohort": "K50",
                "title": "Điều 3 — Giải thích từ ngữ",
                "source_pages": [10],
            },
        }
    }

    executor = _executor(graph=graph, parent_sources_by_id=parent_sources_by_id)
    references = executor._structured_related_references(
        [
            {
                "chunk_id": "K50_Dieu27",
                "source_parent_id": "K50_Dieu27",
                "cohort": "K50",
            }
        ],
        cohort="K50",
    )

    assert len(references) == 1
    assert references[0]["primary_chunk_id"] == "K50_Dieu27"
    assert references[0]["related_chunk_id"] == "K50_Dieu3"
    assert references[0]["article_label"] == "Điều 3"


def test_related_reference_merge_is_deterministic_and_deduplicated() -> None:
    merged = PlanExecutor._merge_related_references(
        [
            {"id": "R9", "primary_chunk_id": "P1", "related_chunk_id": "R1"},
            {"id": "R2", "primary_chunk_id": "P1", "related_chunk_id": "R1"},
            {"id": "R7", "primary_chunk_id": "P1", "related_chunk_id": "R2"},
        ]
    )

    assert [item["id"] for item in merged] == ["R1", "R2"]
    assert [item["related_chunk_id"] for item in merged] == ["R1", "R2"]


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
        ChildParentHybridRetriever.retrieve(
            retriever,
            "dieu kien hoc bong",
            top_k_vector=12,
            top_k_final=5,
            graph_depth=2,
            cohort="K50",
        )

    scored_chunks = retriever._group_parent_results.call_args.kwargs["scored_chunks"]
    assert len(scored_chunks) == 24
    assert [chunk["chunk_id"] for _, chunk in scored_chunks] == [
        f"c{index}" for index in range(24)
    ]
    telemetry = retriever._group_parent_results.call_args.kwargs[
        "retrieval_telemetry"
    ]
    assert telemetry["ranking_method"] == "rrf"
    assert "phoranker_used" not in telemetry
    assert "phoranker_candidate_chunks" not in telemetry
    assert "phoranker_candidate_parents" not in telemetry
    retriever._graph_related_parent_results.assert_called_once()


def test_retrieval_reranks_children_before_grouping_by_parent() -> None:
    hits = _vector_hits()
    retriever = _retriever_stub()
    reranked = [
        (float(index), {"chunk_id": f"r{index}", "content": f"reranked {index}"})
        for index in range(16)
    ]
    retriever.cohere_reranker = Mock()
    retriever.cohere_reranker.rerank.return_value = (
        reranked,
        {
            "ranking_method": "cohere_rerank_v4_fast",
            "cohere_reranker_applied": True,
        },
    )

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

    retriever.cohere_reranker.rerank.assert_called_once()
    assert (
        retriever._group_parent_results.call_args.kwargs["scored_chunks"] == reranked
    )
    telemetry = retriever._group_parent_results.call_args.kwargs[
        "retrieval_telemetry"
    ]
    assert telemetry["ranking_method"] == "cohere_rerank_v4_fast"
    assert telemetry["cohere_reranker_applied"] is True
    assert result == retriever._group_parent_results.return_value


def test_no_graph_ablation_keeps_rrf_without_a_reranker() -> None:
    hits = _vector_hits()
    retriever = _retriever_stub()

    with (
        patch.dict(
            os.environ,
            {
                "STUDENT_RAG_EVAL_RETRIEVAL_MODE": "no_graph",
                "STUDENT_RAG_ALLOW_RETRIEVAL_ABLATION": "1",
            },
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

    scored_chunks = retriever._group_parent_results.call_args.kwargs["scored_chunks"]
    assert len(scored_chunks) == 24
    assert [chunk["chunk_id"] for _, chunk in scored_chunks] == [
        f"c{index}" for index in range(24)
    ]
    telemetry = retriever._group_parent_results.call_args.kwargs[
        "retrieval_telemetry"
    ]
    assert telemetry["ranking_method"] == "rrf"
    assert "phoranker_used" not in telemetry


def test_parent_grouping_preserves_scored_order_and_top_k() -> None:
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


def test_vector_only_ablation_fuses_no_bm25_candidates() -> None:
    hits = _vector_hits()
    retriever = _retriever_stub()
    retriever.bm25.sparse_search.return_value = [
        {"chunk_id": "lexical-only", "bm25_score": 9.0, "content": "bm25"}
    ]

    with (
        patch.dict(
            os.environ,
            {
                "STUDENT_RAG_EVAL_RETRIEVAL_MODE": "vector_only",
                "STUDENT_RAG_ALLOW_RETRIEVAL_ABLATION": "1",
            },
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

    retriever.bm25.sparse_search.assert_not_called()
    scored_chunks = retriever._group_parent_results.call_args.kwargs["scored_chunks"]
    assert "lexical-only" not in {chunk["chunk_id"] for _, chunk in scored_chunks}


def test_reciprocal_rank_fusion_uses_ranks_not_raw_scores() -> None:
    dense = [(0.99, {"chunk_id": "a"}), (0.10, {"chunk_id": "b"})]
    lexical = [(55.0, {"chunk_id": "b"}), (1.0, {"chunk_id": "c"})]

    fused = reciprocal_rank_fusion(dense, lexical)

    # b is ranked by both retrievers, so it beats a (dense #1 only) despite a
    # having the highest raw score.
    assert [chunk["chunk_id"] for _, chunk in fused] == ["b", "a", "c"]
    assert fused[0][0] == 1 / 62 + 1 / 61
