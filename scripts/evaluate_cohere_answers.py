"""Run a controlled answer-suite experiment with a Cohere rerank seam.

The runner explicitly disables the runtime reranker, then reranks the captured
RRF child prefix immediately before production parent grouping. This keeps the
historical experiment reproducible after Cohere became a runtime option and
prevents an accidental double rerank. Planner, structured execution, graph
supplement, evidence packet, Composer, and Judge behavior remain unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.evaluate_cohere_rerank import (
    CANDIDATE_COUNT,
    MODEL,
    EvaluationError,
    append_jsonl,
    call_cohere,
    child_id,
    read_jsonl,
    sha256_file,
    sha256_text,
    validate_response,
)
from src.common.env_loader import load_project_env
from src.evaluation.dataset import load_json
from src.evaluation.suites import generate_answers, judge_answers
from src.retrieval.core.hybrid_pipeline import ChildParentHybridRetriever


CASES_PATH = ROOT / "data/eval/official_v1/generated_answer_cases.json"
EXPECTED_CASES_SHA256 = "0bdefd8a4a541363e9ea9f43721169f965bd2d7227aa9003ac050f7faa5fc49e"


class CheckpointedCohereReranker:
    """Rerank fixed RRF prefixes and persist every successful API response."""

    def __init__(
        self,
        *,
        api_key: str,
        checkpoint_path: Path,
        min_interval_seconds: float,
        timeout_seconds: float,
    ) -> None:
        self.api_key = api_key
        self.checkpoint_path = checkpoint_path
        self.min_interval_seconds = min_interval_seconds
        self.timeout_seconds = timeout_seconds
        rows = read_jsonl(checkpoint_path)
        self.by_key = {str(row["request_key"]): row for row in rows}
        if len(self.by_key) != len(rows):
            raise EvaluationError("Cohere answer checkpoint has duplicate request keys")
        self.previous_request_at = 0.0

    @staticmethod
    def request_key(query: str, chunks: list[dict[str, Any]]) -> str:
        identity = {
            "query": query,
            "candidate_child_ids": [child_id(chunk) for chunk in chunks],
            "candidate_content_sha256": [
                sha256_text(str(chunk.get("content") or "")) for chunk in chunks
            ],
            "model": MODEL,
            "candidate_count": CANDIDATE_COUNT,
        }
        return hashlib.sha256(
            json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()

    def rank(
        self, query: str, scored_chunks: list[tuple[float, dict[str, Any]]]
    ) -> tuple[list[tuple[float, dict[str, Any]]], dict[str, Any]]:
        if len(scored_chunks) < CANDIDATE_COUNT:
            raise EvaluationError(
                f"expected at least {CANDIDATE_COUNT} RRF children, got {len(scored_chunks)}"
            )
        chunks = [dict(chunk) for _, chunk in scored_chunks[:CANDIDATE_COUNT]]
        ids = [child_id(chunk) for chunk in chunks]
        if any(not item for item in ids) or len(set(ids)) != len(ids):
            raise EvaluationError("RRF prefix contains empty or duplicate child IDs")
        key = self.request_key(query, chunks)
        existing = self.by_key.get(key)
        was_cached = existing is not None
        if existing is None:
            elapsed = time.monotonic() - self.previous_request_at
            if elapsed < self.min_interval_seconds:
                time.sleep(self.min_interval_seconds - elapsed)
            response, latency_ms = call_cohere(
                self.api_key,
                query,
                [str(chunk.get("content") or "") for chunk in chunks],
                timeout_seconds=self.timeout_seconds,
            )
            self.previous_request_at = time.monotonic()
            ranking = validate_response(response, len(chunks))
            existing = {
                "request_key": key,
                "query_sha256": sha256_text(query),
                "candidate_child_ids": ids,
                "candidate_content_sha256": [
                    sha256_text(str(chunk.get("content") or "")) for chunk in chunks
                ],
                "ranked_indices": [index for index, _ in ranking],
                "scores": [score for _, score in ranking],
                "latency_ms": latency_ms,
                "response_id": response.get("id"),
                "billed_search_units": int(
                    (((response.get("meta") or {}).get("billed_units") or {}).get("search_units") or 0)
                ),
            }
            append_jsonl(self.checkpoint_path, existing)
            self.by_key[key] = existing
        if existing.get("candidate_child_ids") != ids:
            raise EvaluationError("checkpoint candidate IDs do not match the live RRF prefix")
        content_hashes = [
            sha256_text(str(chunk.get("content") or "")) for chunk in chunks
        ]
        if existing.get("candidate_content_sha256") != content_hashes:
            raise EvaluationError("checkpoint candidate contents do not match")
        indices = [int(index) for index in existing.get("ranked_indices") or []]
        scores = [float(score) for score in existing.get("scores") or []]
        if len(indices) != len(chunks) or set(indices) != set(range(len(chunks))):
            raise EvaluationError("checkpoint ranking is not a complete permutation")
        if len(scores) != len(indices):
            raise EvaluationError("checkpoint score count does not match ranking")
        return (
            [(score, chunks[index]) for index, score in zip(indices, scores)],
            {
                "request_key": key,
                "latency_ms": float(existing.get("latency_ms") or 0.0),
                "cache_hit": was_cached,
            },
        )


def patched_group_method(reranker: CheckpointedCohereReranker, original: Any) -> Any:
    """Create the narrow evaluation seam around production parent grouping."""

    def group(
        self: ChildParentHybridRetriever,
        *,
        query: str,
        scored_chunks: list[tuple[float, dict[str, Any]]],
        top_k_final: int,
        retrieval_telemetry: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        ranked, telemetry = reranker.rank(query, scored_chunks)
        output_telemetry = retrieval_telemetry if retrieval_telemetry is not None else {}
        output_telemetry.update(
            {
                "ranking_method": "cohere_rerank_v4_fast",
                "cohere_reranker_used": True,
                "cohere_candidate_chunks": CANDIDATE_COUNT,
                "cohere_latency_ms": telemetry["latency_ms"],
                "cohere_request_key": telemetry["request_key"],
            }
        )
        return original(
            self,
            query=query,
            scored_chunks=ranked,
            top_k_final=top_k_final,
            retrieval_telemetry=output_telemetry,
        )

    return group


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--generate-only", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--min-interval-seconds", type=float, default=6.2)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args()

    load_project_env()
    api_key = os.getenv("COHERE_API_KEY", "").strip()
    if not api_key:
        raise EvaluationError("COHERE_API_KEY is required")
    if sha256_file(CASES_PATH) != EXPECTED_CASES_SHA256:
        raise EvaluationError("generated-answer dataset hash does not match")
    cases = load_json(CASES_PATH)
    if len(cases) != 150 or len({str(case.get("id")) for case in cases}) != 150:
        raise EvaluationError("expected 150 unique generated-answer cases")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    reranker = CheckpointedCohereReranker(
        api_key=api_key,
        checkpoint_path=output_dir / "cohere_rerank_checkpoint.jsonl",
        min_interval_seconds=args.min_interval_seconds,
        timeout_seconds=args.timeout_seconds,
    )
    context = {
        "experiment": "cohere-rerank-v4-fast-top16",
        "dataset_sha256": EXPECTED_CASES_SHA256,
        "runner_sha256": sha256_file(Path(__file__).resolve()),
        "model": MODEL,
        "candidate_count": CANDIDATE_COUNT,
    }
    original_group = ChildParentHybridRetriever._group_parent_results
    previous_runtime_reranker = os.environ.get(
        "STUDENT_RAG_COHERE_RERANKER_ENABLED"
    )
    os.environ["STUDENT_RAG_COHERE_RERANKER_ENABLED"] = "false"
    try:
        with patch.object(
            ChildParentHybridRetriever,
            "_group_parent_results",
            patched_group_method(reranker, original_group),
        ):
            generation = generate_answers(
                cases,
                cache_path=output_dir / "answer_cache_full.json",
                resume=args.resume,
                limit=args.limit,
                checkpoint_context=context,
            )
    finally:
        if previous_runtime_reranker is None:
            os.environ.pop("STUDENT_RAG_COHERE_RERANKER_ENABLED", None)
        else:
            os.environ["STUDENT_RAG_COHERE_RERANKER_ENABLED"] = (
                previous_runtime_reranker
            )
    write_json(output_dir / "answer_generation_full.json", generation)
    if args.generate_only:
        return 0

    answers = list(generation.get("cases") or [])
    judged = judge_answers(
        cases,
        answers,
        checkpoint_path=output_dir / "judge_checkpoint_full.json",
        resume=args.resume,
        limit=args.limit,
        checkpoint_context=context,
    )
    write_json(output_dir / "generated_answer_judge_full.json", judged)
    summary = {
        "scope": {
            "runtime_integration": False,
            "evaluation_only_patch": True,
            "model": MODEL,
            "candidate_count": CANDIDATE_COUNT,
            "dataset_sha256": EXPECTED_CASES_SHA256,
        },
        "generation_summary": generation.get("summary"),
        "judge_summary": judged.get("summary"),
        "cohere_requests": len(reranker.by_key),
        "successful_response_search_units": sum(
            int(row.get("billed_search_units") or 0) for row in reranker.by_key.values()
        ),
    }
    write_json(output_dir / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
