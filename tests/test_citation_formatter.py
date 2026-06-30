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
