from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.common.console import configure_utf8_stdio
from src.retrieval.core.query_router import route_query


DEFAULT_CASES_PATH = Path("data/eval/router_behavior_queries.json")
DEFAULT_OUTPUT_PATH = Path("data/processed/metadata/router_behavior_eval_report.json")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        f.write("\n")


def evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    routing = route_query(str(case["query"]))
    expected_intent = case.get("expected_intent")
    expected_strategy = case.get("expected_strategy")
    expected_targets = case.get("expected_target_chunk_types")
    actual_targets = routing.get("target_chunk_types", [])

    target_match = (
        None
        if expected_targets is None
        else list(expected_targets) == list(actual_targets)
    )

    return {
        "id": case.get("id"),
        "category": case.get("category"),
        "cohort": case.get("cohort", "all"),
        "query": case["query"],
        "expected_intent": expected_intent,
        "actual_intent": routing.get("intent"),
        "intent_match": routing.get("intent") == expected_intent,
        "expected_strategy": expected_strategy,
        "actual_strategy": routing.get("strategy"),
        "strategy_match": routing.get("strategy") == expected_strategy,
        "expected_target_chunk_types": expected_targets,
        "actual_target_chunk_types": actual_targets,
        "target_match": target_match,
    }


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_cohort: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for result in results:
        by_category[str(result.get("category") or "uncategorized")].append(result)
        by_cohort[str(result.get("cohort") or "all")].append(result)

    return {
        "total_cases": len(results),
        "intent_accuracy": _mean_bool(results, "intent_match"),
        "strategy_accuracy": _mean_bool(results, "strategy_match"),
        "target_accuracy": _mean_bool(results, "target_match"),
        "category_breakdown": {
            category: {
                "cases": len(items),
                "intent_accuracy": _mean_bool(items, "intent_match"),
                "strategy_accuracy": _mean_bool(items, "strategy_match"),
                "target_accuracy": _mean_bool(items, "target_match"),
            }
            for category, items in sorted(by_category.items())
        },
        "cohort_breakdown": {
            cohort: {
                "cases": len(items),
                "intent_accuracy": _mean_bool(items, "intent_match"),
                "strategy_accuracy": _mean_bool(items, "strategy_match"),
                "target_accuracy": _mean_bool(items, "target_match"),
            }
            for cohort, items in sorted(by_cohort.items())
        },
    }


def run_evaluation(cases_path: Path) -> dict[str, Any]:
    cases = load_json(cases_path)
    results = [evaluate_case(case) for case in cases]
    return {
        "evaluation": "router_behavior_eval",
        "cases_path": str(cases_path),
        "summary": build_summary(results),
        "cases": results,
    }


def main() -> None:
    configure_utf8_stdio()

    parser = argparse.ArgumentParser(description="Evaluate router behavior cases.")
    parser.add_argument("--cases", default=str(DEFAULT_CASES_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--fail-under-intent", type=float, default=None)
    parser.add_argument("--fail-under-strategy", type=float, default=None)
    args = parser.parse_args()

    report = run_evaluation(Path(args.cases))
    save_json(report, Path(args.output))

    summary = report["summary"]
    print("\nRouter behavior evaluation")
    for key in ("total_cases", "intent_accuracy", "strategy_accuracy", "target_accuracy"):
        print(f"{key}: {summary[key]}")
    print(f"Saved report: {args.output}")

    if args.fail_under_intent is not None and summary["intent_accuracy"] < args.fail_under_intent:
        sys.exit(1)
    if args.fail_under_strategy is not None and summary["strategy_accuracy"] < args.fail_under_strategy:
        sys.exit(1)


def _mean_bool(items: list[dict[str, Any]], field: str) -> float | None:
    values = [item.get(field) for item in items if item.get(field) is not None]
    if not values:
        return None
    return round(sum(1 for value in values if value is True) / len(values), 4)


if __name__ == "__main__":
    main()
