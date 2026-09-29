from src.generation.citation_formatter import prioritize_citations_by_answer_anchors


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


