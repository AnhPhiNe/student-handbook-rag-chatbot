"""Measure directory matching (services, offices, faculties, programs) on labeled cases.

Runs the runtime lookups (`office_lookup`, `program_lookup`) with the configured
directory selector on the development cases in data/eval/development and on
the planner slots of official_v1. Development data, not a hold-out: use it to
check a selector or catalog change, never official_v3.

    python -m scripts.eval_directory_matching \
        --v1-report data/eval/reports/official_v1_deterministic_<stamp>

Outcomes: correct; wrong (a unit or program outside the gold set, or any
answer where none exists); clarify (asked back where one answer was right);
miss (nothing found although it exists); incomplete (a listed set missing
programs). Asking back is safe; only "wrong" misleads a student.
"""
import argparse
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

from scripts.prepare_official_eval import ROOT

CASES = ROOT / "data/eval/development"
DIRECTORIES = ROOT / "data/processed/directories"
DIRECTORY_LOOKUPS = {
    # lookup_type: (cases file, slot, directory file)
    "student_service": ("service_matching_cases.yaml", "service", "student_service_directory.json"),
    "office": ("office_matching_cases.yaml", "office", "student_office_profiles.json"),
    "faculty": ("faculty_matching_cases.yaml", "faculty", "student_faculty_profiles.json"),
}
PROGRAM_ACTIONS = {"resolve": ("resolve_faculty", "school"), "exists": ("exists", "school"),
                   "list": ("list", "faculty")}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def v1_cases(report: Path, lookup_type: str, slot: str) -> list[dict]:
    """Each official_v1 planner slot value of this lookup, with its case's gold names."""
    gold_field = "program_name" if lookup_type == "program" else "unit_name"
    cases = []
    for case in json.loads((report / "deterministic.json").read_text(encoding="utf-8"))["cases"]:
        gold = set()
        for outcome in case["accepted_outcomes"]:
            for task in outcome.get("required_tasks", []):
                fields = task.get("expected_resolved_fields") or task.get("expected_evidence_fields")
                if task.get("lookup_type") == lookup_type and isinstance(fields, dict) and fields.get(gold_field):
                    gold.add(fields[gold_field])
        for task in (case.get("query_plan") or {}).get("tasks", []):
            value = (task.get("slot_spans") or {}).get(slot) or (task.get("slots") or {}).get(slot)
            if task.get("lookup_type") != lookup_type or not gold or not value:
                continue
            cohort = (task.get("cohorts") or [case["cohort"]])[0]
            for index, item in enumerate(value if isinstance(value, list) else [value]):
                cases.append({"id": f"v1_{case['id'][-3:]}" + (f"_{index}" if isinstance(value, list) else ""),
                              "value": str(item), "expect": "unit" if lookup_type != "program" else "one",
                              "gold": sorted(gold), "cohort": cohort, "action": "resolve"})
    return cases


def directory_outcome(case: dict, result: dict | None) -> tuple[str, list[str]]:
    expect, gold = case["expect"], set(case.get("gold") or [])
    if result is None:
        return ("correct" if expect == "none" else "miss"), []
    if result.get("resolution_status") in {"ambiguous", "unresolved"}:
        units = result.get("candidate_units") or []
        return ("correct" if expect in {"one_of", "none", "clarify"} else "clarify"), units
    units = list(dict.fromkeys(item.get("unit_name") for item in result["result"]))
    if expect in {"none", "clarify"}:
        return "wrong", units
    return ("correct" if units[0] in gold else "wrong"), units


def program_outcome(case: dict, result: dict | None) -> tuple[str, list[str]]:
    expect, gold = case["expect"], set(case.get("gold") or [])
    if result is None:
        return ("correct" if expect == "none" else "miss"), []
    if result.get("needs_clarification"):
        return ("correct" if expect in {"any", "none"} else "clarify"), result.get("candidate_programs") or []
    picked = sorted({item["program_name"] for item in result.get("result") or []})
    if not picked:
        return ("correct" if expect == "none" else "miss"), picked
    if expect == "none" or not set(picked) <= gold:
        return "wrong", picked
    if expect in {"one", "all"} and set(picked) != gold:
        return "incomplete", picked
    return "correct", picked


