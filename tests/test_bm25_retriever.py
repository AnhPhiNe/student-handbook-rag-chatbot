from src.retrieval.core.bm25_retriever import BM25Retriever


def _chunk(
    chunk_id: str,
    content: str,
    *,
    cohort: str,
    content_type: str = "regulation_text",
    chunk_type: str = "regulation",
) -> dict:
    return {
        "chunk_id": chunk_id,
        "content": content,
        "metadata": {
            "cohort": cohort,
            "content_type": content_type,
            "chunk_type": chunk_type,
        },
    }


def test_sparse_search_filters_before_applying_top_k(monkeypatch) -> None:
    retriever = BM25Retriever()
    wrong_cohort = _chunk("wrong-cohort", "hoc bong hoc tap", cohort="K50")
    expected = _chunk("expected", "hoc bong khuyen khich hoc tap", cohort="K51")
    wrong_type = _chunk(
        "wrong-type",
        "hoc bong hoc tap",
        cohort="K51",
        content_type="student_office_profile",
        chunk_type="office_directory",
    )
    retriever.chunks = [wrong_cohort, expected, wrong_type]
    monkeypatch.setattr(
        retriever,
        "search_bm25",
        lambda query, top_k: [
            (3.0, wrong_cohort),
            (2.0, expected),
            (1.0, wrong_type),
        ],
    )

    results = retriever.sparse_search(
        "hoc bong hoc tap",
        top_k=1,
        chunk_types=["regulation"],
        content_types=["regulation_text"],
        cohort="K51",
    )

    assert [item["chunk_id"] for item in results] == ["expected"]
    assert results[0]["bm25_score"] > 0


def test_sparse_search_returns_empty_for_unbuilt_index() -> None:
    retriever = BM25Retriever()

    assert retriever.sparse_search("hoc bong", top_k=5) == []
