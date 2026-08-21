"""Four-layer single-cohort-v2 evaluator and release-gate report."""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.env_loader import load_project_env  # noqa: E402

load_project_env()

from src.evaluation.single_cohort_v2 import (  # noqa: E402
    BUNDLE_DIR,
    EVALUATION_PROTOCOL_VERSION,
    assess_plan,
    evaluate_development_gates,
    evaluate_release_gates,
    execution_plan_match,
    exact_plan_match,
    failure_taxonomy,
    semantic_plan_match,
    semantic_value_equal,
    validate_bundle,
)
from src.evaluation.artifact_fingerprint import (  # noqa: E402
    file_hash,
    release_artifact_fingerprint,
)
from src.generation.answer_pipeline import AnswerPipeline  # noqa: E402
from src.generation.io_utils import load_json, load_yaml  # noqa: E402
from src.retrieval.core.ai_router import (  # noqa: E402
    AIRouter,
    ROUTER_PROMPT_VERSION,
)
from src.retrieval.core.office_lookup import find_grounded_catalog_hint  # noqa: E402
from src.retrieval.core.query_context import (  # noqa: E402
    select_effective_query,
    validated_correction_provenance,
)
from src.retrieval.core.structured_routing import (  # noqa: E402
    bind_effective_cohort,
    load_lookup_registry,
    reject_invalid_plan,
    validate_router_decision,
)
from src.retrieval.core.tool_registry import (  # noqa: E402
    REQUESTED_FIELD_RESULT_KEYS,
)


PLANNER_MODEL = "qwen/qwen3.6-27b"
ANSWER_MODEL = "gemini-3.1-flash-lite"
JUDGE_MODEL = "openai/gpt-oss-120b"
JUDGE_PROMPT_VERSION = "single-cohort-answer-judge-v2"
ANSWER_CONFIG_PATH = ROOT / "configs" / "answer_generation.yaml"
HIDDEN_ATTEMPT_PATH = (
    ROOT / "data/eval/reports/single_cohort_v2/hidden_release_attempt.json"
)


def _commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def _artifact_fingerprint() -> dict[str, str | None]:
    return release_artifact_fingerprint(ROOT)


def _planner_section(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Build the auditable Planner section used by checkpoints and final reports."""

    materialized = [dict(row) for row in rows]
    evaluable = [row for row in materialized if not row.get("planner_skipped")]
    return {
        "passed": sum(bool(row.get("passed", False)) for row in evaluable),
        "exact_passed": sum(
            bool(row.get("exact_passed", row.get("passed", False)))
            for row in evaluable
        ),
        "semantic_passed": sum(
            bool(row.get("semantic_passed", row.get("passed", False)))
            for row in evaluable
        ),
        "execution_eligible": sum(
            bool(
                row.get(
                    "execution_eligible",
                    row.get("semantic_passed", row.get("passed", False)),
                )
            )
            for row in evaluable
        ),
        "provider_failures": sum(
            bool(row.get("provider_failure")) for row in evaluable
        ),
        "case_total": len(materialized),
        "planner_evaluable_total": len(evaluable),
        "deterministic_skipped": len(materialized) - len(evaluable),
        "failure_taxonomy": failure_taxonomy(materialized),
        "rows": materialized,
    }


def _planner_checkpoint_report(
    planner_rows: Mapping[str, Iterable[Mapping[str, Any]]],
    *,
    manifest: Mapping[str, Any],
    validation: Any,
) -> dict[str, Any]:
    """Bind Planner-only output to the exact frozen runtime and dataset."""

    return {
        "report_type": "single_cohort_v2_planner_checkpoint",
        "timestamp": datetime.now(UTC).isoformat(),
        "commit": _commit(),
        "schema_version": manifest.get("schema_version"),
        "evaluation_protocol_version": EVALUATION_PROTOCOL_VERSION,
        "models": {"planner": PLANNER_MODEL},
        "prompt_version": ROUTER_PROMPT_VERSION,
        "dataset_prompt_version": manifest.get("prompt_version"),
        "registry_version": manifest.get("registry_version"),
        "dataset_hashes": validation.hashes,
        "artifact_fingerprint": _artifact_fingerprint(),
        "contract": {
            "passed": validation.valid,
            "errors": validation.errors,
            "coverage": validation.coverage,
        },
        "planner": {
            suite: _planner_section(rows) for suite, rows in planner_rows.items()
        },
    }


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
    """Write a report without exposing a partially serialized checkpoint."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _load_bound_planner_report(
    path: Path,
    *,
    manifest: Mapping[str, Any],
    validation: Any,
) -> dict[str, list[dict[str, Any]]]:
    """Reject stale Planner rows before they can authorize executor/model calls."""

    report = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "commit": _commit(),
        "dataset_hashes": validation.hashes,
        "artifact_fingerprint": _artifact_fingerprint(),
        "prompt_version": ROUTER_PROMPT_VERSION,
        "dataset_prompt_version": manifest.get("prompt_version"),
        "registry_version": manifest.get("registry_version"),
    }
    for field, value in expected.items():
        if report.get(field) != value:
            raise ValueError(f"Planner report {field} does not match current freeze")
    if (report.get("models") or {}).get("planner") != PLANNER_MODEL:
        raise ValueError("Planner report does not use the pinned Planner model")
    if not (report.get("contract") or {}).get("passed"):
        raise ValueError("Planner report was not produced from a valid frozen bundle")

    suites: dict[str, list[dict[str, Any]]] = {}
    for suite, info in (report.get("planner") or {}).items():
        if isinstance(info, Mapping) and isinstance(info.get("rows"), list):
            suites[str(suite)] = list(info["rows"])
    if not suites:
        raise ValueError("Planner report contains no Planner rows")
    return suites


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
        # The bundle is frozen independently from the runtime prompt.  Bind the
        # release attempt to both, so a prompt change cannot be misreported as
        # the version used when the gold labels were frozen.
        "prompt_version": ROUTER_PROMPT_VERSION,
        "dataset_prompt_version": manifest.get("prompt_version"),
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