def run_directory(lookup_type: str, selector, report: Path | None, cases_path: Path | None = None) -> list[dict]:
    from src.retrieval.core.office_lookup import office_lookup

    cases_file, slot, directory_file = DIRECTORY_LOOKUPS[lookup_type]
    spec = _load(cases_path or CASES / cases_file)
    cases = [{"id": c["id"], "value": c[slot], "expect": c["expect"], "gold": c.get("units", []),
              "cohort": spec["cohort"]} for c in spec["cases"]]
    if report:
        cases += v1_cases(report, lookup_type, slot)
    directory = json.loads((DIRECTORIES / directory_file).read_text(encoding="utf-8"))
    rows = []
    for case in cases:
        started = time.perf_counter()
        result = office_lookup(case["value"], directory, candidate_text=case["value"],
                               lookup_type=lookup_type, cohort=case["cohort"], selector=selector)
        outcome, picked = directory_outcome(case, result)
        rows.append({**case, "outcome": outcome, "picked": picked,
                     "ms": round((time.perf_counter() - started) * 1000),
                     "selection": (result or {}).get("selection")})
    return rows


def run_programs(selector, report: Path | None) -> list[dict]:
    from src.common.cohort import is_cohort_applicable, normalize_cohort
    from src.retrieval.core.program_lookup import program_lookup

    spec = _load(CASES / "program_matching_cases.yaml")
    directory = json.loads((DIRECTORIES / "program_directory.json").read_text(encoding="utf-8"))
    cohort_programs = [r for r in directory if is_cohort_applicable(r, normalize_cohort(spec["cohort"]))]
    cases = []
    for c in spec["cases"]:
        # A case naming a faculty expects every program of that faculty.
        gold = c.get("programs") or [r["program_name"] for r in cohort_programs
                                     if c.get("faculty") and r.get("faculty_name") == c["faculty"]]
        cases.append({"id": c["id"], "value": c["text"], "expect": c["expect"], "gold": sorted(set(gold)),
                      "cohort": spec["cohort"], "action": c["action"]})
    if report:
        cases += v1_cases(report, "program", "program_or_faculty")
    rows = []
    for case in cases:
        action, scope = PROGRAM_ACTIONS[case["action"]]
        started = time.perf_counter()
        result = program_lookup(directory, candidate_text=case["value"], cohort=case["cohort"],
                                action=action, scope=scope, selector=selector)
        outcome, picked = program_outcome(case, result)
        rows.append({**case, "outcome": outcome, "picked": picked,
                     "ms": round((time.perf_counter() - started) * 1000),
                     "selection": (result or {}).get("selection")})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1-report", help="official_v1 deterministic report whose planner slots to add.")
    parser.add_argument("--config", default="configs/answer_generation.yaml")
    parser.add_argument("--service-cases", help="Another student-service cases file, e.g. "
                        "data/eval/development/service_everyday_cases.yaml.")
    parser.add_argument("--only", choices=(*DIRECTORY_LOOKUPS, "program"), help="Run one lookup type only.")
    args = parser.parse_args()

    from src.common.env_loader import load_project_env
    from src.generation.answer_pipeline import create_directory_selector
    from src.retrieval.core.directory_selector import SELECTOR_PROMPT_VERSION

    load_project_env()
    config = _load(ROOT / args.config)["directory_selector"]
    selector = create_directory_selector(config)
    report = ROOT / args.v1_report if args.v1_report else None
    service_cases = ROOT / args.service_cases if args.service_cases else None
    results = {
        lookup_type: run_directory(lookup_type, selector, report,
                                   service_cases if lookup_type == "student_service" else None)
        for lookup_type in DIRECTORY_LOOKUPS if args.only in (None, lookup_type)
    }
    if args.only in (None, "program"):
        results["program"] = run_programs(selector, report)

    summary = {}
    for lookup_type, rows in results.items():
        called = sorted(r["ms"] for r in rows if any(str(s.get("method")).startswith("llm_selector") for s in r["selection"] or []))
        summary[lookup_type] = {"n": len(rows), **Counter(r["outcome"] for r in rows),
                                "llm_calls": len(called), "median_ms": called[len(called) // 2] if called else 0}
        for row in rows:
            if row["outcome"] != "correct":
                print(f"{lookup_type:15s} {row['id']:9s} {row['outcome']:10s} {row['value']!r} -> {row['picked']}")
    out = {"created_at": datetime.now(timezone.utc).isoformat(), "prompt_version": SELECTOR_PROMPT_VERSION,
           "selector": config, "v1_report": args.v1_report, "service_cases": args.service_cases,
           "summary": summary, "cases": results}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = ROOT / "data/eval/reports" / f"directory_matching_{stamp}.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Output: {path}")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
