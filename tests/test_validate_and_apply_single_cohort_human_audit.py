from __future__ import annotations

from scripts.validate_and_apply_single_cohort_human_audit import (
    build_approved_decisions,
    validate_external_audit,
)


def _queue() -> list[dict]:
    return [
        {
            "id": "case-1",
            "selection_group": "judge_flagged",
            "expected_requests": [{"request_id": "r1"}],
            "answer": {
                "citations": [
                    {
                        "request_id": "r1",
                        "document_id": "doc",
                        "parent_section_id": "parent",
                        "chunk_id": "chunk",
                        "content": "Điểm thi có thể được phúc khảo.",
                    }
                ]
            },
            "judge": {"omitted_citations": []},
        }
    ]


def _external() -> dict:
    return {
        "audit_protocol_version": "single-cohort-dev-answer-llm-assisted-v1",
        "source": {
            "commit": "deadbeef",
            "queue_sha256": "queue-sha",
            "hidden_included": False,
        },
        "auditor": {"model": "test"},
        "summary": {"total_cases": 1, "clean_control": 1},
        "cases": [
            {
                "id": "case-1",
                "blind_audit": {
                    "claim_audit": [
                        {
                            "claim_id": "c1",
                            "request_id": "r1",
                            "evidence_quote": "Điểm thi có thể được phúc khảo.",
                            "supporting_citations": [
                                {
                                    "document_id": "doc",
                                    "parent_section_id": "parent",
                                    "chunk_id": "chunk",
                                }
                            ],
                        }
                    ]
                },
                "reconciliation": {"supported_but_omitted_claims": []},
                "final_decision": {
                    "label": "clean_control",
                    "severity": "none",
                    "unsupported_claims": [],
                    "supported_but_omitted_claims": [],
                    "answers_user_need": True,
                    "production_impact": "none",
                    "recommended_layer": "none",
                    "notes": "clean",
                },
                "confidence": 1.0,
                "requires_human_attention": False,
            }
        ],
        "human_review": {"human_approved": False},
    }


def test_external_audit_validation_binds_citations_and_queue() -> None:
    result = validate_external_audit(
        _external(),
        _queue(),
        expected_commit="deadbeef",
        expected_queue_sha256="queue-sha",
    )

    assert result["passed"] is True
    assert result["citation_identity_checks"] == 1
    assert result["exact_quote_checks"] == 1


def test_cross_request_citation_is_rejected() -> None:
    external = _external()
    external["cases"][0]["blind_audit"]["claim_audit"][0]["request_id"] = "r2"

    result = validate_external_audit(
        external,
        _queue(),
        expected_commit="deadbeef",
        expected_queue_sha256="queue-sha",
    )

    assert result["passed"] is False
    assert any("invalid request_id" in error for error in result["errors"])


def test_approved_decisions_preserve_external_provenance() -> None:
    decisions = build_approved_decisions(
        _external(),
        _queue(),
        external_sha256="external-sha",
        reviewer="project_owner",
        approval_statement="approved",
        reviewed_at="2026-08-21T00:00:00+00:00",
    )

    assert decisions["status"] == "human_approved"
    assert decisions["audit_method"] == "llm_assisted_human_review"
    assert decisions["external_audit"]["sha256"] == "external-sha"
    assert decisions["reviews"][0]["label"] == "clean_control"
