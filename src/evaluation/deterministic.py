"""Deterministic suite: grade the query plan and structured execution
against each case's accepted outcomes (V9 contract)."""

from __future__ import annotations

import os
import re
import time
import traceback
import unicodedata
from pathlib import Path
from typing import Any, Callable

from .dataset import DETERMINISTIC_CONTRACT
from .metrics import (
    safe_mean,
)
from .shared import (
    case_history_kwargs,
    cohort_matches,
    eval_checkpoint_identity,
    load_eval_checkpoint,
    progress_cases,
    restore_env,
    save_eval_checkpoint,
    wait_for_bm25_ready,
)


def _structured_citations(structured: dict[str, Any]) -> list[dict[str, Any]]:
    if not structured:
        return []
    source_ids = structured.get("source_parent_ids") or []
    if isinstance(source_ids, str):
        source_ids = [source_ids]
    source_id = (
        structured.get("source_parent_id")
        or structured.get("parent_section_id")
        or structured.get("source_section")
        or structured.get("source_record_id")
    )
    if source_id:
        source_ids = [source_id, *list(source_ids)]
    seen: set[str] = set()
    citations: list[dict[str, Any]] = []
    for item in source_ids:
        parent_id = str(item or "")
        if not parent_id or parent_id in seen:
            continue
        seen.add(parent_id)
        citations.append(
            {
                "parent_section_id": parent_id,
                "source_record_id": parent_id,
                "cohort": structured.get("cohort"),
                "chunk_type": structured.get("content_type"),
                "metadata": {
                    "parent_section_id": parent_id,
                    "source_record_id": parent_id,
                    "cohort": structured.get("cohort"),
                    "content_type": structured.get("content_type"),
                    "document_id": structured.get("document_id"),
                },
            }
        )
    return citations


