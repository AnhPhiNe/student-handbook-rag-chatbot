"""Generate + judge suite: produce answers with the runtime pipeline, then
score them with the pinned LLM judge."""

from __future__ import annotations

import hashlib
import os
import re
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from .dataset import stable_json_hash
from .judge import GroqJudgeClient, compact_judge_packet
from .metrics import (
    bootstrap_mean_ci,
    safe_mean,
)
from src.retrieval.core.retrieval_mode import DEFAULT_RETRIEVAL_MODE
from .shared import (
    case_history_kwargs,
    citation_parent_id,
    eval_checkpoint_identity,
    latency_summary,
    load_eval_checkpoint,
    progress_cases,
    restore_env,
    save_eval_checkpoint,
    wait_for_bm25_ready,
)


def generate_answers(
    cases: list[dict[str, Any]],
    *,
    cache_path: Path,
    resume: bool,
    limit: int | None = None,
    pipeline_factory: Callable[[], Any] | None = None,
    checkpoint_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate answer artifacts for the evaluation dataset."""

    from src.retrieval.core.hybrid_pipeline import initialize_hybrid_retriever

    identity = eval_checkpoint_identity(
        cases,
        suite="answer_generation",
        context=checkpoint_context,
        retrieval_mode=DEFAULT_RETRIEVAL_MODE,
    )
    existing = load_eval_checkpoint(cache_path, resume=resume, identity=identity)
    uses_default_pipeline = pipeline_factory is None
    if pipeline_factory is None:
        from src.generation.answer_pipeline import AnswerPipeline

        pipeline_factory = AnswerPipeline
    previous_offline = os.environ.get("STUDENT_RAG_OFFLINE_EVAL")
    previous_quality = os.environ.get("STUDENT_RAG_QUALITY_EVAL")
    previous_runtime_retrieval_mode = os.environ.get("STUDENT_RAG_RETRIEVAL_MODE")
    previous_retrieval_mode = os.environ.get("STUDENT_RAG_EVAL_RETRIEVAL_MODE")
    previous_router_cache = os.environ.get("STUDENT_RAG_DISABLE_ROUTER_CACHE")
    os.environ.pop("STUDENT_RAG_OFFLINE_EVAL", None)
    os.environ["STUDENT_RAG_QUALITY_EVAL"] = "1"
    # Answer-quality evaluation must exercise the configured production retrieval
    # contract instead of inheriting an ablation mode from the ambient environment.
    os.environ["STUDENT_RAG_RETRIEVAL_MODE"] = DEFAULT_RETRIEVAL_MODE
    os.environ["STUDENT_RAG_EVAL_RETRIEVAL_MODE"] = DEFAULT_RETRIEVAL_MODE
    os.environ["STUDENT_RAG_DISABLE_ROUTER_CACHE"] = "1"
    by_id = {row["id"]: row for row in existing}
    try:
        pipeline = pipeline_factory()
        if uses_default_pipeline:
            initialize_hybrid_retriever()
            wait_for_bm25_ready()
        progress = progress_cases(
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
                    case["query"],
                    cohort=case.get("cohort"),
                    **case_history_kwargs(case),
                )
                clean_output = {k: v for k, v in output.items() if k != "tracker"}
                record = {
                    "id": case["id"],
                    **clean_output,
                    "evaluation_retrieval_mode": DEFAULT_RETRIEVAL_MODE,
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
            save_eval_checkpoint(cache_path, list(by_id.values()), identity=identity)
    finally:
        restore_env("STUDENT_RAG_OFFLINE_EVAL", previous_offline)
        restore_env("STUDENT_RAG_QUALITY_EVAL", previous_quality)
        restore_env(
            "STUDENT_RAG_RETRIEVAL_MODE",
            previous_runtime_retrieval_mode,
        )
        restore_env("STUDENT_RAG_DISABLE_ROUTER_CACHE", previous_router_cache)
        restore_env(
            "STUDENT_RAG_EVAL_RETRIEVAL_MODE",
            previous_retrieval_mode,
        )
    rows = [by_id[case["id"]] for case in cases[:limit] if case["id"] in by_id]
    return {
        "suite": "answer_generation",
        "summary": {
            "n": len(rows),
            "retrieval_mode": DEFAULT_RETRIEVAL_MODE,
            "success_rate": safe_mean(
                [float(row.get("status") == "answered") for row in rows]
            ),
            "latency_ms": latency_summary(
                [float(row.get("latency_ms", 0)) for row in rows]
            ),
        },
        "cases": rows,
    }


def load_answer_checkpoint(
    cases: list[dict[str, Any]],
    cache_path: Path,
    *,
    checkpoint_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Verify generation provenance before using cached answers in a new judge run."""
    identity = eval_checkpoint_identity(
        cases,
        suite="answer_generation",
        context=checkpoint_context,
        retrieval_mode=DEFAULT_RETRIEVAL_MODE,
    )
    return load_eval_checkpoint(cache_path, resume=True, identity=identity)


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
    """Score generated answers with the configured automated judge."""

    identity = eval_checkpoint_identity(
        cases,
        suite="judge",
        context=checkpoint_context,
        answer_cache_hash=stable_json_hash(answer_cache),
    )
    existing = load_eval_checkpoint(checkpoint_path, resume=resume, identity=identity)
    client = judge_client or GroqJudgeClient()
    answers = {row["id"]: row for row in answer_cache}
    judged = {row["id"]: row for row in existing}
    progress = progress_cases(
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
        save_eval_checkpoint(checkpoint_path, list(judged.values()), identity=identity)
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
        applicable_values = [
            float(bool(row[metric])) for row in rows if row.get(metric) is not None
        ]
        summary[metric] = safe_mean(applicable_values) if applicable_values else None
        summary[f"{metric}_n"] = len(applicable_values)
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
    numeric_assertions = {
        _canonical_numeric_token(item)
        for item in case.get("numeric_assertions") or []
        if _canonical_numeric_token(item)
    }
    answer_numeric = {
        _canonical_numeric_token(item)
        for item in re.findall(r"\d+(?:[.,]\d+)?%?", text)
    }
    expected_ids = {
        item["parent_section_id"] for item in case.get("expected_citations") or []
    }
    actual_ids = {
        citation_parent_id(item)
        for item in answer.get("citations_used") or answer.get("citations") or []
    }
    answerable = case.get("answerability") == "answerable"
    abstained = answer.get("status") in {
        "needs_clarification",
        "out_of_domain",
        "low_confidence",
    } or _answer_text_abstains(text)
    citation_exact_match = bool(expected_ids & actual_ids) if expected_ids else None
    required_fact_hit = (
        all(_soft_fact_match(fact, text) for fact in required) if required else True
    )
    # Semantic reference prose is not a lexical assertion. Preserve legacy
    # behavior unless the authored suite explicitly marks this check N/A.
    lexical_applicable = case.get("lexical_fact_check_applicable", True)
    answer_success = answer.get("status") in {
        "answered",
        "needs_clarification",
        "out_of_domain",
    }
    behavior = str(case.get("expected_answer_behavior") or "direct_answer")
    expects_no_direct_answer = behavior in {"abstain", "clarify_or_scope"}
    return {
        "required_fact_hit": required_fact_hit if lexical_applicable else None,
        "numeric_accuracy": (
            numeric_assertions <= answer_numeric if numeric_assertions else None
        ),
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
        )
        if lexical_applicable
        else None,
    }


def _normalize_eval_text(value: Any) -> str:
    text = str(value or "").casefold()
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = re.sub(r"[^\w%.,]+", " ", text, flags=re.UNICODE)
    return " ".join(text.split())


def _canonical_numeric_token(value: Any) -> str:
    token = str(value or "").strip().replace(",", ".")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)(%)?", token)
    if not match:
        return ""
    number, percent = match.groups()
    if "." in number:
        number = number.rstrip("0").rstrip(".")
    return f"{number}{percent or ''}"


def _answer_text_abstains(answer_text: str) -> bool:
    abstention_signals = (
        "chua thay",
        "khong tim thay",
        "khong co quy dinh",
        "chua co can cu",
        "khong du can cu",
        "chua du can cu",
        "khong du thong tin",
        "chua du du lieu",
        "khong co du lieu",
        "khong cung cap thong tin",
        "khong the xac dinh",
        "chua truc tiep xac lap",
        "khong co quyen truy cap",
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
    citation_exact_match: bool | None,
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
    """Create a stratified template for manual answer review."""

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
