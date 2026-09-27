"""Eight pre-authored contact-intent probes; no composer, judge or retrieval.

Not answer gold and not an independent holdout. Inference requires --run and
owner approval for a new trial. --regrade reuses saved plans without inference.
"""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.retrieval.core.ai_router import AIRouter, planner_diagnostics_scope
from src.retrieval.core.structured_routing import load_lookup_registry

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data/eval/development/prompt_v47_contact_intent_cases.yaml"
CONFIG = ROOT / "configs/experiments/ai_router_openai_luna_medium.yaml"


def grade_contact(case, plan):
    """Grade target/field selection only, not contact values or execution."""
    tasks = plan.get("tasks") or []
    expected = case["expected"]
    failures = []
    if plan.get("planner_fallback") or plan.get("planner_error_type"):
        failures.append("planner_error")
    if len(tasks) != 1:
        return failures + ["task_count"]
    task = tasks[0]
    for name, value in {"mode": "structured", "lookup_type": expected["lookup_type"],
                        "cohorts": [case["cohort"]]}.items():
        if task.get(name) != value:
            failures.append(name)
    accepted_intents = case.get("accepted_intents", [expected["intent"]])
    spec = load_lookup_registry()["tools"][expected["lookup_type"]]
    required = spec["required_slots"]
    if (expected["intent"] not in accepted_intents
            or any(intent not in spec["intents"]
                   or required[intent] != required[expected["intent"]]
                   for intent in accepted_intents)):
        raise ValueError("Accepted probe intents must share the declared tool input contract")
    if task.get("intent") not in accepted_intents:
        failures.append("intent")
    if task.get("validation_errors") or plan.get("out_of_domain"):
        failures.append("validation_or_domain")
    wanted = expected["slots"]["requested_field"]
    actual = (task.get("slots") or {}).get("requested_field")
    wanted = set(wanted if isinstance(wanted, list) else [wanted])
    actual = set(actual if isinstance(actual, list) else [actual])
    # The shared prompt explicitly permits all for multiple contact fields.
    if actual != wanted and not (len(wanted) > 1 and actual == {"all"}):
        failures.append("requested_field")
    return failures


def regrade_contact_report(source, output):
    """Record a separate rubric-v2 evaluation, retaining original judgments."""
    source = Path(source).resolve()
    content = source.read_bytes()
    saved = json.loads(content)
    authored = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    cases = {case["id"]: case for case in authored["cases"]}
    rows = []
    seen = set()
    for row in saved["rows"]:
        case = cases[row["id"]]
        if (row["id"] in seen or row["query"] != case["query"]
                or row["expected"] != case["expected"]):
            raise ValueError("Saved probe identity/expectation does not match authoring")
        seen.add(row["id"])
        errors = grade_contact(case, row["plan"])
        rows.append({"id": row["id"], "original_passed": row["passed"],
                     "original_failures": row["failures"], "passed": not errors,
                     "failures": errors, "runtime_error": row["runtime_error"]})
    report = {"scope": saved["scope"], "rubric_version": authored["rubric_version"],
              "inference_calls": 0, "independent_holdout": False,
              "source_report": str(source), "source_sha256": hashlib.sha256(content).hexdigest(),
              "evaluation_hashes": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in (CASES, Path(__file__), ROOT / "configs/structured_lookup_registry.yaml")},
              "requested_n": saved["requested_n"], "n": len(rows),
              "not_run_n": saved["requested_n"] - len(rows),
              "original_passed": sum(row["original_passed"] for row in rows),
              "passed": sum(row["passed"] for row in rows), "rows": rows,
              "interpretation": "Rubric change only; saved runtime/model outputs are unchanged."}
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--run", action="store_true")
    mode.add_argument("--regrade", type=Path)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--output", type=Path, help="New directory for offline regrading")
    args = parser.parse_args()
    if args.regrade:
        output = args.output or ROOT / "data/eval/reports" / (
            "luna_contact_rubric_v2_offline_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
        report = regrade_contact_report(args.regrade, output)
        print(f"Output: {output}\nSaved plans: {report['original_passed']}/{report['n']} -> {report['passed']}/{report['n']}; no inference.")
        return
    if args.output:
        parser.error("--output is only supported with --regrade")
    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))["cases"]
    assert len(cases) == 8
    if not args.run:
        print("Prepared 8 contact-intent probes; no inference.")
        return
    router = AIRouter.from_config(args.config)
    assert (router.provider, router.model_name, router._resolved_reasoning_effort(),
            router.cache, router.max_retries,
            router.request_timeout_seconds, router.max_output_tokens) == (
        "openai", "gpt-6-luna", "medium", None, 1, 20, 8192)
    assert router._resolved_response_format() in {"json_object", "json_schema"}
    files = [*ROOT.glob("src/**/*.py"), *ROOT.glob("configs/**/*.yaml"), CASES, Path(__file__)]
    hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    output = ROOT / "data/eval/reports" / ("luna_v49_medium_contact_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output.mkdir(parents=True, exist_ok=False)
    report = {"scope": "contact_intent_only_not_answer_or_execution_accuracy", "requested_n": 8,
              "rubric_version": yaml.safe_load(CASES.read_text(encoding="utf-8"))["rubric_version"],
              "independent_holdout": False, "pre_run_hashes": hashes, "rows": [],
              "planner": {"provider": router.provider, "model": router.model_name,
                          "reasoning_effort": router._resolved_reasoning_effort(),
                          "response_format": router._plan_response_format_payload()}}
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Output: {output}", flush=True)
    failures_in_a_row = 0
    for case in cases:
        started = time.perf_counter()
        try:
            with planner_diagnostics_scope(True):
                plan = router.plan(case["query"], cohort=case["cohort"])
            # Do not store provider exception messages (may contain private data).
            plan.pop("planner_error", None)
            errors = grade_contact(case, plan)
            runtime_error = bool(plan.get("planner_error_type") or plan.get("planner_fallback"))
        except Exception as exc:
            plan = {"planner_error_type": AIRouter._classify_error(exc),
                    "planner_diagnostics": getattr(exc, "planner_diagnostics", None)}
            errors, runtime_error = ["planner_error"], True
        row = {"id": case["id"], "query": case["query"], "expected": case["expected"],
               "plan": plan, "passed": not errors, "failures": errors,
               "runtime_error": runtime_error, "planner_latency_ms": (time.perf_counter()-started)*1000}
        report["rows"].append(row)
        failures_in_a_row = failures_in_a_row + 1 if runtime_error else 0
        report.update(n=len(report["rows"]), not_run_n=8-len(report["rows"]),
                      passed=sum(r["passed"] for r in report["rows"]))
        report["post_run_hashes_match"] = all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h for p, h in hashes.items())
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{report['n']}/8 {case['id']}: {'pass' if row['passed'] else errors}", flush=True)
        if failures_in_a_row >= 3:
            break


if __name__ == "__main__":
    main()
