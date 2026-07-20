from src.generation.citation_formatter import select_relevant_citations


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
