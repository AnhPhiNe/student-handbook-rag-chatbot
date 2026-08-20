from __future__ import annotations

import pytest

from scripts.judge_single_cohort_v2_answers import _judge_case, _validated_answer_targets


def test_judge_targets_only_generated_answers() -> None:
    cases = {
        "planned": {"id": "planned"},
        "planner-failed": {"id": "planner-failed"},
    }

    ids, answers = _validated_answer_targets(
        [{"id": "planned", "answer": "verified"}],
        cases,
        split="dev",
    )

    assert ids == ["planned"]
    assert set(answers) == {"planned"}


@pytest.mark.parametrize(
    "rows, error",
    [
        ([{"id": "case-1"}, {"id": "case-1"}], "duplicate"),
        ([{"id": "hidden-1"}], "outside dev"),
        ([{"answer": "missing id"}], "without an id"),
    ],
)
def test_judge_targets_fail_closed(rows, error) -> None:
    with pytest.raises(ValueError, match=error):
        _validated_answer_targets(rows, {"case-1": {"id": "case-1"}}, split="dev")


def test_judge_case_preserves_gold_evidence_by_request_scope() -> None:
    case = {
        "id": "multi-rag",
        "query": "Hai quy định",
        "expected": {
            "outcome": "execute",
            "effective_cohort": "K51",
            "atomic_requests": [
                {
                    "request_id": "r1",
                    "request_kind": "rag",
                    "query_span": "quy định một",
                    "expected_evidence": {
                        "evidence_excerpts": ["Bằng chứng một"],
                        "source_bindings": [
                            {"document_id": "doc", "parent_section_id": "p1"}
                        ],
                    },
                },
                {
                    "request_id": "r2",
                    "request_kind": "rag",
                    "query_span": "quy định hai",
                    "expected_evidence": {
                        "evidence_excerpts": ["Bằng chứng hai"],
                        "source_bindings": [
                            {"document_id": "doc", "parent_section_id": "p2"}
                        ],
                    },
                },
            ],
        },
    }

    packet_case = _judge_case(case)

    assert "[r1 | quy định một] Bằng chứng một" in packet_case["ground_truth"]
    assert "[r2 | quy định hai] Bằng chứng hai" in packet_case["ground_truth"]
    assert [item["request_id"] for item in packet_case["expected_citations"]] == [
        "r1",
        "r2",
    ]
