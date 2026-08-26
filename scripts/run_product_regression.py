from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.env_loader import load_project_env


DEFAULT_DATASET = Path("data/eval/product_regression/cases.json")
DEFAULT_OUTPUT = Path("data/eval/reports/product_regression.json")
ALLOWED_OUTCOMES = {
    "answered",
    "partial",
    "needs_clarification",
    "out_of_domain",
}
REVIEW_TEMPLATE = {
    "decision": None,
    "tasks_complete": None,
    "grounded": None,
    "citations_correct": None,
    "cohort_correct": None,
    "abstention_correct": None,
    "runtime_stable": None,
    "severity": None,
    "notes": "",
}


def load_cases(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Dataset root must be an object")
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("Dataset must contain a cases list")
    validate_cases(cases)
    return payload, cases


def validate_cases(cases: list[dict[str, Any]]) -> None:
    if not 20 <= len(cases) <= 30:
        raise ValueError("Product regression must contain 20-30 cases")

    seen_ids: set[str] = set()
    for index, case in enumerate(cases, start=1):
        if not isinstance(case, dict):
            raise ValueError(f"Case {index} must be an object")
        case_id = str(case.get("id") or "").strip()
        if not case_id:
            raise ValueError(f"Case {index} is missing id")
        if case_id in seen_ids:
            raise ValueError(f"Duplicate case id: {case_id}")
        seen_ids.add(case_id)

        for field in ("category", "query", "review_focus"):
            if not str(case.get(field) or "").strip():
                raise ValueError(f"{case_id} is missing {field}")
        outcome = str(case.get("expected_outcome") or "")
        if outcome not in ALLOWED_OUTCOMES:
            raise ValueError(f"{case_id} has invalid expected_outcome={outcome!r}")
        history = case.get("history", [])
        if not isinstance(history, list):
            raise ValueError(f"{case_id}.history must be a list")


def _automatic_checks(case: dict[str, Any], result: dict[str, Any]) -> dict[str, bool]:
    status = str(result.get("status") or "")
    expected = str(case["expected_outcome"])
    no_runtime_error = status not in {"retrieval_error", "api_error"}

    outcome_shape_ok = True
    if expected == "needs_clarification":
        outcome_shape_ok = bool(result.get("clarification_needed"))
    elif expected == "out_of_domain":
        outcome_shape_ok = status == "out_of_domain" and not bool(result.get("llm_called"))
    elif expected == "answered":
        outcome_shape_ok = status not in {
            "needs_clarification",
            "out_of_domain",
            "retrieval_error",
            "api_error",
        }
    elif expected == "partial":
        coverage = result.get("coverage_by_task") or {}
        outcome_shape_ok = len(coverage) >= 2 and len(set(coverage.values())) >= 2

    covered_have_citations = True
    coverage = result.get("coverage_by_task") or {}
    citations = result.get("citations_used") or []
    for task_id, task_coverage in coverage.items():
        if task_coverage != "covered":
            continue
        if not any(task_id in (citation.get("supports_task_ids") or []) for citation in citations):
            covered_have_citations = False
            break

    return {
        "no_runtime_error": no_runtime_error,
        "expected_outcome_shape": outcome_shape_ok,
        "covered_tasks_have_citations": covered_have_citations,
    }


def _result_for_review(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": result.get("answer"),
        "status": result.get("status"),
        "clarification_needed": bool(result.get("clarification_needed")),
        "llm_called": bool(result.get("llm_called")),
        "used_cache": bool(result.get("used_cache")),
        "model_used": result.get("model_used"),
        "planner_fallback": result.get("planner_fallback"),
        "query_plan": result.get("query_plan") or {},
        "task_results": result.get("task_results") or [],
        "coverage_by_task": result.get("coverage_by_task") or {},
        "citations_used": result.get("citations_used") or [],
        "structured_results": result.get("structured_results") or [],
        "error_type": result.get("error_type"),
        "error_message": result.get("error_message"),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the lightweight product regression set")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--use-cache", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    dataset, cases = load_cases(args.dataset)
    selected_ids = set(args.case_ids or [])
    if selected_ids:
        known_ids = {str(case["id"]) for case in cases}
        unknown_ids = sorted(selected_ids - known_ids)
        if unknown_ids:
            raise ValueError(f"Unknown case ids: {unknown_ids}")
        cases = [case for case in cases if case["id"] in selected_ids]
    if args.limit is not None:
        if args.limit < 1:
            raise ValueError("--limit must be positive")
        cases = cases[: args.limit]

    category_counts = Counter(str(case["category"]) for case in cases)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "schema_version": dataset.get("schema_version"),
                    "total": len(cases),
                    "categories": dict(sorted(category_counts.items())),
                    "valid": True,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    load_project_env(override=False)
    from src.generation.answer_pipeline import AnswerPipeline

    pipeline = AnswerPipeline()
    if not args.use_cache and hasattr(pipeline.response_cache, "enabled"):
        pipeline.response_cache.enabled = False

    rows: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        started = time.perf_counter()
        try:
            result = pipeline.answer(
                str(case["query"]),
                chat_history=case.get("history") or [],
                cohort=case.get("cohort"),
            )
            runtime_error = None
        except Exception as exc:
            result = {
                "answer": "",
                "status": "unhandled_error",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
            runtime_error = f"{type(exc).__name__}: {exc}"

        elapsed = round(time.perf_counter() - started, 3)
        checks = _automatic_checks(case, result)
        row = {
            "id": case["id"],
            "category": case["category"],
            "query": case["query"],
            "cohort": case.get("cohort"),
            "history": case.get("history") or [],
            "expected_outcome": case["expected_outcome"],
            "review_focus": case["review_focus"],
            "latency_seconds": elapsed,
            "runtime_error": runtime_error,
            "automatic_checks": checks,
            "automatic_checks_passed": all(checks.values()),
            "result": _result_for_review(result),
            "human_review": dict(REVIEW_TEMPLATE),
        }
        rows.append(row)
        label = "READY" if row["automatic_checks_passed"] else "CHECK"
        print(f"[{index:02d}/{len(cases)}] {case['id']}: {label} ({elapsed:.2f}s)", flush=True)

    report = {
        "schema_version": "product-regression-report-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_schema_version": dataset.get("schema_version"),
        "dataset_path": str(args.dataset.as_posix()),
        "review_status": "pending_human_review",
        "summary": {
            "total": len(rows),
            "automatic_checks_passed": sum(
                bool(row["automatic_checks_passed"]) for row in rows
            ),
            "categories": dict(sorted(category_counts.items())),
            "human_passed": None,
            "human_pass_rate": None,
            "critical_failures": None,
        },
        "cases": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Report: {args.output}")
    print("Kết quả cuối cần human review; automatic checks không phải quality score.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

