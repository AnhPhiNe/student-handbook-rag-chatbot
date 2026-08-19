"""Four-layer single-cohort-v2 evaluator and release-gate report."""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.evaluation.single_cohort_v2 import (  # noqa: E402
    BUNDLE_DIR,
    evaluate_development_gates,
    evaluate_release_gates,
    exact_plan_match,
    failure_taxonomy,
    validate_bundle,
)
from src.evaluation.artifact_fingerprint import (  # noqa: E402
    file_hash,
    release_artifact_fingerprint,
)
from src.generation.answer_pipeline import AnswerPipeline  # noqa: E402
from src.retrieval.core.ai_router import AIRouter  # noqa: E402
from src.retrieval.core.query_context import select_effective_query  # noqa: E402
from src.retrieval.core.structured_routing import (  # noqa: E402
    bind_effective_cohort,
    load_lookup_registry,
    reject_invalid_plan,
    validate_router_decision,
)


PLANNER_MODEL = "qwen/qwen3.6-27b"
ANSWER_MODEL = "gemini-3.1-flash-lite"
JUDGE_MODEL = "openai/gpt-oss-120b"
JUDGE_PROMPT_VERSION = "single-cohort-answer-judge-v1"
HIDDEN_ATTEMPT_PATH = (
    ROOT / "data/eval/reports/single_cohort_v2/hidden_release_attempt.json"
)


def _commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _artifact_fingerprint() -> dict[str, str | None]:
    return release_artifact_fingerprint(ROOT)


def _hidden_attempt_binding(
    dataset_hashes: Mapping[str, str], manifest: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "commit": _commit(),
        "dataset_hashes": dict(dataset_hashes),
        "artifact_fingerprint": _artifact_fingerprint(),
        "models": {
            "planner": PLANNER_MODEL,
            "answer": ANSWER_MODEL,
            "judge": JUDGE_MODEL,
        },
        "prompt_version": manifest.get("prompt_version"),
        "registry_version": manifest.get("registry_version"),
    }


