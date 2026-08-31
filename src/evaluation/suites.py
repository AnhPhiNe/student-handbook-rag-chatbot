from __future__ import annotations

import json
import hashlib
import os
import re
import statistics
import time
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from itertools import permutations
from pathlib import Path
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import request as urllib_request
from tqdm import tqdm

from .dataset import load_json, stable_json_hash
from .judge import GroqJudgeClient, compact_judge_packet
from .metrics import (
    bootstrap_mean_ci,
    percentile,
    retrieval_metrics,
    safe_mean,
    wilson_interval,
)
from src.retrieval.core.runtime_health import get_bm25_runtime_status


ROOT = Path(__file__).resolve().parents[2]
DETERMINISTIC_STRATEGIES = {
    "foreign_language_lookup",
    "study_duration_lookup",
    "scholarship_classification_lookup",
    "student_service_lookup",
    "office_lookup",
    "program_lookup",
    "formula_lookup",
    "structured_lookup",
    "structured_table",
    "multi_structured_lookup",
}
STRUCTURED_STRATEGIES = {"structured_table", "multi_structured_lookup"}
CONTENT_TYPE_ALIASES = {
    "office_directory": {
        "office_directory",
        "student_service_directory",
        "student_office_profile",
    },
    "formula": {"formula", "formula_rule", "structured_lookup"},
}
LOOKUP_TYPE_ALIASES = {
    "scoring": {
        "academic_classification",
        "conduct",
        "conduct_classification",
        "grade_10_to_letter",
        "letter_to_grade4",
        "letter_to_grade_4",
        "pass_fail_ungraded",
        "pass_threshold",
        "scoring",
        "structured_lookup",
    },
    "faculty": {"faculty", "program_directory", "program_topic_faculty"},
}


def _wait_for_bm25_ready(timeout_seconds: float | None = None) -> None:
    """Make answer-quality runs deterministic with respect to BM25 startup.

    Production may deliberately serve dense-only while BM25 initializes. A
    generate/judge benchmark must not let case order decide which retrieval
    stack a question receives, so evaluation fails explicitly if hybrid search
    cannot become ready within a bounded startup window.
    """

    timeout = (
        float(timeout_seconds)
        if timeout_seconds is not None
        else float(os.environ.get("STUDENT_RAG_EVAL_BM25_READY_TIMEOUT_SECONDS", "180"))
    )
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        snapshot = get_bm25_runtime_status()
        status = snapshot["status"]
        if status == "ready":
            return
        if status == "degraded":
            raise RuntimeError(
                "BM25 entered degraded state before answer-quality evaluation "
                f"(error_type={snapshot.get('error_type') or 'unknown'})"
            )
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"BM25 did not become ready within {timeout:.1f}s before evaluation"
            )
        time.sleep(0.25)


def _is_structured_path(
    strategy: str | None,
    structured: dict[str, Any],
    *,
    needs_llm_answer: bool,
) -> bool:
    if not structured:
        return False
    if strategy in STRUCTURED_STRATEGIES:
        return True
    return bool(needs_llm_answer) and strategy in DETERMINISTIC_STRATEGIES


def _router_validation_errors(result: dict[str, Any]) -> list[str]:
    direct_errors = result.get("router_validation_errors")
    if isinstance(direct_errors, list):
        normalized_direct = [
            str(error) for error in direct_errors if str(error).strip()
        ]
        if normalized_direct:
            return normalized_direct

    router_decision = result.get("router_decision")
    if not isinstance(router_decision, dict):
        return []
    nested_errors = router_decision.get("router_validation_errors")
    if not isinstance(nested_errors, list):
        return []
    return [str(error) for error in nested_errors if str(error).strip()]


def _lookup_match_text(structured: dict[str, Any], lookup_type: str) -> str:
    return " ".join(
        str(value or "")
        for value in (
            lookup_type,
            structured.get("lookup_scope"),
            structured.get("source_lookup_type"),
            structured.get("content_type"),
            structured.get("table_type"),
            structured.get("table_subtype"),
            structured.get("source_section"),
            _flatten_text(structured.get("items") or structured.get("result") or []),
        )
    )


def _cohort_matches(actual: Any, expected: str | None) -> bool:
    if not expected or expected == "general":
        return True
    if isinstance(actual, list):
        return expected in actual or (
            expected == "K48-K49" and any(item in actual for item in ("K48", "K49"))
        )
    return (
        str(actual or "") in {expected, "K48", "K49"}
        if expected == "K48-K49"
        else str(actual or "") == expected
    )


def _item_applicability(item: dict[str, Any]) -> Any:
    metadata = item.get("metadata") or {}
    return (
        metadata.get("applicable_cohorts")
        or metadata.get("cohorts")
        or metadata.get("cohort")
    )


def _citation_parent_id(citation: dict[str, Any]) -> str:
    metadata = citation.get("metadata") or {}
    return str(
        citation.get("parent_section_id")
        or citation.get("source_record_id")
        or citation.get("chunk_id")
        or citation.get("_id")
        or metadata.get("parent_section_id")
        or metadata.get("source_record_id")
        or metadata.get("chunk_id")
        or ""
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


def _router_model_from_result(result: dict[str, Any]) -> Any:
    router_decision = result.get("router_decision") or {}
    if not isinstance(router_decision, dict):
        router_decision = {}
    return (
        result.get("router_model")
        or router_decision.get("model_used")
        or router_decision.get("model")
    )


def _router_cache_hit_from_result(result: dict[str, Any]) -> bool:
    router_decision = result.get("router_decision") or {}
    if not isinstance(router_decision, dict):
        router_decision = {}
    return bool(result.get("router_cache_hit") or router_decision.get("cache_hit"))


def _router_api_success_from_result(result: dict[str, Any]) -> bool:
    router_decision = result.get("router_decision") or {}
    if not isinstance(router_decision, dict):
        router_decision = {}
    return bool(_router_model_from_result(result)) and not bool(
        router_decision.get("router_error")
    )


def _content_type_matches(actual: Any, expected: str | None) -> bool:
    if not expected:
        return True
    actual_text = str(actual or "")
    accepted = CONTENT_TYPE_ALIASES.get(expected, {expected})
    return actual_text in accepted


def _lookup_type_matches(actual: Any, expected: str | None) -> bool:
    if not expected:
        return True
    actual_text = str(actual or "")
    accepted = LOOKUP_TYPE_ALIASES.get(expected, {expected})
    return actual_text in accepted


def _item_parent_id(item: dict[str, Any]) -> str:
    metadata = item.get("metadata") or {}
    return str(
        metadata.get("parent_section_id")
        or item.get("parent_section_id")
        or item.get("chunk_id")
        or item.get("_id")
        or metadata.get("chunk_id")
        or ""
    )


def _flatten_text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten_text(item) for item in value.values())
    if isinstance(value, list):
        return " ".join(_flatten_text(item) for item in value)
    return str(value or "")


def _numeric_values(value: Any) -> list[float]:
    if isinstance(value, dict):
        return [number for item in value.values() for number in _numeric_values(item)]
    if isinstance(value, list):
        return [number for item in value for number in _numeric_values(item)]
    if isinstance(value, bool):
        return []
    if isinstance(value, int | float):
        return [float(value)]
    return []


def _structured_expected_ids(value: Any, expected_ids: set[str]) -> list[str]:
    identifiers: set[str] = set()

    def visit(item: Any, key: str = "") -> None:
        if isinstance(item, dict):
            for child_key, child in item.items():
                visit(child, str(child_key))
        elif isinstance(item, list):
            for child in item:
                visit(child, key)
        elif key.endswith("_id") or key in {
            "record_id",
            "service_id",
            "source_section",
        }:
            identifiers.add(str(item or ""))

    visit(value)
    return [
        expected_id
        for expected_id in expected_ids
        if any(identifier and identifier in expected_id for identifier in identifiers)
    ]


def load_runtime_resources(root: Path = ROOT) -> dict[str, Any]:
    paths = {
        "scoring_tables": "data/processed/tables/scoring_tables.json",
        "formula_rules": "data/processed/tables/formula_rules.json",
        "student_service_directory": "data/processed/directories/student_service_directory.json",
        "student_office_profiles": "data/processed/directories/student_office_profiles.json",
        "foreign_language_tables": "data/processed/tables/foreign_language_equivalency_table.json",
        "structured_tables_registry": "data/processed/tables/structured_tables_registry.json",
        "program_directory": "data/processed/directories/program_directory.json",
    }
    return {key: load_json(root / value) for key, value in paths.items()}


def _split_rows(rows: list[dict[str, Any]], split: str) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("eval_split") == split]


def _split_pass_rate(rows: list[dict[str, Any]]) -> float:
    return safe_mean([float(bool(row.get("passed"))) for row in rows])


def _first_retrieval_telemetry(items: list[dict[str, Any]]) -> dict[str, Any]:
    for item in items:
        telemetry = (item.get("metadata") or {}).get("retrieval_telemetry") or {}
        if telemetry:
            return telemetry
    return {}


def _progress_cases(
    cases: list[dict[str, Any]],
    *,
    limit: int | None,
    desc: str,
) -> tqdm:
    selected = cases[:limit]
    return tqdm(selected, desc=desc, unit="case", dynamic_ncols=True)


