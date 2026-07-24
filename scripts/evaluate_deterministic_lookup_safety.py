from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.retrieval.core import retrieval_pipeline as pipeline

DEFAULT_CASES = ROOT / "data" / "eval" / "deterministic_lookup_safety_cases.json"
DEFAULT_REPORT = ROOT / "data" / "eval" / "reports" / "deterministic_lookup_safety_report.json"

DETERMINISTIC_STRATEGIES = {
    "foreign_language_lookup",
    "study_duration_lookup",
    "scholarship_classification_lookup",
    "student_service_lookup",
    "office_lookup",
    "program_lookup",
    "formula_lookup",
    "structured_lookup",
}


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _patch_retrieval() -> None:
    def fake_retrieve_with_plan(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []

    pipeline.retrieve_with_plan = fake_retrieve_with_plan


def _run_case(case: dict[str, Any], resources: dict[str, Any]) -> dict[str, Any]:
    result = pipeline.run_retrieval_pipeline(
        query=case["query"],
        model=None,
        collection=None,
        scoring_tables=resources["scoring_tables"],
        formula_rules=resources["formula_rules"],
        entity_registry=[],
        expansion_rules=[],
        office_directory=resources["student_office_profiles"],
        student_service_directory=resources["student_service_directory"],
        foreign_language_tables=resources["foreign_language_tables"],
        structured_tables_registry=resources["structured_tables_registry"],
        program_directory=resources["program_directory"],
        cohort=case.get("cohort"),
    )
    strategy = result.get("strategy")
    actual_group = (
        "deterministic"
        if strategy in DETERMINISTIC_STRATEGIES and result.get("needs_llm_answer") is False
        else "rag"
    )
    expected_group = case["expected_group"]
    expected_strategy = case.get("expected_strategy")
    must_not_strategy = case.get("must_not_strategy")

    is_pass = actual_group == expected_group
    if expected_strategy:
        is_pass = is_pass and strategy == expected_strategy
    if must_not_strategy:
        is_pass = is_pass and strategy != must_not_strategy

    return {
        **case,
        "actual_strategy": strategy,
        "actual_intent": result.get("intent"),
        "actual_group": actual_group,
        "needs_llm_answer": result.get("needs_llm_answer"),
        "passed": is_pass,
    }


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    passed = sum(1 for row in rows if row["passed"])
    expected_det = [row for row in rows if row["expected_group"] == "deterministic"]
    expected_rag = [row for row in rows if row["expected_group"] == "rag"]
    false_positive = [
        row
        for row in expected_rag
        if row["actual_group"] == "deterministic"
    ]
    false_negative = [
        row
        for row in expected_det
        if row["actual_group"] != "deterministic"
    ]
    wrong_strategy = [
        row
        for row in rows
        if row.get("expected_strategy")
        and row["actual_group"] == "deterministic"
        and row["actual_strategy"] != row["expected_strategy"]
    ]

    by_expected_strategy: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        key = row.get("expected_strategy") or row.get("must_not_strategy") or "rag"
        by_expected_strategy[key][row["actual_strategy"] or "none"] += 1

    deterministic_predictions = [row for row in rows if row["actual_group"] == "deterministic"]
    true_positive = [
        row
        for row in deterministic_predictions
        if row["expected_group"] == "deterministic"
        and (
            not row.get("expected_strategy")
            or row["actual_strategy"] == row["expected_strategy"]
        )
    ]
    lookup_precision = len(true_positive) / len(deterministic_predictions) if deterministic_predictions else 0.0
    lookup_recall = (
        len([row for row in expected_det if row["actual_group"] == "deterministic"])
        / len(expected_det)
        if expected_det
        else 0.0
    )

    return {
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "strategy_accuracy": passed / total if total else 0.0,
        "lookup_precision": lookup_precision,
        "lookup_recall": lookup_recall,
        "false_positive_count": len(false_positive),
        "false_positive_rate_on_rag_cases": len(false_positive) / len(expected_rag) if expected_rag else 0.0,
        "false_negative_count": len(false_negative),
        "wrong_strategy_count": len(wrong_strategy),
        "actual_strategy_counts": dict(Counter(row["actual_strategy"] for row in rows)),
        "confusion_by_expected": {
            key: dict(counter)
            for key, counter in sorted(by_expected_strategy.items())
        },
        "failures": [
            {
                "id": row["id"],
                "query": row["query"],
                "expected_group": row["expected_group"],
                "expected_strategy": row.get("expected_strategy"),
                "must_not_strategy": row.get("must_not_strategy"),
                "actual_group": row["actual_group"],
                "actual_strategy": row["actual_strategy"],
                "reason": row["reason"],
            }
            for row in rows
            if not row["passed"]
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate deterministic lookup safety without calling Qdrant/Gemini.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    # os.environ["STUDENT_RAG_DISABLE_AI_ROUTER"] = "1"
    _patch_retrieval()

    resources = {
        "scoring_tables": _load_json(ROOT / "data" / "processed" / "tables" / "scoring_tables.json", []),
        "formula_rules": _load_json(ROOT / "data" / "processed" / "tables" / "formula_rules.json", []),
        "student_service_directory": _load_json(ROOT / "data" / "processed" / "directories" / "student_service_directory.json", []),
        "student_office_profiles": _load_json(ROOT / "data" / "processed" / "directories" / "student_office_profiles.json", []),
        "foreign_language_tables": _load_json(ROOT / "data" / "processed" / "tables" / "foreign_language_equivalency_table.json", []),
        "structured_tables_registry": _load_json(ROOT / "data" / "processed" / "tables" / "structured_tables_registry.json", []),
        "program_directory": _load_json(ROOT / "data" / "processed" / "directories" / "program_directory.json", []),
    }
    cases = _load_json(args.cases, [])
    rows = [_run_case(case, resources) for case in cases]
    summary = _summarize(rows)
    report = {"summary": summary, "cases": rows}

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