def evaluate_deterministic(
    cases: list[dict[str, Any]],
    *,
    limit: int | None = None,
    evaluation_contract: str = DETERMINISTIC_CONTRACT,
    checkpoint_path: Path | None = None,
    resume: bool = False,
    pipeline_factory: Callable[[], Any] | None = None,
    checkpoint_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score planning and execution against each case's accepted outcomes (V9 contract)."""
    previous_cache = os.environ.get("STUDENT_RAG_DISABLE_ROUTER_CACHE")
    os.environ["STUDENT_RAG_DISABLE_ROUTER_CACHE"] = "1"
    try:
        return _evaluate_deterministic_uncached(
            cases,
            limit=limit,
            evaluation_contract=evaluation_contract,
            checkpoint_path=checkpoint_path,
            resume=resume,
            pipeline_factory=pipeline_factory,
            checkpoint_context=checkpoint_context,
        )
    finally:
        restore_env("STUDENT_RAG_DISABLE_ROUTER_CACHE", previous_cache)


def _normalized_contract_value(value: Any) -> Any:
    if isinstance(value, str):
        text = unicodedata.normalize("NFD", value.casefold())
        text = "".join(char for char in text if unicodedata.category(char) != "Mn")
        return " ".join(text.replace("đ", "d").split())
    if isinstance(value, list):
        return sorted(str(_normalized_contract_value(item)) for item in value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return format(value, ".15g")
    return value


def _task_matches(gold: dict[str, Any], actual: dict[str, Any]) -> bool:
    """Match only architecture-significant task fields declared by the gold."""

    for field in ("mode", "lookup_type", "cohorts"):
        if field in gold and _normalized_contract_value(actual.get(field)) != (
            _normalized_contract_value(gold[field])
        ):
            return False
    allowed_intents = gold.get("allowed_intents") or []
    if allowed_intents and actual.get("intent") not in allowed_intents:
        return False
    slots = actual.get("slots") or {}
    if not set(gold.get("required_slot_keys") or []) <= set(slots):
        return False
    for key, alternatives in (gold.get("slot_value_alternatives") or {}).items():
        if not isinstance(alternatives, list):
            alternatives = [alternatives]
        if key not in slots or _normalized_contract_value(slots[key]) not in [
            _normalized_contract_value(item) for item in alternatives
        ]:
            return False
    return True


def _required_tasks_match(
    required: list[dict[str, Any]], actual: list[dict[str, Any]]
) -> bool:
    """Injectively match required semantic tasks to an unordered actual plan."""

    def visit(index: int, used: set[int]) -> bool:
        if index >= len(required):
            return True
        return any(
            visit(index + 1, used | {actual_index})
            for actual_index, task in enumerate(actual)
            if actual_index not in used and _task_matches(required[index], task)
        )

    return len(required) <= len(actual) and visit(0, set())


def _has_task_evidence(
    task_results: list[dict[str, Any]], *, mode: str, lookup_type: str | None = None
) -> bool:
    for task in task_results:
        if task.get("mode") != mode:
            continue
        if lookup_type and task.get("lookup_type") != lookup_type:
            continue
        if task.get("coverage") == "covered" and bool(task.get("evidence")):
            return True
    return False


def _nested_mappings(value: Any) -> list[dict[str, Any]]:
    mappings: list[dict[str, Any]] = []
    if isinstance(value, dict):
        mappings.append(value)
        for child in value.values():
            mappings.extend(_nested_mappings(child))
    elif isinstance(value, list):
        for child in value:
            mappings.extend(_nested_mappings(child))
    return mappings


_PUBLIC_EVIDENCE_FIELDS: dict[str, set[str]] = {
    "formula": {"rule_id", "rule_name", "formula_text", "source_article"},
    "office": {
        "cohort",
        "unit_name",
        "phone",
        "email",
        "website",
        "office",
        "source_section",
    },
    "faculty": {
        "cohort",
        "unit_name",
        "phone",
        "email",
        "website",
        "office",
        "source_section",
    },
    "program": {
        "program_name",
        "faculty_name",
        "cohort",
        "source_section",
        "faculty_name_source",
    },
    "student_service": {
        "service_id",
        "cohort",
        "service",
        "unit_name",
        "phone",
        "email",
        "website",
        "office",
    },
}


_PUBLIC_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "phone": ("phone", "phones"),
    "email": ("email", "emails"),
    "website": ("website", "websites"),
    "Loại": ("Loại", "status"),
    "Thang điểm 10": ("Thang điểm 10", "score_10_range"),
    "Thang điểm chữ": ("Thang điểm chữ", "letter_grade"),
    # Depending on the scoring table, this public heading denotes either one
    # scalar grade-4 value or the grade-4 interval used for classification.
    "Thang điểm 4": ("Thang điểm 4", "grade_4", "score_4", "range"),
    "Xếp loại": ("Xếp loại", "label", "classification"),
    "Khung điểm": ("Khung điểm", "range", "score_range"),
}


def _contract_scalar(value: Any) -> Any:
    normalized = _normalized_contract_value(value)
    if not isinstance(normalized, str):
        return normalized
    normalized = re.sub(r"(?<=\d),(?=\d)", ".", normalized)
    normalized = re.sub(r"\s*[-–—]\s*", "-", normalized)

    # Public table schemas may expose a number as a JSON number while the
    # source-grounded gold preserves its localized textual form (for example
    # ``0,0``).  Compare those representations by value, not serialization.
    if re.fullmatch(r"[+-]?\d+(?:\.\d+)?", normalized):
        return format(float(normalized), ".15g")

    # Range labels are rendered differently by source tables and resolvers:
    # Equivalent lower-bound phrases should produce the same interval.
    # Remove presentation-only words while preserving semantic qualifiers such
    # Preserve meaningful distinctions between open and closed bounds.
    if re.search(r"\d", normalized) and (
        "-" in normalized or re.search(r"\b(?:tu|den|duoi|tren|diem)\b", normalized)
    ):
        normalized = re.sub(r"\b(?:tu|den|diem)\b", " ", normalized)
        normalized = normalized.replace("-", " ")
        return " ".join(normalized.split())

    return normalized


def _contract_values_equal(actual: Any, expected: Any) -> bool:
    if isinstance(actual, list):
        actual_values = {_contract_scalar(item) for item in actual}
        if isinstance(expected, str) and ";" in expected:
            expected_values = {
                _contract_scalar(item) for item in expected.split(";") if item.strip()
            }
            return actual_values == expected_values
        return _contract_scalar(expected) in actual_values
    return _contract_scalar(actual) == _contract_scalar(expected)


def _observable_expected_fields(
    expected: dict[str, Any], *, lookup_type: str | None
) -> dict[str, Any]:
    allowed = _PUBLIC_EVIDENCE_FIELDS.get(str(lookup_type or ""))
    if allowed is None:
        return expected
    return {key: value for key, value in expected.items() if key in allowed}


def _mapping_contains_fields(
    value: Any,
    expected: dict[str, Any],
    *,
    lookup_type: str | None = None,
) -> bool:
    """Match stable public evidence fields across equivalent API schemas."""

    observable = _observable_expected_fields(expected, lookup_type=lookup_type)
    if not observable:
        return False

    def field_matches(mapping: dict[str, Any], key: str, expected_value: Any) -> bool:
        aliases = _PUBLIC_FIELD_ALIASES.get(key, (key,))
        return any(
            alias in mapping and _contract_values_equal(mapping[alias], expected_value)
            for alias in aliases
        )

    return any(
        all(
            field_matches(mapping, key, expected_value)
            for key, expected_value in observable.items()
        )
        for mapping in _nested_mappings(value)
    )


def _structured_source_identities(value: Any) -> set[str]:
    identities: set[str] = set()
    identity_keys = {
        "table_id",
        "source_id",
        "source_record_id",
        "source_parent_id",
        "source_section",
        "parent_section_id",
        "record_id",
        "service_id",
        "office_profile_id",
        "faculty_profile_id",
    }
    for mapping in _nested_mappings(value):
        for key in identity_keys:
            raw = mapping.get(key)
            if isinstance(raw, str) and raw.strip():
                identities.add(raw.strip())
        parent_id = str(mapping.get("source_parent_id") or "").strip()
        subtype = str(mapping.get("table_subtype") or "").strip()
        if parent_id and subtype:
            identities.add(f"{parent_id}_{subtype}")
        cohort = str(mapping.get("cohort") or "").strip()
        record_id = str(mapping.get("record_id") or "").strip()
        if cohort and record_id:
            identities.add(f"{cohort}_{record_id}")
    return identities


def _task_execution_checks(
    expected: dict[str, Any], task_results: list[dict[str, Any]]
) -> dict[str, bool | None]:
    """Check only grounded structured assertions declared by one V8 task gold."""

    if expected.get("execution_units"):
        checks = []
        for unit in expected["execution_units"]:
            cohort = unit["cohorts"][0]
            scoped_results = []
            for task in task_results:
                if task.get("mode") != expected.get("mode") or task.get(
                    "lookup_type"
                ) != expected.get("lookup_type"):
                    continue
                # Only the execution envelope establishes which cohort was
                # looked up. Document applicability is not result provenance.
                evidence = [
                    item
                    for item in task.get("evidence", [])
                    if isinstance(item, dict) and item.get("cohort") == cohort
                ]
                scoped_results.append(
                    {**task, "cohorts": [cohort], "evidence": evidence}
                )
            checks.append(_task_execution_checks(unit, scoped_results))
        return {
            key: (all(values) if values else None)
            for key in ("source", "evidence_fields", "resolved_result")
            for values in [[c[key] for c in checks if c[key] is not None]]
        }

    source_ids = set(expected.get("expected_source_ids") or [])
    evidence_fields = expected.get("expected_evidence_fields")
    evidence_rows = expected.get("expected_evidence_rows") or []
    resolved_fields = expected.get("expected_resolved_fields")
    resolved_required = expected.get("resolved_result_required")
    if expected.get("fact_lock_applicable") is False:
        resolved_fields = None
        resolved_required = None
    applicable = bool(
        source_ids or evidence_fields or evidence_rows or resolved_fields
    ) or (resolved_required is not None)
    if not applicable:
        return {"source": None, "evidence_fields": None, "resolved_result": None}

    candidates = [
        task
        for task in task_results
        if task.get("mode") == expected.get("mode")
        and (
            not expected.get("lookup_type")
            or task.get("lookup_type") == expected.get("lookup_type")
        )
        and (
            not expected.get("cohorts")
            or not task.get("cohorts")
            or _normalized_contract_value(task["cohorts"])
            == _normalized_contract_value(expected["cohorts"])
        )
    ]
    # Formula, office/faculty profiles, and program rows intentionally expose
    # stable public fields instead of the ingestion-only record identifiers used
    # by older artifacts. Their identity is therefore checked by the grounded
    # row contract below, while table/service IDs remain directly assertable.
    source_id_is_public = expected.get("lookup_type") not in {
        "formula",
        "office",
        "faculty",
        "program",
    }
    source_ok = (
        any(source_ids <= _structured_source_identities(task) for task in candidates)
        if source_ids and source_id_is_public
        else None
    )
    evidence_ok = (
        any(
            _mapping_contains_fields(
                task.get("evidence") or [],
                evidence_fields,
                lookup_type=expected.get("lookup_type"),
            )
            for task in candidates
        )
        if evidence_fields
        else None
    )
    if evidence_rows:
        rows_ok = any(
            all(
                _mapping_contains_fields(
                    task.get("evidence") or [],
                    row,
                    lookup_type=expected.get("lookup_type"),
                )
                for row in evidence_rows
            )
            for task in candidates
        )
        evidence_ok = rows_ok if evidence_ok is None else evidence_ok and rows_ok
    resolved_values = [
        _resolved_fact_payload(mapping.get("resolved_result"))
        for task in candidates
        for mapping in _nested_mappings(task.get("evidence") or [])
        if mapping.get("resolved_result") is not None
    ]
    if resolved_fields:
        resolved_ok: bool | None = any(
            _mapping_contains_fields(
                value,
                resolved_fields,
                lookup_type=expected.get("lookup_type"),
            )
            for value in resolved_values
        )
    elif resolved_required is not None:
        resolved_ok = bool(resolved_values) == bool(resolved_required)
    else:
        resolved_ok = None
    return {
        "source": source_ok,
        "evidence_fields": evidence_ok,
        "resolved_result": resolved_ok,
    }


def _resolved_fact_payload(value: Any) -> Any:
    """Exclude full display tables from a fact-lock correctness assertion."""
    if isinstance(value, dict):
        return {
            key: _resolved_fact_payload(child)
            for key, child in value.items()
            if key not in {"display_rows", "display_items", "sub_lookups"}
        }
    if isinstance(value, list):
        return [_resolved_fact_payload(child) for child in value]
    return value


def _bound_execution_results(expected, tasks, task_results):
    """Bind execution to semantic plan matches, never to another task's payload."""
    ids = {
        task.get("id")
        for task in tasks
        if task.get("id") and _task_matches(expected, task)
    }
    return [result for result in task_results if result.get("task_id") in ids]


def _evaluate_outcome_case(
    case: dict[str, Any], result: dict[str, Any], *, started: float
) -> dict[str, Any]:
    """Evaluate one case against its declared safe outcomes."""

    plan = result.get("query_plan") or {}
    tasks = plan.get("tasks") if isinstance(plan, dict) else []
    tasks = tasks if isinstance(tasks, list) else []
    task_results = result.get("task_results") or []
    # Execution may discover missing input after a valid structured plan.
    # Accept clarification only when bound to this task and every target cohort,
    # with an actual question; a bare status or sibling question is insufficient.
    executed_clarifications = {
        task.get("id")
        for task in tasks
        if task.get("id")
        and task.get("cohorts")
        and any(
            execution.get("task_id") == task["id"]
            and execution.get("coverage") == "needs_clarification"
            and all(
                execution.get("coverage_by_cohort", {}).get(cohort)
                == "needs_clarification"
                and str(
                    execution.get("clarification_by_cohort", {}).get(cohort) or ""
                ).strip()
                for cohort in task["cohorts"]
            )
            for execution in task_results
        )
    }
    has_clarification_question = bool(executed_clarifications) or any(
        str(value or "").strip()
        for value in (
            result.get("clarification_question"),
            plan.get("clarification_question"),
            *(task.get("clarification_question") for task in tasks),
        )
    )
    tasks = [
        {**task, "mode": "clarify"}
        if task.get("id") in executed_clarifications
        else task
        for task in tasks
    ]
    actual_modes = [str(task.get("mode") or "") for task in tasks]
    actual_lookup_types = sorted(
        {
            str(task.get("lookup_type") or "")
            for task in tasks
            if task.get("lookup_type")
        }
    )
    actual_cohorts = sorted(
        {
            str(cohort)
            for task in tasks
            for cohort in (task.get("cohorts") or [])
            if cohort
        }
    )
    structured = (
        result.get("structured_result")
        or result.get("formula_result")
        or result.get("tool_result")
        or {}
    )
    citations = result.get("citations") or _structured_citations(structured)
    has_structured_payload = _has_structured_payload(structured)
    has_rag_evidence = bool(citations) or any(
        task.get("mode") == "rag"
        and task.get("coverage") == "covered"
        and bool(task.get("evidence"))
        for task in task_results
    )
    needs_clarification = bool(result.get("needs_clarification")) or any(
        task.get("mode") == "clarify" for task in tasks
    )
    out_of_domain = bool(plan.get("out_of_domain"))

    evaluations: list[dict[str, Any]] = []
    for outcome in case.get("accepted_outcomes") or []:
        allowed_modes = set(outcome.get("allowed_modes") or [])
        mode_ok = not allowed_modes or all(
            mode in allowed_modes for mode in actual_modes
        )
        count = outcome.get("task_count") or {}
        count_ok = int(count.get("min", 0)) <= len(tasks) <= int(count.get("max", 3))
        required_tasks = outcome.get("required_tasks") or []
        semantics_ok = _required_tasks_match(required_tasks, tasks)
        state = outcome.get("state")
        state_ok = (
            state == "answer"
            and not needs_clarification
            and not out_of_domain
            or state == "clarify"
            and needs_clarification
            or state == "out_of_domain"
            and out_of_domain
            or state == "safe_unavailable"
            and (
                needs_clarification
                or out_of_domain
                or not has_structured_payload
                and not has_rag_evidence
            )
        )
        required_structured = [
            task for task in required_tasks if task.get("mode") == "structured"
        ]
        structured_execution_ok = all(
            _has_task_evidence(
                task_results,
                mode="structured",
                lookup_type=str(task.get("lookup_type") or "") or None,
            )
            for task in required_structured
        )
        if outcome.get("structured_evidence") == "required":
            has_required_task_evidence = bool(required_structured) and (
                structured_execution_ok
            )
            structured_execution_ok = structured_execution_ok and (
                has_structured_payload or has_required_task_evidence
            )
        rag_evidence_ok = (
            has_rag_evidence if outcome.get("rag_evidence") == "required" else True
        )
        task_execution_checks = [
            _task_execution_checks(
                task,
                _bound_execution_results(task, tasks, task_results)
                if case.get("bind_execution_to_plan")
                else task_results,
            )
            for task in required_structured
        ]

        def combined_check(name: str) -> bool | None:
            values = [
                item[name]
                for item in task_execution_checks
                if item.get(name) is not None
            ]
            return all(values) if values else None

        checks: dict[str, bool | None] = {
            "state": state_ok,
            "task_count": count_ok,
            "task_modes": mode_ok,
            "task_semantics": semantics_ok,
            "structured_execution": structured_execution_ok,
            "rag_evidence": rag_evidence_ok,
            "structured_source": combined_check("source"),
            "structured_row": combined_check("evidence_fields"),
            "resolved_result": combined_check("resolved_result"),
            "clarification_question": (
                has_clarification_question
                if outcome.get("clarification_question_required")
                else None
            ),
        }
        evaluations.append(
            {
                "name": outcome.get("name"),
                "checks": checks,
                "passed": all(
                    bool(value) for value in checks.values() if value is not None
                ),
            }
        )

    selected = next((item for item in evaluations if item["passed"]), None)
    best = selected or max(
        evaluations,
        key=lambda item: sum(
            bool(value) for value in item["checks"].values() if value is not None
        ),
        default={"name": None, "checks": {}},
    )
    checks = best.get("checks") or {}
    expected_citation_cohort = case.get("expected_citation_cohort")
    citation_ok: bool | None = None
    cross_cohort_leak = False
    if expected_citation_cohort and citations:
        citation_ok = all(
            cohort_matches(
                citation.get("cohort")
                or (citation.get("metadata") or {}).get("cohort"),
                expected_citation_cohort,
            )
            for citation in citations
        )
        cross_cohort_leak = not citation_ok

    return {
        **case,
        "query_plan": plan,
        "router_usage": result.get("router_usage"),
        "task_results": task_results,
        "structured_result": structured,
        "citations": citations,
        "actual_task_modes": actual_modes,
        "actual_lookup_types": actual_lookup_types,
        "actual_cohorts": actual_cohorts,
        "accepted_outcome_evaluations": evaluations,
        "matched_outcome": selected.get("name") if selected else None,
        "task_count_correct": checks.get("task_count"),
        "task_modes_correct": checks.get("task_modes"),
        "task_semantics_correct": checks.get("task_semantics"),
        "out_of_domain_correct": checks.get("state") if out_of_domain else None,
        "clarification_correct": checks.get("state") if needs_clarification else None,
        "planner_fallback_free": not bool(result.get("planner_fallback")),
        "structured_execution_correct": checks.get("structured_execution"),
        "structured_evidence_present": (
            has_structured_payload
            if any(
                outcome.get("structured_evidence") == "required"
                for outcome in case.get("accepted_outcomes") or []
            )
            else None
        ),
        "citation_metadata_correct": citation_ok,
        "cross_cohort_leak": cross_cohort_leak,
        "structured_source_correct": checks.get("structured_source"),
        "structured_row_correct": checks.get("structured_row"),
        "resolved_result_correct": checks.get("resolved_result"),
        "outcome_contract_correct": bool(selected),
        "passed": bool(selected) and not bool(result.get("planner_fallback")),
        "latency_ms": (time.perf_counter() - started) * 1000,
    }


def _evaluate_deterministic_uncached(
    cases: list[dict[str, Any]],
    *,
    limit: int | None,
    evaluation_contract: str,
    checkpoint_path: Path | None,
    resume: bool,
    pipeline_factory: Callable[[], Any] | None,
    checkpoint_context: dict[str, Any] | None,
) -> dict[str, Any]:
    unsupported = sorted(
        {str(case.get("contract_version")) for case in cases[:limit]}
        - {DETERMINISTIC_CONTRACT}
    )
    if unsupported:
        raise ValueError(f"Unsupported deterministic contract(s): {unsupported}")
    uses_default_pipeline = pipeline_factory is None
    if pipeline_factory is None:
        from src.generation.answer_pipeline import AnswerPipeline

        pipeline_factory = AnswerPipeline
    identity = (
        eval_checkpoint_identity(
            cases,
            suite="deterministic",
            context=checkpoint_context,
            evaluation_contract=evaluation_contract,
        )
        if checkpoint_path
        else None
    )
    rows = load_eval_checkpoint(checkpoint_path, resume=resume, identity=identity)
    completed_ids = {row["id"] for row in rows}
    pipeline = pipeline_factory()
    capture_planner_diagnostics = bool(
        (checkpoint_context or {}).get("capture_planner_diagnostics")
    )
    from src.retrieval.core.ai_router import planner_diagnostics_scope

    if uses_default_pipeline:
        from src.retrieval.core.hybrid_pipeline import initialize_hybrid_retriever

        initialize_hybrid_retriever()
        wait_for_bm25_ready()
    progress = progress_cases(cases, limit=limit, desc="Deterministic eval")
    for case in progress:
        progress.set_postfix_str(str(case.get("id") or "unknown"))
        if case["id"] in completed_ids:
            continue
        started = time.perf_counter()
        result = None
        try:
            retrieval_kwargs = {
                "cohort": case.get("cohort"),
                **case_history_kwargs(case),
            }
            capture_case_diagnostics = capture_planner_diagnostics and not bool(
                retrieval_kwargs.get("chat_history")
            )
            with planner_diagnostics_scope(capture_case_diagnostics):
                result = pipeline._run_retrieval(case["query"], **retrieval_kwargs)
            row = _evaluate_outcome_case(case, result, started=started)
            if capture_case_diagnostics:
                row["planner_diagnostics"] = result.get("planner_diagnostics")
            rows.append(row)
            progress.set_postfix(
                {
                    "case": case.get("id"),
                    "pass": int(bool(row.get("passed"))),
                    "outcome": row.get("matched_outcome") or "none",
                },
                refresh=False,
            )
        except Exception as exc:
            rows.append(
                {
                    **case,
                    "passed": False,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "error_stage": "runtime" if result is None else "evaluator",
                    "raw_result": result,
                    "traceback": traceback.format_exc(),
                    "latency_ms": (time.perf_counter() - started) * 1000,
                }
            )
            progress.set_postfix(
                {"case": case.get("id"), "pass": 0, "error": type(exc).__name__},
                refresh=False,
            )
        finally:
            save_eval_checkpoint(checkpoint_path, rows, identity=identity)

    rows_by_id = {row["id"]: row for row in rows}
    rows = [
        rows_by_id[case["id"]] for case in cases[:limit] if case["id"] in rows_by_id
    ]

    predicted_structured = [
        row for row in rows if "structured" in (row.get("actual_task_modes") or [])
    ]

    def expects_structured(row: dict[str, Any]) -> bool:
        return any(
            task.get("mode") == "structured"
            for outcome in row.get("accepted_outcomes") or []
            for task in outcome.get("required_tasks") or []
        )

    expected_positive_rows = [row for row in rows if expects_structured(row)]
    expected_negative_rows = [row for row in rows if not expects_structured(row)]
    true_positive_n = sum(expects_structured(row) for row in predicted_structured)
    false_positive_n = sum(not expects_structured(row) for row in predicted_structured)
    passed_n = sum(bool(row.get("passed")) for row in rows)

    def assertion_accuracy(field: str) -> float | None:
        values = [row[field] for row in rows if row.get(field) is not None]
        return safe_mean([float(bool(value)) for value in values])

    assertion_fields = {
        "task_semantics": "task_semantics_correct",
        "out_of_domain": "out_of_domain_correct",
        "clarification": "clarification_correct",
        "structured_execution": "structured_execution_correct",
        "structured_evidence": "structured_evidence_present",
        "citation_metadata": "citation_metadata_correct",
        "structured_source": "structured_source_correct",
        "structured_row": "structured_row_correct",
        "resolved_result": "resolved_result_correct",
        "outcome_contract": "outcome_contract_correct",
    }
    summary = {
        "n": len(rows),
        "passed": passed_n,
        "accuracy": passed_n / len(rows) if rows else 0.0,
        "precision": (
            true_positive_n / len(predicted_structured) if predicted_structured else 0.0
        ),
        "recall": true_positive_n / len(expected_positive_rows)
        if expected_positive_rows
        else 0.0,
        "false_positive_rate": false_positive_n / len(expected_negative_rows)
        if expected_negative_rows
        else 0.0,
        "structured_selection_counts": {
            "true_positive": true_positive_n,
            "false_positive": false_positive_n,
            "expected_positive_n": len(expected_positive_rows),
            "expected_negative_n": len(expected_negative_rows),
            "predicted_positive_n": len(predicted_structured),
        },
        "plan_structure_accuracy": safe_mean(
            [
                float(
                    bool(row.get("task_count_correct"))
                    and bool(row.get("task_modes_correct"))
                )
                for row in rows
            ]
        ),
        "task_semantics_accuracy": assertion_accuracy("task_semantics_correct"),
        "out_of_domain_accuracy": assertion_accuracy("out_of_domain_correct"),
        "clarification_accuracy": assertion_accuracy("clarification_correct"),
        "structured_execution_accuracy": assertion_accuracy(
            "structured_execution_correct"
        ),
        "structured_evidence_accuracy": assertion_accuracy(
            "structured_evidence_present"
        ),
        "citation_metadata_accuracy": assertion_accuracy("citation_metadata_correct"),
        "cross_cohort_leak": sum(bool(row.get("cross_cohort_leak")) for row in rows)
        / len(rows)
        if rows
        else 0.0,
        "structured_source_accuracy": assertion_accuracy("structured_source_correct"),
        "structured_row_accuracy": assertion_accuracy("structured_row_correct"),
        "resolved_result_accuracy": assertion_accuracy("resolved_result_correct"),
        "outcome_contract_accuracy": assertion_accuracy("outcome_contract_correct"),
        "assertion_support": {
            name: sum(row.get(field) is not None for row in rows)
            for name, field in assertion_fields.items()
        },
        "planner_fallback_rate": 1.0
        - safe_mean([float(bool(row.get("planner_fallback_free"))) for row in rows]),
    }
    return {
        "suite": "deterministic",
        "evaluation_contract": evaluation_contract,
        "summary": summary,
        "cases": rows,
    }


def _has_structured_payload(value: Any) -> bool:
    """Recognize current structured evidence shapes without semantic guessing.

    Table-first lookups use several deterministic containers: table collections,
    display rows, directory records, and formula records. Metadata alone does not
    count as evidence.
    """
    if isinstance(value, list):
        return bool(value) and any(_has_structured_payload(item) for item in value)
    if not isinstance(value, dict):
        return bool(str(value).strip()) if isinstance(value, str) else False

    for key in ("tables", "rows", "display_rows", "items", "records"):
        items = value.get(key)
        if isinstance(items, list) and items:
            return True

    result = value.get("result")
    if isinstance(result, list) and result:
        return True
    if isinstance(result, dict) and _has_structured_payload(result):
        return True

    # Formula lookup is deterministic structured evidence but is not a table.
    if value.get("lookup_type") == "formula" and value.get("formula_text"):
        return True
    return False
