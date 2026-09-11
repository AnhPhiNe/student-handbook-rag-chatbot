"""Retrieval suite: rank quality (hit@k, MRR, nDCG) of the evidence the
pipeline retrieves for each case."""

from __future__ import annotations

import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from .metrics import (
    bootstrap_mean_ci,
    retrieval_metrics,
    safe_mean,
)
from src.retrieval.core.retrieval_mode import (
    DEFAULT_RETRIEVAL_MODE,
    SUPPORTED_RETRIEVAL_MODES,
)
from .shared import (
    case_history_kwargs,
    citation_parent_id,
    cohort_matches,
    eval_checkpoint_identity,
    latency_summary,
    load_eval_checkpoint,
    progress_cases,
    restore_env,
    save_eval_checkpoint,
    wait_for_bm25_ready,
)


def _item_applicability(item: dict[str, Any]) -> Any:
    metadata = item.get("metadata") or {}
    return (
        metadata.get("applicable_cohorts")
        or metadata.get("cohorts")
        or metadata.get("cohort")
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


def _first_retrieval_telemetry(items: list[dict[str, Any]]) -> dict[str, Any]:
    for item in items:
        telemetry = (item.get("metadata") or {}).get("retrieval_telemetry") or {}
        if telemetry:
            return telemetry
    return {}


def _run_pure_regulation_retrieval(
    pipeline: Any,
    query: str,
    cohort: str | None,
) -> dict[str, Any]:
    """Run retrieval-only evaluation without changing production orchestration."""

    from src.retrieval.core.hybrid_pipeline import run_hybrid_retrieval_pipeline

    retrieval_query = pipeline.slang_normalizer.normalize_for_retrieval(query)
    result = run_hybrid_retrieval_pipeline(
        query=query,
        top_k=pipeline.config["retrieval"]["default_top_k"],
        cohort=cohort,
        intent="open_question",
        strategy="regulation",
        retrieval_query=retrieval_query,
    )
    query_handling = {
        "raw_query": query,
        "effective_query": query,
        "mode": "raw",
        "context_mode": "standalone",
        "source": "evaluation_pure_regulation",
        "normalized_query": None,
        "standalone_query": None,
        "referenced_turns": [],
        "normalization_confidence": "none",
        "context_confidence": "none",
        "validation_errors": [],
        "needs_clarification": False,
        "clarification_question": None,
    }
    result.update(
        {
            "selected_cohort": cohort,
            "evaluation_scope": "pure_regulation",
            "raw_query": query,
            "effective_query": query,
            "query_handling": query_handling,
            "retrieval_query": retrieval_query,
        }
    )
    return result


def evaluate_retrieval(
    cases: list[dict[str, Any]],
    *,
    backend: str,
    mode: str = DEFAULT_RETRIEVAL_MODE,
    scope: str = "pure",
    limit: int | None = None,
    pipeline_factory: Callable[[], Any] | None = None,
    checkpoint_path: Path | None = None,
    resume: bool = False,
    checkpoint_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Evaluate retrieval quality against labeled evidence targets."""

    if backend != "qdrant":
        raise ValueError("backend must be qdrant")
    if mode not in SUPPORTED_RETRIEVAL_MODES:
        raise ValueError(f"mode must be one of {sorted(SUPPORTED_RETRIEVAL_MODES)}")
    if scope not in {"pure", "end_to_end"}:
        raise ValueError("scope must be pure or end_to_end")
    identity = (
        eval_checkpoint_identity(
            cases,
            suite="retrieval",
            context=checkpoint_context,
            backend=backend,
            mode=mode,
            scope=scope,
        )
        if checkpoint_path
        else None
    )
    rows = load_eval_checkpoint(checkpoint_path, resume=resume, identity=identity)
    completed_ids = {row["id"] for row in rows}
    previous_runtime_mode = os.environ.get("STUDENT_RAG_RETRIEVAL_MODE")
    previous_mode = os.environ.get("STUDENT_RAG_EVAL_RETRIEVAL_MODE")
    previous_ablation_guard = os.environ.get("STUDENT_RAG_ALLOW_RETRIEVAL_ABLATION")
    previous_router_wait = os.environ.get("STUDENT_RAG_ROUTER_WAIT_WHEN_LIMITED")
    previous_router_cache = os.environ.get("STUDENT_RAG_DISABLE_ROUTER_CACHE")
    os.environ["STUDENT_RAG_RETRIEVAL_MODE"] = mode
    os.environ["STUDENT_RAG_EVAL_RETRIEVAL_MODE"] = mode
    os.environ["STUDENT_RAG_ALLOW_RETRIEVAL_ABLATION"] = "1"
    os.environ["STUDENT_RAG_DISABLE_ROUTER_CACHE"] = "1"
    if scope != "pure":
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
            wait_for_bm25_ready()
        progress = progress_cases(
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
                if scope == "pure" and uses_default_pipeline:
                    result = _run_pure_regulation_retrieval(
                        pipeline,
                        case["query"],
                        retrieval_cohort,
                    )
                else:
                    result = pipeline._run_retrieval(
                        case["query"],
                        cohort=retrieval_cohort,
                        **case_history_kwargs(case),
                    )
                items = result.get("retrieved_items") or []
                related_items = result.get("related_items") or []
                ranked_ids = list(
                    dict.fromkeys(_item_parent_id(item) for item in items)
                )
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
                citation_ids = {citation_parent_id(item) for item in citations}
                structured = result.get("structured_result") or {}
                cohort_ok = all(
                    cohort_matches(_item_applicability(item), case.get("cohort"))
                    for item in items
                ) and (
                    not structured
                    or cohort_matches(
                        structured.get("applicable_cohorts")
                        or structured.get("cohorts")
                        or structured.get("cohort"),
                        case.get("cohort"),
                    )
                )
                related_cohort_ok = all(
                    cohort_matches(_item_applicability(item), case.get("cohort"))
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
                query_handling = result.get("query_handling")
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
                save_eval_checkpoint(checkpoint_path, rows, identity=identity)
    finally:
        restore_env("STUDENT_RAG_RETRIEVAL_MODE", previous_runtime_mode)
        restore_env("STUDENT_RAG_EVAL_RETRIEVAL_MODE", previous_mode)
        restore_env(
            "STUDENT_RAG_ALLOW_RETRIEVAL_ABLATION",
            previous_ablation_guard,
        )
        restore_env("STUDENT_RAG_ROUTER_WAIT_WHEN_LIMITED", previous_router_wait)
        restore_env("STUDENT_RAG_DISABLE_ROUTER_CACHE", previous_router_cache)

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
        "hit_at_1",
        "hit_at_3",
        "hit_at_5",
        "mrr",
        "ndcg_at_5",
        "primary_hit_at_5",
        "required_source_recall_at_5",
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
            "latency_ms": latency_summary([float(row["latency_ms"]) for row in rows]),
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
            "phoranker_candidate_chunks": latency_summary(
                [
                    float(row.get("phoranker_candidate_chunks") or 0)
                    for row in rows
                    if row.get("phoranker_candidate_chunks") is not None
                ]
            ),
            "phoranker_candidate_parents": latency_summary(
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
        aliases = {}
        for group in case.get("equivalent_source_groups") or []:
            members = [parent for parent in group if parent in relevance]
            if members:
                aliases.update({parent: members[0] for parent in members})
        relevance = {
            aliases.get(parent, parent): grade for parent, grade in relevance.items()
        }
        # Equivalent sources satisfy one requirement. A duplicate still consumes
        # its retrieval rank but earns no second gain; never shift rank six to five.
        seen = set()
        ranked_units = []
        for parent in ids:
            unit = aliases.get(parent, parent)
            ranked_units.append(unit if unit not in seen else None)
            seen.add(unit)
        metrics = retrieval_metrics(
            [relevance.get(parent_id, 0) for parent_id in ranked_units],
            gold_grades=list(relevance.values()),
        )
        required_ids = {
            parent_id for parent_id, grade in relevance.items() if grade == 2
        }
        found = required_ids & set(ranked_units[:5])
        metrics["primary_hit_at_5"] = float(bool(found))
        metrics["required_source_recall_at_5"] = (
            len(found) / len(required_ids) if required_ids else 0.0
        )
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
            "ndcg_at_5": safe_mean([metric["ndcg_at_5"] for metric in unit_metrics]),
            "primary_hit_at_5": min(
                metric["primary_hit_at_5"] for metric in unit_metrics
            ),
            "required_source_recall_at_5": safe_mean(
                [metric["required_source_recall_at_5"] for metric in unit_metrics]
            ),
        },
        "per_cohort_execution_unit",
    )


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
