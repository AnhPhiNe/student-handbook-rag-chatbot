from __future__ import annotations

from typing import Any

from .metrics import safe_mean


def summarize_human_audit(
    audit_rows: list[dict[str, Any]],
    judge_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    judge_by_id = {row["id"]: row for row in judge_rows}
    completed = [row for row in audit_rows if row.get("human_score") is not None]
    differences: list[float] = []
    agreement: list[float] = []
    critical_false_passes = 0
    for row in completed:
        judge_row = judge_by_id.get(row["id"], {})
        scores = (judge_row.get("judge") or {}).get("scores") or {}
        judge_score = safe_mean(
            [
                float(scores[name])
                for name in (
                    "faithfulness",
                    "answer_correctness",
                    "citation_correctness",
                )
                if scores.get(name) is not None
            ]
        )
        if judge_score is not None:
            difference = abs(float(row["human_score"]) - judge_score)
            differences.append(difference)
            agreement.append(float(difference <= 0.15))
        critical_false_passes += int(bool(row.get("critical_false_pass")))

    repeated = [row for row in completed if row.get("repeat_score") is not None]
    consistency = [
        abs(float(row["human_score"]) - float(row["repeat_score"])) for row in repeated
    ]
    return {
        "required_n": 20,
        "completed_n": len(completed),
        "complete": len(completed) >= 20,
        "human_judge_mae": safe_mean(differences),
        "agreement_within_0_15": safe_mean(agreement),
        "critical_false_passes": critical_false_passes,
        "repeat_required_n": 5,
        "repeat_completed_n": len(repeated),
        "human_repeat_mae": safe_mean(consistency),
    }
