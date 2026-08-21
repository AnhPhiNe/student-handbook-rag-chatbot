"""Replay frozen dev model outputs after evaluator-only or additive-gold changes.

This tool never calls a provider.  It fails closed unless runtime inputs and all
runtime artifact hashes are unchanged from the source report.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import evaluate_single_cohort_v2 as evaluator  # noqa: E402
from src.evaluation.single_cohort_v2 import (  # noqa: E402
    assess_plan,
    evaluate_development_gates,
    evaluate_release_gates,
    execution_plan_match,
    exact_plan_match,
    failure_taxonomy,
    semantic_plan_match,
    validate_bundle,
)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=ROOT, text=True, encoding="utf-8"
    ).strip()


def _runtime_case_projection(case: Mapping[str, Any]) -> dict[str, Any]:
    """Fields sent to Planner/runtime; gold labels are deliberately excluded."""

    return {
        "id": case.get("id"),
        "category": case.get("category"),
        "query": case.get("query"),
        "selected_cohort": case.get("selected_cohort"),
        "chat_history": case.get("chat_history") or [],
        "fault_injection": case.get("fault_injection"),
    }


def _allowed_replay_change(path: str) -> bool:
    return bool(
        path.startswith("data/eval/single_cohort_v2/")
        or path == "scripts/evaluate_single_cohort_v2.py"
        or path == "scripts/replay_single_cohort_v2_dev.py"
        or path.startswith("tests/")
    )


def _validate_source(
    source: Mapping[str, Any],
    *,
    current_cases: list[dict[str, Any]],
) -> dict[str, Any]:
    source_commit = str(source.get("commit") or "").strip()
    if not source_commit:
        raise ValueError("Replay source has no commit")
    subprocess.check_call(
        ["git", "merge-base", "--is-ancestor", source_commit, "HEAD"],
        cwd=ROOT,
    )
    changed_paths = [
        value
        for value in _git("diff", "--name-only", f"{source_commit}..HEAD").splitlines()
        if value
    ]
    unsafe = [path for path in changed_paths if not _allowed_replay_change(path)]
    if unsafe:
        raise ValueError(f"Replay crosses runtime changes: {unsafe}")

    current_fingerprint = evaluator._artifact_fingerprint()
    source_fingerprint = source.get("artifact_fingerprint") or {}
    runtime_keys = set(current_fingerprint) - {"implementation_tree"}
    mismatched = sorted(
        key
        for key in runtime_keys
        if source_fingerprint.get(key) != current_fingerprint.get(key)
    )
    if mismatched:
        raise ValueError(f"Replay runtime artifact mismatch: {mismatched}")

    old_payload = _git(
        "show", f"{source_commit}:data/eval/single_cohort_v2/dev.json"
    )
    old_cases = json.loads(old_payload)
    old_inputs = [_runtime_case_projection(case) for case in old_cases]
    current_inputs = [_runtime_case_projection(case) for case in current_cases]
    if old_inputs != current_inputs:
        raise ValueError("Replay source and current dev runtime inputs differ")

    if (source.get("models") or {}).get("planner") != evaluator.PLANNER_MODEL:
        raise ValueError("Replay source Planner model differs")
    if (source.get("models") or {}).get("answer") != evaluator.ANSWER_MODEL:
        raise ValueError("Replay source answer model differs")
    if source.get("prompt_version") != evaluator.ROUTER_PROMPT_VERSION:
        raise ValueError("Replay source Planner prompt differs")
    answers = source.get("answers") or []
    if any(str(row.get("id") or "").startswith("hidden-") for row in answers):
        raise ValueError("Dev replay source must not contain hidden rows")
    return {
        "source_commit": source_commit,
        "changed_paths": changed_paths,
        "runtime_artifact_keys_verified": sorted(runtime_keys),
    }


def _result_from_answer(row: Mapping[str, Any]) -> dict[str, Any]:
    citations = copy.deepcopy(list(row.get("citations") or []))
    return {
        "structured_result": copy.deepcopy(row.get("structured_result")),
        "retrieved_items": copy.deepcopy(list(row.get("retrieved_items") or [])),
        "citations": citations,
        "citations_used": citations,
        "request_results": copy.deepcopy(list(row.get("request_results") or [])),
        "router_decision": copy.deepcopy(dict(row.get("router_decision") or {})),
        "effective_query": row.get("effective_query"),
    }


def _reevaluate_execution(
    case: Mapping[str, Any],
    answer_row: Mapping[str, Any],
    source_execution_row: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    expected = case["expected"]
    result = _result_from_answer(answer_row)
    actual_plan = evaluator._plan_from_decision(result["router_decision"])
    plan_correct = execution_plan_match(expected, actual_plan)
    expected_requests = expected.get("atomic_requests") or []
    actual_statuses = {
        item.get("request_id"): item.get("status")
        for item in result.get("request_results") or []
    }
    status_match = all(
        actual_statuses.get(request["request_id"]) == request["expected_status"]
        for request in expected_requests
    )
    actual_ok = evaluator._actual_ok_requests(expected_requests, actual_statuses)
    structured_ok = [
        request for request in actual_ok if request["request_kind"] == "structured"
    ]
    rag_ok = [request for request in actual_ok if request["request_kind"] == "rag"]
    rag_gold = evaluator._expected_rag_gold_requests(expected_requests)
    citations = result.get("citations") or []
    retrieved_items = result.get("retrieved_items") or []
    if rag_gold and not retrieved_items:
        # Answer artifacts intentionally omit the full retrieval candidate pool.
        # Preserve Hit@5 from the source execution artifact rather than treating
        # missing replay inputs as retrieval misses. Runtime inputs/artifact
        # fingerprints are validated before this path is reachable.
        source_rag_hits = list((source_execution_row or {}).get("rag_hits") or [])
        if len(source_rag_hits) != len(rag_gold) or any(
            not isinstance(value, bool) for value in source_rag_hits
        ):
            raise ValueError(
                f"Replay source lacks bound RAG Hit@5 data for {case['id']}"
            )
        rag_hits = source_rag_hits
    else:
        rag_hits = [evaluator._rag_hit_at_5(result, request) for request in rag_gold]
    structured_bindings = [
        evaluator._structured_source_bound(result, request)
        for request in structured_ok
    ]
    structured_results = [
        evaluator._structured_result_matches(result, request)
        for request in structured_ok
    ]
    citation_bindings = [
        evaluator._citation_bound(citations, request)
        for request in [*structured_ok, *rag_ok]
    ]
    request_ids = {request["request_id"] for request in expected_requests}
    citation_isolated = evaluator._citation_isolated(result, request_ids)
    structured_requests = [
        request
        for request in expected_requests
        if request["request_kind"] == "structured"
    ]
    structured_fallbacks = sum(
        bool(evaluator._request_items(result, request["request_id"]))
        for request in structured_requests
    )
    semantic_executable = bool(
        plan_correct
        and status_match
        and all(rag_hits)
        and all(structured_bindings)
        and all(structured_results)
        and all(citation_bindings)
        and citation_isolated
        and structured_fallbacks == 0
    )
    return {
        "id": case["id"],
        "category": case.get("category"),
        "plan_correct": plan_correct,
        "status_match": status_match,
        "rag_hits": rag_hits if plan_correct else [],
        "structured_bindings": structured_bindings,
        "structured_result_matches": structured_results,
        "citation_bindings": citation_bindings,
        "citation_isolated": citation_isolated,
        "structured_to_rag_fallbacks": structured_fallbacks,
        "semantic_executable": semantic_executable,
        "provider_failure": bool(answer_row.get("provider_failure")),
        "failure_type": "pass" if semantic_executable else "executor",
    }


def _reevaluate_answer(
    case: Mapping[str, Any], answer_row: Mapping[str, Any]
) -> dict[str, Any]:
    row = copy.deepcopy(dict(answer_row))
    expected = case["expected"]
    request_results = row.get("request_results") or []
    statuses = {
        item.get("request_id"): item.get("status") for item in request_results
    }
    actual_ok = evaluator._actual_ok_requests(
        expected.get("atomic_requests") or [], statuses
    )
    citations = row.get("citations") or []
    composition = row.get("answer_composition") or {}
    request_ids = {
        request["request_id"] for request in expected.get("atomic_requests") or []
    }
    result = _result_from_answer(row)
    execution_bound = execution_plan_match(
        expected, evaluator._plan_from_decision(row.get("router_decision") or {})
    )
    composition_bound = bool(
        not actual_ok or evaluator._final_composition_contract_passed(composition)
    )
    citation_bound = all(
        evaluator._citation_bound(citations, request) for request in actual_ok
    )
    row.update(
        {
            "exact_plan_bound": exact_plan_match(
                expected,
                evaluator._plan_from_decision(row.get("router_decision") or {}),
            ),
            "semantic_plan_bound": semantic_plan_match(
                expected,
                evaluator._plan_from_decision(row.get("router_decision") or {}),
            ),
            "execution_plan_bound": execution_bound,
            "answer_contract_bound": bool(
                execution_bound
                and citation_bound
                and evaluator._citation_isolated(result, request_ids)
                and composition_bound
            ),
        }
    )
    if not row.get("provider_failure"):
        row["failure_type"] = "answer_contract" if not composition_bound else "pass"
    return row


def _refresh_planner_rows(
    source: Mapping[str, Any], cases: Mapping[str, Mapping[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    planner_rows, _, _ = evaluator._reuse_answer_report_evaluation(source)
    refreshed: dict[str, list[dict[str, Any]]] = {}
    for suite, rows in planner_rows.items():
        output_rows: list[dict[str, Any]] = []
        for source_row in rows:
            row = copy.deepcopy(source_row)
            case = cases.get(str(row.get("id")))
            if case is None or row.get("planner_skipped") or row.get("provider_failure"):
                output_rows.append(row)
                continue
            expected = case["expected"]
            actual = row.get("actual") or {}
            assessment = assess_plan(expected, actual)
            row.update(
                {
                    "passed": assessment.semantic_match,
                    "exact_passed": assessment.exact_match,
                    "semantic_passed": assessment.semantic_match,
                    "execution_eligible": execution_plan_match(expected, actual),
                    "mismatch_reasons": list(assessment.mismatch_reasons),
                    "critical_failure": assessment.critical_failure,
                    "failure_type": (
                        "pass"
                        if assessment.exact_match
                        else "representation"
                        if assessment.semantic_match
                        else "planner"
                    ),
                    "expected": expected,
                }
            )
            output_rows.append(row)
        refreshed[suite] = output_rows
    return refreshed


def _replay_execution_rows(
    cases: Mapping[str, Mapping[str, Any]],
    answer_rows: list[dict[str, Any]],
    source_execution_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Rebind answer-backed rows and retain only deterministic fault rows."""

    answer_by_id = {str(row["id"]): row for row in answer_rows}
    source_execution_by_id = {
        str(row["id"]): row for row in source_execution_rows
    }
    unknown_answers = sorted(set(answer_by_id) - set(source_execution_by_id))
    if unknown_answers:
        raise ValueError(f"Replay answers lack source execution rows: {unknown_answers}")

    output: list[dict[str, Any]] = []
    for source_row in source_execution_rows:
        case_id = str(source_row["id"])
        answer_row = answer_by_id.get(case_id)
        if answer_row is not None:
            output.append(
                _reevaluate_execution(
                    cases[case_id],
                    answer_row,
                    source_row,
                )
            )
            continue
        if not (
            source_row.get("skipped")
            and source_row.get("failure_type") == "deterministic_fault_suite"
            and source_row.get("semantic_executable") is None
        ):
            raise ValueError(f"Replay source execution row has no answer: {case_id}")
        output.append(copy.deepcopy(source_row))
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--quality-report", type=Path, required=True)
    parser.add_argument("--parity-report", type=Path, required=True)
    parser.add_argument("--conformance-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if _git("status", "--porcelain"):
        parser.error("Dev replay requires a clean worktree")
    source = _load(args.source_report)
    validation = validate_bundle(require_gold_complete=True)
    if not validation.valid:
        parser.error("Current single-cohort bundle is invalid")
    current_cases = _load(evaluator.BUNDLE_DIR / "dev.json")
    case_by_id = {str(case["id"]): case for case in current_cases}
    try:
        provenance = _validate_source(source, current_cases=current_cases)
    except (ValueError, subprocess.CalledProcessError) as exc:
        parser.error(str(exc))

    quality_passed, quality_report = evaluator._verified_check_report(
        args.quality_report,
        required_checks=("pytest", "ruff", "frontend_lint", "frontend_build"),
    )
    parity_passed, parity_report = evaluator._verified_check_report(
        args.parity_report,
        required_checks=("sync_stream", "sync_cache", "stream_cache", "debug_metadata"),
        deterministic=True,
    )
    conformance_passed, conformance_report = evaluator._verified_check_report(
        args.conformance_report,
        required_checks=(
            "no_match",
            "invalid",
            "unresolved",
            "adapter_exception",
            "plan_tampering",
            "structured_to_rag_fallback_zero",
            "citation_isolation",
            "no_retrieval_on_non_execute",
        ),
        deterministic=True,
    )
    if not all((quality_passed, parity_passed, conformance_passed)):
        parser.error("Replay requires current passing preflight reports")

    planner_rows = _refresh_planner_rows(source, case_by_id)
    _, source_execution_rows, source_answers = evaluator._reuse_answer_report_evaluation(
        source
    )
    answer_rows = [
        _reevaluate_answer(case_by_id[str(row["id"])], row)
        for row in source_answers
    ]
    execution_rows = _replay_execution_rows(
        case_by_id,
        answer_rows,
        source_execution_rows,
    )
    metrics = evaluator._metrics(
        validation.valid,
        planner_rows,
        execution_rows,
        answer_rows,
        [],
        quality_checks_passed=quality_passed,
        parity_passed=parity_passed,
        conformance_passed=conformance_passed,
    )
    development_gates = evaluate_development_gates(metrics)
    release_gates = evaluate_release_gates(metrics)
    manifest = _load(evaluator.BUNDLE_DIR / "manifest.json")
    report = copy.deepcopy(dict(source))
    report.update(
        {
            "timestamp": datetime.now(UTC).isoformat(),
            "commit": evaluator._commit(),
            "schema_version": manifest.get("schema_version"),
            "dataset_hashes": validation.hashes,
            "artifact_fingerprint": evaluator._artifact_fingerprint(),
            "evaluation_scope": {
                **dict(source.get("evaluation_scope") or {}),
                "replayed": True,
            },
            "replay_provenance": {
                **provenance,
                "source_report": str(args.source_report.resolve()),
                "source_report_sha256": _sha(args.source_report),
                "replayed_at": datetime.now(UTC).isoformat(),
                "provider_calls": 0,
            },
            "planner": {
                suite: evaluator._planner_section(rows)
                for suite, rows in planner_rows.items()
            },
            "executor_retrieval": {
                "failure_taxonomy": failure_taxonomy(execution_rows),
                "rows": execution_rows,
            },
            "answers": answer_rows,
            "answers_report_hash": None,
            "answer_judgments": [],
            "quality_report": quality_report,
            "parity_report": parity_report,
            "conformance_report": conformance_report,
            "legacy_compatibility_report": None,
            "metrics": metrics,
            "development_gates": {
                "passed": development_gates.passed,
                "checks": development_gates.checks,
                "missing_metrics": development_gates.missing_metrics,
            },
            "gates": {
                "passed": release_gates.passed,
                "checks": release_gates.checks,
                "missing_metrics": release_gates.missing_metrics,
            },
            "development_ready": development_gates.passed,
            "release_ready": release_gates.passed,
        }
    )
    evaluator._write_json_atomic(args.output, report)
    print(
        json.dumps(
            {
                "commit": report["commit"],
                "source_commit": provenance["source_commit"],
                "provider_calls": 0,
                "metrics": metrics,
                "development_gates": report["development_gates"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
