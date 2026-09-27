"""Replay the composer on recorded evidence packets from an earlier answers run.

A replay isolates the composer (its prompt or model): every case gets the
exact evidence it had before, so retrieval variation cannot confound the
comparison. It skips planning and retrieval, so it is valid only while the
retrieval stack and the evidence packet builder are unchanged.

The pipeline's post-composer steps are reproduced with the same functions:
output cleanup (`format_final_response`) and answer-anchored ordering of the
public citations. That ordering draws from the source run's public citation
list, which is the one approximation: a pool larger than the public limit
was already truncated by the source run.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from src.generation.answer_formatter import format_final_response
from src.generation.citation_formatter import prioritize_citations_by_answer_anchors
from src.generation.prompt_builder import ANSWER_PROMPT_VERSION, render_answer_prompt
from src.retrieval.core.retrieval_mode import DEFAULT_RETRIEVAL_MODE

from .shared import eval_checkpoint_identity, load_eval_checkpoint, progress_cases, save_eval_checkpoint


def replay_record(source: dict[str, Any], *, client: Any, public_max_sources: int) -> dict[str, Any]:
    """Compose one answer again from a recorded packet; copy cases without a composer call."""
    if not source.get("llm_called") or not source.get("context_used"):
        return {**source, "replay": "copied"}
    packet = json.loads(source["context_used"])
    packet["answer_prompt_version"] = ANSWER_PROMPT_VERSION
    prompt, context_used = render_answer_prompt(str(source.get("effective_query") or source["query"]), packet)
    started = time.perf_counter()
    result = client.generate(prompt)
    llm_ms = (time.perf_counter() - started) * 1000
    answer = format_final_response(str(result.get("text") or "").strip()) if result.get("ok") else ""
    ok = bool(answer.strip())
    telemetry = {**(source.get("evaluation_telemetry") or {}), "llm_ms": llm_ms,
                 "retry_count": max(0, int(result.get("attempts") or 1) - 1)}
    return {
        **source,
        "answer": answer,
        "context_used": context_used,
        "citations": prioritize_citations_by_answer_anchors(
            list(source.get("citations") or []), answer, max_sources=public_max_sources,
        ) if ok else list(source.get("citations") or []),
        "status": "answered" if ok else "api_error",
        "error_type": None if ok else (result.get("error_type") or "api_error"),
        "error_message": None if ok else (result.get("error_message") or "Empty answer after output cleanup."),
        "model_used": result.get("model_used"),
        "model": result.get("model_used"),
        "latency_ms": llm_ms,
        "evaluation_telemetry": telemetry,
        "replay": "composer",
    }


def replay_answers(
    cases: list[dict[str, Any]],
    source_rows: list[dict[str, Any]],
    *,
    client: Any,
    cache_path: Path,
    resume: bool,
    public_max_sources: int,
    limit: int | None = None,
    checkpoint_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Replay every case in dataset order and checkpoint like generate_answers."""
    identity = eval_checkpoint_identity(
        cases, suite="answer_generation", context=checkpoint_context,
        retrieval_mode=DEFAULT_RETRIEVAL_MODE,
    )
    by_id = {row["id"]: row for row in load_eval_checkpoint(cache_path, resume=resume, identity=identity)}
    sources = {row["id"]: row for row in source_rows}
    missing = [case["id"] for case in cases[:limit] if case["id"] not in sources]
    if missing:
        raise ValueError(f"Source run lacks cases: {missing[:5]}")
    progress = progress_cases(cases, limit=limit, desc="Replaying Composer")
    for case in progress:
        if case["id"] in by_id:
            continue
        by_id[case["id"]] = replay_record(sources[case["id"]], client=client,
                                          public_max_sources=public_max_sources)
        save_eval_checkpoint(cache_path, list(by_id.values()), identity=identity)
    rows = [by_id[case["id"]] for case in cases[:limit] if case["id"] in by_id]
    return {
        "suite": "answer_generation",
        "summary": {
            "n": len(rows),
            "replayed_n": sum(row.get("replay") == "composer" for row in rows),
            "copied_n": sum(row.get("replay") == "copied" for row in rows),
            "success_rate": sum(row.get("status") == "answered" for row in rows) / max(1, len(rows)),
        },
        "rows": rows,
    }
