from __future__ import annotations

import json
import os
import re
import statistics
import time
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable
from urllib import request as urllib_request
from tqdm import tqdm

from .dataset import load_json
from .judge import GroqJudgeClient, compact_judge_packet
from .metrics import (
    bootstrap_mean_ci,
    percentile,
    retrieval_metrics,
    safe_mean,
    wilson_interval,
)


ROOT = Path(__file__).resolve().parents[2]
DETERMINISTIC_STRATEGIES = {
    "foreign_language_lookup",
    "study_duration_lookup",
    "scholarship_classification_lookup",
    "student_service_lookup",
    "office_lookup",
    "program_lookup",
    "form_lookup",
    "formula_lookup",
    "structured_lookup",
    "structured_table",
}
STRUCTURED_STRATEGIES = {"structured_table"}


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
        "form_templates": "data/processed/forms/clean_form_templates.json",
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


def evaluate_deterministic(
    cases: list[dict[str, Any]],
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    from src.retrieval.core import retrieval_pipeline as pipeline

    resources = load_runtime_resources()
    original_retrieve = pipeline.retrieve_with_plan
    pipeline.retrieve_with_plan = lambda *args, **kwargs: []
    previous_router_cache = os.environ.get("STUDENT_RAG_DISABLE_ROUTER_CACHE")
    previous_router_wait = os.environ.get("STUDENT_RAG_ROUTER_WAIT_WHEN_LIMITED")
    os.environ["STUDENT_RAG_DISABLE_ROUTER_CACHE"] = "1"
    os.environ["STUDENT_RAG_ROUTER_WAIT_WHEN_LIMITED"] = "1"
    rows: list[dict[str, Any]] = []
    try:
        for case in cases[:limit]:
            started = time.perf_counter()
            try:
                result = pipeline.run_retrieval_pipeline(
                    query=case["query"],
                    model=None,
                    collection=None,
                    scoring_tables=resources["scoring_tables"],
                    formula_rules=resources["formula_rules"],
                    entity_registry=[],
                    expansion_rules=[],
                    form_templates=resources["form_templates"],
                    office_directory=resources["student_office_profiles"],
                    student_service_directory=resources["student_service_directory"],
                    foreign_language_tables=resources["foreign_language_tables"],
                    structured_tables_registry=resources["structured_tables_registry"],
                    program_directory=resources["program_directory"],
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
                elif result.get("out_of_domain") or result.get("intent") == "out_of_domain":
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
                citations = result.get("citations") or []
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
                    not expected_citation_type
                    or c.get("chunk_type") == expected_citation_type
                    or (c.get("metadata") or {}).get("content_type")
                    == expected_citation_type
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
                item_count_ok = expected_count is None or (
                    isinstance(actual_items, list)
                    and len(actual_items) == int(expected_count)
                )
                numeric_expected = case.get("expected_numeric_value")
                tolerance = float(case.get("numeric_tolerance", 0.0))
                numeric_ok = numeric_expected is None or any(
                    abs(number - float(numeric_expected)) <= tolerance
                    for number in _numeric_values(structured)
                )
                expected_group = case["expected_group"]
                accepted_groups = (
                    {"clarification", "rag"}
                    if expected_group == "clarification_or_rag"
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
                elif expected_group == "clarification_or_rag":
                    intent_ok = actual_group in {"clarification", "rag"}
                elif expected_group == "structured":
                    intent_ok = actual_group == "structured"
                else:
                    intent_ok = not any(expected_intents) or result.get(
                        "intent"
                    ) in set(expected_intents)
                expected_strategies = case.get("expected_strategies") or [
                    case.get("expected_strategy")
                ]
                if expected_group == "rag":
                    strategy_ok = actual_group == "rag" and str(
                        result.get("strategy") or ""
                    ).startswith("semantic")
                elif expected_group == "clarification_or_rag":
                    strategy_ok = actual_group in {"clarification", "rag"}
                elif expected_group == "structured":
                    if set(expected_strategies) == {"structured_table"}:
                        strategy_ok = actual_group == "structured"
                    else:
                        strategy_ok = actual_group == "structured" and (
                            not any(expected_strategies)
                            or result.get("strategy") in set(expected_strategies)
                        )
                else:
                    strategy_ok = not any(expected_strategies) or result.get(
                        "strategy"
                    ) in set(expected_strategies)
                fallback_ok = (
                    actual_group not in {"deterministic", "structured"}
                    if expected_group not in {"deterministic", "structured"}
                    else True
                )
                expected_llm_called = case.get("expected_llm_called")
                llm_call_ok = expected_llm_called is None or bool(
                    result.get("needs_llm_answer")
                ) == bool(expected_llm_called)
                lookup_type_ok = (
                    expected_group not in {"deterministic", "structured"}
                    or not case.get("expected_lookup_type")
                    or case["expected_lookup_type"] in lookup_match_text
                    or lookup_type in case["expected_lookup_type"]
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
                rows.append(
                    {
                        **case,
                        "actual_group": actual_group,
                        "actual_intent": result.get("intent"),
                        "actual_strategy": strategy,
                        "actual_lookup_type": lookup_type,
                        "actual_llm_called": bool(result.get("needs_llm_answer")),
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
                        "router_model": result.get("router_model"),
                        "router_cache_hit": bool(result.get("router_cache_hit")),
                        "router_api_success": bool(result.get("router_model"))
                        and not bool(
                            (result.get("router_decision") or {}).get("router_error")
                        ),
                        "router_validation_errors": result.get(
                            "router_validation_errors"
                        )
                        or [],
                        "router_decision": result.get("router_decision") or {},
                        "passed": passed,
                        "latency_ms": (time.perf_counter() - started) * 1000,
                    }
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
    finally:
        pipeline.retrieve_with_plan = original_retrieve
        if previous_router_cache is None:
            os.environ.pop("STUDENT_RAG_DISABLE_ROUTER_CACHE", None)
        else:
            os.environ["STUDENT_RAG_DISABLE_ROUTER_CACHE"] = previous_router_cache
        if previous_router_wait is None:
            os.environ.pop("STUDENT_RAG_ROUTER_WAIT_WHEN_LIMITED", None)
        else:
            os.environ["STUDENT_RAG_ROUTER_WAIT_WHEN_LIMITED"] = previous_router_wait

    positives = [
        row
        for row in rows
        if row["expected_group"] in {"deterministic", "structured"}
    ]
    negatives = [
        row
        for row in rows
        if row["expected_group"] not in {"deterministic", "structured"}
    ]
    tp = sum(
        row.get("actual_group") in {"deterministic", "structured"}
        for row in positives
    )
    fn = len(positives) - tp
    fp = sum(
        row.get("actual_group") in {"deterministic", "structured"}
        for row in negatives
    )
    tn = len(negatives) - fp
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    summary = {
        "n": len(rows),
        "passed": sum(bool(row.get("passed")) for row in rows),
        "exactness": safe_mean([float(bool(row.get("passed"))) for row in rows]),
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
        "cross_cohort_leak": sum(bool(row.get("cross_cohort_leak")) for row in rows),
        "router_api_success_rate": safe_mean(
            [float(bool(row.get("router_api_success"))) for row in rows]
        ),
        "router_cache_hit_rate": safe_mean(
            [float(bool(row.get("router_cache_hit"))) for row in rows]
        ),
        "router_validation_failure_rate": safe_mean(
            [float(bool(row.get("router_validation_errors"))) for row in rows]
        ),
        "latency_ms": _latency_summary([row["latency_ms"] for row in rows]),
        "pass_ci95": wilson_interval(
            sum(bool(row.get("passed")) for row in rows), len(rows)
        ),
        "realistic_score": _split_pass_rate(_split_rows(rows, "realistic")),
        "stress_score": _split_pass_rate(_split_rows(rows, "stress")),
    }
    return {"suite": "deterministic", "summary": summary, "cases": rows}


def evaluate_retrieval(
    cases: list[dict[str, Any]],
    *,
    backend: str,
    mode: str = "full",
    limit: int | None = None,
    pipeline_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    if backend not in {"qdrant", "chroma"}:
        raise ValueError("backend must be qdrant or chroma")
    if mode not in {"full", "no_graph", "vector_only"}:
        raise ValueError("mode must be full, no_graph or vector_only")
    if backend == "chroma" and mode != "full":
        raise ValueError("Chroma is reproducibility-only; ablations require Qdrant")
    previous_backend = os.environ.get("STUDENT_RAG_USE_QDRANT")
    previous_hybrid = os.environ.get("STUDENT_RAG_DISABLE_HYBRID_RETRIEVAL")
    previous_mode = os.environ.get("STUDENT_RAG_EVAL_RETRIEVAL_MODE")
    os.environ["STUDENT_RAG_USE_QDRANT"] = "1" if backend == "qdrant" else "0"
    if backend == "chroma":
        os.environ["STUDENT_RAG_DISABLE_HYBRID_RETRIEVAL"] = "1"
    else:
        os.environ.pop("STUDENT_RAG_DISABLE_HYBRID_RETRIEVAL", None)
    os.environ["STUDENT_RAG_EVAL_RETRIEVAL_MODE"] = mode
    if pipeline_factory is None:
        from src.generation.answer_pipeline import AnswerPipeline

        pipeline_factory = AnswerPipeline
    pipeline = pipeline_factory()
    rows: list[dict[str, Any]] = []
    try:
        for case in cases[:limit]:
            started = time.perf_counter()
            try:
                requested_cohort = case.get("cohort")
                retrieval_cohort = (
                    None
                    if requested_cohort in {None, "", "general", "all"}
                    else requested_cohort
                )
                result = pipeline._run_retrieval(
                    case["query"], cohort=retrieval_cohort
                )
                items = result.get("retrieved_items") or []
                ranked_ids = [_item_parent_id(item) for item in items]
                expected_ids = {
                    item["parent_section_id"] for item in case["relevance_judgments"]
                }
                if not ranked_ids and result.get("structured_result"):
                    ranked_ids = _structured_expected_ids(
                        result["structured_result"], expected_ids
                    )
                grade_by_id = {
                    item["parent_section_id"]: int(item["grade"])
                    for item in case["relevance_judgments"]
                }
                metrics = retrieval_metrics(
                    [grade_by_id.get(parent_id, 0) for parent_id in ranked_ids]
                )
                metrics["mrr"] = metrics.pop("reciprocal_rank")
                citations = result.get("citations") or []
                citation_ids = {_citation_parent_id(item) for item in citations}
                structured = result.get("structured_result") or {}
                cohort_ok = all(
                    _cohort_matches(
                        (item.get("metadata") or {}).get("cohort"), case.get("cohort")
                    )
                    for item in items
                ) and (
                    not structured
                    or _cohort_matches(structured.get("cohort"), case.get("cohort"))
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
                rows.append(
                    {
                        **case,
                        **metrics,
                        "ranked_parent_ids": ranked_ids,
                        "actual_intent": result.get("intent"),
                        "actual_strategy": result.get("strategy"),
                        "citation_binding": bool(expected_ids & citation_ids)
                        or bool(metrics["hit_at_5"]),
                        "cohort_match": cohort_ok,
                        "content_type_match": content_ok,
                        "empty_retrieval": not bool(items),
                        "cohort_leak": not cohort_ok,
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
                        "empty_retrieval": True,
                        "cohort_leak": False,
                        "synthetic_leak": False,
                        "latency_ms": (time.perf_counter() - started) * 1000,
                    }
                )
    finally:
        _restore_env("STUDENT_RAG_USE_QDRANT", previous_backend)
        _restore_env("STUDENT_RAG_DISABLE_HYBRID_RETRIEVAL", previous_hybrid)
        _restore_env("STUDENT_RAG_EVAL_RETRIEVAL_MODE", previous_mode)

    true_rag = [row for row in rows if row["case_type"] == "regulation_true_rag"]
    summary = _retrieval_summary(rows, true_rag)
    return {
        "suite": "retrieval",
        "backend": backend,
        "mode": mode,
        "summary": summary,
        "breakdowns": _retrieval_breakdowns(rows),
        "cases": rows,
    }


def _retrieval_summary(
    rows: list[dict[str, Any]], headline: list[dict[str, Any]]
) -> dict[str, Any]:
    metric_names = ("hit_at_1", "hit_at_3", "hit_at_5", "mrr", "ndcg_at_5")
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
                [float(row.get("hit_at_5", 0.0)) for row in headline if row.get("eval_split") == "realistic"]
            ),
            "stress_score": safe_mean(
                [float(row.get("hit_at_5", 0.0)) for row in headline if row.get("eval_split") == "stress"]
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


def _retrieval_breakdowns(rows: list[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for field in ("cohort", "topic", "query_style", "question_style", "expected_path", "eval_split"):
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
) -> dict[str, Any]:
    if pipeline_factory is None:
        from src.generation.answer_pipeline import AnswerPipeline

        pipeline_factory = AnswerPipeline
    previous_offline = os.environ.get("STUDENT_RAG_OFFLINE_EVAL")
    previous_quality = os.environ.get("STUDENT_RAG_QUALITY_EVAL")
    os.environ.pop("STUDENT_RAG_OFFLINE_EVAL", None)
    os.environ["STUDENT_RAG_QUALITY_EVAL"] = "1"
    existing = load_json(cache_path) if resume and cache_path.exists() else []
    by_id = {row["id"]: row for row in existing}
    try:
        pipeline = pipeline_factory()
        for case in tqdm(cases[:limit], desc="Generating Answers", unit="case"):
            if case["id"] in by_id:
                continue
            started = time.perf_counter()
            try:
                output = pipeline.answer(case["query"], cohort=case.get("cohort"))
                record = {
                    "id": case["id"],
                    **output,
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
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps(list(by_id.values()), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    finally:
        _restore_env("STUDENT_RAG_OFFLINE_EVAL", previous_offline)
        _restore_env("STUDENT_RAG_QUALITY_EVAL", previous_quality)
    rows = [by_id[case["id"]] for case in cases[:limit] if case["id"] in by_id]
    return {
        "suite": "answer_generation",
        "summary": {
            "n": len(rows),
            "success_rate": safe_mean(
                [float(row.get("status") == "answered") for row in rows]
            ),
            "latency_ms": _latency_summary(
                [float(row.get("latency_ms", 0)) for row in rows]
            ),
        },
        "cases": rows,
    }


def judge_answers(
    cases: list[dict[str, Any]],
    answer_cache: list[dict[str, Any]],
    *,
    checkpoint_path: Path,
    resume: bool,
    limit: int | None = None,
    judge_client: GroqJudgeClient | None = None,
) -> dict[str, Any]:
    client = judge_client or GroqJudgeClient()
    answers = {row["id"]: row for row in answer_cache}
    existing = load_json(checkpoint_path) if resume and checkpoint_path.exists() else []
    judged = {row["id"]: row for row in existing}
    for case in tqdm(cases[:limit], desc="Judging Answers", unit="case"):
        if case["id"] in judged:
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
            "judge": result,
            **deterministic,
            "judge_latency_ms": (time.perf_counter() - started) * 1000,
            "packet_required_fact_coverage": len(
                packet["required_facts_present_in_packet"]
            )
            / max(1, len(case.get("required_facts") or [])),
        }
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(
            json.dumps(list(judged.values()), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
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
            [
                row["judge"]["scores"]["answer_correctness"]
                for row in split_valid
            ]
        )
    return {
        "suite": "judge",
        "summary": summary,
        "cases": rows,
        "human_audit_template": build_human_audit_template(cases, rows),
    }


def _answer_checks(case: dict[str, Any], answer: dict[str, Any]) -> dict[str, Any]:
    text = _normalize_eval_text(answer.get("answer") or "")
    required = [
        _normalize_eval_text(item) for item in case.get("required_facts") or []
    ]
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
    }
    citation_exact_match = bool(expected_ids & actual_ids) if expected_ids else not actual_ids
    required_fact_hit = (
        all(_soft_fact_match(fact, text) for fact in required) if required else True
    )
    answer_success = answer.get("status") in {
        "answered",
        "needs_clarification",
        "out_of_domain",
    }
    behavior = str(case.get("expected_answer_behavior") or "direct_answer")
    return {
        "required_fact_hit": required_fact_hit,
        "numeric_accuracy": all(value in text for value in numeric)
        if numeric
        else True,
        "citation_exact_match": citation_exact_match,
        "abstention_correct": (not abstained) if answerable else abstained,
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
    row_ids = {row["id"] for row in rows}
    selected: list[dict[str, Any]] = []
    buckets = (
        ("regulation_true_rag", 12),
        ("structured_mixed", 4),
        ("unanswerable", 4),
    )
    for case_type, count in buckets:
        candidates = [
            case
            for case in cases
            if case["id"] in row_ids and case.get("case_type") == case_type
        ]
        for case in candidates[:count]:
            selected.append(
                {
                    "id": case["id"],
                    "case_type": case_type,
                    "human_score": None,
                    "critical_false_pass": None,
                    "notes": "",
                    "repeat_for_consistency": len(selected) < 5,
                    "repeat_score": None,
                }
            )
    return selected


def evaluate_production(
    cases: list[dict[str, Any]],
    *,
    base_url: str,
    limit: int | None = None,
) -> dict[str, Any]:
    selected = cases[:limit]
    rows: list[dict[str, Any]] = []

    def run(case: dict[str, Any]) -> dict[str, Any]:
        endpoint = "/chat/stream" if case["scenario"] == "streaming" else "/chat"
        payload = json.dumps(
            {
                "query": case["query"],
                "cohort": case.get("cohort"),
                "include_debug": True,
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
                        elif (
                            decoded.startswith("data:")
                            and current_event == "token"
                            and ttft is None
                        ):
                            ttft = (time.perf_counter() - started) * 1000
                    body = b"".join(chunks)
                else:
                    body = response.read()
                    ttft = (time.perf_counter() - started) * 1000
            parsed = (
                json.loads(body.decode("utf-8")) if endpoint.endswith("chat") else {}
            )
            debug = parsed.get("debug") or {}
            telemetry = debug.get("evaluation_telemetry") or {}
            return {
                **case,
                "success": 200 <= status_code < 300,
                "status_code": status_code,
                "latency_ms": (time.perf_counter() - started) * 1000,
                "ttft_ms": ttft,
                "used_cache": parsed.get("used_cache"),
                "source_count": len(parsed.get("citations_used") or []),
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
        except Exception as exc:
            return {
                **case,
                "success": False,
                "status_code": status_code,
                "latency_ms": (time.perf_counter() - started) * 1000,
                "ttft_ms": ttft,
                "error": str(exc),
            }

    sequential = [case for case in selected if case["scenario"] != "burst"]
    rows.extend(run(case) for case in sequential)
    bursts = [case for case in selected if case["scenario"] == "burst"]
    by_concurrency: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for case in bursts:
        by_concurrency[int(case.get("concurrency", 3))].append(case)
    for concurrency, group in by_concurrency.items():
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [executor.submit(run, case) for case in group]
            rows.extend(future.result() for future in as_completed(futures))

    summary = {
        "n": len(rows),
        "success_rate": safe_mean([float(row["success"]) for row in rows]),
        "error_rate": safe_mean([float(not row["success"]) for row in rows]),
        "http_429_rate": safe_mean(
            [float(row.get("status_code") == 429) for row in rows]
        ),
        "timeout_rate": safe_mean(
            [float("timed out" in str(row.get("error") or "").lower()) for row in rows]
        ),
        "latency_ms": _latency_summary([row["latency_ms"] for row in rows]),
        "streaming_ttft_ms": _latency_summary(
            [row["ttft_ms"] for row in rows if row.get("ttft_ms") is not None]
        ),
        "cache_hit_rate": safe_mean(
            [float(bool(row.get("used_cache"))) for row in rows]
        ),
        "source_count_mean": safe_mean(
            [float(row.get("source_count", 0)) for row in rows]
        ),
        "context_chars_mean": safe_mean(
            [float(row.get("context_chars", 0)) for row in rows]
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
                row.get("key_fingerprint") for row in rows if row.get("key_fingerprint")
            )
        ),
        "retry_count": sum(int(row.get("retry_count") or 0) for row in rows),
        "cooldown_events": sum(int(row.get("cooldown_events") or 0) for row in rows),
        "realistic_score": safe_mean(
            [float(row["success"]) for row in rows if row.get("eval_split") == "realistic"]
        ),
        "stress_score": safe_mean(
            [float(row["success"]) for row in rows if row.get("eval_split") == "stress"]
        ),
        "by_scenario": {},
    }
    for scenario in sorted({row["scenario"] for row in rows}):
        group = [row for row in rows if row["scenario"] == scenario]
        summary["by_scenario"][scenario] = {
            "n": len(group),
            "success_rate": safe_mean([float(row["success"]) for row in group]),
            "latency_ms": _latency_summary([row["latency_ms"] for row in group]),
        }
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
