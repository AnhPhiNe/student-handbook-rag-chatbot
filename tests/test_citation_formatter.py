from src.generation.citation_formatter import (
    prioritize_citations_by_answer_anchors,
    select_relevant_citations,
)


def _citation(source_id: str, article: str) -> dict:
    return {
        "source_parent_id": source_id,
        "article_label": article,
        "title": f"{article} — Quy định",
        "chunk_type": "regulation",
    }


def test_prioritize_citations_uses_exact_article_match_and_stable_order():
    citations = [
        _citation("source-1", "Điều 1"),
        _citation("source-10", "Điều 10"),
        _citation("source-8", "Điều 8"),
        _citation("source-30", "Điều 30"),
    ]

    ordered = prioritize_citations_by_answer_anchors(
        citations,
        "Thủ tục nằm tại khoản 2 Điều 10 và Điều 30.",
    )

    assert [item["source_parent_id"] for item in ordered] == [
        "source-10",
        "source-30",
        "source-1",
        "source-8",
    ]


def test_prioritize_citations_without_anchor_preserves_retrieval_order():
    citations = [
        _citation("source-16", "Điều 16"),
        _citation("source-30", "Điều 30"),
    ]

    ordered = prioritize_citations_by_answer_anchors(
        citations,
        "Sinh viên thực hiện theo quy định của Trường.",
    )

    assert ordered == citations


def test_prioritize_citations_deduplicates_canonical_source_and_caps_result():
    citations = [_citation("source-1", "Điều 1")]
    citations.append({**citations[0], "chunk_id": "duplicate-child"})
    citations.extend(
        _citation(f"source-{index}", f"Điều {index}")
        for index in range(2, 13)
    )

    ordered = prioritize_citations_by_answer_anchors(
        citations,
        "Theo Điều 12.",
        max_sources=10,
    )

    assert len(ordered) == 10
    assert ordered[0]["source_parent_id"] == "source-12"
    assert sum(
        item["source_parent_id"] == "source-1" for item in ordered
    ) == 1


def test_select_relevant_citations_prefers_rerank_score_over_vector_distance():
    citations = [
        {
            "chunk_id": "generic",
            "chunk_type": "regulation",
            "title": "Điều 15. Quyền khiếu nại",
            "distance": 0.10,
            "rerank": {"final_score": 0.70},
        },
        {
            "chunk_id": "specific",
            "chunk_type": "regulation",
            "title": "Điều 39. Quyền khiếu nại về khen thưởng, kỷ luật",
            "distance": 0.40,
            "rerank": {"final_score": 0.95},
        },
    ]

    selected = select_relevant_citations(
        citations,
        intent="regulation_query",
        max_sources=1,
    )

    assert [citation["chunk_id"] for citation in selected] == ["specific"]


def test_select_relevant_citations_prefers_matching_cohort_and_chunk_type():
    citations = [
        {
            "chunk_id": "wrong_cohort",
            "chunk_type": "regulation",
            "cohort": "K48-K49",
            "title": "Quy dinh chung",
            "distance": 0.05,
            "rerank": {"final_score": 0.80},
        },
        {
            "chunk_id": "right_cohort",
            "chunk_type": "regulation",
            "cohort": "K50-K51",
            "title": "Quy dinh dung khoa",
            "source_section": "Quy che dao tao",
            "source_pages": [42],
            "distance": 0.20,
            "rerank": {"final_score": 0.80},
        },
    ]

    selected = select_relevant_citations(
        citations,
        intent="regulation_query",
        retrieval_result={
            "selected_cohort": "K50-K51",
            "target_chunk_types": ["regulation"],
        },
        max_sources=1,
    )

    assert [citation["chunk_id"] for citation in selected] == ["right_cohort"]
