"""Re-grade a frozen report without treating it as release evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.single_cohort_v2 import (  # noqa: E402
    EVALUATION_PROTOCOL_VERSION,
    PlanAssessment,
    assess_plan,
)


def _planner_layers(
    row: Mapping[str, Any], assessment: PlanAssessment
) -> list[str]:
    if row.get("provider_failure"):
        return ["provider"]
    if assessment.exact_match:
        return ["exact_pass"]
    if assessment.semantic_match:
        return ["representation"]
    reasons = set(assessment.mismatch_reasons)
    layers: list[str] = []
    validation_errors = (
        (row.get("validated_decision") or {}).get("router_validation_errors") or []
    )
    if validation_errors:
        layers.append("validator_or_invalid_proposal")
    if any(reason.endswith(":slots") for reason in reasons):
        layers.append("registry_or_planner_slots")
    structural = {
        "outcome", "context_mode", "effective_cohort", "effective_cohort_source",
        "request_count",
    }
    if reasons & structural or any(
        reason.endswith((":request_kind", ":tool_name", ":intent"))
        for reason in reasons
    ):
        layers.append("planner_semantics")
    if any(reason.endswith(":query_span") for reason in reasons):
        layers.append("planner_grounding")
    return layers or ["review_required"]


def analyze_report(report: Mapping[str, Any]) -> dict[str, Any]:
    planner_rows = ((report.get("planner") or {}).get("dev") or {}).get("rows") or []
    planner_counts: Counter[str] = Counter()
    category_counts: dict[str, Counter[str]] = defaultdict(Counter)
    analyzed_rows: list[dict[str, Any]] = []
    for row in planner_rows:
        if not row.get("expected") or not row.get("actual"):
            layers = ["provider"] if row.get("provider_failure") else ["review_required"]
            assessment = None
        else:
            assessment = assess_plan(row["expected"], row["actual"])
            layers = _planner_layers(row, assessment)
        category = str(row.get("category") or "") or re.sub(
            r"-\d+$", "", re.sub(r"^(?:dev|hidden)-", "", str(row.get("id") or "unknown"))
        )
        for layer in layers:
            planner_counts[layer] += 1
            category_counts[category][layer] += 1
        analyzed_rows.append(
            {
                "id": row.get("id"),
                "exact_match": bool(assessment and assessment.exact_match),
                "semantic_match": bool(assessment and assessment.semantic_match),
                "critical_failure": bool(assessment and assessment.critical_failure),
                "mismatch_reasons": list(assessment.mismatch_reasons) if assessment else [],
                "layers": layers,
                "validator_errors": (
                    (row.get("validated_decision") or {}).get("router_validation_errors") or []
                ),
            }
        )

    execution_counts: Counter[str] = Counter()
    for row in ((report.get("executor_retrieval") or {}).get("rows") or []):
        if row.get("provider_failure"):
            execution_counts["provider"] += 1
        if row.get("status_match") is False:
            execution_counts["adapter_or_retrieval_status"] += 1
        if any(not value for value in row.get("rag_hits") or []):
            execution_counts["retrieval"] += 1
        if any(not value for value in row.get("structured_bindings") or []):
            execution_counts["adapter_source_binding"] += 1
        if any(not value for value in row.get("citation_bindings") or []):
            execution_counts["citation_binding"] += 1

    composer_counts: Counter[str] = Counter()
    for row in report.get("answers") or []:
        if row.get("provider_failure"):
            composer_counts["provider"] += 1
        elif not row.get("answer_contract_bound"):
            composer_counts["composer_contract"] += 1

    return {
        "source_commit": report.get("commit"),
        "evaluation_protocol_version": EVALUATION_PROTOCOL_VERSION,
        "diagnostic_only": True,
        "planner": {
            "total": len(planner_rows),
            "exact_passed": sum(row["exact_match"] for row in analyzed_rows),
            "semantic_passed": sum(row["semantic_match"] for row in analyzed_rows),
            "critical_failures": sum(row["critical_failure"] for row in analyzed_rows),
            "layer_counts": dict(planner_counts),
            "category_layer_counts": {
                key: dict(value) for key, value in category_counts.items()
            },
            "rows": analyzed_rows,
        },
        "executor_retrieval_failure_counts": dict(execution_counts),
        "composer_failure_counts": dict(composer_counts),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    analysis = analyze_report(payload)
    analysis["generated_at"] = datetime.now(UTC).isoformat()
    analysis["source_report_sha256"] = hashlib.sha256(args.input.read_bytes()).hexdigest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    planner = analysis["planner"]
    print(
        json.dumps(
            {
                "source_commit": analysis["source_commit"],
                "exact_passed": planner["exact_passed"],
                "semantic_passed": planner["semantic_passed"],
                "critical_failures": planner["critical_failures"],
                "layer_counts": planner["layer_counts"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
