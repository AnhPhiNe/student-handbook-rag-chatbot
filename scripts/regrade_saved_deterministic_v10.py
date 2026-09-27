"""Re-score saved deterministic envelopes with V10 gold; never call a model.

Default: reuse evidence to isolate evaluator changes. --replay-structured:
execute saved structured plans offline with current catalogs, without embedding,
retrieval APIs or a planner/composer. The source report is always read-only.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from scripts.run_official_deterministic import select_case_ids
from src.evaluation.deterministic import evaluate_deterministic


ROOT = Path(__file__).resolve().parents[1]
V10_CASES = ROOT / "data/eval/official_v1/deterministic_tool_cases_v10.json"


class SavedOperationalFailure(RuntimeError):
    """Represent a saved runtime failure without attempting execution."""


def _structured_executor():
    from src.generation.plan_executor import PlanExecutor, StructuredCatalogs
    from src.retrieval.core.slang_normalizer import SlangNormalizer

    paths = {
        "office_directory": ROOT / "data/processed/directories/student_office_profiles.json",
        "student_service_directory": ROOT / "data/processed/directories/student_service_directory.json",
        "student_faculty_profiles": ROOT / "data/processed/directories/student_faculty_profiles.json",
        "program_directory": ROOT / "data/processed/directories/program_directory.json",
        "structured_tables_registry": ROOT / "data/processed/tables/structured_tables_registry.json",
    }
    catalogs = StructuredCatalogs(
        formula_rules=[], **{name: json.loads(path.read_text(encoding="utf-8"))
                             for name, path in paths.items()},
    )
    executor = PlanExecutor(
        router=None, slang_normalizer=SlangNormalizer(), catalogs=catalogs,
        parent_sources_by_id={}, top_k=5, public_source_limit=10, directory_selector=None,
        graph=SimpleNamespace(expand_context=lambda *_args, **_kwargs: []),
    )
    paths["plan_executor"] = ROOT / "src/generation/plan_executor.py"
    return executor, {path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                      for path in paths.values()}


def regrade(source_path: Path, output_path: Path, *, replay_structured: bool = False) -> dict:
    if output_path.exists() or output_path.resolve() == source_path.resolve():
        raise FileExistsError(output_path)
    source_bytes = source_path.read_bytes()
    saved = json.loads(source_bytes)
    cases_bytes = V10_CASES.read_bytes()
    old_rows = saved.get("cases") or []
    ids = [row.get("id") for row in old_rows]
    cases = select_case_ids(json.loads(cases_bytes), ids)
    if ids != [case["id"] for case in cases]:
        raise ValueError("Saved cases must follow canonical V1 order")
    for case, old in zip(cases, old_rows, strict=True):
        if any(old.get(key) != case.get(key) for key in ("query", "cohort", "history")):
            raise ValueError(f"Saved input differs from V10 case: {case['id']}")
    replay_hashes = {}
    executor = None
    if replay_structured:
        for old in old_rows:
            plan = old.get("query_plan") or {}
            tasks = plan.get("tasks") or []
            if (old.get("error_type") or old.get("planner_error_type") or not tasks
                    or any(task.get("mode") != "structured"
                           or task.get("lookup_type") == "formula" for task in tasks)):
                raise ValueError("Offline runtime replay requires successful, non-formula structured plans")
        executor, replay_hashes = _structured_executor()

    class SavedPipeline:
        def __init__(self):
            self.position = 0

        def _run_retrieval(self, query, **_kwargs):
            old = old_rows[self.position]
            self.position += 1
            if query != old["query"]:
                raise ValueError("Saved query differs from V10 case")
            if old.get("error_type"):
                error = SavedOperationalFailure(old["error_type"])
                error.planner_diagnostics = old.get("planner_diagnostics")
                error.planner_latency_ms = old.get("planner_latency_ms")
                raise error
            if executor is not None:
                # Do not call run(): planning is not being repeated. Reuse the
                # exact saved plan; recompute only structured evidence/citations.
                plan = copy.deepcopy(old["query_plan"])
                executions = [executor.execute_task(
                    task=task, task_index=index, default_cohort=old.get("cohort"),
                ) for index, task in enumerate(plan["tasks"])]
                return executor.aggregate_results(
                    base_result={"query": query, "raw_query": query,
                                 "query_plan": plan, "cohort": old.get("cohort")},
                    plan=plan, task_executions=executions,
                )
            return old

    result = evaluate_deterministic(
        cases, evaluation_contract="query-plan-grounded-outcome-v10",
        pipeline_factory=SavedPipeline,
    )
    changes = []
    for old, new in zip(old_rows, result["cases"], strict=True):
        if replay_structured:
            new["source_observed_latency_ms"] = old.get("latency_ms")
            new["source_planner_latency_ms"] = old.get("planner_latency_ms")
        else:
            new["latency_ms"] = old.get("latency_ms")
        if old.get("planner_diagnostics") is not None:
            new["planner_diagnostics"] = old["planner_diagnostics"]
        if old.get("error_type"):
            # Restore the observed error identity/stage. The replay's sentinel
            # is not a newly observed production failure.
            for field in ("error", "error_type", "error_stage", "error_diagnostic",
                          "execution_error_type", "evaluation_error_type", "traceback"):
                if field in old:
                    new[field] = old[field]
        if bool(old.get("passed")) != bool(new.get("passed")):
            changes.append({"id": old["id"], "source_passed": bool(old.get("passed")),
                            "regraded_passed": bool(new.get("passed")),
                            "matched_outcome": new.get("matched_outcome")})
    result["offline_regrade"] = {
        "source_report": str(source_path),
        "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        "v10_cases_sha256": hashlib.sha256(cases_bytes).hexdigest(),
        "source_contract": saved.get("evaluation_contract"),
        "source_evaluator_revision": saved.get("evaluator_revision", "legacy-unversioned"),
        "source_passed": sum(bool(row.get("passed")) for row in old_rows),
        "regraded_passed": result["summary"]["passed"],
        "mode": "saved_plan_structured_replay" if replay_structured else "same_saved_outputs",
        "source_summary": saved.get("summary"),
        "selected_case_ids": ids,
        "runtime_replay_hashes": replay_hashes,
        "changed_cases": changes,
        "interpretation": (
            "Current structured runtime with saved plans; no new inference. Embedding, graph-related "
            "references and parent citation enrichment disabled. Operational/timing metrics describe "
            "offline execution, not new planner requests or production performance."
            if replay_structured else
            "Evaluator-only regrade of unchanged saved evidence/plans; timings are historical, not new inference."
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Saved V1 deterministic.json, full run or explicit subset")
    parser.add_argument("--output", type=Path, help="New report path; never overwrite")
    parser.add_argument("--replay-structured", action="store_true",
                        help="Execute saved non-formula structured plans offline; no models or retrieval APIs.")
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    mode = "structured_replay" if args.replay_structured else "regraded_v10_r2"
    output = args.output or ROOT / "data/eval/reports" / f"official_v1_{mode}_{stamp}" / "deterministic.json"
    result = regrade(args.source, output, replay_structured=args.replay_structured)
    print(json.dumps({"output": str(output), "summary": result["summary"],
                      "offline_regrade": result["offline_regrade"]},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
