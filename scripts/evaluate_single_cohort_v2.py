"""Four-layer single-cohort-v2 evaluator and release-gate report."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.single_cohort_v2 import (  # noqa: E402
    BUNDLE_DIR,
    evaluate_release_gates,
    exact_plan_match,
    failure_taxonomy,
    validate_bundle,
)
from src.generation.answer_pipeline import AnswerPipeline  # noqa: E402
from src.retrieval.core.ai_router import AIRouter  # noqa: E402
from src.retrieval.core.structured_routing import bind_effective_cohort  # noqa: E402


PLANNER_MODEL = "qwen/qwen3.6-27b"
ANSWER_MODEL = "gemini-3.1-flash-lite"


def _commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _file_hash(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _load_cases(suite: str) -> list[dict[str, Any]]:
    return json.loads((BUNDLE_DIR / f"{suite}.json").read_text(encoding="utf-8"))


def _effective_query(case: Mapping[str, Any], decision: Mapping[str, Any]) -> str:
    if decision.get("context_mode") == "follow_up":
        return str(decision.get("standalone_query") or decision.get("normalized_query") or case["query"])
    return str(decision.get("normalized_query") or case["query"])


def _bind_plan(case: Mapping[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    return bind_effective_cohort(
        decision,
        raw_query=str(case["query"]),
        effective_query=_effective_query(case, decision),
        selected_cohort=case.get("selected_cohort"),
    )


def _plan_from_decision(decision: Mapping[str, Any]) -> dict[str, Any]:
    requests = []
    for index, request in enumerate(decision.get("lookup_requests") or [], 1):
        if not isinstance(request, Mapping):
            continue
        requests.append(
            {
                "request_id": f"r{index}",
                "request_kind": request.get("request_kind"),
                "tool_name": request.get("tool_name") or request.get("lookup_type"),
                "intent": request.get("intent"),
                "query_span": request.get("query_span"),
                "slots": request.get("slots") or {},
                "cohort_refs": request.get("cohort_refs") or [],
            }
        )
    return {
        "outcome": decision.get("outcome"),
        "context_mode": decision.get("context_mode"),
        "effective_cohort": decision.get("cohort"),
        "effective_cohort_source": decision.get("effective_cohort_source"),
        "atomic_requests": requests,
    }


def run_live_planner(
    cases: Iterable[dict[str, Any]], router: AIRouter | None = None
) -> list[dict[str, Any]]:
    active_router = router or AIRouter.from_config()
    if active_router.model_name != PLANNER_MODEL:
        raise RuntimeError(
            f"Planner model must be {PLANNER_MODEL}, got {active_router.model_name}"
        )
    rows: list[dict[str, Any]] = []
    for case in cases:
        try:
            decision = active_router.route(
                case["query"],
                chat_history=case.get("chat_history") or [],
                cohort=case.get("selected_cohort"),
            )
            bound = _bind_plan(case, decision)
            actual = _plan_from_decision(bound)
            matched = exact_plan_match(case["expected"], actual)
            rows.append(
                {
                    "id": case["id"],
                    "passed": matched,
                    "failure_type": "pass" if matched else "planner",
                    "expected": case["expected"],
                    "actual": actual,
                    "provider_failure": False,
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "id": case["id"],
                    "passed": False,
                    "failure_type": "provider",
                    "provider_failure": True,
                    "error_type": type(exc).__name__,
                }
            )
    return rows


def _request_items(result: Mapping[str, Any], request_id: str) -> list[dict[str, Any]]:
    return [
        item
        for item in result.get("retrieved_items") or []
        if item.get("request_id") == request_id
        or (item.get("metadata") or {}).get("request_id") == request_id
    ]


def _item_text(item: Mapping[str, Any]) -> str:
    metadata = item.get("metadata") or {}
    return " ".join(
        str(value or "")
        for value in (
            item.get("content"), item.get("text"), metadata.get("content"),
            metadata.get("title"), metadata.get("section_title"),
        )
    ).casefold()


def _rag_hit_at_5(result: Mapping[str, Any], request: Mapping[str, Any]) -> bool:
    evidence = request.get("expected_evidence") or {}
    document_ids = {str(value) for value in evidence.get("document_ids") or []}
    anchors = [str(value).casefold() for value in evidence.get("anchor_terms") or []]
    items = _request_items(result, str(request["request_id"]))[:5]
    if document_ids:
        return any(
            str((item.get("metadata") or {}).get("document_id") or item.get("document_id"))
            in document_ids
            for item in items
        )
    if not anchors:
        return False
    required = min(2, len(anchors))
    return any(sum(anchor in _item_text(item) for anchor in anchors) >= required for item in items)


def _structured_source_bound(result: Mapping[str, Any], request_id: str) -> bool:
    structured = result.get("structured_result")
    if not isinstance(structured, Mapping):
        return False
    candidates = structured.get("sub_results") or [structured]
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        nested = candidate.get("result") if isinstance(candidate.get("result"), Mapping) else candidate
        if nested.get("request_id") == request_id and nested.get("source_records"):
            return True
    return False


def _citation_isolated(result: Mapping[str, Any], request_ids: set[str]) -> bool:
    citations = result.get("citations") or []
    items = result.get("retrieved_items") or []
    citation_ids = {citation.get("request_id") for citation in citations}
    item_ids = {
        item.get("request_id") or (item.get("metadata") or {}).get("request_id")
        for item in items
    }
    return bool((citation_ids | item_ids) <= request_ids | {None})


def run_executor_retrieval(
    cases: Iterable[dict[str, Any]], pipeline: AnswerPipeline
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case in cases:
        expected = case["expected"]
        if case.get("fault_injection"):
            rows.append(
                {
                    "id": case["id"],
                    "skipped": True,
                    "failure_type": "deterministic_fault_suite",
                    "reason": "Fault injection is executed by deterministic adapter tests.",
                }
            )
            continue
        try:
            result = pipeline._run_retrieval(
                case["query"],
                chat_history=case.get("chat_history") or [],
                cohort=case.get("selected_cohort"),
            )
            plan_correct = exact_plan_match(
                expected, _plan_from_decision(result.get("router_decision") or {})
            )
            expected_requests = expected.get("atomic_requests") or []
            request_ids = {request["request_id"] for request in expected_requests}
            actual_statuses = {
                item.get("request_id"): item.get("status")
                for item in result.get("request_results") or []
            }
            status_match = all(
                actual_statuses.get(request["request_id"]) == request["expected_status"]
                for request in expected_requests
            )
            rag_requests = [request for request in expected_requests if request["request_kind"] == "rag"]
            structured_ok = [request for request in expected_requests if request["request_kind"] == "structured" and request["expected_status"] == "ok"]
            rag_ok = [request for request in expected_requests if request["request_kind"] == "rag" and request["expected_status"] == "ok"]
            citations = result.get("citations") or []
            rows.append(
                {
                    "id": case["id"],
                    "plan_correct": plan_correct,
                    "status_match": status_match,
                    "rag_hits": [
                        _rag_hit_at_5(result, request) for request in rag_requests
                    ] if plan_correct else [],
                    "structured_bindings": [
                        _structured_source_bound(result, request["request_id"])
                        for request in structured_ok
                    ],
                    "citation_bindings": [
                        any(citation.get("request_id") == request["request_id"] for citation in citations)
                        for request in structured_ok + rag_ok
                    ],
                    "citation_isolated": _citation_isolated(result, request_ids),
                    "structured_to_rag_fallbacks": sum(
                        bool(_request_items(result, request["request_id"]))
                        for request in structured_ok
                    ),
                    "provider_failure": False,
                    "failure_type": "pass" if status_match else "executor",
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "id": case["id"],
                    "provider_failure": True,
                    "failure_type": "provider",
                    "error_type": type(exc).__name__,
                }
            )
    return rows


def run_answers(
    cases: Iterable[dict[str, Any]], pipeline: AnswerPipeline
) -> list[dict[str, Any]]:
    rows = []
    for case in cases:
        if case.get("fault_injection"):
            continue
        try:
            result = pipeline.answer(
                case["query"],
                chat_history=case.get("chat_history") or [],
                cohort=case.get("selected_cohort"),
            )
            model_used = result.get("model_used")
            wrong_model = bool(result.get("llm_called") and model_used != ANSWER_MODEL)
            rows.append(
                {
                    "id": case["id"],
                    "status": result.get("status"),
                    "answer": result.get("answer"),
                    "model_used": model_used,
                    "citations": result.get("citations_used") or result.get("citations") or [],
                    "request_results": (result.get("debug") or {}).get("request_results") or [],
                    "partial_status": (result.get("debug") or {}).get("partial_status"),
                    "provider_failure": wrong_model,
                    "failure_type": "wrong_answer_model" if wrong_model else "pass",
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "id": case["id"],
                    "provider_failure": True,
                    "failure_type": "provider",
                    "error_type": type(exc).__name__,
                }
            )
    return rows


def _mean(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def _metrics(
    validation_passed: bool,
    planner_rows: Mapping[str, list[dict[str, Any]]],
    execution_rows: list[dict[str, Any]],
    answer_rows: list[dict[str, Any]],
    judgments: list[dict[str, Any]],
    *,
    quality_checks_passed: bool | None,
    parity_passed: bool | None,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {"contract_invariants": 1.0 if validation_passed else 0.0}
    for suite, rows in planner_rows.items():
        if rows:
            metrics[f"{suite}_exact_plan"] = _mean(float(row.get("passed", False)) for row in rows)
    if execution_rows:
        evaluated = [row for row in execution_rows if not row.get("skipped")]
        rag_hits = [hit for row in evaluated if row.get("plan_correct") for hit in row.get("rag_hits") or []]
        bindings = [value for row in evaluated for value in row.get("structured_bindings") or []]
        citation_bindings = [value for row in evaluated for value in row.get("citation_bindings") or []]
        metrics.update(
            {
                "retrieval_hit_at_5": _mean(float(value) for value in rag_hits),
                "structured_source_binding": _mean(float(value) for value in bindings),
                "structured_to_rag_fallbacks": sum(int(row.get("structured_to_rag_fallbacks") or 0) for row in evaluated),
                "cross_request_leakage": sum(not bool(row.get("citation_isolated")) for row in evaluated),
                "citation_binding": _mean(float(value) for value in citation_bindings),
            }
        )
    if judgments:
        valid = [row for row in judgments if not row.get("provider_failure")]
        metrics.update(
            {
                "faithfulness": _mean(float(row["faithfulness"]) for row in valid),
                "answer_correctness": _mean(float(row["answer_correctness"]) for row in valid),
                "hallucination_rate": _mean(float(row["hallucination"]) for row in valid),
                "critical_false_pass": sum(bool(row.get("critical_false_pass")) for row in valid),
            }
        )
    provider_rows = [row for rows in planner_rows.values() for row in rows] + execution_rows + answer_rows + judgments
    metrics["provider_failures"] = sum(bool(row.get("provider_failure")) for row in provider_rows)
    if planner_rows:
        rejection_rows = [row for rows in planner_rows.values() for row in rows if (row.get("expected") or {}).get("multi_cohort_rejection")]
        if rejection_rows:
            metrics["multi_cohort_rejection"] = _mean(float(row.get("passed", False)) for row in rejection_rows)
    if quality_checks_passed is not None:
        metrics["quality_checks_passed"] = quality_checks_passed
    if parity_passed is not None:
        metrics["parity_passed"] = parity_passed
    return metrics


def _read_optional_rows(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"Expected JSON list: {path}")
    return value


def _read_answer_judgments(path: Path | None) -> list[dict[str, Any]]:
    rows = _read_optional_rows(path)
    required = {
        "id", "answer_model", "faithfulness", "answer_correctness",
        "hallucination", "critical_false_pass", "provider_failure",
    }
    for row in rows:
        missing = required - set(row)
        if missing:
            raise ValueError(f"Judgment {row.get('id')} missing {sorted(missing)}")
        if row.get("answer_model") != ANSWER_MODEL:
            raise ValueError(
                f"Judgment {row.get('id')} uses unapproved answer model {row.get('answer_model')}"
            )
    return rows


def _verified_check_report(
    path: Path | None, *, required_checks: tuple[str, ...], deterministic: bool = False
) -> tuple[bool | None, dict[str, Any] | None]:
    if path is None:
        return None, None
    report = json.loads(path.read_text(encoding="utf-8"))
    if report.get("commit") != _commit():
        return False, report
    if deterministic and report.get("provider") != "deterministic":
        return False, report
    checks = report.get("checks") or {}
    return all(checks.get(name) is True for name in required_checks), report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--planner", choices=("none", "dev", "hidden", "both"), default="none")
    parser.add_argument("--run-executor", choices=("none", "dev", "hidden"), default="none")
    parser.add_argument("--run-answers", choices=("none", "dev", "hidden"), default="none")
    parser.add_argument("--answer-judgments", type=Path)
    parser.add_argument("--confirm-hidden-frozen", action="store_true")
    parser.add_argument("--quality-report", type=Path)
    parser.add_argument("--parity-report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    hidden_requested = (
        args.planner in {"hidden", "both"}
        or args.run_executor == "hidden"
        or args.run_answers == "hidden"
    )
    if hidden_requested and not args.confirm_hidden_frozen:
        parser.error("Hidden evaluation requires --confirm-hidden-frozen after code/prompt/config freeze.")

    validation = validate_bundle()
    planner_rows: dict[str, list[dict[str, Any]]] = {}
    if validation.valid and args.planner != "none":
        suites = ("dev", "hidden") if args.planner == "both" else (args.planner,)
        for suite in suites:
            planner_rows[suite] = run_live_planner(_load_cases(suite))

    pipeline: AnswerPipeline | None = None
    execution_rows: list[dict[str, Any]] = []
    answer_rows: list[dict[str, Any]] = []
    if validation.valid and (args.run_executor != "none" or args.run_answers != "none"):
        pipeline = AnswerPipeline()
    if pipeline and args.run_executor != "none":
        execution_rows = run_executor_retrieval(_load_cases(args.run_executor), pipeline)
    if pipeline and args.run_answers != "none":
        answer_rows = run_answers(_load_cases(args.run_answers), pipeline)
    judgments = _read_answer_judgments(args.answer_judgments)
    quality_passed, quality_report = _verified_check_report(
        args.quality_report,
        required_checks=("pytest", "ruff", "frontend_lint", "frontend_build"),
    )
    parity_passed, parity_report = _verified_check_report(
        args.parity_report,
        required_checks=("sync_stream", "sync_cache", "stream_cache", "debug_metadata"),
        deterministic=True,
    )
    metrics = _metrics(
        validation.valid,
        planner_rows,
        execution_rows,
        answer_rows,
        judgments,
        quality_checks_passed=quality_passed,
        parity_passed=parity_passed,
    )
    gates = evaluate_release_gates(metrics)
    manifest = json.loads((BUNDLE_DIR / "manifest.json").read_text(encoding="utf-8"))
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "commit": _commit(),
        "schema_version": manifest.get("schema_version"),
        "models": {"planner": PLANNER_MODEL, "answer": ANSWER_MODEL},
        "prompt_version": manifest.get("prompt_version"),
        "registry_version": manifest.get("registry_version"),
        "dataset_hashes": validation.hashes,
        "config_hash": _file_hash(ROOT / "configs" / "structured_lookup_registry.yaml"),
        "index_data_version": {
            "structured_manifest": _file_hash(ROOT / "data" / "processed" / "metadata" / "structured_data_manifest.json"),
            "chunk_manifest": _file_hash(ROOT / "data" / "processed" / "metadata" / "chunk_manifest.json"),
        },
        "contract": {"passed": validation.valid, "errors": validation.errors, "coverage": validation.coverage},
        "planner": {suite: {"passed": sum(row.get("passed", False) for row in rows), "total": len(rows), "failure_taxonomy": failure_taxonomy(rows), "rows": rows} for suite, rows in planner_rows.items()},
        "executor_retrieval": {"failure_taxonomy": failure_taxonomy(execution_rows), "rows": execution_rows},
        "answers": answer_rows,
        "answer_judgments": judgments,
        "quality_report": quality_report,
        "parity_report": parity_report,
        "metrics": metrics,
        "gates": {"passed": gates.passed, "checks": gates.checks, "missing_metrics": gates.missing_metrics},
        "release_ready": gates.passed,
    }
    output = args.output or BUNDLE_DIR / "latest_evaluation_report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"commit": report["commit"], "contract": report["contract"]["passed"], "metrics": metrics, "gates": report["gates"], "release_ready": report["release_ready"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
