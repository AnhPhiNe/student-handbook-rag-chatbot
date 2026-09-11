"""Checkpoint, progress and small helpers shared by the evaluation suites."""

from __future__ import annotations

import json
import os
import statistics
import time
from pathlib import Path
from typing import Any
from tqdm import tqdm

from .dataset import load_json, stable_json_hash
from .metrics import (
    percentile,
)
from src.retrieval.core.runtime_health import get_bm25_runtime_status


def wait_for_bm25_ready(timeout_seconds: float | None = None) -> None:
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


def cohort_matches(actual: Any, expected: str | None) -> bool:
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


def citation_parent_id(citation: dict[str, Any]) -> str:
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


def progress_cases(
    cases: list[dict[str, Any]],
    *,
    limit: int | None,
    desc: str,
) -> tqdm:
    selected = cases[:limit]
    return tqdm(selected, desc=desc, unit="case", dynamic_ncols=True)


def eval_checkpoint_identity(
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


def load_eval_checkpoint(
    path: Path | None,
    *,
    resume: bool,
    identity: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if path is None:
        return []
    identity_path = path.with_suffix(path.suffix + ".identity.json")
    if not path.exists():
        if identity_path.exists() and load_json(identity_path) != identity:
            raise ValueError(
                f"Evaluation checkpoint identity mismatch: {path}; use a fresh output path"
            )
        return []
    if not resume:
        raise FileExistsError(
            f"Refusing to overwrite evaluation checkpoint: {path}; use --resume"
        )
    if identity is None or not identity_path.exists():
        raise ValueError(
            f"Legacy checkpoint has no verifiable identity: {path}. "
            "Keep it as a historical artifact; use a fresh output path or an "
            "explicit legacy compatibility diagnostic, not a headline resume."
        )
    if load_json(identity_path) != identity:
        raise ValueError(
            f"Evaluation checkpoint identity mismatch: {path}; use a fresh output path"
        )
    rows = load_json(path)
    if (
        not isinstance(rows, list)
        or any(
            not isinstance(row, dict) or not isinstance(row.get("id"), str)
            for row in rows
        )
        or len({row["id"] for row in rows}) != len(rows)
    ):
        raise ValueError(f"Invalid or duplicate checkpoint rows: {path}")
    return rows


def save_eval_checkpoint(
    path: Path | None,
    rows: list[dict[str, Any]],
    *,
    identity: dict[str, Any] | None,
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


def case_history_kwargs(case: dict[str, Any]) -> dict[str, Any]:
    history = case.get("chat_history") or case.get("history")
    return {"chat_history": history} if history else {}


def latency_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "p50": 0.0, "p90": 0.0, "p95": 0.0, "max": 0.0}
    return {
        "mean": statistics.fmean(values),
        "p50": percentile(values, 0.50),
        "p90": percentile(values, 0.90),
        "p95": percentile(values, 0.95),
        "max": max(values),
    }


def restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value
