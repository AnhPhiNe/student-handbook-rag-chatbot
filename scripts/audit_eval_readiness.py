"""Audit evaluation coverage and annotation readiness without calling model APIs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.dataset import DATASET_FILES, load_json, validate_bundle  # noqa: E402


DEFAULT_DATASET = ROOT / "data" / "eval" / "v8_5_answer_holdout"
DEFAULT_DOCSTORE = ROOT / "data" / "processed" / "chunks" / "all_docstore_items.json"


def _distribution(cases: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(
        sorted(
            Counter(str(case.get(field) or "missing") for case in cases).items()
        )
    )


def _word_count(query: str) -> int:
    return len(re.findall(r"\w+", query, flags=re.UNICODE))


def _query_profile(cases: list[dict[str, Any]]) -> dict[str, Any]:
    lengths = [_word_count(str(case.get("query") or "")) for case in cases]
    explicit_cohort = sum(
        bool(re.search(r"\bK(?:48|49|50|51)\b", str(case.get("query") or "")))
        for case in cases
    )
    boilerplate = sum(
        str(case.get("query") or "").casefold().startswith(("case ", "em thuộc"))
        for case in cases
    )
    return {
        "mean_words": round(sum(lengths) / len(lengths), 2) if lengths else 0.0,
        "short_query_rate_le_8_words": (
            round(sum(length <= 8 for length in lengths) / len(lengths), 4)
            if lengths
            else 0.0
        ),
        "long_query_rate_gt_25_words": (
            round(sum(length > 25 for length in lengths) / len(lengths), 4)
            if lengths
            else 0.0
        ),
        "explicit_cohort_rate": (
            round(explicit_cohort / len(cases), 4) if cases else 0.0
        ),
        "boilerplate_prefix_count": boilerplate,
    }


def audit_bundle(
    bundle_dir: Path,
    *,
    docstore_path: Path = DEFAULT_DOCSTORE,
) -> dict[str, Any]:
    datasets = {
        suite: load_json(bundle_dir / filename)
        for suite, filename in DATASET_FILES.items()
    }
    validation = validate_bundle(bundle_dir, docstore_path)
    deterministic = datasets["deterministic"]
    retrieval = datasets["retrieval"]
    answers = datasets["answers"]
    production = datasets["production"]

    structured_answers = [
        case
        for case in answers
        if case.get("expected_path") in {"structured", "mixed"}
    ]
    mixed_answers = [
        case for case in answers if case.get("expected_path") == "mixed"
    ]
    supporting_judgment_cases = sum(
        any(int(item.get("grade") or 0) == 1 for item in case.get("relevance_judgments") or [])
        for case in retrieval
    )
    source_usage = Counter(
        (
            str(case.get("cohort") or "general"),
            str(item.get("parent_section_id") or ""),
        )
        for case in retrieval
        for item in case.get("relevance_judgments") or []
        if int(item.get("grade") or 0) == 2
    )
    overloaded_sources = {
        f"{cohort}:{source_id}": count
        for (cohort, source_id), count in source_usage.items()
        if count > 2
    }

    issues: list[dict[str, str]] = []

    def add_issue(code: str, severity: str, message: str) -> None:
        issues.append({"code": code, "severity": severity, "message": message})

    if not validation["valid"]:
        add_issue(
            "validator_failed",
            "blocker",
            f"Dataset validator has {len(validation['errors'])} error(s).",
        )
    if len(mixed_answers) < 10:
        add_issue(
            "mixed_answer_coverage",
            "blocker",
            f"Only {len(mixed_answers)} mixed answer cases; target is at least 10.",
        )
    structured_groups = Counter(
        str(case.get("lookup_group") or "missing") for case in structured_answers
    )
    missing_structured_groups = sorted(
        {
            "faculty",
            "foreign_language",
            "formula",
            "conduct",
            "office",
            "program",
            "scholarship",
            "scoring",
            "service",
            "study_duration",
        }
        - set(structured_groups)
    )
    if missing_structured_groups:
        add_issue(
            "structured_answer_groups",
            "blocker",
            "Missing structured answer groups: " + ", ".join(missing_structured_groups),
        )
    answer_query_profile = _query_profile(answers)
    retrieval_query_profile = _query_profile(retrieval)
    if answer_query_profile["short_query_rate_le_8_words"] < 0.15:
        add_issue(
            "short_answer_queries",
            "warning",
            "Fewer than 15% answer queries are short natural student questions.",
        )
    if retrieval_query_profile["short_query_rate_le_8_words"] < 0.15:
        add_issue(
            "short_retrieval_queries",
            "warning",
            "Fewer than 15% retrieval queries are short natural student questions.",
        )
    if supporting_judgment_cases < 20:
        add_issue(
            "graph_support_labels",
            "warning",
            f"Only {supporting_judgment_cases} retrieval cases label supporting sources.",
        )
    if overloaded_sources:
        add_issue(
            "parent_overuse",
            "blocker",
            f"{len(overloaded_sources)} primary parent/cohort pairs exceed two queries.",
        )
    production_paths = _distribution(production, "expected_path")
    if production_paths.get("mixed", 0) == 0:
        add_issue(
            "production_mixed_path",
            "warning",
            "Production suite has no explicit mixed-path request.",
        )
    if production_paths.get("clarify", 0) == 0:
        add_issue(
            "production_clarify_path",
            "warning",
            "Production suite has no explicit clarification request.",
        )

    blockers = sum(issue["severity"] == "blocker" for issue in issues)
    return {
        "dataset": str(bundle_dir),
        "ready_for_headline_run": blockers == 0,
        "blocker_count": blockers,
        "warning_count": sum(issue["severity"] == "warning" for issue in issues),
        "validation": validation,
        "coverage": {
            "counts": {suite: len(cases) for suite, cases in datasets.items()},
            "deterministic": {
                "case_type": _distribution(deterministic, "case_type"),
                "lookup_group": _distribution(deterministic, "lookup_group"),
                "expected_path": _distribution(deterministic, "expected_path"),
                "cohort": _distribution(deterministic, "cohort"),
                "query_profile": _query_profile(deterministic),
            },
            "retrieval": {
                "case_type": _distribution(retrieval, "case_type"),
                "cohort": _distribution(retrieval, "cohort"),
                "topic": _distribution(retrieval, "topic"),
                "query_style": _distribution(retrieval, "query_style"),
                "eval_split": _distribution(retrieval, "eval_split"),
                "query_profile": retrieval_query_profile,
                "supporting_judgment_cases": supporting_judgment_cases,
                "overloaded_primary_sources": overloaded_sources,
            },
            "answers": {
                "case_type": _distribution(answers, "case_type"),
                "source_relation": _distribution(answers, "source_relation"),
                "expected_path": _distribution(answers, "expected_path"),
                "cohort": _distribution(answers, "cohort"),
                "structured_lookup_group": dict(sorted(structured_groups.items())),
                "query_profile": answer_query_profile,
            },
            "production": {
                "scenario": _distribution(production, "scenario"),
                "expected_path": production_paths,
                "eval_split": _distribution(production, "eval_split"),
                "query_profile": _query_profile(production),
            },
        },
        "issues": issues,
    }


def _markdown(report: dict[str, Any]) -> str:
    status = "READY" if report["ready_for_headline_run"] else "NOT READY"
    lines = [
        "# Evaluation Readiness Audit",
        "",
        f"- Status: **{status}**",
        f"- Blockers: {report['blocker_count']}",
        f"- Warnings: {report['warning_count']}",
        "",
        "## Dataset Counts",
        "",
        "| Suite | Cases |",
        "|---|---:|",
    ]
    for suite, count in report["coverage"]["counts"].items():
        lines.append(f"| {suite} | {count} |")
    lines.extend(["", "## Findings", ""])
    if not report["issues"]:
        lines.append("- No readiness issues found.")
    else:
        for issue in report["issues"]:
            lines.append(
                f"- **{issue['severity'].upper()}** `{issue['code']}`: "
                f"{issue['message']}"
            )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--docstore", type=Path, default=DEFAULT_DOCSTORE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = audit_bundle(args.dataset.resolve(), docstore_path=args.docstore.resolve())
    if args.output:
        output_path = args.output.resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        output_path.with_suffix(".md").write_text(
            _markdown(report),
            encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