def evaluate_deterministic(
    cases: list[dict[str, Any]],
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    from src.generation.answer_pipeline import AnswerPipeline

    pipeline = AnswerPipeline()
    previous_router_cache = os.environ.get("STUDENT_RAG_DISABLE_ROUTER_CACHE")
    previous_router_wait = os.environ.get("STUDENT_RAG_ROUTER_WAIT_WHEN_LIMITED")
    os.environ["STUDENT_RAG_DISABLE_ROUTER_CACHE"] = "1"
    os.environ["STUDENT_RAG_ROUTER_WAIT_WHEN_LIMITED"] = "1"
    rows: list[dict[str, Any]] = []
    try:
        progress = _progress_cases(
            cases,
            limit=limit,
            desc="Deterministic Eval",
        )
        for case in progress:
            progress.set_postfix_str(str(case.get("id") or "unknown"))
            started = time.perf_counter()
            try:
                result = pipeline._run_retrieval(
                    case["query"],
                    cohort=case.get("cohort"),
                )
                strategy = result.get("strategy")
                deterministic = (
                    strategy in DETERMINISTIC_STRATEGIES
                    and result.get("needs_llm_answer") is False
                )
                structured = (
                    result.get("structured_result")
                    or result.get("formula_result")
                    or result.get("tool_result")
                    or {}
                )
                needs_llm_answer = bool(result.get("needs_llm_answer"))
                structured_group = _is_structured_path(
                    strategy,
                    structured,
                    needs_llm_answer=needs_llm_answer,
                )
                if result.get("needs_clarification"):
                    actual_group = "clarification"
                elif (
                    result.get("out_of_domain")
                    or result.get("intent") == "out_of_domain"
                ):
                    actual_group = "guardrail"
                elif structured_group:
                    actual_group = "structured"
                else:
                    actual_group = "deterministic" if deterministic else "rag"
                lookup_type = str(
                    structured.get("source_lookup_type")
                    or structured.get("lookup_type")
                    or structured.get("table_type")
                    or structured.get("rule_type")
                    or ""
                )
                lookup_match_text = _lookup_match_text(structured, lookup_type)
                citations = result.get("citations") or _structured_citations(
                    structured
                )
                expected_citation_type = case.get("expected_citation_content_type")
                citation_required = expected_citation_type is not None
                citation_cohort_ok = (bool(citations) or not citation_required) and all(
                    _cohort_matches(
                        c.get("cohort") or (c.get("metadata") or {}).get("cohort"),
                        case.get("expected_citation_cohort"),
                    )
                    for c in citations
                )
                cross_cohort_leak = any(
                    not _cohort_matches(
                        c.get("cohort") or (c.get("metadata") or {}).get("cohort"),
                        case.get("expected_citation_cohort"),
                    )
                    for c in citations
                    if case.get("expected_citation_cohort")
                )
                citation_type_ok = (bool(citations) or not citation_required) and all(
                    _content_type_matches(c.get("chunk_type"), expected_citation_type)
                    or _content_type_matches(
                        (c.get("metadata") or {}).get("content_type"),
                        expected_citation_type,
                    )
                    for c in citations
                )
                flattened = _flatten_text(structured)
                expected_any = case.get("expected_contains_any") or []
                value_exact = not expected_any or any(
                    value.casefold() in flattened.casefold() for value in expected_any
                )
                expected_count = case.get("expected_item_count")
                actual_items = (
                    structured.get("items") if isinstance(structured, dict) else None
                )
                actual_result = (
                    structured.get("result") if isinstance(structured, dict) else None
                )
                actual_item_count = (
                    len(actual_items)
                    if isinstance(actual_items, list)
                    else 1
                    if isinstance(actual_result, dict)
                    else len(actual_result)
                    if isinstance(actual_result, list)
                    else None
                )
                item_count_ok = expected_count is None or (
                    actual_item_count == int(expected_count)
                )
                numeric_expected = case.get("expected_numeric_value")
                tolerance = float(case.get("numeric_tolerance", 0.0))
                numeric_ok = numeric_expected is None or any(
                    abs(number - float(numeric_expected)) <= tolerance
                    for number in _numeric_values(structured)
                )
                expected_group = case["expected_group"]
                accepted_groups = (
                    {"clarification", "rag", "deterministic", "structured"}
                    if expected_group in {"clarification_or_rag", "clarification_or_deterministic", "clarification_or_structured"}
                    else {"structured", "deterministic"}
                    if expected_group in {"structured", "deterministic"}
                    else {expected_group}
                )
                group_ok = actual_group in accepted_groups
                expected_intents = case.get("expected_intents") or [
                    case.get("expected_intent")
                ]
                if expected_group == "rag":
                    intent_ok = actual_group == "rag"
                elif expected_group in {"clarification_or_rag", "clarification_or_deterministic", "clarification_or_structured"}:
                    intent_ok = actual_group in {"clarification", "rag", "deterministic", "structured"}
                elif expected_group == "structured":
                    intent_ok = actual_group in {"structured", "deterministic"}
                else:
                    intent_ok = not any(expected_intents) or result.get(
                        "intent"
                    ) in set(expected_intents)
                expected_strategies = case.get("expected_strategies") or [
                    case.get("expected_strategy")
                ]
                if expected_group == "rag":
                    strategy_ok = actual_group == "rag"
                elif expected_group in {"clarification_or_rag", "clarification_or_deterministic", "clarification_or_structured"}:
                    strategy_ok = actual_group in {"clarification", "rag", "deterministic", "structured"}
                elif expected_group == "structured":
                    if set(expected_strategies) == {"structured_table"}:
                        strategy_ok = actual_group in {"structured", "deterministic"}
                    else:
                        strategy_ok = actual_group in {
                            "structured",
                            "deterministic",
                        } and (
                            not any(expected_strategies)
                            or result.get("strategy") in set(expected_strategies)
                        )
                else:
                    strategy_ok = not any(expected_strategies) or result.get(
                        "strategy"
                    ) in set(expected_strategies)
                fallback_ok = (
                    actual_group not in {"deterministic", "structured"}
                    if expected_group not in {
                        "deterministic",
                        "structured",
                        "clarification_or_rag",
                        "clarification_or_deterministic",
                        "clarification_or_structured",
                    }
                    else True
                )
                expected_llm_called = case.get("expected_llm_called")
                actual_llm_called = bool(result.get("needs_llm_answer"))
                direct_lookup_ok = (
                    expected_group in {"structured", "deterministic"}
                    and actual_group == "deterministic"
                    and actual_llm_called is False
                )
                llm_call_ok = (
                    expected_llm_called is None
                    or actual_llm_called == bool(expected_llm_called)
                    or direct_lookup_ok
                )
                lookup_type_ok = (
                    expected_group not in {"deterministic", "structured"}
                    or not case.get("expected_lookup_type")
                    or case["expected_lookup_type"] in lookup_match_text
                    or _lookup_type_matches(
                        lookup_type, case.get("expected_lookup_type")
                    )
                )
                passed = group_ok and fallback_ok and strategy_ok
                passed = passed and intent_ok
                passed = (
                    passed
                    and citation_cohort_ok
                    and citation_type_ok
                    and lookup_type_ok
                )
                passed = (
                    passed
                    and value_exact
                    and item_count_ok
                    and numeric_ok
                    and llm_call_ok
                )
                router_model = _router_model_from_result(result)
                router_cache_hit = _router_cache_hit_from_result(result)
                router_api_success = _router_api_success_from_result(result)
                rows.append(
                    {
                        **case,
                        "actual_group": actual_group,
                        "actual_intent": result.get("intent"),
                        "actual_strategy": strategy,
                        "actual_lookup_type": lookup_type,
                        "actual_llm_called": actual_llm_called,
                        "structured_result": structured,
                        "citations": citations,
                        "group_correct": group_ok,
                        "intent_correct": intent_ok,
                        "strategy_correct": strategy_ok,
                        "fallback_correct": fallback_ok,
                        "llm_call_correct": llm_call_ok,
                        "lookup_type_correct": lookup_type_ok,
                        "citation_metadata_correct": citation_cohort_ok,
                        "cross_cohort_leak": cross_cohort_leak,
                        "citation_content_type_correct": citation_type_ok,
                        "structured_value_exact": value_exact,
                        "structured_item_count_correct": item_count_ok,
                        "numeric_value_correct": numeric_ok,
                        "router_model": router_model,
                        "router_cache_hit": router_cache_hit,
                        "router_api_success": router_api_success,
                        "router_validation_errors": _router_validation_errors(result),
                        "router_decision": result.get("router_decision") or {},
                        "passed": passed,
                        "latency_ms": (time.perf_counter() - started) * 1000,
                    }
                )
                progress.set_postfix(
                    {
                        "case": case.get("id"),
                        "group": actual_group,
                        "pass": int(passed),
                        "api": int(router_api_success),
                    },
                    refresh=False,
                )
            except Exception as exc:
                rows.append(
                    {
                        **case,
                        "passed": False,
                        "error": str(exc),
                        "latency_ms": (time.perf_counter() - started) * 1000,
                    }
                )
                progress.set_postfix(
                    {
                        "case": case.get("id"),
                        "pass": 0,
                        "error": type(exc).__name__,
                    },
                    refresh=False,
                )
    finally:
        if previous_router_cache is None:
            os.environ.pop("STUDENT_RAG_DISABLE_ROUTER_CACHE", None)
        else:
            os.environ["STUDENT_RAG_DISABLE_ROUTER_CACHE"] = previous_router_cache
        if previous_router_wait is None:
            os.environ.pop("STUDENT_RAG_ROUTER_WAIT_WHEN_LIMITED", None)
        else:
            os.environ["STUDENT_RAG_ROUTER_WAIT_WHEN_LIMITED"] = previous_router_wait

    return {
        "suite": "deterministic",
        "summary": summarize_deterministic_rows(rows),
        "cases": rows,
    }


def evaluate_deterministic_v2(
    cases: list[dict[str, Any]],
    *,
    limit: int | None = None,
    evaluation_contract: str = "query-plan-table-first-v2",
    checkpoint_path: Path | None = None,
    resume: bool = False,
    pipeline_factory: Callable[[], Any] | None = None,
    checkpoint_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate QueryPlan/table-first contracts without legacy route aliases."""
    previous_cache = os.environ.get("STUDENT_RAG_DISABLE_ROUTER_CACHE")
    os.environ["STUDENT_RAG_DISABLE_ROUTER_CACHE"] = "1"
    try:
        return _evaluate_deterministic_v2_uncached(
            cases,
            limit=limit,
            evaluation_contract=evaluation_contract,
            checkpoint_path=checkpoint_path,
            resume=resume,
            pipeline_factory=pipeline_factory,
            checkpoint_context=checkpoint_context,
        )
    finally:
        _restore_env("STUDENT_RAG_DISABLE_ROUTER_CACHE", previous_cache)


def _eval_checkpoint_identity(
    cases: list[dict[str, Any]],
    *,
    suite: str,
    context: dict[str, Any] | None = None,
    **settings: Any,
) -> dict[str, Any]:
    """Bind resume to the dataset and declared run contract.

    ``context`` already carries the frozen commit, dataset/config hashes, model
    settings and collection recorded by the CLI. Hashing the whole source tree,
    package inventory or ambient environment here would add unstable duplicate
    state without improving the benchmark contract.
    """
    return {
        "schema_version": 1,
        "suite": suite,
        "cases_hash": stable_json_hash(cases),
        "settings": settings,
        "context": context or {},
    }


def _load_eval_checkpoint(
    path: Path | None, *, resume: bool, identity: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if path is None:
        return []
    identity_path = path.with_suffix(path.suffix + ".identity.json")
    if not path.exists():
        if identity_path.exists() and load_json(identity_path) != identity:
            raise ValueError(f"Evaluation checkpoint identity mismatch: {path}; use a fresh output path")
        return []
    if not resume:
        raise FileExistsError(f"Refusing to overwrite evaluation checkpoint: {path}; use --resume")
    if identity is None or not identity_path.exists():
        raise ValueError(
            f"Legacy checkpoint has no verifiable identity: {path}. "
            "Keep it as a historical artifact; use a fresh output path or an "
            "explicit legacy compatibility diagnostic, not a headline resume."
        )
    if load_json(identity_path) != identity:
        raise ValueError(f"Evaluation checkpoint identity mismatch: {path}; use a fresh output path")
    rows = load_json(path)
    if (
        not isinstance(rows, list)
        or any(not isinstance(row, dict) or not isinstance(row.get("id"), str) for row in rows)
        or len({row["id"] for row in rows}) != len(rows)
    ):
        raise ValueError(f"Invalid or duplicate checkpoint rows: {path}")
    return rows


def _save_eval_checkpoint(
    path: Path | None, rows: list[dict[str, Any]], *, identity: dict[str, Any] | None,
) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if identity is None:
        raise ValueError("Evaluation checkpoints require an identity")
    identity_path = path.with_suffix(path.suffix + ".identity.json")
    if identity_path.exists():
        if load_json(identity_path) != identity:
            raise ValueError(f"Evaluation checkpoint identity mismatch: {path}")
    else:
        identity_temporary = identity_path.with_suffix(identity_path.suffix + ".tmp")
        identity_temporary.write_text(
            json.dumps(identity, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        identity_temporary.replace(identity_path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    temporary.replace(path)


def _case_history_kwargs(case: dict[str, Any]) -> dict[str, Any]:
    history = case.get("chat_history") or case.get("history")
    return {"chat_history": history} if history else {}


def _expected_tasks_match(expected: list[dict[str, Any]], actual: list[dict[str, Any]]) -> bool:
    """Compare frozen semantic task golds, independent of emission order/IDs."""
    if len(expected) != len(actual):
        return False

    def normalized(value: Any) -> Any:
        if isinstance(value, str):
            # Preserve semantic punctuation: B+ must never compare equal to B.
            text = unicodedata.normalize("NFD", value.casefold())
            text = "".join(char for char in text if unicodedata.category(char) != "Mn")
            return " ".join(text.replace("đ", "d").split())
        if isinstance(value, list):
            return sorted(str(normalized(item)) for item in value)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            # JSON models may emit 367 or "367" for the same schema union.
            return format(value, ".15g")
        return value

    def matches(gold: dict[str, Any], task: dict[str, Any]) -> bool:
        for field in ("mode", "lookup_type", "cohorts"):
            if field in gold and normalized(task.get(field)) != normalized(gold[field]):
                return False
        allowed_intents = gold.get("allowed_intents") or (
            [gold["intent"]] if "intent" in gold else []
        )
        if allowed_intents and task.get("intent") not in allowed_intents:
            return False
        slots = task.get("slots") or {}
        if not set(gold.get("required_slot_keys") or []) <= set(slots):
            return False
        for key, value in (gold.get("slots") or {}).items():
            alternatives = (gold.get("slot_value_alternatives") or {}).get(key) or [value]
            if key not in slots or normalized(slots[key]) not in [normalized(item) for item in alternatives]:
                return False
        return True

    return any(
        all(matches(gold, task) for gold, task in zip(expected, ordering))
        for ordering in permutations(actual)
    )


def _evaluate_deterministic_v2_uncached(
    cases: list[dict[str, Any]],
    *,
    limit: int | None,
    evaluation_contract: str,
    checkpoint_path: Path | None,
    resume: bool,
    pipeline_factory: Callable[[], Any] | None,
    checkpoint_context: dict[str, Any] | None,
) -> dict[str, Any]:
    uses_default_pipeline = pipeline_factory is None
    if pipeline_factory is None:
        from src.generation.answer_pipeline import AnswerPipeline

        pipeline_factory = AnswerPipeline
    identity = _eval_checkpoint_identity(
        cases, suite="deterministic", context=checkpoint_context,
        evaluation_contract=evaluation_contract,
    ) if checkpoint_path else None
    rows = _load_eval_checkpoint(checkpoint_path, resume=resume, identity=identity)
    completed_ids = {row["id"] for row in rows}
    pipeline = pipeline_factory()
    if uses_default_pipeline:
        from src.retrieval.core.hybrid_pipeline import initialize_hybrid_retriever

        initialize_hybrid_retriever()
        _wait_for_bm25_ready()
    progress = _progress_cases(cases, limit=limit, desc="Deterministic Eval V2")
    for case in progress:
        progress.set_postfix_str(str(case.get("id") or "unknown"))
        if case["id"] in completed_ids:
            continue
        started = time.perf_counter()
        try:
            result = pipeline._run_retrieval(
                case["query"], cohort=case.get("cohort"), **_case_history_kwargs(case)
            )
            plan = result.get("query_plan") or {}
            tasks = plan.get("tasks") if isinstance(plan, dict) else []
            tasks = tasks if isinstance(tasks, list) else []
            expected = case.get("expected_plan") or {}
            allowed_modes = set(expected.get("allowed_modes") or [])
            actual_modes = [str(task.get("mode") or "") for task in tasks]
            expected_task_count = int(expected.get("task_count") or 0)
            task_count_ok = len(tasks) == expected_task_count
            task_modes_ok = (
                not allowed_modes
                or bool(actual_modes)
                and all(mode in allowed_modes for mode in actual_modes)
            )
            required_modes = set(expected.get("required_modes") or [])
            task_modes_ok = task_modes_ok and required_modes <= set(actual_modes)
            if expected.get("mode_counts") is not None:
                task_modes_ok = task_modes_ok and dict(Counter(actual_modes)) == expected["mode_counts"]
            task_semantics_ok = (
                _expected_tasks_match(case["expected_tasks"], tasks)
                if "expected_tasks" in case
                else True
            )

            expected_lookup_types = set(expected.get("lookup_types") or [])
            actual_lookup_types = {
                str(task.get("lookup_type") or "")
                for task in tasks
                if task.get("lookup_type")
            }
            lookup_type_ok = (
                not expected_lookup_types
                or actual_lookup_types == expected_lookup_types
            )

            expected_cohorts = set(expected.get("cohorts") or [])
            actual_cohorts = {
                str(cohort)
                for task in tasks
                for cohort in (task.get("cohorts") or [])
                if cohort
            }
            cohort_ok = not expected_cohorts or actual_cohorts == expected_cohorts
            out_of_domain_ok = bool(plan.get("out_of_domain")) == bool(
                expected.get("out_of_domain")
            )

            clarification_expected = bool(expected.get("needs_clarification"))
            clarification_ok = bool(result.get("needs_clarification")) == (
                clarification_expected
            )
            expected_llm_called = case.get("expected_llm_called")
            llm_call_ok = (
                True
                if expected_llm_called is None
                else bool(result.get("needs_llm_answer")) == bool(expected_llm_called)
            )
            fallback_ok = not bool(result.get("planner_fallback"))

            task_results = result.get("task_results") or []
            required_structured = Counter(
                str(task.get("lookup_type") or "")
                for task in case.get("expected_tasks") or []
                if task.get("mode") == "structured"
            )
            covered_structured = Counter(
                str(task.get("lookup_type") or "")
                for task in task_results
                if task.get("mode") == "structured"
                and task.get("coverage") == "covered"
                and bool(task.get("evidence"))
            )
            structured_execution_ok = all(
                covered_structured[lookup_type] >= count
                for lookup_type, count in required_structured.items()
            )

            structured = (
                result.get("structured_result")
                or result.get("formula_result")
                or result.get("tool_result")
                or {}
            )
            # A table-first task may deterministically end in clarification when
            # required components are missing (for example, a four-skill score
            # reported only as a total). Such a task must not fabricate evidence
            # or citations merely to satisfy the structured-path assertion.
            expects_structured = (
                allowed_modes == {"structured"} and not clarification_expected
            )
            structured_evidence_ok = True
            table_first_ok = True
            if expects_structured:
                structured_evidence_ok = bool(structured)
                table_first_ok = _has_structured_payload(structured)

            citations = result.get("citations") or _structured_citations(structured)
            citation_ok = True
            cross_cohort_leak = False
            if expects_structured:
                citation_ok = bool(citations) and all(
                    _cohort_matches(
                        citation.get("cohort")
                        or (citation.get("metadata") or {}).get("cohort"),
                        case.get("expected_citation_cohort"),
                    )
                    for citation in citations
                )
                cross_cohort_leak = any(
                    not _cohort_matches(
                        citation.get("cohort")
                        or (citation.get("metadata") or {}).get("cohort"),
                        case.get("expected_citation_cohort"),
                    )
                    for citation in citations
                )

            flattened = _flatten_text(structured)
            expected_any = case.get("expected_contains_any") or []
            value_exact = not expected_any or any(
                str(value).casefold() in flattened.casefold() for value in expected_any
            )
            numeric_expected = case.get("expected_numeric_value")
            tolerance = float(case.get("numeric_tolerance", 0.0))
            numeric_ok = numeric_expected is None or any(
                abs(number - float(numeric_expected)) <= tolerance
                for number in _numeric_values(structured)
            )

            passed = all(
                (
                    task_count_ok,
                    task_modes_ok,
                    task_semantics_ok,
                    lookup_type_ok,
                    cohort_ok,
                    out_of_domain_ok,
                    clarification_ok,
                    llm_call_ok,
                    fallback_ok,
                    structured_execution_ok,
                    structured_evidence_ok,
                    table_first_ok,
                    citation_ok,
                    value_exact,
                    numeric_ok,
                )
            )
            row = {
                **case,
                "query_plan": plan,
                "task_results": result.get("task_results") or [],
                "structured_result": structured,
                "citations": citations,
                "actual_task_modes": actual_modes,
                "actual_lookup_types": sorted(actual_lookup_types),
                "actual_cohorts": sorted(actual_cohorts),
                "task_count_correct": task_count_ok,
                "task_modes_correct": task_modes_ok,
                "task_semantics_correct": task_semantics_ok,
                "lookup_type_correct": lookup_type_ok,
                "cohort_correct": cohort_ok,
                "out_of_domain_correct": out_of_domain_ok,
                "clarification_correct": clarification_ok,
                "llm_call_correct": llm_call_ok,
                "planner_fallback_free": fallback_ok,
                "structured_execution_correct": structured_execution_ok,
                "structured_evidence_present": structured_evidence_ok,
                "table_first_evidence_present": table_first_ok,
                "citation_metadata_correct": citation_ok,
                "cross_cohort_leak": cross_cohort_leak,
                "structured_value_exact": value_exact,
                "numeric_value_correct": numeric_ok,
                "passed": passed,
                "latency_ms": (time.perf_counter() - started) * 1000,
            }
            rows.append(row)
            progress.set_postfix(
                {"case": case.get("id"), "pass": int(passed)}, refresh=False
            )
        except Exception as exc:
            rows.append(
                {
                    **case,
                    "passed": False,
                    "error": str(exc),
                    "latency_ms": (time.perf_counter() - started) * 1000,
                }
            )
            progress.set_postfix(
                {"case": case.get("id"), "pass": 0, "error": type(exc).__name__},
                refresh=False,
            )
        finally:
            _save_eval_checkpoint(checkpoint_path, rows, identity=identity)

    rows_by_id = {row["id"]: row for row in rows}
    rows = [rows_by_id[case["id"]] for case in cases[:limit] if case["id"] in rows_by_id]

    positives = [
        row
        for row in rows
        if (row.get("evaluation_case_type") or row.get("case_type")) == "positive"
    ]
    predicted_structured = [
        row for row in rows if "structured" in (row.get("actual_task_modes") or [])
    ]
    def expects_structured(row: dict[str, Any]) -> bool:
        gold = row.get("expected_plan") or {}
        return "structured" in (gold.get("allowed_modes") or [])

    expected_positive_rows = [row for row in rows if expects_structured(row)]
    expected_negative_rows = [row for row in rows if not expects_structured(row)]
    true_positive_n = sum(expects_structured(row) for row in predicted_structured)
    false_positive_n = sum(not expects_structured(row) for row in predicted_structured)
    passed_n = sum(bool(row.get("passed")) for row in rows)
    summary = {
        "n": len(rows),
        "passed": passed_n,
        "accuracy": passed_n / len(rows) if rows else 0.0,
        "precision": (
            true_positive_n / len(predicted_structured)
            if predicted_structured
            else 0.0
        ),
        "recall": true_positive_n / len(expected_positive_rows) if expected_positive_rows else 0.0,
        "false_positive_rate": false_positive_n / len(expected_negative_rows) if expected_negative_rows else 0.0,
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
        "lookup_type_accuracy": safe_mean(
            [float(bool(row.get("lookup_type_correct"))) for row in rows]
        ),
        "citation_metadata_accuracy": safe_mean(
            [float(bool(row.get("citation_metadata_correct"))) for row in positives]
        ),
        "cross_cohort_leak": sum(
            bool(row.get("cross_cohort_leak")) for row in rows
        )
        / len(rows)
        if rows
        else 0.0,
        "table_first_evidence_accuracy": safe_mean(
            [float(bool(row.get("table_first_evidence_present"))) for row in positives]
        ),
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


def summarize_deterministic_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        normalized = dict(row)
        nested_errors = _router_validation_errors(normalized)
        if nested_errors:
            normalized["router_validation_errors"] = nested_errors
        else:
            normalized.setdefault("router_validation_errors", [])
        normalized_rows.append(normalized)

    positives = [
        row
        for row in normalized_rows
        if row["expected_group"] in {"deterministic", "structured"}
    ]
    negatives = [
        row
        for row in normalized_rows
        if row["expected_group"] not in {"deterministic", "structured"}
    ]
    tp = sum(
        row.get("actual_group") in {"deterministic", "structured"} for row in positives
    )
    fn = len(positives) - tp
    fp = sum(
        row.get("actual_group") in {"deterministic", "structured"} for row in negatives
    )
    tn = len(negatives) - fp
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    summary = {
        "n": len(normalized_rows),
        "passed": sum(bool(row.get("passed")) for row in normalized_rows),
        "exactness": safe_mean(
            [float(bool(row.get("passed"))) for row in normalized_rows]
        ),
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall)
        if precision + recall
        else 0.0,
        "false_positive_rate": fp / (fp + tn) if fp + tn else 0.0,
        "false_negative_rate": fn / (fn + tp) if fn + tp else 0.0,
        "intent_accuracy": safe_mean(
            [
                float(bool(row.get("intent_correct")))
                for row in rows
                if row.get("expected_intent") is not None
            ]
        ),
        "strategy_accuracy": safe_mean(
            [
                float(bool(row.get("strategy_correct")))
                for row in rows
                if row.get("expected_strategy") is not None
            ]
        ),
        "fallback_correctness": safe_mean(
            [float(bool(row.get("fallback_correct"))) for row in negatives]
        ),
        "llm_call_accuracy": safe_mean(
            [
                float(bool(row.get("llm_call_correct")))
                for row in rows
                if row.get("expected_llm_called") is not None
            ]
        ),
        "citation_metadata_accuracy": safe_mean(
            [float(bool(row.get("citation_metadata_correct"))) for row in positives]
        ),
        "citation_content_type_accuracy": safe_mean(
            [float(bool(row.get("citation_content_type_correct"))) for row in positives]
        ),
        "structured_value_exactness": safe_mean(
            [float(bool(row.get("structured_value_exact"))) for row in positives]
        ),
        "structured_item_count_accuracy": safe_mean(
            [float(bool(row.get("structured_item_count_correct"))) for row in positives]
        ),
        "cross_cohort_leak": sum(
            bool(row.get("cross_cohort_leak")) for row in normalized_rows
        ),
        "router_api_success_rate": safe_mean(
            [float(bool(row.get("router_api_success"))) for row in normalized_rows]
        ),
        "router_cache_hit_rate": safe_mean(
            [float(bool(row.get("router_cache_hit"))) for row in normalized_rows]
        ),
        "router_validation_failure_rate": safe_mean(
            [
                float(bool(row.get("router_validation_errors")))
                for row in normalized_rows
            ]
        ),
        "latency_ms": _latency_summary(
            [row["latency_ms"] for row in normalized_rows]
        ),
        "pass_ci95": wilson_interval(
            sum(bool(row.get("passed")) for row in normalized_rows),
            len(normalized_rows),
        ),
        "realistic_score": _split_pass_rate(
            _split_rows(normalized_rows, "realistic")
        ),
        "stress_score": _split_pass_rate(_split_rows(normalized_rows, "stress")),
    }
    return summary


def evaluate_retrieval(
    cases: list[dict[str, Any]],
    *,
    backend: str,
    mode: str = "full",
    scope: str = "pure",
    limit: int | None = None,
    pipeline_factory: Callable[[], Any] | None = None,
    checkpoint_path: Path | None = None,
    resume: bool = False,
    checkpoint_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if backend != "qdrant":
        raise ValueError("backend must be qdrant")
    if mode not in {
        "full",
        "no_graph",
        "vector_only",
        "vector_primary_graph_supplement",
    }:
        raise ValueError(
            "mode must be full, no_graph, vector_only, "
            "or vector_primary_graph_supplement"
        )
    if scope not in {"pure", "end_to_end"}:
        raise ValueError("scope must be pure or end_to_end")
    identity = _eval_checkpoint_identity(
        cases, suite="retrieval", context=checkpoint_context,
        backend=backend, mode=mode, scope=scope,
    ) if checkpoint_path else None
    rows = _load_eval_checkpoint(checkpoint_path, resume=resume, identity=identity)
    completed_ids = {row["id"] for row in rows}
    previous_backend = os.environ.get("STUDENT_RAG_USE_QDRANT")
    previous_hybrid = os.environ.get("STUDENT_RAG_DISABLE_HYBRID_RETRIEVAL")
    previous_mode = os.environ.get("STUDENT_RAG_EVAL_RETRIEVAL_MODE")
    previous_force_regulation = os.environ.get(
        "STUDENT_RAG_EVAL_FORCE_REGULATION_RAG"
    )
    previous_router_wait = os.environ.get("STUDENT_RAG_ROUTER_WAIT_WHEN_LIMITED")
    previous_router_cache = os.environ.get("STUDENT_RAG_DISABLE_ROUTER_CACHE")
    os.environ["STUDENT_RAG_USE_QDRANT"] = "1"
    os.environ.pop("STUDENT_RAG_DISABLE_HYBRID_RETRIEVAL", None)
    os.environ["STUDENT_RAG_EVAL_RETRIEVAL_MODE"] = mode
    os.environ["STUDENT_RAG_DISABLE_ROUTER_CACHE"] = "1"
    if scope == "pure":
        os.environ["STUDENT_RAG_EVAL_FORCE_REGULATION_RAG"] = "1"
    else:
        os.environ.pop("STUDENT_RAG_EVAL_FORCE_REGULATION_RAG", None)
        os.environ["STUDENT_RAG_ROUTER_WAIT_WHEN_LIMITED"] = "1"
    uses_default_pipeline = pipeline_factory is None
    if pipeline_factory is None:
        from src.generation.answer_pipeline import AnswerPipeline

        pipeline_factory = AnswerPipeline
    try:
        pipeline = pipeline_factory()
        if uses_default_pipeline:
            from src.retrieval.core.hybrid_pipeline import initialize_hybrid_retriever

            initialize_hybrid_retriever()
            _wait_for_bm25_ready()
        progress = _progress_cases(
            cases,
            limit=limit,
            desc=f"Retrieval Eval [{backend}/{mode}]",
        )
        for case in progress:
            progress.set_postfix_str(str(case.get("id") or "unknown"))
            if case["id"] in completed_ids:
                continue
            started = time.perf_counter()
            try:
                requested_cohort = case.get("cohort")
                retrieval_cohort = (
                    None
                    if requested_cohort in {None, "", "general", "all"}
                    else requested_cohort
                )
                result = pipeline._run_retrieval(
                    case["query"], cohort=retrieval_cohort, **_case_history_kwargs(case)
                )
                items = result.get("retrieved_items") or []
                related_items = result.get("related_items") or []
                ranked_ids = list(dict.fromkeys(_item_parent_id(item) for item in items))
                related_ids = [_item_parent_id(item) for item in related_items]
                expected_ids = {
                    item["parent_section_id"] for item in case["relevance_judgments"]
                }
                supporting_ids = {
                    item["parent_section_id"]
                    for item in case["relevance_judgments"]
                    if int(item.get("grade") or 0) == 1
                }
                if not ranked_ids and result.get("structured_result"):
                    ranked_ids = _structured_expected_ids(
                        result["structured_result"], expected_ids
                    )
                grade_by_id = {
                    item["parent_section_id"]: int(item["grade"])
                    for item in case["relevance_judgments"]
                }
                metrics, metric_scope = _retrieval_metrics_for_execution_units(
                    case=case,
                    ranked_ids=ranked_ids,
                    grade_by_id=grade_by_id,
                    scope=scope,
                )
                metrics["mrr"] = metrics.pop("reciprocal_rank")
                citations = result.get("citations") or []
                citation_ids = {_citation_parent_id(item) for item in citations}
                structured = result.get("structured_result") or {}
                cohort_ok = all(
                    _cohort_matches(
                        _item_applicability(item), case.get("cohort")
                    )
                    for item in items
                ) and (
                    not structured
                    or _cohort_matches(
                        structured.get("applicable_cohorts")
                        or structured.get("cohorts")
                        or structured.get("cohort"),
                        case.get("cohort"),
                    )
                )
                related_cohort_ok = all(
                    _cohort_matches(
                        _item_applicability(item), case.get("cohort")
                    )
                    for item in related_items
                )
                actual_content_types = {
                    (item.get("metadata") or {}).get("content_type") for item in items
                }
                if structured.get("content_type"):
                    actual_content_types.add(structured["content_type"])
                expected_content_types = set(case.get("expected_content_types") or [])
                content_ok = (
                    bool(actual_content_types)
                    and actual_content_types <= expected_content_types
                )
                retrieval_telemetry = _first_retrieval_telemetry(items)
                router_decision = result.get("router_decision") or {}
                query_handling = result.get("query_handling") or (
                    router_decision.get("query_handling")
                    if isinstance(router_decision, dict)
                    else {}
                )
                if not isinstance(query_handling, dict):
                    query_handling = {}
                rows.append(
                    {
                        **case,
                        **metrics,
                        "metric_scope": metric_scope,
                        "ranked_parent_ids": ranked_ids,
                        "related_parent_ids": related_ids,
                        "actual_intent": result.get("intent"),
                        "actual_strategy": result.get("strategy"),
                        "raw_query": result.get("raw_query") or case["query"],
                        "effective_query": result.get("effective_query")
                        or query_handling.get("effective_query")
                        or case["query"],
                        "query_handling_source": query_handling.get("source"),
                        "query_handling_validation_errors": query_handling.get(
                            "validation_errors"
                        )
                        or [],
                        "router_route": (
                            router_decision.get("route")
                            if isinstance(router_decision, dict)
                            else None
                        ),
                        "router_execution_mode": (
                            router_decision.get("execution_mode")
                            if isinstance(router_decision, dict)
                            else None
                        ),
                        "citation_binding": bool(expected_ids & citation_ids)
                        or bool(metrics["hit_at_5"]),
                        "cohort_match": cohort_ok,
                        "content_type_match": content_ok,
                        "related_cohort_match": related_cohort_ok,
                        "graph_related_hit": bool(expected_ids & set(related_ids)),
                        "graph_supporting_hit": (
                            bool(supporting_ids & set(related_ids))
                            if supporting_ids
                            else None
                        ),
                        "graph_supporting_recall": (
                            len(supporting_ids & set(related_ids)) / len(supporting_ids)
                            if supporting_ids
                            else None
                        ),
                        "context_hit_at_10": bool(
                            expected_ids & set([*ranked_ids, *related_ids])
                        ),
                        "empty_retrieval": not bool(items),
                        "cohort_leak": not cohort_ok,
                        "related_cohort_leak": not related_cohort_ok,
                        "synthetic_leak": case["case_type"] == "regulation_true_rag"
                        and not content_ok,
                        "retrieval_telemetry": retrieval_telemetry,
                        "phoranker_candidate_chunks": int(
                            retrieval_telemetry.get("phoranker_candidate_chunks") or 0
                        ),
                        "phoranker_candidate_parents": int(
                            retrieval_telemetry.get("phoranker_candidate_parents") or 0
                        ),
                        "graph_neighbor_chunks_selected": int(
                            retrieval_telemetry.get("graph_neighbor_chunks_selected")
                            or 0
                        ),
                        "latency_ms": (time.perf_counter() - started) * 1000,
                    }
                )
                progress.set_postfix(
                    {
                        "case": case.get("id"),
                        "hit5": int(bool(metrics["hit_at_5"])),
                        "items": len(items),
                        "ms": int((time.perf_counter() - started) * 1000),
                    },
                    refresh=False,
                )
            except Exception as exc:
                empty_metrics = retrieval_metrics([])
                empty_metrics["mrr"] = empty_metrics.pop("reciprocal_rank")
                rows.append(
                    {
                        **case,
                        **empty_metrics,
                        "error": str(exc),
                        "citation_binding": False,
                        "cohort_match": False,
                        "content_type_match": False,
                        "related_cohort_match": False,
                        "graph_related_hit": False,
                        "graph_supporting_hit": None,
                        "graph_supporting_recall": None,
                        "context_hit_at_10": False,
                        "empty_retrieval": True,
                        "cohort_leak": False,
                        "related_cohort_leak": False,
                        "synthetic_leak": False,
                        "latency_ms": (time.perf_counter() - started) * 1000,
                    }
                )
                progress.set_postfix(
                    {
                        "case": case.get("id"),
                        "hit5": 0,
                        "error": type(exc).__name__,
                    },
                    refresh=False,
                )
            finally:
                _save_eval_checkpoint(checkpoint_path, rows, identity=identity)
    finally:
        _restore_env("STUDENT_RAG_USE_QDRANT", previous_backend)
        _restore_env("STUDENT_RAG_DISABLE_HYBRID_RETRIEVAL", previous_hybrid)
        _restore_env("STUDENT_RAG_EVAL_RETRIEVAL_MODE", previous_mode)
        _restore_env(
            "STUDENT_RAG_EVAL_FORCE_REGULATION_RAG",
            previous_force_regulation,
        )
        _restore_env("STUDENT_RAG_ROUTER_WAIT_WHEN_LIMITED", previous_router_wait)
        _restore_env("STUDENT_RAG_DISABLE_ROUTER_CACHE", previous_router_cache)

    by_id = {row["id"]: row for row in rows}
    rows = [by_id[case["id"]] for case in cases[:limit] if case["id"] in by_id]
    true_rag = [row for row in rows if row["case_type"] == "regulation_true_rag"]
    summary = _retrieval_summary(rows, true_rag)
    summary["retrieval_scope"] = scope
    return {
        "suite": "retrieval",
        "backend": backend,
        "mode": mode,
        "scope": scope,
        "summary": summary,
        "breakdowns": _retrieval_breakdowns(rows),
        "cases": rows,
    }


def _retrieval_summary(
    rows: list[dict[str, Any]], headline: list[dict[str, Any]]
) -> dict[str, Any]:
    metric_names = (
        "hit_at_1", "hit_at_3", "hit_at_5", "mrr", "ndcg_at_5",
        "primary_hit_at_5", "required_source_recall_at_5",
    )
    summary: dict[str, Any] = {"n": len(rows), "headline_n": len(headline)}
    for name in metric_names:
        values = [float(row.get(name, 0.0)) for row in headline]
        summary[name] = safe_mean(values)
        summary[f"{name}_ci95"] = bootstrap_mean_ci(values)
    summary.update(
        {
            "parent_section_match": safe_mean(
                [float(row.get("hit_at_5", 0.0) > 0) for row in rows]
            ),
            "citation_binding": safe_mean(
                [float(bool(row.get("citation_binding"))) for row in rows]
            ),
            "cohort_match": safe_mean(
                [float(bool(row.get("cohort_match"))) for row in rows]
            ),
            "content_type_match": safe_mean(
                [float(bool(row.get("content_type_match"))) for row in rows]
            ),
            "cohort_leak_rate": safe_mean(
                [float(bool(row.get("cohort_leak"))) for row in rows]
            ),
            "synthetic_leak_rate": safe_mean(
                [float(bool(row.get("synthetic_leak"))) for row in rows]
            ),
            "empty_retrieval_rate": safe_mean(
                [float(bool(row.get("empty_retrieval"))) for row in rows]
            ),
            "latency_ms": _latency_summary([float(row["latency_ms"]) for row in rows]),
            "realistic_score": safe_mean(
                [
                    float(row.get("hit_at_5", 0.0))
                    for row in headline
                    if row.get("eval_split") == "realistic"
                ]
            ),
            "stress_score": safe_mean(
                [
                    float(row.get("hit_at_5", 0.0))
                    for row in headline
                    if row.get("eval_split") == "stress"
                ]
            ),
            "phoranker_candidate_chunks": _latency_summary(
                [
                    float(row.get("phoranker_candidate_chunks") or 0)
                    for row in rows
                    if row.get("phoranker_candidate_chunks") is not None
                ]
            ),
            "phoranker_candidate_parents": _latency_summary(
                [
                    float(row.get("phoranker_candidate_parents") or 0)
                    for row in rows
                    if row.get("phoranker_candidate_parents") is not None
                ]
            ),
        }
    )
    return summary


def _cohort_from_parent_id(parent_id: str) -> str | None:
    if parent_id.startswith("K48-K49_"):
        return "K48-K49"
    if parent_id.startswith("K50_"):
        return "K50"
    if parent_id.startswith("K51_"):
        return "K51"
    return None


def _retrieval_metrics_for_execution_units(
    *,
    case: dict[str, Any],
    ranked_ids: list[str],
    grade_by_id: dict[str, int],
    scope: str,
) -> tuple[dict[str, float], str]:
    """Score cohort-local E2E retrieval units before combining the request.

    QueryPlan executes a ``general`` regulation task once per applicable cohort
    and returns up to five primary parents for each unit. A global cutoff over
    the flattened groups would incorrectly turn the first K50 result into rank
    six merely because five K48-K49 parents were emitted first.
    """
    def score(ids: list[str], relevance: dict[str, int]) -> dict[str, float]:
        # Score unique parent sections, not repeated chunks/tasks from a parent.
        ids = list(dict.fromkeys(ids))
        metrics = retrieval_metrics(
            [relevance.get(parent_id, 0) for parent_id in ids],
            gold_grades=list(relevance.values()),
        )
        required_ids = {parent_id for parent_id, grade in relevance.items() if grade == 2}
        found = required_ids & set(ids[:5])
        metrics["primary_hit_at_5"] = float(bool(found))
        metrics["required_source_recall_at_5"] = len(found) / len(required_ids) if required_ids else 0.0
        return metrics

    relevance_by_cohort: dict[str, dict[str, int]] = {}
    for judgment in case.get("relevance_judgments") or []:
        cohort = str(judgment.get("cohort") or "").strip()
        parent_id = str(judgment.get("parent_section_id") or "").strip()
        if cohort and parent_id:
            relevance_by_cohort.setdefault(cohort, {})[parent_id] = int(
                judgment.get("grade") or 0
            )

    if (
        scope != "end_to_end"
        or case.get("cohort") != "general"
        or len(relevance_by_cohort) <= 1
    ):
        return (
            score(ranked_ids, grade_by_id),
            "request_global",
        )

    ranked_by_cohort: dict[str, list[str]] = {}
    for parent_id in ranked_ids:
        cohort = _cohort_from_parent_id(parent_id)
        if cohort:
            ranked_by_cohort.setdefault(cohort, []).append(parent_id)

    unit_metrics = [
        score(ranked_by_cohort.get(cohort, []), cohort_relevance)
        for cohort, cohort_relevance in sorted(relevance_by_cohort.items())
    ]
    if not unit_metrics:
        return retrieval_metrics([]), "per_cohort_execution_unit"

    return (
        {
            "hit_at_1": min(metric["hit_at_1"] for metric in unit_metrics),
            "hit_at_3": min(metric["hit_at_3"] for metric in unit_metrics),
            "hit_at_5": min(metric["hit_at_5"] for metric in unit_metrics),
            "reciprocal_rank": safe_mean(
                [metric["reciprocal_rank"] for metric in unit_metrics]
            ),
            "ndcg_at_5": safe_mean(
                [metric["ndcg_at_5"] for metric in unit_metrics]
            ),
            "primary_hit_at_5": min(metric["primary_hit_at_5"] for metric in unit_metrics),
            "required_source_recall_at_5": safe_mean(
                [metric["required_source_recall_at_5"] for metric in unit_metrics]
            ),
        },
        "per_cohort_execution_unit",
    )


def evaluate_graph_supplement(
    *,
    edges_path: Path | None = None,
    graph_depth: int = 2,
    related_limit: int = 5,
    limit: int | None = None,
) -> dict[str, Any]:
    """Evaluate bounded graph expansion separately from headline retrieval.

    This suite answers: when a primary parent has an outbound graph edge to a
    related parent, does the production graph selector surface that target
    inside the RELATED SOURCES budget?
    """

    from src.retrieval.core.graph_traverser import NetworkXGraphTraverser
    from src.retrieval.core.hybrid_pipeline import (
        select_graph_related_parent_candidates,
    )

    actual_edges_path = edges_path or (
        ROOT / "data" / "processed" / "graphs" / "document_edges.json"
    )
    edge_rows = load_json(actual_edges_path)
    if limit is not None:
        edge_rows = edge_rows[:limit]

    traverser = NetworkXGraphTraverser(str(actual_edges_path))
    rows: list[dict[str, Any]] = []
    progress = _progress_cases(
        edge_rows,
        limit=None,
        desc="Graph Supplement Eval",
    )
    for index, edge in enumerate(progress, start=1):
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        progress.set_postfix_str(source or f"edge-{index}")
        started = time.perf_counter()
        expanded_nodes = (
            traverser.expand_context([source], max_depth=graph_depth)
            if source
            else []
        )
        selected = select_graph_related_parent_candidates(
            [source],
            expanded_nodes,
            max_related_total=related_limit,
        )
        expanded_ids = [str(node.get("id") or "") for node in expanded_nodes]
        selected_ids = [str(item.get("parent_id") or "") for item in selected]
        target_nodes = [
            node for node in expanded_nodes if str(node.get("id") or "") == target
        ]
        target_depth = (
            min(int(node.get("depth") or 99) for node in target_nodes)
            if target_nodes
            else None
        )
        source_cohort = _cohort_from_parent_id(source)
        selected_cohort_leak = any(
            _cohort_from_parent_id(parent_id) not in {None, source_cohort}
            for parent_id in selected_ids
        )
        rows.append(
            {
                "id": edge.get("id") or f"graph_edge_{index:03d}",
                "source_parent_id": source,
                "target_parent_id": target,
                "relation": edge.get("relation"),
                "reason": edge.get("reason"),
                "source_in_graph": bool(source and source in traverser.graph),
                "target_in_graph": bool(target and target in traverser.graph),
                "target_expanded": target in expanded_ids,
                "target_selected": target in selected_ids,
                "target_depth": target_depth,
                "expanded_parent_count": len(expanded_ids),
                "selected_related_parent_count": len(selected_ids),
                "selected_related_parent_ids": selected_ids,
                "related_cohort_leak": selected_cohort_leak,
                "latency_ms": (time.perf_counter() - started) * 1000,
            }
        )
    selected_counts = [
        float(row["selected_related_parent_count"]) for row in rows
    ]
    summary = {
        "n": len(rows),
        "graph_nodes": traverser.graph.number_of_nodes(),
        "graph_edges": traverser.graph.number_of_edges(),
        "graph_depth": graph_depth,
        "related_limit": related_limit,
        "source_coverage": safe_mean(
            [float(bool(row["source_in_graph"])) for row in rows]
        ),
        "target_coverage": safe_mean(
            [float(bool(row["target_in_graph"])) for row in rows]
        ),
        "direct_expansion_recall": safe_mean(
            [float(bool(row["target_expanded"])) for row in rows]
        ),
        "related_selection_recall_at_5": safe_mean(
            [float(bool(row["target_selected"])) for row in rows]
        ),
        "related_cohort_leak_rate": safe_mean(
            [float(bool(row["related_cohort_leak"])) for row in rows]
        ),
        "selected_related_parent_count": _latency_summary(selected_counts),
        "latency_ms": _latency_summary([float(row["latency_ms"]) for row in rows]),
    }
    return {
        "suite": "graph",
        "evaluation": "graph_supplement",
        "summary": summary,
        "cases": rows,
    }


def _retrieval_breakdowns(rows: list[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for field in (
        "cohort",
        "topic",
        "query_style",
        "question_style",
        "expected_path",
        "eval_split",
    ):
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            groups[str(row.get(field) or "unknown")].append(row)
        output[field] = {
            key: {
                "n": len(group),
                "hit_at_3": safe_mean([r["hit_at_3"] for r in group]),
                "mrr": safe_mean([r["mrr"] for r in group]),
                "ndcg_at_5": safe_mean([r["ndcg_at_5"] for r in group]),
            }
            for key, group in sorted(groups.items())
        }
    tag_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for tag in row.get("tags") or []:
            tag_groups[tag].append(row)
    output["tag"] = {
        key: {
            "n": len(group),
            "hit_at_3": safe_mean([r["hit_at_3"] for r in group]),
            "mrr": safe_mean([r["mrr"] for r in group]),
        }
        for key, group in sorted(tag_groups.items())
    }
    return output


def generate_answers(
    cases: list[dict[str, Any]],
    *,
    cache_path: Path,
    resume: bool,
    limit: int | None = None,
    pipeline_factory: Callable[[], Any] | None = None,
    checkpoint_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from src.retrieval.core.hybrid_pipeline import (
        DEFAULT_RETRIEVAL_MODE,
        initialize_hybrid_retriever,
    )

    identity = _eval_checkpoint_identity(
        cases, suite="answer_generation", context=checkpoint_context,
        retrieval_mode=DEFAULT_RETRIEVAL_MODE,
    )
    existing = _load_eval_checkpoint(cache_path, resume=resume, identity=identity)
    uses_default_pipeline = pipeline_factory is None
    if pipeline_factory is None:
        from src.generation.answer_pipeline import AnswerPipeline

        pipeline_factory = AnswerPipeline
    previous_offline = os.environ.get("STUDENT_RAG_OFFLINE_EVAL")
    previous_quality = os.environ.get("STUDENT_RAG_QUALITY_EVAL")
    previous_retrieval_mode = os.environ.get("STUDENT_RAG_EVAL_RETRIEVAL_MODE")
    previous_router_cache = os.environ.get("STUDENT_RAG_DISABLE_ROUTER_CACHE")
    os.environ.pop("STUDENT_RAG_OFFLINE_EVAL", None)
    os.environ["STUDENT_RAG_QUALITY_EVAL"] = "1"
    # Answer-quality evaluation must exercise the production retrieval contract.
    # PhoRanker is reserved for explicit retrieval-ablation suites and must not
    # silently enter the 150-case generate/judge result through ambient env.
    os.environ["STUDENT_RAG_EVAL_RETRIEVAL_MODE"] = DEFAULT_RETRIEVAL_MODE
    os.environ["STUDENT_RAG_DISABLE_ROUTER_CACHE"] = "1"
    by_id = {row["id"]: row for row in existing}
    try:
        pipeline = pipeline_factory()
        if uses_default_pipeline:
            initialize_hybrid_retriever()
            _wait_for_bm25_ready()
        progress = _progress_cases(
            cases,
            limit=limit,
            desc="Generating Answers",
        )
        for case in progress:
            progress.set_postfix_str(str(case.get("id") or "unknown"))
            if case["id"] in by_id:
                progress.set_postfix(
                    {"case": case.get("id"), "cache": 1},
                    refresh=False,
                )
                continue
            started = time.perf_counter()
            try:
                output = pipeline.answer(
                    case["query"], cohort=case.get("cohort"), **_case_history_kwargs(case)
                )
                clean_output = {k: v for k, v in output.items() if k != "tracker"}
                record = {
                    "id": case["id"],
                    **clean_output,
                    "evaluation_retrieval_mode": DEFAULT_RETRIEVAL_MODE,
                    "phoranker_used": False,
                    "latency_ms": (time.perf_counter() - started) * 1000,
                }
            except Exception as exc:
                record = {
                    "id": case["id"],
                    "status": "exception",
                    "answer": "",
                    "error": str(exc),
                    "latency_ms": (time.perf_counter() - started) * 1000,
                }
            by_id[case["id"]] = record
            progress.set_postfix(
                {
                    "case": case.get("id"),
                    "status": record.get("status"),
                    "ms": int(float(record.get("latency_ms") or 0)),
                },
                refresh=False,
            )
            _save_eval_checkpoint(cache_path, list(by_id.values()), identity=identity)
    finally:
        _restore_env("STUDENT_RAG_OFFLINE_EVAL", previous_offline)
        _restore_env("STUDENT_RAG_QUALITY_EVAL", previous_quality)
        _restore_env("STUDENT_RAG_DISABLE_ROUTER_CACHE", previous_router_cache)
        _restore_env(
            "STUDENT_RAG_EVAL_RETRIEVAL_MODE",
            previous_retrieval_mode,
        )
    rows = [by_id[case["id"]] for case in cases[:limit] if case["id"] in by_id]
    return {
        "suite": "answer_generation",
        "summary": {
            "n": len(rows),
            "retrieval_mode": DEFAULT_RETRIEVAL_MODE,
            "phoranker_used": False,
            "success_rate": safe_mean(
                [float(row.get("status") == "answered") for row in rows]
            ),
            "latency_ms": _latency_summary(
                [float(row.get("latency_ms", 0)) for row in rows]
            ),
        },
        "cases": rows,
    }


def load_answer_checkpoint(
    cases: list[dict[str, Any]], cache_path: Path, *,
    checkpoint_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Verify generation provenance before using cached answers in a new judge run."""
    from src.retrieval.core.hybrid_pipeline import DEFAULT_RETRIEVAL_MODE

    identity = _eval_checkpoint_identity(
        cases, suite="answer_generation", context=checkpoint_context,
        retrieval_mode=DEFAULT_RETRIEVAL_MODE,
    )
    return _load_eval_checkpoint(cache_path, resume=True, identity=identity)


def judge_answers(
    cases: list[dict[str, Any]],
    answer_cache: list[dict[str, Any]],
    *,
    checkpoint_path: Path,
    resume: bool,
    limit: int | None = None,
    judge_client: GroqJudgeClient | None = None,
    checkpoint_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    identity = _eval_checkpoint_identity(
        cases, suite="judge", context=checkpoint_context,
        answer_cache_hash=stable_json_hash(answer_cache),
    )
    existing = _load_eval_checkpoint(checkpoint_path, resume=resume, identity=identity)
    client = judge_client or GroqJudgeClient()
    answers = {row["id"]: row for row in answer_cache}
    judged = {row["id"]: row for row in existing}
    progress = _progress_cases(
        cases,
        limit=limit,
        desc="Judging Answers",
    )
    for case in progress:
        progress.set_postfix_str(str(case.get("id") or "unknown"))
        if case["id"] in judged:
            progress.set_postfix(
                {"case": case.get("id"), "cache": 1},
                refresh=False,
            )
            continue
        answer = answers.get(case["id"], {})
        packet = compact_judge_packet(case, answer)
        started = time.perf_counter()
        result = client.judge(packet)
        deterministic = _answer_checks(case, answer)
        judged[case["id"]] = {
            "id": case["id"],
            "case_type": case.get("case_type"),
            "topic": case.get("topic"),
            "question_style": case.get("question_style"),
            "question_specificity": case.get("question_specificity"),
            "expected_answer_behavior": case.get("expected_answer_behavior"),
            "expected_path": case.get("expected_path"),
            "eval_split": case.get("eval_split"),
            "generation_model": answer.get("model_used"),
            "effective_query": answer.get("effective_query"),
            "query_handling": answer.get("query_handling"),
            "router_decision": answer.get("router_decision"),
            "judge": result,
            **deterministic,
            "judge_latency_ms": (time.perf_counter() - started) * 1000,
            "packet_required_fact_coverage": len(
                packet["required_facts_present_in_packet"]
            )
            / max(1, len(case.get("required_facts") or [])),
        }
        progress.set_postfix(
            {
                "case": case.get("id"),
                "ok": int(bool(result.get("ok"))),
                "ms": int((time.perf_counter() - started) * 1000),
            },
            refresh=False,
        )
        _save_eval_checkpoint(checkpoint_path, list(judged.values()), identity=identity)
    rows = [judged[c["id"]] for c in cases[:limit] if c["id"] in judged]
    valid = [row for row in rows if (row.get("judge") or {}).get("ok")]
    summary = {
        "n": len(rows),
        "judged_n": len(valid),
        "judge_model": "openai/gpt-oss-120b",
    }
    for metric in (
        "faithfulness",
        "answer_relevancy",
        "answer_correctness",
        "context_precision",
        "context_recall",
        "citation_correctness",
    ):
        values = [row["judge"]["scores"][metric] for row in valid]
        summary[metric] = safe_mean(values)
        summary[f"{metric}_ci95"] = bootstrap_mean_ci(values)
    for metric in (
        "required_fact_hit",
        "numeric_accuracy",
        "abstention_correct",
        "answer_success",
        "question_handling_correctness",
    ):
        summary[metric] = safe_mean([float(bool(row.get(metric))) for row in rows])
    summary["hallucination_rate"] = safe_mean(
        [float(bool(row["judge"]["scores"].get("unsupported_claim"))) for row in valid]
    )
    summary["critical_false_passes"] = sum(
        bool(row["judge"]["scores"].get("critical_false_pass")) for row in valid
    )
    summary["packet_required_fact_coverage"] = safe_mean(
        [row["packet_required_fact_coverage"] for row in rows]
    )
    for split in ("realistic", "stress"):
        split_valid = [row for row in valid if row.get("eval_split") == split]
        summary[f"{split}_score"] = safe_mean(
            [row["judge"]["scores"]["answer_correctness"] for row in split_valid]
        )
    return {
        "suite": "judge",
        "summary": summary,
        "cases": rows,
        "human_audit_template": build_human_audit_template(cases, rows),
    }


def _answer_checks(case: dict[str, Any], answer: dict[str, Any]) -> dict[str, Any]:
    text = _normalize_eval_text(answer.get("answer") or "")
    required = [_normalize_eval_text(item) for item in case.get("required_facts") or []]
    numeric = re.findall(r"\d+(?:[.,]\d+)?%?", " ".join(required))
    expected_ids = {
        item["parent_section_id"] for item in case.get("expected_citations") or []
    }
    actual_ids = {
        _citation_parent_id(item)
        for item in answer.get("citations_used") or answer.get("citations") or []
    }
    answerable = case.get("answerability") == "answerable"
    abstained = answer.get("status") in {
        "needs_clarification",
        "out_of_domain",
        "low_confidence",
    } or _answer_text_abstains(text)
    citation_exact_match = (
        bool(expected_ids & actual_ids) if expected_ids else not actual_ids
    )
    required_fact_hit = (
        all(_soft_fact_match(fact, text) for fact in required) if required else True
    )
    answer_success = answer.get("status") in {
        "answered",
        "needs_clarification",
        "out_of_domain",
    }
    behavior = str(case.get("expected_answer_behavior") or "direct_answer")
    expects_no_direct_answer = behavior in {"abstain", "clarify_or_scope"}
    return {
        "required_fact_hit": required_fact_hit,
        "numeric_accuracy": all(value in text for value in numeric)
        if numeric
        else True,
        "citation_exact_match": citation_exact_match,
        "abstention_correct": (
            abstained if expects_no_direct_answer or not answerable else not abstained
        ),
        "answer_success": answer_success,
        "question_handling_correctness": _question_handling_correct(
            behavior=behavior,
            answer_success=answer_success,
            required_fact_hit=required_fact_hit,
            citation_exact_match=citation_exact_match,
            abstained=abstained,
            has_citations=bool(actual_ids),
        ),
    }


def _normalize_eval_text(value: Any) -> str:
    text = str(value or "").casefold()
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = re.sub(r"[^\w%.,]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def _answer_text_abstains(answer_text: str) -> bool:
    abstention_signals = (
        "chua thay",
        "khong tim thay",
        "khong co quy dinh",
        "chua co can cu",
        "khong du can cu",
        "chua du can cu",
        "khong du thong tin",
        "khong thay can cu",
        "khong co can cu truc tiep",
        "chua thay can cu truc tiep",
    )
    return any(signal in answer_text for signal in abstention_signals)


def _soft_fact_match(fact: str, answer_text: str) -> bool:
    if not fact:
        return True
    if fact in answer_text:
        return True
    fact_tokens = set(re.findall(r"\w+", fact))
    answer_tokens = set(re.findall(r"\w+", answer_text))
    if len(fact_tokens) < 5:
        return fact in answer_text
    overlap = len(fact_tokens & answer_tokens) / max(1, len(fact_tokens))
    numeric_values = set(re.findall(r"\d+(?:[.,]\d+)?%?", fact))
    answer_numeric = set(re.findall(r"\d+(?:[.,]\d+)?%?", answer_text))
    numeric_ok = not numeric_values or numeric_values <= answer_numeric
    return numeric_ok and overlap >= 0.62


def _question_handling_correct(
    *,
    behavior: str,
    answer_success: bool,
    required_fact_hit: bool,
    citation_exact_match: bool,
    abstained: bool,
    has_citations: bool,
) -> bool:
    if behavior == "abstain":
        return abstained
    if behavior == "clarify_or_scope":
        return abstained or (answer_success and (has_citations or required_fact_hit))
    if behavior == "scoped_summary":
        return answer_success and (citation_exact_match or has_citations)
    return answer_success and required_fact_hit


def build_human_audit_template(
    cases: list[dict[str, Any]], rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows_by_id = {str(row["id"]): row for row in rows}
    candidates = [case for case in cases if str(case["id"]) in rows_by_id]

    def risk_key(case: dict[str, Any]) -> tuple[float, float, str]:
        row = rows_by_id[str(case["id"])]
        scores = (row.get("judge") or {}).get("scores") or {}
        core_scores = [
            float(scores.get(metric, 1.0))
            for metric in (
                "faithfulness",
                "answer_correctness",
                "citation_correctness",
            )
        ]
        risk = (
            2.0 * float(bool(scores.get("critical_false_pass")))
            + float(bool(scores.get("unsupported_claim")))
            + (1.0 - safe_mean(core_scores))
        )
        has_judge = float(bool(scores))
        return (-has_judge, -risk, str(case["id"]))

    risk_candidates = sorted(candidates, key=risk_key)
    low_risk_audit = [
        case
        for case in risk_candidates
        if (rows_by_id[str(case["id"])].get("judge") or {}).get("scores")
    ][:10]
    selected_ids = {str(case["id"]) for case in low_risk_audit}

    def stratum(case: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(case.get("case_type") or "unknown"),
            str(case.get("eval_split") or "unknown"),
            str(case.get("cohort") or "general"),
        )

    def seeded_order(case: dict[str, Any]) -> str:
        return hashlib.sha256(
            f"v9-human-audit:{case['id']}".encode("utf-8")
        ).hexdigest()

    remaining_by_stratum: dict[tuple[str, str, str], list[dict[str, Any]]] = (
        defaultdict(list)
    )
    for case in candidates:
        if str(case["id"]) not in selected_ids:
            remaining_by_stratum[stratum(case)].append(case)
    for group in remaining_by_stratum.values():
        group.sort(key=seeded_order)

    random_audit: list[dict[str, Any]] = []
    strata = sorted(remaining_by_stratum)
    while len(random_audit) < 15 and strata:
        next_strata: list[tuple[str, str, str]] = []
        for key in strata:
            group = remaining_by_stratum[key]
            if group and len(random_audit) < 15:
                random_audit.append(group.pop(0))
            if group:
                next_strata.append(key)
        strata = next_strata

    chosen = [
        *[(case, "risk_low_score") for case in low_risk_audit],
        *[(case, "stratified_random") for case in random_audit],
    ]
    return [
        {
            "id": case["id"],
            "case_type": case.get("case_type"),
            "cohort": case.get("cohort"),
            "eval_split": case.get("eval_split"),
            "selection_reason": reason,
            "human_score": None,
            "human_correctness": None,
            "human_faithfulness": None,
            "human_citation_correctness": None,
            "unsupported_claim_actual": None,
            "root_cause": None,
            "critical_false_pass": None,
            "notes": "",
            "repeat_for_consistency": index < 5,
            "repeat_score": None,
        }
        for index, (case, reason) in enumerate(chosen)
    ]


def _expected_response_status(case: dict[str, Any]) -> str:
    expected_path = case.get("expected_path")
    expected_behavior = case.get("expected_answer_behavior")
    if expected_path == "clarify" and expected_behavior == "abstain":
        return "answered_or_guardrail"
    if expected_path == "clarify":
        return "needs_clarification"
    if expected_path == "out_of_domain":
        return "out_of_domain"
    return "answered"


def _response_status_matches_expected(
    response_status: str,
    expected_status: str,
) -> bool:
    if expected_status == "answered_or_guardrail":
        return response_status in {
            "answered",
            "needs_clarification",
            "out_of_domain",
        }
    return response_status == expected_status


def _summarize_production_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    streaming_rows = [row for row in rows if row.get("scenario") == "streaming"]
    cold_rows = [row for row in rows if row.get("scenario") == "cold_rag"]
    warm_rows = [row for row in rows if row.get("scenario") == "warm_cache"]
    cold_regulation_rows = [
        row for row in cold_rows if row.get("expected_path") == "regulation_rag"
    ]

    cold_cache_observed = [
        row for row in cold_rows if row.get("used_cache") is not None
    ]
    warm_cache_observed = [
        row for row in warm_rows if row.get("used_cache") is not None
    ]
    cold_cache_hit_rate = safe_mean(
        [float(bool(row.get("used_cache"))) for row in cold_cache_observed]
    )
    warm_cache_hit_rate = safe_mean(
        [float(bool(row.get("used_cache"))) for row in warm_cache_observed]
    )
    cold_cache_coverage = (
        len(cold_cache_observed) / len(cold_rows) if cold_rows else 0.0
    )
    warm_cache_coverage = (
        len(warm_cache_observed) / len(warm_rows) if warm_rows else 0.0
    )
    streaming_ttft_coverage = (
        len([row for row in streaming_rows if row.get("ttft_ms") is not None])
        / len(streaming_rows)
        if streaming_rows
        else 0.0
    )

    summary: dict[str, Any] = {
        "n": len(rows),
        "success_rate": safe_mean([float(row["success"]) for row in rows]),
        "transport_success_rate": safe_mean(
            [float(bool(row.get("transport_success"))) for row in rows]
        ),
        "payload_success_rate": safe_mean(
            [float(bool(row.get("payload_success"))) for row in rows]
        ),
        "response_status_accuracy": safe_mean(
            [
                float(bool(row.get("expected_status_match")))
                for row in rows
                if row.get("expected_path")
            ]
        ),
        "error_rate": safe_mean([float(not row["success"]) for row in rows]),
        "http_429_rate": safe_mean(
            [float(row.get("status_code") == 429) for row in rows]
        ),
        "timeout_rate": safe_mean(
            [
                float("timed out" in str(row.get("error") or "").lower())
                for row in rows
            ]
        ),
        "latency_ms": _latency_summary([row["latency_ms"] for row in rows]),
        "streaming_ttft_ms": _latency_summary(
            [
                row["ttft_ms"]
                for row in streaming_rows
                if row.get("ttft_ms") is not None
            ]
        ),
        "streaming_ttft_coverage": streaming_ttft_coverage,
        "cold_regulation_rag_latency_ms": _latency_summary(
            [row["latency_ms"] for row in cold_regulation_rows]
        ),
        "cache_hit_rate": safe_mean(
            [float(bool(row.get("used_cache"))) for row in rows]
        ),
        "cold_cache_hit_rate": cold_cache_hit_rate,
        "warm_cache_hit_rate": warm_cache_hit_rate,
        "cold_cache_status_coverage": cold_cache_coverage,
        "warm_cache_status_coverage": warm_cache_coverage,
        "cache_protocol_valid": (
            cold_cache_coverage == 1.0
            and warm_cache_coverage == 1.0
            and cold_cache_hit_rate == 0.0
            and warm_cache_hit_rate is not None
            and warm_cache_hit_rate >= 0.90
        ),
        "source_count_mean": safe_mean(
            [float(row.get("source_count", 0)) for row in rows]
        ),
        "context_chars_mean": safe_mean(
            [float(row.get("context_chars", 0)) for row in rows]
        ),
        "answer_chars_mean": safe_mean(
            [float(row.get("answer_chars", 0)) for row in rows]
        ),
        "source_utilization": safe_mean(
            [min(1.0, float(row.get("source_count", 0)) / 5.0) for row in rows]
        ),
        "telemetry_coverage": safe_mean(
            [
                float(bool(row.get("telemetry")))
                for row in rows
                if row.get("scenario") != "streaming"
            ]
        ),
        "key_distribution": dict(
            Counter(
                row.get("key_fingerprint")
                for row in rows
                if row.get("key_fingerprint")
            )
        ),
        "retry_count": sum(int(row.get("retry_count") or 0) for row in rows),
        "cooldown_events": sum(
            int(row.get("cooldown_events") or 0) for row in rows
        ),
        "realistic_score": safe_mean(
            [
                float(row["success"])
                for row in rows
                if row.get("eval_split") == "realistic"
            ]
        ),
        "stress_score": safe_mean(
            [float(row["success"]) for row in rows if row.get("eval_split") == "stress"]
        ),
        "by_scenario": {},
        "by_expected_path": {},
    }
    for scenario in sorted({str(row["scenario"]) for row in rows}):
        group = [row for row in rows if row["scenario"] == scenario]
        summary["by_scenario"][scenario] = {
            "n": len(group),
            "success_rate": safe_mean([float(row["success"]) for row in group]),
            "latency_ms": _latency_summary([row["latency_ms"] for row in group]),
        }
    for expected_path in sorted(
        {str(row["expected_path"]) for row in rows if row.get("expected_path")}
    ):
        group = [row for row in rows if row.get("expected_path") == expected_path]
        summary["by_expected_path"][expected_path] = {
            "n": len(group),
            "success_rate": safe_mean([float(row["success"]) for row in group]),
            "status_accuracy": safe_mean(
                [float(bool(row.get("expected_status_match"))) for row in group]
            ),
            "latency_ms": _latency_summary([row["latency_ms"] for row in group]),
        }
    return summary


def evaluate_production(
    cases: list[dict[str, Any]],
    *,
    base_url: str,
    limit: int | None = None,
    checkpoint_path: Path | None = None,
    resume: bool = False,
    checkpoint_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    selected = cases[:limit]
    identity = _eval_checkpoint_identity(
        cases, suite="production", context=checkpoint_context, base_url=base_url,
    ) if checkpoint_path else None
    rows = _load_eval_checkpoint(checkpoint_path, resume=resume, identity=identity)
    completed_ids = {row["id"] for row in rows}
    pending = [case for case in selected if case["id"] not in completed_ids]

    def run(case: dict[str, Any]) -> dict[str, Any]:
        endpoint = "/chat/stream" if case["scenario"] == "streaming" else "/chat"
        payload = json.dumps(
            {
                "query": case["query"],
                "cohort": case.get("cohort"),
                "include_debug": True,
                **_case_history_kwargs(case),
            }
        ).encode("utf-8")
        req = urllib_request.Request(
            base_url.rstrip("/") + endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.perf_counter()
        ttft = None
        status_code = 0
        body = b""
        try:
            stream_done = False
            stream_error = False
            stream_token_chars = 0
            stream_metadata: dict[str, Any] = {}
            answer_parts: list[str] = []
            with urllib_request.urlopen(
                req, timeout=float(case.get("timeout_seconds", 90))
            ) as response:
                status_code = response.status
                if endpoint.endswith("/stream"):
                    chunks: list[bytes] = []
                    current_event = ""
                    for line in response:
                        chunks.append(line)
                        decoded = line.decode("utf-8", errors="replace").strip()
                        if decoded.startswith("event:"):
                            current_event = decoded.split(":", 1)[1].strip()
                            stream_done = stream_done or current_event == "done"
                            stream_error = stream_error or current_event == "error"
                        elif decoded.startswith("data:"):
                            raw_data = decoded.split(":", 1)[1].strip()
                            try:
                                event_data = json.loads(raw_data)
                            except json.JSONDecodeError:
                                event_data = {}
                            if current_event == "metadata":
                                stream_metadata = event_data
                            elif current_event == "token":
                                answer_parts.append(str(event_data.get("text") or ""))
                                stream_token_chars += len(
                                    str(event_data.get("text") or "")
                                )
                                if ttft is None:
                                    ttft = (time.perf_counter() - started) * 1000
                    body = b"".join(chunks)
                else:
                    body = response.read()
            parsed = (
                json.loads(body.decode("utf-8")) if endpoint.endswith("chat") else {}
            )
            response_payload = (
                stream_metadata if endpoint.endswith("/stream") else parsed
            )
            debug = response_payload.get("debug") or {}
            telemetry = debug.get("evaluation_telemetry") or {}
            transport_success = 200 <= status_code < 300
            if endpoint.endswith("/stream"):
                payload_success = (
                    stream_done
                    and not stream_error
                    and (
                        stream_token_chars > 0
                        or str(stream_metadata.get("status") or "")
                        in {
                            "needs_clarification",
                            "out_of_domain",
                        }
                    )
                )
                answer_chars = stream_token_chars
                answer_text = "".join(answer_parts)
            else:
                answer_text = str(parsed.get("answer") or "").strip()
                payload_success = bool(answer_text) and not parsed.get("error_type")
                answer_chars = len(answer_text)
            response_status = str(response_payload.get("status") or "")
            expected_status = _expected_response_status(case)
            return {
                **case,
                "success": transport_success and payload_success,
                "transport_success": transport_success,
                "payload_success": payload_success,
                "status_code": status_code,
                "latency_ms": (time.perf_counter() - started) * 1000,
                "ttft_ms": ttft,
                "answer_chars": answer_chars,
                "answer": answer_text,
                "response_payload": response_payload,
                "stream_done": stream_done if endpoint.endswith("/stream") else None,
                "stream_error": stream_error if endpoint.endswith("/stream") else None,
                "response_status": response_status,
                "response_intent": response_payload.get("intent"),
                "response_strategy": response_payload.get("strategy"),
                "response_error_type": response_payload.get("error_type"),
                "response_error_message": response_payload.get("error_message"),
                "expected_response_status": expected_status,
                "expected_status_match": _response_status_matches_expected(
                    response_status,
                    expected_status,
                ),
                "used_cache": response_payload.get("used_cache"),
                "source_count": len(
                    response_payload.get("citations_used")
                    or response_payload.get("citations")
                    or []
                ),
                "context_chars": int(
                    debug.get("context_used_length")
                    or telemetry.get("context_chars")
                    or 0
                ),
                "key_fingerprint": telemetry.get("key_fingerprint"),
                "retry_count": int(telemetry.get("retry_count") or 0),
                "cooldown_events": int(telemetry.get("cooldown_events") or 0),
                "telemetry": telemetry,
            }
        except urllib_error.HTTPError as exc:
            try:
                error_body = exc.read().decode("utf-8", errors="replace")
            except OSError:
                error_body = ""
            return {
                **case,
                "success": False,
                "transport_success": False,
                "payload_success": False,
                "status_code": int(exc.code),
                "latency_ms": (time.perf_counter() - started) * 1000,
                "ttft_ms": ttft,
                "expected_response_status": _expected_response_status(case),
                "expected_status_match": False,
                "error": f"HTTP {exc.code}: {error_body or exc.reason}",
            }
        except Exception as exc:
            return {
                **case,
                "success": False,
                "status_code": status_code,
                "latency_ms": (time.perf_counter() - started) * 1000,
                "ttft_ms": ttft,
                "expected_response_status": _expected_response_status(case),
                "expected_status_match": False,
                "error": str(exc),
            }

    sequential = [case for case in pending if case["scenario"] != "burst"]
    sequential_progress = tqdm(
        sequential,
        desc="Production Eval",
        unit="req",
        dynamic_ncols=True,
    )
    for case in sequential_progress:
        sequential_progress.set_postfix_str(str(case.get("id") or "unknown"))
        row = run(case)
        rows.append(row)
        _save_eval_checkpoint(checkpoint_path, rows, identity=identity)
        sequential_progress.set_postfix(
            {
                "case": case.get("id"),
                "ok": int(bool(row.get("success"))),
                "ms": int(float(row.get("latency_ms") or 0)),
            },
            refresh=False,
        )
    bursts = [case for case in pending if case["scenario"] == "burst"]
    by_concurrency: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for case in bursts:
        by_concurrency[int(case.get("concurrency", 3))].append(case)
    for concurrency, group in by_concurrency.items():
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {executor.submit(run, case): case for case in group}
            burst_progress = tqdm(
                as_completed(futures),
                total=len(futures),
                desc=f"Production Burst c={concurrency}",
                unit="req",
                dynamic_ncols=True,
            )
            for future in burst_progress:
                case = futures[future]
                row = future.result()
                rows.append(row)
                _save_eval_checkpoint(checkpoint_path, rows, identity=identity)
                burst_progress.set_postfix(
                    {
                        "case": case.get("id"),
                        "ok": int(bool(row.get("success"))),
                        "ms": int(float(row.get("latency_ms") or 0)),
                    },
                    refresh=False,
                )

    by_id = {row["id"]: row for row in rows}
    rows = [by_id[case["id"]] for case in selected if case["id"] in by_id]
    summary = _summarize_production_rows(rows)
    return {
        "suite": "production",
        "base_url": base_url,
        "summary": summary,
        "cases": rows,
    }


def _latency_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "max": 0.0}
    return {
        "mean": statistics.fmean(values),
        "p50": percentile(values, 0.50),
        "p90": percentile(values, 0.90),
        "p95": percentile(values, 0.95),
        "max": max(values),
    }


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
