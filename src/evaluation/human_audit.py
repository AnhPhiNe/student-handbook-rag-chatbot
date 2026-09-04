from __future__ import annotations

from typing import Any

from .metrics import safe_mean


def summarize_human_audit(
    audit_rows: list[dict[str, Any]],
    judge_rows: list[dict[str, Any]],
    template_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Aggregate completed human-review labels into summary metrics."""

    contract_errors: list[str] = []
    expected_rows = template_rows if template_rows is not None else audit_rows
    expected_by_id = {str(row.get("id") or ""): row for row in expected_rows}
    actual_by_id = {str(row.get("id") or ""): row for row in audit_rows}
    if template_rows is not None:
        if len(expected_by_id) != len(expected_rows):
            contract_errors.append("human_audit_template_has_duplicate_ids")
        if len(actual_by_id) != len(audit_rows):
            contract_errors.append("human_audit_has_duplicate_ids")
        missing_ids = sorted(set(expected_by_id) - set(actual_by_id))
        unexpected_ids = sorted(set(actual_by_id) - set(expected_by_id))
        if missing_ids:
            contract_errors.append(
                "human_audit_missing_template_ids:" + ",".join(missing_ids)
            )
        if unexpected_ids:
            contract_errors.append(
                "human_audit_unexpected_ids:" + ",".join(unexpected_ids)
            )
        for case_id in sorted(set(expected_by_id) & set(actual_by_id)):
            expected_repeat = bool(
                expected_by_id[case_id].get("repeat_for_consistency")
            )
            actual_repeat = bool(actual_by_id[case_id].get("repeat_for_consistency"))
            if expected_repeat != actual_repeat:
                contract_errors.append(f"human_audit_repeat_flag_mismatch:{case_id}")

    judge_by_id = {row["id"]: row for row in judge_rows}
    completed = [
        row
        for row in audit_rows
        if str(row.get("id") or "") in expected_by_id
        and row.get("human_score") is not None
    ]
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

    repeated = [
        row
        for row in completed
        if bool(expected_by_id[str(row.get("id") or "")].get("repeat_for_consistency"))
        and row.get("repeat_score") is not None
    ]
    required_n = len(expected_rows)
    repeat_required_n = sum(
        bool(row.get("repeat_for_consistency")) for row in expected_rows
    )
    consistency = [
        abs(float(row["human_score"]) - float(row["repeat_score"])) for row in repeated
    ]
    return {
        "required_n": required_n,
        "completed_n": len(completed),
        "complete": bool(
            required_n > 0
            and len(completed) == required_n
            and len(repeated) == repeat_required_n
            and not contract_errors
        ),
        "contract_errors": contract_errors,
        "human_judge_mae": safe_mean(differences),
        "agreement_within_0_15": safe_mean(agreement),
        "critical_false_passes": critical_false_passes,
        "repeat_required_n": repeat_required_n,
        "repeat_completed_n": len(repeated),
        "human_repeat_mae": safe_mean(consistency),
    }