def _load_case_ids(path: Path | None) -> set[str] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        values = payload
    elif isinstance(payload, dict) and isinstance(payload.get("case_ids"), list):
        values = payload["case_ids"]
    elif isinstance(payload, dict) and isinstance(payload.get("reviews"), list):
        values = [
            review.get("id")
            for review in payload["reviews"]
            if isinstance(review, dict) and review.get("requires_human_attention")
        ]
    else:
        raise ValueError(
            "Case ID file must be a JSON list, contain case_ids, or contain "
            "human-audit reviews with requires_human_attention=true."
        )
    case_ids = {
        str(value).strip() for value in values if str(value or "").strip()
    }
    if not case_ids:
        raise ValueError("Case ID selection is empty.")
    return case_ids


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
            query=str(case["query"]),
            selected_cohort=bound.get("cohort"),
            grounding_context=effective_query,
            registry=registry,
            validated_corrections=validated_correction_provenance(
                decision, handling
            ),
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


def _is_deterministic_plan_tampering(case: Mapping[str, Any]) -> bool:
    fault = case.get("fault_injection")
    return isinstance(fault, Mapping) and fault.get("type") == "plan_tampering"


def _planner_skip_row(case: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": case["id"],
        "category": case.get("category"),
        "planner_skipped": True,
        "passed": False,
        "exact_passed": False,
        "semantic_passed": False,
        "failure_type": "deterministic_fault_suite",
        "reason": "Plan tampering is exercised after a valid plan by deterministic conformance.",
        "provider_failure": False,
    }


def _planner_catalogs() -> dict[str, list[dict[str, Any]]]:
    """Load precisely the exact-match catalogs supplied to the production planner.

    This prepares metadata only: it does not select a route or execute a tool.
    Keeping it here avoids constructing the full retrieval pipeline just to make
    a planner-only evaluation match the production prompt.
    """

    config = load_yaml(ANSWER_CONFIG_PATH)
    inputs = config.get("input") if isinstance(config, Mapping) else {}
    inputs = inputs if isinstance(inputs, Mapping) else {}

    def _catalog(key: str) -> list[dict[str, Any]]:
        location = inputs.get(key)
        if not location:
            return []
        path = Path(str(location))
        if not path.is_absolute():
            path = ROOT / path
        value = load_json(path)
        return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

    return {
        "office": _catalog("student_office_profiles"),
        "student_service": _catalog("student_service_directory"),
        "faculty": _catalog("student_faculty_profiles"),
    }


def _planner_routing_hint(
    case: Mapping[str, Any],
    catalogs: Mapping[str, list[dict[str, Any]]],
) -> dict[str, Any] | None:
    return find_grounded_catalog_hint(
        str(case.get("query") or ""),
        list(catalogs.get("office") or []),
        list(catalogs.get("student_service") or []),
        list(catalogs.get("faculty") or []),
        cohort=case.get("selected_cohort"),
    )


