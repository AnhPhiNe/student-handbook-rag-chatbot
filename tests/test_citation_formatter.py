from src.generation.citation_formatter import (
    deduplicate_citations,
    select_relevant_citations,
)


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


def test_select_relevant_citations_keeps_formula_for_structured_result():
    formula = {
        "chunk_id": "formula:course-grade",
        "chunk_type": "formula",
        "title": "Công thức điểm học phần",
        "source_section": "K51_Dieu16",
        "source_pages": [38],
        "cohort": "K51",
    }

    selected = select_relevant_citations(
        [formula],
        intent="calculation_query",
        retrieval_result={"structured_result": {"lookup_type": "formula"}},
        max_sources=2,
    )

    assert selected == [formula]


def test_deduplicate_citations_deduplicates_within_request_scope():
    citation = {
        "request_id": "r1",
        "chunk_id": "same-source",
        "title": "Điều 15",
        "source_pages": [42],
    }

    assert deduplicate_citations([citation, dict(citation)]) == [citation]


def test_deduplicate_citations_preserves_same_source_across_requests():
    first = {
        "request_id": "r1",
        "chunk_id": "same-source",
        "title": "Điều 15",
        "source_pages": [42],
    }
    second = {**first, "request_id": "r2"}

    assert deduplicate_citations([first, second]) == [first, second]


def test_multi_request_selection_covers_each_request_before_extra_sources():
    citations = [
        {
            "request_id": "r1",
            "request_index": 0,
            "chunk_id": "structured-r1",
            "chunk_type": "structured_lookup",
            "title": "Bảng quy đổi ngoại ngữ",
            "source_pages": [20],
        },
        {
            "request_id": "r2",
            "request_index": 1,
            "chunk_id": "rag-r2",
            "chunk_type": "regulation",
            "title": "Điều kiện tốt nghiệp",
            "source_pages": [40],
            "rerank": {"final_score": 0.95},
        },
        {
            "request_id": "r3",
            "request_index": 2,
            "chunk_id": "structured-r3",
            "chunk_type": "structured_lookup",
            "title": "Bảng học bổng",
            "source_pages": [50],
        },
    ]

    selected = select_relevant_citations(
        citations,
        intent="mixed_query",
        retrieval_result={"structured_result": {"result": {"ok": True}}},
        max_sources=2,
    )

    assert {citation["request_id"] for citation in selected} == {"r1", "r2", "r3"}
    assert len(selected) == 3
