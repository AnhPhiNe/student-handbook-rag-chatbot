from __future__ import annotations

import json

from scripts.audit_answer_failures_v8 import (
    build_answer_failure_audit,
    build_human_audit_sample,
)


def test_build_answer_failure_audit_groups_judge_failures(tmp_path) -> None:
    cases_path = tmp_path / "cases.json"
    answers_path = tmp_path / "answers.json"
    judge_path = tmp_path / "judge.json"

    cases_path.write_text(
        json.dumps(
            [
                {
                    "id": "case_1",
                    "query": "Hoi hoc bong",
                    "topic": "hoc_bong",
                    "case_type": "regulation_true_rag",
                    "eval_split": "realistic",
                }
            ]
        ),
        encoding="utf-8",
    )
    answers_path.write_text(
        json.dumps(
            [
                {
                    "id": "case_1",
                    "answer": "A" * 2601,
                }
            ]
        ),
        encoding="utf-8",
    )
    judge_path.write_text(
        json.dumps(
            {
                "summary": {"n": 1},
                "cases": [
                    {
                        "id": "case_1",
                        "topic": "hoc_bong",
                        "case_type": "regulation_true_rag",
                        "eval_split": "realistic",
                        "judge": {
                            "scores": {
                                "faithfulness": 0.6,
                                "answer_correctness": 0.7,
                                "citation_correctness": 0.5,
                                "unsupported_claim": True,
                                "critical_false_pass": False,
                                "rationale": "unsupported detail",
                            }
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = build_answer_failure_audit(
        cases_path=cases_path,
        answers_path=answers_path,
        judge_path=judge_path,
    )

    summary = report["summary"]
    assert summary["n"] == 1
    assert summary["categories"]["unsupported_claim"] == 1
    assert summary["categories"]["low_faithfulness"] == 1
    assert summary["categories"]["long_answer"] == 1
    assert summary["by_topic"]["hoc_bong"]["low_citation"] == 1
    assert report["cases"][0]["id"] == "case_1"
    assert "answer_scope" not in report["cases"][0]
    assert "scope_abstention_reason" not in report["cases"][0]

    packet = build_human_audit_sample(
        cases_path=cases_path,
        answers_path=answers_path,
        judge_path=judge_path,
        low_count=1,
        random_count=0,
    )
    assert len(packet) == 1
    assert packet[0]["selection_group"] == "low_score"
    assert packet[0]["answer"] == "A" * 2601
    assert packet[0]["human_correctness"] is None
