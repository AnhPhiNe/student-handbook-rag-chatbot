from __future__ import annotations

from scripts.prepare_single_cohort_dev_answer_audit import (
    build_human_decision_template,
    build_rank5_technical_audit,
)


def test_human_decision_template_is_blank_and_queue_bound() -> None:
    queue = [
        {"id": "case-1", "selection_group": "judge_flagged"},
        {"id": "case-2", "selection_group": "negative_control"},
    ]

    result = build_human_decision_template(
        queue,
        queue_sha256="abc123",
        commit="deadbeef",
    )

    assert result["queue_sha256"] == "abc123"
    assert result["status"] == "pending_human_review"
    assert [row["id"] for row in result["reviews"]] == ["case-1", "case-2"]
    assert all(row["label"] is None for row in result["reviews"])
    assert all(row["unsupported_claims"] == [] for row in result["reviews"])


def test_rank5_audit_uses_request_scoped_parent_or_chunk_gold() -> None:
    cases = [
        {
            "id": "case-1",
            "category": "single_rag",
            "query": "question",
            "expected": {
                "effective_cohort": "K51",
                "atomic_requests": [
                    {
                        "request_id": "r1",
                        "request_kind": "rag",
                        "query_span": "policy",
                        "expected_status": "ok",
                        "expected_evidence": {
                            "parent_section_ids": ["gold-parent"],
                            "chunk_ids": ["gold-child"],
                            "document_ids": ["doc"],
                            "source_pages": [10],
                            "relevance_grade": 2,
                        },
                    }
                ],
            },
        }
    ]
    citations = [
        {
            "request_id": "r1",
            "request_retrieval_rank": rank,
            "parent_section_id": (
                "gold-parent" if rank == 5 else f"distractor-{rank}"
            ),
            "chunk_id": "gold-child" if rank == 5 else f"chunk-{rank}",
            "document_id": "doc",
            "title": f"title {rank}",
        }
        for rank in range(1, 6)
    ]
    answers = [{"id": "case-1", "answer": "answer", "citations": citations}]
    judgments = [{"id": "case-1", "hallucination": False}]

    report = build_rank5_technical_audit(
        cases,
        answers,
        judgments,
        commit="deadbeef",
    )

    assert report["rank5_count"] == 1
    assert report["rank_distribution"] == {"5": 1}
    assert report["rows"][0]["request_id"] == "r1"
    assert report["rows"][0]["top5_candidates"][-1]["parent_section_id"] == (
        "gold-parent"
    )
