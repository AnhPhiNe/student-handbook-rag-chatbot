"""Run the development smoke cases through the current answer pipeline.

Preliminary route, source and phrase checks help review the answers. They are
not a correctness judge or a hold-out metric. Review results against the case
sources and manual_checks before deciding whether another fix is needed.

    python -m scripts.eval_retrieval_hardening --check-only
    python -m scripts.eval_retrieval_hardening
    python -m scripts.eval_retrieval_hardening --out data/eval/reports/<run>
"""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

from scripts.eval_supplementary_questions import evidence_parent_ids, fold
from src.common.env_loader import load_project_env
from src.evaluation.answers import generate_answers

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data/eval/development/retrieval_hardening_questions.yaml"


def review_checks(case: dict, record: dict) -> dict:
    tasks = (record.get("query_plan") or {}).get("tasks") or []
    if case.get("expected_lookup"):
        route_ok = any(t.get("mode") == "structured" and
                       t.get("lookup_type") == case["expected_lookup"] for t in tasks)
    elif case.get("expected_directory"):
        route_ok = any(t.get("mode") == "structured" and
                       t.get("lookup_type") in {"office", "student_service"} for t in tasks)
    else:
        route_ok = any(t.get("mode") == case.get("expected_mode") for t in tasks)
    answer = fold(record.get("answer") or "")
    missing_facts = [fact for fact in case["must_include"] if not any(
        fold(wording) in answer for wording in (fact if isinstance(fact, list) else [fact])
    )]
    expected_parents = case.get("gold_parents_all") or (
        [case["gold_parent"]] if case.get("gold_parent") else []
    )
    missing_parents = sorted(set(expected_parents) - evidence_parent_ids(record))
    return {
        "id": case["id"], "query": case["query"], "status": record.get("status"),
        "route_ok": route_ok,
        "routes": [t.get("lookup_type") or t.get("mode") for t in tasks],
        "missing_facts": missing_facts, "facts_ok": not missing_facts,
        "missing_parents": missing_parents,
        "retrieved_ok": not missing_parents if expected_parents else None,
        "manual_checks": case.get("manual_checks") or [],
        "answer": record.get("answer") or "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, help="Existing run directory to resume.")
    parser.add_argument("--limit", type=int, help="Run only the first N cases.")
    parser.add_argument("--check-only", action="store_true", help="Validate cases locally; no API calls.")
    args = parser.parse_args()
    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))["cases"]
    if len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Case ids must be unique")
    parents = {p["_id"] for p in json.loads(
        (ROOT / "data/processed/chunks/all_docstore_items.json").read_text(encoding="utf-8")
    )}
    for case in cases:
        if not case.get("query") or not case.get("must_include"):
            raise ValueError(f"Incomplete case: {case['id']}")
        wanted = case.get("gold_parents_all") or (
            [case["gold_parent"]] if case.get("gold_parent") else []
        )
        if not set(wanted) <= parents:
            raise ValueError(f"Missing source parent: {case['id']}")
    if args.check_only:
        print(f"Validated {len(cases)} development cases; no API calls.")
        return
    load_project_env()
    os.environ["STUDENT_RAG_EVAL_TELEMETRY"] = "1"
    from scripts.run_official_answers import _snapshot
    if args.out:
        out = args.out.resolve()
        snapshot = json.loads((out / "run_snapshot.json").read_text(encoding="utf-8"))
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = ROOT / "data/eval/reports" / f"retrieval_hardening_{stamp}"
        out.mkdir(parents=True, exist_ok=False)
        snapshot = {**_snapshot("development_answers", CASES),
                    "independent_holdout": False, "planned_cases": len(cases)}
        (out / "run_snapshot.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(f"Output: {out}", flush=True)
    try:
        run = generate_answers(
            cases, cache_path=out / "answer_cache.json", resume=bool(args.out),
            limit=args.limit, checkpoint_context=snapshot,
            answer_config=snapshot["composer"]["config"],
        )
    except Exception as exc:
        # Do not print configuration, credentials or raw client exception text.
        (out / "failure.json").write_text(
            json.dumps({"error_type": type(exc).__name__, "completed_report": False}), encoding="utf-8"
        )
        raise SystemExit(f"Run stopped ({type(exc).__name__}); no completed report.") from None
    records = {row["id"]: row for row in run["cases"]}
    checked = [review_checks(case, records[case["id"]]) for case in cases if case["id"] in records]
    summary = {"n": len(checked), "independent_holdout": False,
               "manual_review_required": True,
               "generation": run["summary"]}
    for key in ("route_ok", "facts_ok", "retrieved_ok"):
        summary[key] = sum(row[key] is True for row in checked)
    summary["n_with_gold_parent"] = sum(row["retrieved_ok"] is not None for row in checked)
    (out / "answer_generation.json").write_text(
        json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / "review_checks.json").write_text(
        json.dumps({"summary": summary, "cases": checked}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