def _start_hidden_attempt(
    binding: Mapping[str, Any], *, retry_provider_outage: bool
) -> dict[str, Any]:
    existing = (
        json.loads(HIDDEN_ATTEMPT_PATH.read_text(encoding="utf-8"))
        if HIDDEN_ATTEMPT_PATH.exists()
        else None
    )
    if existing is not None:
        retry_allowed = bool(
            retry_provider_outage
            and existing.get("status") == "provider_outage"
            and existing.get("model_output_count") == 0
            and existing.get("binding") == binding
        )
        if not retry_allowed:
            raise ValueError(
                "Hidden release attempt already exists; only a zero-output provider "
                "outage with unchanged artifacts may be retried"
            )
        incidents = list(existing.get("incidents") or [])
        incidents.append(
            {
                "type": "provider_outage_retry",
                "previous_attempt_id": existing.get("attempt_id"),
                "recorded_at": datetime.now(UTC).isoformat(),
            }
        )
    else:
        if retry_provider_outage:
            raise ValueError("No provider-outage hidden attempt exists to retry")
        incidents = []
    attempt = {
        "attempt_id": str(uuid.uuid4()),
        "status": "running",
        "started_at": datetime.now(UTC).isoformat(),
        "binding": dict(binding),
        "model_output_count": 0,
        "provider_failures": 0,
        "incidents": incidents,
    }
    HIDDEN_ATTEMPT_PATH.parent.mkdir(parents=True, exist_ok=True)
    HIDDEN_ATTEMPT_PATH.write_text(
        json.dumps(attempt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return attempt


def _finish_hidden_attempt(
    attempt: dict[str, Any],
    *,
    planner_rows: Iterable[Mapping[str, Any]],
    answer_rows: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    model_rows = list(planner_rows) + list(answer_rows)
    output_count = sum(not row.get("provider_failure") for row in model_rows)
    provider_failures = sum(bool(row.get("provider_failure")) for row in model_rows)
    attempt = {
        **attempt,
        "status": (
            "provider_outage"
            if provider_failures and output_count == 0
            else "completed"
        ),
        "finished_at": datetime.now(UTC).isoformat(),
        "model_output_count": output_count,
        "provider_failures": provider_failures,
    }
    HIDDEN_ATTEMPT_PATH.write_text(
        json.dumps(attempt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return attempt


def _load_cases(suite: str) -> list[dict[str, Any]]:
    return json.loads((BUNDLE_DIR / f"{suite}.json").read_text(encoding="utf-8"))


def _validated_planner_decision(
    case: Mapping[str, Any], decision: dict[str, Any]
) -> dict[str, Any]:
    history = list(case.get("chat_history") or [])
    handling = select_effective_query(
        str(case["query"]),
        decision,
        chat_history=history,
        selected_cohort=case.get("selected_cohort"),
    )
    effective_query = handling.effective_query or str(case["query"])
    bound = bind_effective_cohort(
        decision,
        raw_query=str(case["query"]),
        effective_query=effective_query,
        selected_cohort=case.get("selected_cohort"),
    )
    bound = {
        **bound,
        "query_handling": handling.to_dict(),
        "effective_query": effective_query,
    }
    if handling.needs_clarification:
        return {
            **bound,
            "outcome": "clarify",
            "route": "clarify",
            "execution_mode": "regulation",
            "lookup_requests": [],
            "retrieval_query": None,
            "retrieval_executed": False,
            "clarification_question": handling.clarification_question,
        }
    if bound.get("route") in {"structured", "rag"} and isinstance(
        bound.get("lookup_requests"), list
    ):
        registry = load_lookup_registry()
        errors = validate_router_decision(
            bound,
            query=effective_query,
            selected_cohort=bound.get("cohort"),
            registry=registry,
        )
        if errors:
            bound = reject_invalid_plan(bound, errors, query=effective_query)
            bound["query_handling"] = handling.to_dict()
            bound["effective_query"] = effective_query
    return bound


def _plan_from_decision(decision: Mapping[str, Any]) -> dict[str, Any]:
    query_handling = decision.get("query_handling") or {}
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
        "query_mode": query_handling.get("mode") or decision.get("query_mode"),
        "effective_cohort": decision.get("cohort"),
        "effective_cohort_source": decision.get("effective_cohort_source"),
        "atomic_requests": requests,
    }


def run_live_planner(
    cases: Iterable[dict[str, Any]], router: AIRouter | None = None
) -> list[dict[str, Any]]:
    case_rows = list(cases)
    try:
        active_router = router or AIRouter.from_config()
    except Exception as exc:
        return [
            {
                "id": case["id"],
                "passed": False,
                "failure_type": "provider",
                "provider_failure": True,
                "error_type": type(exc).__name__,
            }
            for case in case_rows
        ]
    if active_router.model_name != PLANNER_MODEL:
        raise RuntimeError(
            f"Planner model must be {PLANNER_MODEL}, got {active_router.model_name}"
        )
    rows: list[dict[str, Any]] = []
    for case in case_rows:
        try:
            decision = active_router.route(
                case["query"],
                chat_history=case.get("chat_history") or [],
                cohort=case.get("selected_cohort"),
            )
            bound = _validated_planner_decision(case, decision)
            actual = _plan_from_decision(bound)
            matched = exact_plan_match(case["expected"], actual)
            rows.append(
                {
                    "id": case["id"],
                    "passed": matched,
                    "failure_type": "pass" if matched else "planner",
                    "expected": case["expected"],
                    "actual": actual,
                    "validated_decision": bound,
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


def _rag_hit_at_5(result: Mapping[str, Any], request: Mapping[str, Any]) -> bool:
    evidence = request.get("expected_evidence") or {}
    parent_ids = {str(value) for value in evidence.get("parent_section_ids") or []}
    chunk_ids = {str(value) for value in evidence.get("chunk_ids") or []}
    items = _request_items(result, str(request["request_id"]))[:5]
    if not parent_ids and not chunk_ids:
        return False
    for item in items:
        metadata = item.get("metadata") or {}
        actual_parent = str(
            metadata.get("parent_section_id")
            or metadata.get("parent_chunk_id")
            or item.get("parent_section_id")
            or ""
        )
        actual_chunk = str(
            item.get("chunk_id") or item.get("_id") or metadata.get("chunk_id") or ""
        )
        if actual_parent in parent_ids or actual_chunk in chunk_ids:
            return True
    return False


def _source_identity(value: Mapping[str, Any]) -> tuple[str, str, str]:
    metadata = value.get("metadata") or {}
    return (
        str(
            value.get("record_id")
            or value.get("source_record_id")
            or value.get("table_id")
            or value.get("row_id")
            or value.get("id")
            or value.get("_id")
            or ""
        ),
        str(value.get("document_id") or metadata.get("document_id") or ""),
        str(value.get("parent_section_id") or value.get("source_parent_id") or metadata.get("parent_section_id") or ""),
    )


def _structured_source_bound(
    result: Mapping[str, Any], request: Mapping[str, Any]
) -> bool:
    structured = result.get("structured_result")
    if not isinstance(structured, Mapping):
        return False
    candidates = structured.get("sub_results") or [structured]
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        nested = candidate.get("result") if isinstance(candidate.get("result"), Mapping) else candidate
        request_index = int(str(request["request_id"]).removeprefix("r")) - 1
        if nested.get("request_id") not in {None, request["request_id"]}:
            continue
        if nested.get("request_index") not in {None, request_index}:
            continue
        actual = {
            _source_identity(record)
            for record in nested.get("source_records") or candidate.get("source_records") or []
        }
        expected = {
            _source_identity(record)
            for record in request.get("expected_source_records") or []
        }
        if expected and expected <= actual:
            return True
    return False


def _citation_isolated(result: Mapping[str, Any], request_ids: set[str]) -> bool:
    citations = result.get("citations_used") or result.get("citations") or []
    items = result.get("retrieved_items") or []
    citation_ids = {citation.get("request_id") for citation in citations}
    item_ids = {
        item.get("request_id") or (item.get("metadata") or {}).get("request_id")
        for item in items
    }
    return bool((citation_ids | item_ids) <= request_ids)


def _citation_bound(citations: Iterable[Mapping[str, Any]], request: Mapping[str, Any]) -> bool:
    expected_parents = {
        str(value)
        for value in (request.get("expected_evidence") or {}).get("parent_section_ids") or []
    }
    expected_chunks = {
        str(value)
        for value in (request.get("expected_evidence") or {}).get("chunk_ids") or []
    }
    expected_sources = {
        _source_identity(record)
        for record in request.get("expected_source_records") or []
    }
    for citation in citations:
        if citation.get("request_id") != request["request_id"]:
            continue
        metadata = citation.get("metadata") or {}
        parent = str(
            citation.get("parent_section_id")
            or citation.get("source_parent_id")
            or metadata.get("parent_section_id")
            or ""
        )
        chunk = str(
            citation.get("chunk_id") or citation.get("_id") or metadata.get("chunk_id") or ""
        )
        if parent in expected_parents or chunk in expected_chunks:
            return True
        if expected_sources and _source_identity(citation) in expected_sources:
            return True
    return False


def run_executor_retrieval(
    cases: Iterable[dict[str, Any]],
    pipeline: AnswerPipeline,
    *,
    planner_rows: Mapping[str, Mapping[str, Any]],
    result_sink: dict[str, dict[str, Any]] | None = None,
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
        planner_row = planner_rows.get(case["id"])
        if not planner_row or not planner_row.get("passed"):
            raise ValueError(
                f"Executor received a case without a correct validated plan: {case['id']}"
            )
        decision = planner_row.get("validated_decision") or {}
        if expected.get("outcome") != "execute":
            if result_sink is not None:
                outcome = str(decision.get("outcome") or "clarify")
                result_sink[case["id"]] = {
                    "router_decision": dict(decision),
                    "effective_query": str(
                        decision.get("effective_query") or case["query"]
                    ),
                    "query_handling": dict(decision.get("query_handling") or {}),
                    "request_results": [],
                    "retrieved_items": [],
                    "citations": [],
                    "retrieval_executed": False,
                    "needs_clarification": outcome == "clarify",
                    "clarification_question": str(
                        decision.get("clarification_question")
                        or "Bạn có thể làm rõ câu hỏi được không?"
                    ),
                    "out_of_domain": outcome == "out_of_domain",
                }
            rows.append(
                {
                    "id": case["id"],
                    "skipped": True,
                    "failure_type": "non_execute_no_retrieval",
                    "provider_failure": False,
                }
            )
            continue
        try:
            effective_query = str(decision.get("effective_query") or case["query"])
            retrieval_query = pipeline.slang_normalizer.normalize_for_retrieval(
                effective_query
            )
            result = pipeline._execute_single_cohort_retrieval(
                query=case["query"],
                effective_query=effective_query,
                retrieval_query=retrieval_query,
                cohort=decision.get("cohort"),
                router_decision=dict(decision),
                query_handling=dict(decision.get("query_handling") or {}),
                chat_history=case.get("chat_history") or [],
            )
            if result_sink is not None:
                result_sink[case["id"]] = copy.deepcopy(result)
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
            structured_requests = [
                request
                for request in expected_requests
                if request["request_kind"] == "structured"
            ]
            structured_ok = [request for request in expected_requests if request["request_kind"] == "structured" and request["expected_status"] == "ok"]
            rag_ok = [request for request in expected_requests if request["request_kind"] == "rag" and request["expected_status"] == "ok"]
            citations = result.get("citations") or []
            rows.append(
                {
                    "id": case["id"],
                    "plan_correct": plan_correct,
                    "status_match": status_match,
                    "rag_hits": [
                        _rag_hit_at_5(result, request) for request in rag_ok
                    ] if plan_correct else [],
                    "structured_bindings": [
                        _structured_source_bound(result, request)
                        for request in structured_ok
                    ],
                    "citation_bindings": [
                        _citation_bound(citations, request)
                        for request in structured_ok + rag_ok
                    ],
                    "citation_isolated": _citation_isolated(result, request_ids),
                    "structured_to_rag_fallbacks": sum(
                        bool(_request_items(result, request["request_id"]))
                        for request in structured_requests
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
    cases: Iterable[dict[str, Any]],
    pipeline: AnswerPipeline,
    *,
    planner_rows: Mapping[str, Mapping[str, Any]],
    execution_results: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows = []
    for case in cases:
        if case.get("fault_injection"):
            continue
        planner_row = planner_rows.get(case["id"])
        if not planner_row or not planner_row.get("passed"):
            raise ValueError(
                f"Answer composer received an incorrect plan: {case['id']}"
            )
        execution_result = execution_results.get(case["id"])
        if execution_result is None:
            rows.append(
                {
                    "id": case["id"],
                    "provider_failure": True,
                    "failure_type": "missing_validated_execution",
                }
            )
            continue
        original_run_retrieval = pipeline._run_retrieval

        def use_validated_execution(
            _query: str,
            _cohort: str | None,
            *,
            chat_history: list[dict[str, str]] | None = None,
        ) -> dict[str, Any]:
            del chat_history
            return copy.deepcopy(dict(execution_result))

        try:
            pipeline._run_retrieval = use_validated_execution  # type: ignore[method-assign]
            result = pipeline.answer(
                case["query"],
                chat_history=case.get("chat_history") or [],
                cohort=case.get("selected_cohort"),
            )
            model_used = result.get("model_used")
            wrong_model = bool(result.get("llm_called") and model_used != ANSWER_MODEL)
            expected = case["expected"]
            expected_requests = expected.get("atomic_requests") or []
            request_results = (result.get("debug") or {}).get("request_results") or []
            actual_statuses = {
                item.get("request_id"): item.get("status")
                for item in request_results
            }
            statuses_bound = all(
                actual_statuses.get(request["request_id"])
                == request["expected_status"]
                for request in expected_requests
            )
            citations = result.get("citations_used") or result.get("citations") or []
            successful_requests = [
                request
                for request in expected_requests
                if request.get("expected_status") == "ok"
            ]
            citations_bound = all(
                _citation_bound(citations, request)
                for request in successful_requests
            )
            request_ids = {request["request_id"] for request in expected_requests}
            plan_bound = exact_plan_match(
                expected,
                _plan_from_decision(result.get("router_decision") or {}),
            )
            rows.append(
                {
                    "id": case["id"],
                    "status": result.get("status"),
                    "answer": result.get("answer"),
                    "model_used": model_used,
                    "citations": citations,
                    "context_used": result.get("context_used"),
                    "structured_result": result.get("structured_result"),
                    "formula_result": result.get("formula_result"),
                    "retrieved_items": result.get("retrieved_items") or [],
                    "router_decision": result.get("router_decision") or {},
                    "effective_query": result.get("effective_query"),
                    "request_results": request_results,
                    "partial_status": (result.get("debug") or {}).get("partial_status"),
                    "answer_contract_bound": bool(
                        plan_bound
                        and statuses_bound
                        and citations_bound
                        and _citation_isolated(result, request_ids)
                    ),
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
        finally:
            pipeline._run_retrieval = original_run_retrieval  # type: ignore[method-assign]
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
    conformance_passed: bool | None,
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
    if answer_rows:
        metrics["answer_contract_binding"] = _mean(
            float(row.get("answer_contract_bound", False))
            for row in answer_rows
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
    if conformance_passed is not None:
        metrics["conformance_passed"] = conformance_passed
    if conformance_passed:
        metrics.setdefault("structured_to_rag_fallbacks", 0)
        metrics.setdefault("cross_request_leakage", 0)
    return metrics


def _read_optional_rows(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list):
        raise ValueError(f"Expected JSON list: {path}")
    return value


def _read_answer_judgments(
    path: Path | None, *, answers_report_hash: str | None
) -> list[dict[str, Any]]:
    rows = _read_optional_rows(path)
    required = {
        "id", "answer_model", "judge_model", "judge_prompt_version",
        "answers_report_hash",
        "faithfulness", "answer_correctness",
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
        if row.get("judge_model") != JUDGE_MODEL:
            raise ValueError(
                f"Judgment {row.get('id')} uses unapproved judge {row.get('judge_model')}"
            )
        if row.get("judge_prompt_version") != JUDGE_PROMPT_VERSION:
            raise ValueError(
                f"Judgment {row.get('id')} uses unapproved judge prompt"
            )
        if not answers_report_hash or row.get("answers_report_hash") != answers_report_hash:
            raise ValueError(
                f"Judgment {row.get('id')} is not bound to the supplied answer report"
            )
    ids = [str(row.get("id") or "") for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Answer judgments contain duplicate case ids")
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
    if report.get("artifact_fingerprint") != _artifact_fingerprint():
        return False, report
    checks = report.get("checks") or {}
    return all(checks.get(name) is True for name in required_checks), report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--planner", choices=("none", "dev", "hidden", "both"), default="none")
    parser.add_argument("--run-executor", choices=("none", "dev", "hidden"), default="none")
    parser.add_argument("--run-answers", choices=("none", "dev", "hidden"), default="none")
    parser.add_argument("--answer-judgments", type=Path)
    parser.add_argument("--answers-report", type=Path)
    parser.add_argument("--confirm-hidden-frozen", action="store_true")
    parser.add_argument("--retry-provider-outage", action="store_true")
    parser.add_argument("--quality-report", type=Path)
    parser.add_argument("--parity-report", type=Path)
    parser.add_argument("--conformance-report", type=Path)
    parser.add_argument("--legacy-compatibility-report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    hidden_requested = (
        args.planner in {"hidden", "both"}
        or args.run_executor == "hidden"
        or args.run_answers == "hidden"
    )
    if hidden_requested and not args.confirm_hidden_frozen:
        parser.error("Hidden evaluation requires --confirm-hidden-frozen after code/prompt/config freeze.")
    if hidden_requested and not (
        args.planner == "hidden"
        and args.run_executor == "hidden"
        and args.run_answers == "hidden"
    ):
        parser.error(
            "Hidden release evaluation must run Planner, executor/retrieval and "
            "answers together in one attempt."
        )
    if args.run_executor != "none" and args.planner not in {args.run_executor, "both"}:
        parser.error("Executor/retrieval evaluation requires Planner evaluation for the same split.")
    if args.run_answers != "none" and args.run_executor != args.run_answers:
        parser.error(
            "Answer evaluation requires executor/retrieval evaluation for the same split."
        )
    if args.answers_report and args.run_answers != "none":
        parser.error("Use either --run-answers or --answers-report, not both.")

    live_requested = bool(
        args.planner != "none"
        or args.run_executor != "none"
        or args.run_answers != "none"
        or args.answers_report
        or args.answer_judgments
    )
    validation = validate_bundle(require_gold_complete=live_requested)
    manifest = json.loads((BUNDLE_DIR / "manifest.json").read_text(encoding="utf-8"))
    if hidden_requested and not (
        manifest.get("hidden_frozen")
        and manifest.get("hidden_human_review_complete")
    ):
        parser.error("Hidden is not human-approved and frozen.")
    hidden_attempt: dict[str, Any] | None = None
    if hidden_requested and validation.valid:
        try:
            hidden_attempt = _start_hidden_attempt(
                _hidden_attempt_binding(validation.hashes, manifest),
                retry_provider_outage=args.retry_provider_outage,
            )
        except ValueError as exc:
            parser.error(str(exc))
    planner_rows: dict[str, list[dict[str, Any]]] = {}
    if validation.valid and args.planner != "none":
        suites = ("dev", "hidden") if args.planner == "both" else (args.planner,)
        for suite in suites:
            planner_rows[suite] = run_live_planner(_load_cases(suite))

    pipeline: AnswerPipeline | None = None
    execution_rows: list[dict[str, Any]] = []
    execution_results: dict[str, dict[str, Any]] = {}
    answer_rows: list[dict[str, Any]] = []
    if validation.valid and (args.run_executor != "none" or args.run_answers != "none"):
        pipeline = AnswerPipeline()
    if pipeline and args.run_executor != "none":
        passed_ids = {
            row["id"]
            for row in planner_rows.get(args.run_executor, [])
            if row.get("passed")
        }
        execution_rows = run_executor_retrieval(
            [case for case in _load_cases(args.run_executor) if case["id"] in passed_ids],
            pipeline,
            planner_rows={
                row["id"]: row for row in planner_rows.get(args.run_executor, [])
            },
            result_sink=execution_results,
        )
    if pipeline and args.run_answers != "none":
        passed_ids = {
            row["id"]
            for row in planner_rows.get(args.run_answers, [])
            if row.get("passed")
        }
        answer_rows = run_answers(
            [case for case in _load_cases(args.run_answers) if case["id"] in passed_ids],
            pipeline,
            planner_rows={
                row["id"]: row for row in planner_rows.get(args.run_answers, [])
            },
            execution_results=execution_results,
        )
    answers_report_hash: str | None = None
    if args.answers_report:
        answer_report = json.loads(args.answers_report.read_text(encoding="utf-8"))
        if answer_report.get("commit") != _commit():
            parser.error("Answer report commit does not match the current commit.")
        if answer_report.get("dataset_hashes") != validation.hashes:
            parser.error("Answer report dataset hashes do not match the frozen bundle.")
        if (answer_report.get("models") or {}).get("answer") != ANSWER_MODEL:
            parser.error("Answer report does not use the pinned answer model.")
        answer_rows = list(answer_report.get("answers") or [])
        if any(str(row.get("id") or "").startswith("hidden-") for row in answer_rows):
            if not args.confirm_hidden_frozen:
                parser.error("Hidden answer report requires --confirm-hidden-frozen.")
            if not (
                manifest.get("hidden_frozen")
                and manifest.get("hidden_human_review_complete")
            ):
                parser.error("Hidden is not human-approved and frozen.")
        answers_report_hash = file_hash(args.answers_report)
    judgments = _read_answer_judgments(
        args.answer_judgments,
        answers_report_hash=answers_report_hash,
    )
    if judgments and not answer_rows:
        parser.error("Answer judgments require generated answer rows.")
    if judgments and {row["id"] for row in judgments} != {
        row["id"] for row in answer_rows
    }:
        parser.error("Answer judgments must cover every generated answer exactly once.")
    if hidden_attempt is not None:
        hidden_attempt = _finish_hidden_attempt(
            hidden_attempt,
            planner_rows=planner_rows.get("hidden", []),
            answer_rows=answer_rows,
        )
    quality_passed, quality_report = _verified_check_report(
        args.quality_report,
        required_checks=("pytest", "ruff", "frontend_lint", "frontend_build"),
    )
    parity_passed, parity_report = _verified_check_report(
        args.parity_report,
        required_checks=("sync_stream", "sync_cache", "stream_cache", "debug_metadata"),
        deterministic=True,
    )
    conformance_passed, conformance_report = _verified_check_report(
        args.conformance_report,
        required_checks=(
            "no_match", "invalid", "unresolved", "adapter_exception",
            "plan_tampering", "structured_to_rag_fallback_zero",
            "citation_isolation", "no_retrieval_on_non_execute",
        ),
        deterministic=True,
    )
    legacy_passed: bool | None = None
    legacy_report: dict[str, Any] | None = None
    if args.legacy_compatibility_report is not None:
        legacy_report = json.loads(
            args.legacy_compatibility_report.read_text(encoding="utf-8")
        )
        legacy_passed = bool(
            legacy_report.get("commit") == _commit()
            and legacy_report.get("artifact_fingerprint")
            == _artifact_fingerprint()
            and legacy_report.get("provider") == "live"
            and legacy_report.get("passed") is True
        )
    metrics = _metrics(
        validation.valid,
        planner_rows,
        execution_rows,
        answer_rows,
        judgments,
        quality_checks_passed=quality_passed,
        parity_passed=parity_passed,
        conformance_passed=conformance_passed,
    )
    if legacy_passed is not None:
        metrics["legacy_compatibility_passed"] = legacy_passed
    gates = evaluate_release_gates(metrics)
    development_gates = evaluate_development_gates(metrics)
    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "commit": _commit(),
        "schema_version": manifest.get("schema_version"),
        "models": {"planner": PLANNER_MODEL, "answer": ANSWER_MODEL, "judge": JUDGE_MODEL},
        "judge_prompt_version": JUDGE_PROMPT_VERSION,
        "prompt_version": manifest.get("prompt_version"),
        "registry_version": manifest.get("registry_version"),
        "dataset_hashes": validation.hashes,
        "artifact_fingerprint": _artifact_fingerprint(),
        "contract": {"passed": validation.valid, "errors": validation.errors, "coverage": validation.coverage},
        "planner": {suite: {"passed": sum(row.get("passed", False) for row in rows), "total": len(rows), "failure_taxonomy": failure_taxonomy(rows), "rows": rows} for suite, rows in planner_rows.items()},
        "executor_retrieval": {"failure_taxonomy": failure_taxonomy(execution_rows), "rows": execution_rows},
        "answers": answer_rows,
        "answers_report_hash": answers_report_hash,
        "answer_judgments": judgments,
        "hidden_release_attempt": hidden_attempt,
        "quality_report": quality_report,
        "parity_report": parity_report,
        "conformance_report": conformance_report,
        "legacy_compatibility_report": legacy_report,
        "metrics": metrics,
        "gates": {"passed": gates.passed, "checks": gates.checks, "missing_metrics": gates.missing_metrics},
        "development_gates": {
            "passed": development_gates.passed,
            "checks": development_gates.checks,
            "missing_metrics": development_gates.missing_metrics,
        },
        "development_ready": development_gates.passed,
        "release_ready": gates.passed,
    }
    output = args.output or BUNDLE_DIR / "latest_evaluation_report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "commit": report["commit"],
                "contract": report["contract"]["passed"],
                "metrics": metrics,
                "development_gates": report["development_gates"],
                "gates": report["gates"],
                "development_ready": report["development_ready"],
                "release_ready": report["release_ready"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
