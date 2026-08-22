from __future__ import annotations

from src.evaluation.material_hallucination import (
    MATERIAL_AUDIT_SCHEMA_VERSION,
    build_material_audit_packet,
    summarize_material_audit,
)


def _case(case_id: str) -> dict:
    return {
        "id": case_id,
        "query": "Quy định bảo lưu thế nào?",
        "selected_cohort": "K50",
        "expected": {
            "atomic_requests": [
                {"request_id": "r1", "request_kind": "rag", "intent": "policy"}
            ]
        },
    }


def _answer(case_id: str) -> dict:
    return {
        "id": case_id,
        "answer": "Câu trả lời đã được tạo.",
        "citations": [
            {
                "request_id": "r1",
                "citation_id": f"citation-{case_id}",
                "document_id": "handbook-k50",
                "parent_section_id": "dieu-1",
                "source_pages": [1],
                "cohort": "K50",
                "content": "Nguồn cho đúng request.",
            }
        ],
    }


def test_packet_is_blinded_but_preserves_request_scoped_sources() -> None:
    packet = build_material_audit_packet(
        [_case("a"), _case("b")],
        [_answer("a"), _answer("b")],
        [{"id": "a", "hallucination": True}, {"id": "b", "hallucination": False}],
        answers_report_hash="answer-hash",
        commit="commit-sha",
        control_count=1,
    )

    assert packet["schema_version"] == MATERIAL_AUDIT_SCHEMA_VERSION
    assert packet["audit_manifest"]["required_judge_flag_ids"] == ["a"]
    entries = packet["audit_packet"]["entries"]
    assert "hallucination" not in str(entries)
    assert "audit_role" not in str(entries)
    assert entries[0]["request_scoped_sources"]["r1"][0][
        "citation_id"
    ].startswith("citation-")
    assert entries[0]["request_scoped_sources"]["r1"][0]["cohort"] == "K50"


def test_material_summary_requires_completed_approved_decisions() -> None:
    packet = build_material_audit_packet(
        [_case("a"), _case("b")],
        [_answer("a"), _answer("b")],
        [{"id": "a", "hallucination": True}],
        answers_report_hash="answer-hash",
        commit="commit-sha",
        control_count=1,
    )
    packet["audit_manifest"]["decisions"] = [
        {
            "id": "a",
            "final_verdict": "judge_false_positive",
            "claims": [],
            "approved_by": "project-owner",
            "approved_at": "2026-08-22T10:00:00+07:00",
        },
        {
            "id": "b",
            "final_verdict": "material_unsupported",
            "claims": [
                {
                    "material_unsupported": True,
                    "critical": True,
                    "materiality_dimensions": ["direct_answer_conclusion"],
                }
            ],
            "approved_by": "project-owner",
            "approved_at": "2026-08-22T10:00:00+07:00",
        },
    ]

    summary = summarize_material_audit(
        packet,
        [{"id": "a", "hallucination": True}],
        answer_ids=["a", "b"],
    )

    assert summary["complete"] is True
    assert summary["raw_judge_hallucination_rate"] == 0.5
    assert summary["material_unsupported_answer_rate"] == 0.5
    assert summary["material_critical_unsupported_claims"] == 1
    assert summary["judge_false_positive_rate"] == 1.0


def test_material_summary_fails_closed_for_changed_judge_flags() -> None:
    packet = build_material_audit_packet(
        [_case("a")],
        [_answer("a")],
        [{"id": "a", "hallucination": True}],
        answers_report_hash="answer-hash",
        commit="commit-sha",
        control_count=0,
    )
    packet["audit_manifest"]["decisions"][0].update(
        {
            "final_verdict": "supported",
            "approved_by": "project-owner",
            "approved_at": "2026-08-22T10:00:00+07:00",
        }
    )

    summary = summarize_material_audit(
        packet,
        [],
        answer_ids=["a"],
    )

    assert summary["complete"] is False


def test_non_material_unsupported_is_not_a_judge_false_positive() -> None:
    packet = build_material_audit_packet(
        [_case("a")],
        [_answer("a")],
        [{"id": "a", "hallucination": True}],
        answers_report_hash="answer-hash",
        commit="commit-sha",
        control_count=0,
    )
    packet["audit_manifest"]["decisions"][0].update(
        {
            "final_verdict": "non_material_unsupported",
            "approved_by": "project-owner",
            "approved_at": "2026-08-22T10:00:00+07:00",
        }
    )

    summary = summarize_material_audit(
        packet,
        [{"id": "a", "hallucination": True}],
        answer_ids=["a"],
    )

    assert summary["complete"] is True
    assert summary["judge_false_positive_rate"] == 0.0


def test_material_verdict_requires_a_dimensioned_material_claim() -> None:
    packet = build_material_audit_packet(
        [_case("a")],
        [_answer("a")],
        [{"id": "a", "hallucination": True}],
        answers_report_hash="answer-hash",
        commit="commit-sha",
        control_count=0,
    )
    packet["audit_manifest"]["decisions"][0].update(
        {
            "final_verdict": "material_unsupported",
            "approved_by": "project-owner",
            "approved_at": "2026-08-22T10:00:00+07:00",
        }
    )

    summary = summarize_material_audit(
        packet,
        [{"id": "a", "hallucination": True}],
        answer_ids=["a"],
    )

    assert summary["complete"] is False
    assert summary["invalid_material_decisions"] == 1
