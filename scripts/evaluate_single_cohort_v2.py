"""Release evaluator entry point. Hidden suite is never used for tuning."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.evaluation.single_cohort_v2 import BUNDLE_DIR, exact_plan_match, failure_taxonomy, validate_bundle
from src.retrieval.core.ai_router import AIRouter


def _commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _plan_from_decision(decision: dict[str, Any]) -> dict[str, Any]:
    requests = []
    for index, request in enumerate(decision.get("lookup_requests") or [], 1):
        if not isinstance(request, dict):
            continue
        requests.append({"request_id": f"r{index}", "request_kind": request.get("request_kind"), "lookup_type": request.get("lookup_type"), "intent": request.get("intent"), "query_span": request.get("query_span"), "slots": request.get("slots") or {}, "cohort_refs": request.get("cohort_refs") or []})
    return {"outcome": decision.get("outcome"), "context_mode": decision.get("context_mode"), "effective_cohort": decision.get("cohort"), "effective_cohort_source": decision.get("effective_cohort_source"), "atomic_requests": requests}


def run_live_planner(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    router = AIRouter.from_config()
    rows: list[dict[str, Any]] = []
    for case in cases:
        try:
            decision = router.route(case["query"], chat_history=case.get("chat_history") or [], cohort=case.get("selected_cohort"))
            matched = exact_plan_match(case["expected"], _plan_from_decision(decision))
            rows.append({"id": case["id"], "passed": matched, "failure_type": "pass" if matched else "planner"})
        except Exception as error:  # provider failure intentionally stays denominator.
            rows.append({"id": case["id"], "passed": False, "failure_type": "provider", "error": str(error)})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", choices=("dev", "hidden"), default="dev")
    parser.add_argument("--live-planner", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    validation = validate_bundle()
    report: dict[str, Any] = {"timestamp": datetime.now(UTC).isoformat(), "commit": _commit(), "schema_version": "single-cohort-v2.0", "models": {"planner": "qwen/qwen3.6-27b", "answer": "gemini-3.1-flash-lite"}, "bundle_hashes": validation.hashes, "contract": {"passed": validation.valid, "errors": validation.errors}, "release_ready": False}
    if args.live_planner and validation.valid:
        cases = json.loads((BUNDLE_DIR / f"{args.suite}.json").read_text(encoding="utf-8"))
        rows = run_live_planner(cases)
        report["planner"] = {"suite": args.suite, "passed": sum(row["passed"] for row in rows), "total": len(rows), "exact_plan_accuracy": sum(row["passed"] for row in rows) / len(rows), "failure_taxonomy": failure_taxonomy(rows), "rows": rows}
    else:
        report["planner"] = {"not_run": True, "reason": "Use --live-planner after code/prompt freeze."}
    output = args.output or BUNDLE_DIR / "latest_evaluation_report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("commit", "contract", "planner", "release_ready")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