def _router_error_row(case: Mapping[str, Any], decision: Mapping[str, Any]) -> dict[str, Any]:
    """Represent a router fallback as a provider failure, never as clarify."""

    return {
        "id": case["id"],
        "category": case.get("category"),
        "passed": False,
        "exact_passed": False,
        "semantic_passed": False,
        "failure_type": "provider",
        "provider_failure": True,
        "error_type": str(decision.get("router_error_type") or "router_error"),
        "error_message": str(decision.get("router_error") or "router fallback"),
    }


def _router_cache_row(case: Mapping[str, Any]) -> dict[str, Any]:
    """Fail a live-evaluation row that did not make a model request."""

    return {
        "id": case["id"],
        "category": case.get("category"),
        "passed": False,
        "exact_passed": False,
        "semantic_passed": False,
        "failure_type": "evaluation_integrity",
        # A cache hit is not a transport outage, but treating it as a failed
        # provider row ensures it cannot satisfy the provider-failure release
        # gate or be mistaken for a fresh live-planner outcome.
        "provider_failure": True,
        "error_type": "router_cache_hit",
        "error_message": "Live planner evaluation must not use a router cache.",
    }


def run_live_planner(
    cases: Iterable[dict[str, Any]],
    router: AIRouter | None = None,
    *,
    catalogs: Mapping[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    case_rows = list(cases)
    active_cases = [
        case for case in case_rows if not _is_deterministic_plan_tampering(case)
    ]
    if not active_cases:
        return [_planner_skip_row(case) for case in case_rows]
    try:
        active_router = router or AIRouter.from_config(
            cache_enabled=False, wait_when_limited=True
        )
        active_catalogs = dict(catalogs) if catalogs is not None else _planner_catalogs()
    except Exception as exc:
        return [
            _planner_skip_row(case)
            if _is_deterministic_plan_tampering(case)
            else {
                "id": case["id"],
                "category": case.get("category"),
                "passed": False,
                "exact_passed": False,
                "semantic_passed": False,
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
    for case in tqdm(case_rows, desc="Planner", unit="case", dynamic_ncols=True):
        if _is_deterministic_plan_tampering(case):
            rows.append(_planner_skip_row(case))
            continue
        try:
            decision = active_router.route(
                case["query"],
                chat_history=case.get("chat_history") or [],
                cohort=case.get("selected_cohort"),
                routing_hint=_planner_routing_hint(case, active_catalogs),
            )
            if decision.get("router_error_type") or decision.get("router_error"):
                rows.append(_router_error_row(case, decision))
                continue
            if decision.get("router_cache_hit"):
                rows.append(_router_cache_row(case))
                continue
            bound = _validated_planner_decision(case, decision)
            actual = _plan_from_decision(bound)
            assessment = assess_plan(case["expected"], actual)
            execution_eligible = execution_plan_match(case["expected"], actual)
            rows.append(
                {
                    "id": case["id"],
                    "category": case.get("category"),
                    "passed": assessment.semantic_match,
                    "exact_passed": assessment.exact_match,
                    "semantic_passed": assessment.semantic_match,
                    "execution_eligible": execution_eligible,
                    "mismatch_reasons": list(assessment.mismatch_reasons),
                    "critical_failure": assessment.critical_failure,
                    "failure_type": (
                        "pass"
                        if assessment.exact_match
                        else "representation"
                        if assessment.semantic_match
                        else "planner"
                    ),
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
                    "category": case.get("category"),
                    "passed": False,
                    "exact_passed": False,
                    "semantic_passed": False,
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
    nested = _structured_request_result(result, request)
    if nested is None:
        return False
    actual = {_source_identity(record) for record in nested.get("source_records") or []}
    expected = {
        _source_identity(record)
        for record in request.get("expected_source_records") or []
    }
    requested_field = str((request.get("slots") or {}).get("requested_field") or "")
    if requested_field:
        return bool(expected and expected.intersection(actual))
    return bool(expected and expected <= actual)


def _structured_request_result(
    result: Mapping[str, Any], request: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    structured = result.get("structured_result")
    if not isinstance(structured, Mapping):
        return None
    sub_results = structured.get("sub_results")
    candidates = sub_results or [structured]
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        nested = (
            candidate.get("result")
            if sub_results and isinstance(candidate.get("result"), Mapping)
            else candidate
        )
        request_index = int(str(request["request_id"]).removeprefix("r")) - 1
        candidate_request_id = candidate.get("request_id") or nested.get("request_id")
        candidate_request_index = candidate.get("request_index")
        if candidate_request_index is None:
            candidate_request_index = nested.get("request_index")
        if candidate_request_id not in {None, request["request_id"]}:
            continue
        if candidate_request_index not in {None, request_index}:
            continue
        if not nested.get("source_records") and candidate.get("source_records"):
            return {**nested, "source_records": candidate.get("source_records")}
        return nested
    return None


def _semantic_subset(expected: Any, actual: Any) -> bool:
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            return False
        return all(
            key in actual and _semantic_subset(value, actual[key])
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) > len(actual):
            return False
        unmatched = list(actual)
        for expected_item in expected:
            match_index = next(
                (
                    index
                    for index, actual_item in enumerate(unmatched)
                    if _semantic_subset(expected_item, actual_item)
                ),
                None,
            )
            if match_index is None:
                return False
            unmatched.pop(match_index)
        return True
    return semantic_value_equal(expected, actual)


_STRUCTURED_RANKING_DIAGNOSTICS = {
    "match_score",
    "score_margin",
    "lexical_score",
    "semantic_score",
    "selection_method",
}
_STRUCTURED_RANKING_MARKERS = {
    "lexical_score",
    "semantic_score",
    "selection_method",
}


def _without_structured_ranking_diagnostics(value: Any) -> Any:
    """Remove volatile ranking telemetry while retaining business fields."""

    if isinstance(value, Mapping):
        ranking_record = bool(_STRUCTURED_RANKING_MARKERS.intersection(value))
        return {
            key: _without_structured_ranking_diagnostics(item)
            for key, item in value.items()
            if key not in _STRUCTURED_RANKING_DIAGNOSTICS
            and not (key == "score" and ranking_record)
        }
    if isinstance(value, list):
        return [_without_structured_ranking_diagnostics(item) for item in value]
    return value


def _structured_result_matches(
    result: Mapping[str, Any], request: Mapping[str, Any]
) -> bool:
    expected = request.get("expected_result")
    if expected is None:
        return request.get("expected_status") != "ok"
    actual = _structured_request_result(result, request)
    if actual is None:
        return False
    requested_field = str((request.get("slots") or {}).get("requested_field") or "")
    record_field = REQUESTED_FIELD_RESULT_KEYS.get(requested_field)
    expected_records = expected.get("result")
    actual_records = actual.get("result")
    if (
        record_field
        and isinstance(expected_records, list)
        and expected_records
        and isinstance(actual_records, list)
        and actual_records
    ):
        expected_value = expected_records[0].get(record_field)
        actual_value = actual_records[0].get(record_field)
        return expected_value is not None and _semantic_subset(
            expected_value, actual_value
        )
    # ``input_value`` is an adapter echo of the execution query, not the
    # business result.  A validated standalone/retrieval query may expand the
    # user's wording while resolving to the exact same record.  Comparing this
    # echo made execution accuracy depend on representation.  Source fields are
    # deliberately retained here and are additionally checked by the stricter
    # source-binding gate.
    semantic_expected = _without_structured_ranking_diagnostics(
        {
            key: value
            for key, value in expected.items()
            if key != "input_value"
        }
    )
    return _semantic_subset(semantic_expected, actual)


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


def _final_composition_contract_passed(
    composition: Mapping[str, Any],
) -> bool:
    """Evaluate the rendered answer, while retaining composer degradation telemetry."""

    explicit = composition.get("final_contract_passed")
    request_rows = composition.get("request_results")
    if not isinstance(request_rows, list) or not request_rows:
        return bool(
            explicit
            if isinstance(explicit, bool)
            else composition.get("contract_passed", False)
        )
    if not all(isinstance(row, Mapping) for row in request_rows):
        return False
    computed = all(
        bool(row.get("contract_passed"))
        or bool(
            row.get("request_kind") == "structured"
            and row.get("used_fallback")
            and int(row.get("claim_count") or 0) > 0
        )
        for row in request_rows
    )
    return bool(explicit and computed) if isinstance(explicit, bool) else computed


def run_executor_retrieval(
    cases: Iterable[dict[str, Any]],
    pipeline: AnswerPipeline,
    *,
    planner_rows: Mapping[str, Mapping[str, Any]],
    result_sink: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    case_rows = list(cases)
    for case in tqdm(
        case_rows,
        desc="Executor/retrieval",
        unit="case",
        dynamic_ncols=True,
    ):
        expected = case["expected"]
        if case.get("fault_injection"):
            rows.append(
                {
                    "id": case["id"],
                    "category": case.get("category"),
                    "skipped": True,
                    "semantic_executable": None,
                    "failure_type": "deterministic_fault_suite",
                    "reason": "Fault injection is executed by deterministic adapter tests.",
                }
            )
            continue
        planner_row = planner_rows.get(case["id"])
        if not planner_row or not planner_row.get("execution_eligible"):
            raise ValueError(
                f"Executor received a case without an executable validated plan: {case['id']}"
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
                    "category": case.get("category"),
                    "skipped": True,
                    "plan_correct": True,
                    "status_match": True,
                    "semantic_executable": True,
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
            plan_correct = execution_plan_match(
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
            rag_hits = [_rag_hit_at_5(result, request) for request in rag_ok]
            structured_bindings = [
                _structured_source_bound(result, request) for request in structured_ok
            ]
            structured_results = [
                _structured_result_matches(result, request) for request in structured_ok
            ]
            citation_bindings = [
                _citation_bound(citations, request) for request in structured_ok + rag_ok
            ]
            citation_isolated = _citation_isolated(result, request_ids)
            structured_fallbacks = sum(
                bool(_request_items(result, request["request_id"]))
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
            rows.append(
                {
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
                    "provider_failure": False,
                    "failure_type": "pass" if semantic_executable else "executor",
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "id": case["id"],
                    "category": case.get("category"),
                    "semantic_executable": False,
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
    case_rows = list(cases)
    for case in tqdm(case_rows, desc="Answer", unit="case", dynamic_ncols=True):
        if case.get("fault_injection"):
            continue
        planner_row = planner_rows.get(case["id"])
        if not planner_row or not planner_row.get("execution_eligible"):
            raise ValueError(
                f"Answer composer received a non-executable plan: {case['id']}"
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
            previous_telemetry = os.environ.get("STUDENT_RAG_EVAL_TELEMETRY")
            os.environ["STUDENT_RAG_EVAL_TELEMETRY"] = "1"
            try:
                result = pipeline.answer(
                    case["query"],
                    chat_history=case.get("chat_history") or [],
                    cohort=case.get("selected_cohort"),
                )
            finally:
                if previous_telemetry is None:
                    os.environ.pop("STUDENT_RAG_EVAL_TELEMETRY", None)
                else:
                    os.environ["STUDENT_RAG_EVAL_TELEMETRY"] = previous_telemetry
            model_used = result.get("model_used")
            wrong_model = bool(result.get("llm_called") and model_used != ANSWER_MODEL)
            debug = result.get("debug") or {}
            composition = debug.get("answer_composition") or {}
            composition_provider_failure = bool(
                int(composition.get("provider_failures") or 0)
            )
            expected = case["expected"]
            expected_requests = expected.get("atomic_requests") or []
            request_results = debug.get("request_results") or []
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
            composition_contract_bound = bool(
                not successful_requests
                or _final_composition_contract_passed(composition)
            )
            citations_bound = all(
                _citation_bound(citations, request)
                for request in successful_requests
            )
            request_ids = {request["request_id"] for request in expected_requests}
            plan_bound = semantic_plan_match(
                expected,
                _plan_from_decision(result.get("router_decision") or {}),
            )
            execution_plan_bound = execution_plan_match(
                expected,
                _plan_from_decision(result.get("router_decision") or {}),
            )
            exact_plan_bound = exact_plan_match(
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
                    "partial_status": debug.get("partial_status"),
                    "answer_composition": composition,
                    "evaluation_telemetry": result.get("evaluation_telemetry") or {},
                    "exact_plan_bound": exact_plan_bound,
                    "semantic_plan_bound": plan_bound,
                    "execution_plan_bound": execution_plan_bound,
                    "answer_contract_bound": bool(
                        execution_plan_bound
                        and statuses_bound
                        and citations_bound
                        and _citation_isolated(result, request_ids)
                        and composition_contract_bound
                    ),
                    "provider_failure": bool(
                        wrong_model or composition_provider_failure
                    ),
                    "failure_type": (
                        "wrong_answer_model"
                        if wrong_model
                        else (
                            "answer_provider"
                            if composition_provider_failure
                            else (
                                "answer_contract"
                                if not composition_contract_bound
                                else "pass"
                            )
                        )
                    ),
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
        applicable_rows = [row for row in rows if not row.get("planner_skipped")]
        if applicable_rows:
            metrics[f"{suite}_exact_plan"] = _mean(
                float(row.get("exact_passed", row.get("passed", False)))
                for row in applicable_rows
            )
            metrics[f"{suite}_semantic_plan"] = _mean(
                float(row.get("semantic_passed", row.get("passed", False)))
                for row in applicable_rows
            )
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
        execution_by_id = {str(row.get("id")): row for row in execution_rows}
        for suite, rows in planner_rows.items():
            applicable_rows = [row for row in rows if not row.get("planner_skipped")]
            execution_eligible_ids = {
                str(row.get("id"))
                for row in applicable_rows
                if row.get(
                    "execution_eligible",
                    row.get("semantic_passed", row.get("passed", False)),
                )
            }
            if (
                not execution_eligible_ids
                or not execution_eligible_ids <= set(execution_by_id)
            ):
                continue
            case_scores: list[float] = []
            category_scores: dict[str, list[float]] = {}
            for row in applicable_rows:
                eligible = bool(
                    row.get(
                        "execution_eligible",
                        row.get("semantic_passed", row.get("passed", False)),
                    )
                )
                execution = execution_by_id.get(str(row.get("id"))) if eligible else None
                executable = (
                    conformance_passed is True
                    if execution and execution.get("semantic_executable") is None
                    else bool(execution and execution.get("semantic_executable"))
                )
                score = float(eligible and executable)
                case_scores.append(score)
                category = str(row.get("category") or "unknown")
                category_scores.setdefault(category, []).append(score)
            metrics[f"{suite}_semantic_executable"] = _mean(case_scores)
            per_category = {
                category: _mean(values)
                for category, values in category_scores.items()
            }
            metrics[f"{suite}_semantic_categories"] = per_category
            metrics[f"{suite}_semantic_category_floor"] = min(
                per_category.values(), default=0.0
            )
            safety_values = [
                per_category[name]
                for name in ("cohort_resolution", "failure_isolation")
                if name in per_category
            ]
            if safety_values:
                metrics[f"{suite}_safety_category_floor"] = min(safety_values)
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


def _reuse_answer_report_evaluation(
    answer_report: Mapping[str, Any],
) -> tuple[
    dict[str, list[dict[str, Any]]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    prior_planner = answer_report.get("planner")
    prior_execution = answer_report.get("executor_retrieval")
    answer_rows = answer_report.get("answers")
    if not isinstance(prior_planner, Mapping) or not prior_planner:
        raise ValueError("Answer report is missing Planner evaluation rows")
    planner_rows: dict[str, list[dict[str, Any]]] = {}
    for suite, payload in prior_planner.items():
        if not isinstance(payload, Mapping) or not isinstance(payload.get("rows"), list):
            raise ValueError(f"Answer report has invalid Planner rows for {suite}")
        planner_rows[str(suite)] = list(payload["rows"])
    if not isinstance(prior_execution, Mapping) or not isinstance(
        prior_execution.get("rows"), list
    ):
        raise ValueError("Answer report is missing executor/retrieval rows")
    if not isinstance(answer_rows, list):
        raise ValueError("Answer report is missing answer rows")
    execution_rows = list(prior_execution["rows"])
    answers = list(answer_rows)
    executable_planner_ids = {
        str(row.get("id") or "")
        for rows in planner_rows.values()
        for row in rows
        if row.get(
            "execution_eligible",
            row.get("semantic_passed", row.get("passed", False)),
        )
    }
    execution_ids = {str(row.get("id") or "") for row in execution_rows}
    answer_ids = [str(row.get("id") or "") for row in answers]
    if any(not case_id for case_id in answer_ids):
        raise ValueError("Answer report contains an answer row without an id")
    if len(answer_ids) != len(set(answer_ids)):
        raise ValueError("Answer report contains duplicate answer ids")
    if not set(answer_ids) <= executable_planner_ids:
        raise ValueError("Answer rows are not bound to executable Planner rows")
    if not set(answer_ids) <= execution_ids:
        raise ValueError("Answer rows are not bound to executor/retrieval rows")
    return planner_rows, execution_rows, answers


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


def _legacy_report_is_current_and_passing(report: Mapping[str, Any] | None) -> bool:
    return bool(
        isinstance(report, Mapping)
        and report.get("commit") == _commit()
        and report.get("artifact_fingerprint") == _artifact_fingerprint()
        and report.get("provider") == "live"
        and report.get("passed") is True
    )


def _verify_hidden_development_freeze(
    path: Path | None,
    *,
    dataset_hashes: Mapping[str, str],
    manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """Fail closed unless a current, passing development freeze precedes hidden."""

    if path is None:
        raise ValueError("Hidden evaluation requires --dev-report from a passing frozen development run.")
    report = json.loads(path.read_text(encoding="utf-8"))
    expected = {
        "commit": _commit(),
        "dataset_hashes": dict(dataset_hashes),
        "artifact_fingerprint": _artifact_fingerprint(),
        "prompt_version": ROUTER_PROMPT_VERSION,
        "dataset_prompt_version": manifest.get("prompt_version"),
        "registry_version": manifest.get("registry_version"),
    }
    mismatches = [
        key
        for key, value in expected.items()
        if report.get(key) != value
    ]
    if mismatches:
        raise ValueError(
            "Development report is not bound to the current frozen release inputs: "
            + ", ".join(mismatches)
        )
    if not bool((report.get("development_gates") or {}).get("passed")):
        raise ValueError("Development report did not pass the single-cohort development gates.")
    return report


def _working_tree_is_clean() -> bool:
    return not subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True
    ).strip()


def _development_stage_error(
    *,
    hidden_requested: bool,
    planner: str,
    run_executor: str,
    run_answers: str,
    planner_output: Path | None,
) -> str | None:
    """Keep costly development stages separated by an inspectable checkpoint."""

    if hidden_requested or planner == "none":
        return None
    if planner_output is None:
        return "Development Planner evaluation requires --planner-output."
    if run_executor != "none" or run_answers != "none":
        return (
            "Development Planner must run alone. Inspect its checkpoint, then run "
            "executor/answers separately with --planner-report."
        )
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--planner", choices=("none", "dev", "hidden", "both"), default="none")
    parser.add_argument("--run-executor", choices=("none", "dev", "hidden"), default="none")
    parser.add_argument("--run-answers", choices=("none", "dev", "hidden"), default="none")
    parser.add_argument("--answer-judgments", type=Path)
    parser.add_argument("--answers-report", type=Path)
    parser.add_argument("--confirm-hidden-frozen", action="store_true")
    parser.add_argument("--retry-provider-outage", action="store_true")
    parser.add_argument("--planner-report", type=Path)
    parser.add_argument("--planner-output", type=Path)
    parser.add_argument("--dev-report", type=Path)
    parser.add_argument("--quality-report", type=Path)
    parser.add_argument("--parity-report", type=Path)
    parser.add_argument("--conformance-report", type=Path)
    parser.add_argument("--legacy-compatibility-report", type=Path)
    parser.add_argument("--case-ids-file", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        selected_case_ids = _load_case_ids(args.case_ids_file)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    hidden_requested = (
        args.planner in {"hidden", "both"}
        or args.run_executor == "hidden"
        or args.run_answers == "hidden"
    )
    if hidden_requested and not args.confirm_hidden_frozen:
        parser.error("Hidden evaluation requires --confirm-hidden-frozen after code/prompt/config freeze.")
    if hidden_requested and selected_case_ids is not None:
        parser.error("Hidden evaluation cannot be filtered by case IDs.")

    def selected_cases(suite: str) -> list[dict[str, Any]]:
        cases = _load_cases(suite)
        if selected_case_ids is None:
            return cases
        available = {str(case.get("id")) for case in cases}
        missing = selected_case_ids - available
        if missing:
            parser.error(
                "Unknown case IDs for " + suite + ": " + ", ".join(sorted(missing))
            )
        return [case for case in cases if str(case.get("id")) in selected_case_ids]
    if hidden_requested and args.planner_output is not None:
        parser.error(
            "Planner checkpoints are development-only; hidden must remain one sealed attempt."
        )
    stage_error = _development_stage_error(
        hidden_requested=hidden_requested,
        planner=args.planner,
        run_executor=args.run_executor,
        run_answers=args.run_answers,
        planner_output=args.planner_output,
    )
    if stage_error:
        parser.error(stage_error)
    if hidden_requested and not (
        args.planner == "hidden"
        and args.run_executor == "hidden"
        and args.run_answers == "hidden"
    ):
        parser.error(
            "Hidden release evaluation must run Planner, executor/retrieval and "
            "answers together in one attempt."
        )
    if (
        args.run_executor != "none"
        and not args.planner_report
        and args.planner not in {args.run_executor, "both"}
    ):
        parser.error("Executor/retrieval evaluation requires Planner evaluation or --planner-report for the same split.")
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
        legacy_passed = _legacy_report_is_current_and_passing(legacy_report)
    if hidden_requested and not (
        manifest.get("hidden_frozen")
        and manifest.get("hidden_human_review_complete")
    ):
        parser.error("Hidden is not human-approved and frozen.")
    if hidden_requested and not validation.valid:
        parser.error("Hidden evaluation requires a valid frozen single-cohort bundle.")
    if hidden_requested:
        try:
            _verify_hidden_development_freeze(
                args.dev_report,
                dataset_hashes=validation.hashes,
                manifest=manifest,
            )
            if quality_passed is not True:
                raise ValueError("Hidden evaluation requires a current passing quality report.")
            if parity_passed is not True:
                raise ValueError("Hidden evaluation requires a current passing deterministic parity report.")
            if conformance_passed is not True:
                raise ValueError("Hidden evaluation requires a current passing deterministic conformance report.")
            if legacy_passed is not True:
                raise ValueError("Hidden evaluation requires a current passing legacy compatibility report.")
            if not _working_tree_is_clean():
                raise ValueError("Hidden evaluation requires a clean worktree after code/prompt/config/index freeze.")
        except ValueError as exc:
            parser.error(str(exc))
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
    if args.planner_report:
        try:
            planner_rows.update(
                _load_bound_planner_report(
                    args.planner_report,
                    manifest=manifest,
                    validation=validation,
                )
            )
        except ValueError as exc:
            parser.error(str(exc))
    if validation.valid and args.planner != "none":
        suites = ("dev", "hidden") if args.planner == "both" else (args.planner,)
        for suite in suites:
            planner_rows[suite] = run_live_planner(selected_cases(suite))
        if args.planner_output is not None:
            _write_json_atomic(
                args.planner_output,
                _planner_checkpoint_report(
                    planner_rows,
                    manifest=manifest,
                    validation=validation,
                ),
            )

    pipeline: AnswerPipeline | None = None
    execution_rows: list[dict[str, Any]] = []
    execution_results: dict[str, dict[str, Any]] = {}
    answer_rows: list[dict[str, Any]] = []
    if validation.valid and (args.run_executor != "none" or args.run_answers != "none"):
        pipeline = AnswerPipeline()
        if args.run_answers != "none":
            pipeline.response_cache.enabled = False
    if pipeline and args.run_executor != "none":
        passed_ids = {
            row["id"]
            for row in planner_rows.get(args.run_executor, [])
            if row.get(
                "execution_eligible",
                row.get("semantic_passed", row.get("passed", False)),
            )
        }
        execution_rows = run_executor_retrieval(
            [case for case in selected_cases(args.run_executor) if case["id"] in passed_ids],
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
            if row.get(
                "execution_eligible",
                row.get("semantic_passed", row.get("passed", False)),
            )
        }
        answer_rows = run_answers(
            [case for case in selected_cases(args.run_answers) if case["id"] in passed_ids],
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
        if answer_report.get("artifact_fingerprint") != _artifact_fingerprint():
            parser.error("Answer report artifact fingerprint does not match current inputs.")
        if (answer_report.get("models") or {}).get("answer") != ANSWER_MODEL:
            parser.error("Answer report does not use the pinned answer model.")
        try:
            prior_planner_rows, prior_execution_rows, answer_rows = (
                _reuse_answer_report_evaluation(answer_report)
            )
        except ValueError as exc:
            parser.error(str(exc))
        if not planner_rows:
            planner_rows = prior_planner_rows
        if not execution_rows:
            execution_rows = prior_execution_rows
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
        "evaluation_protocol_version": EVALUATION_PROTOCOL_VERSION,
        "models": {"planner": PLANNER_MODEL, "answer": ANSWER_MODEL, "judge": JUDGE_MODEL},
        "evaluation_scope": {
            "filtered": selected_case_ids is not None,
            "case_ids": sorted(selected_case_ids or []),
            "case_count": len(selected_case_ids or []),
            "answer_architecture": "request_scoped_composer_no_verifier",
        },
        "judge_prompt_version": JUDGE_PROMPT_VERSION,
        "prompt_version": ROUTER_PROMPT_VERSION,
        "dataset_prompt_version": manifest.get("prompt_version"),
        "registry_version": manifest.get("registry_version"),
        "dataset_hashes": validation.hashes,
        "artifact_fingerprint": _artifact_fingerprint(),
        "contract": {"passed": validation.valid, "errors": validation.errors, "coverage": validation.coverage},
        "planner": {
            suite: _planner_section(rows)
            for suite, rows in planner_rows.items()
        },
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
    _write_json_atomic(output, report)
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
