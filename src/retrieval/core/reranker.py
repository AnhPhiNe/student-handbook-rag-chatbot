"""Rerank the RRF children with Voyage rerank-3; fall back to RRF.

Measured on official_v1 with one shared set of 24 BGE-M3 v35 candidates
(2026-09-30, `scripts/compare_rerankers.py`): the gold parent reached the top 5
for 155/155 questions and ranked first for 0.942, at p50 0.76 s, p90 0.85 s,
max 1.35 s. Qwen3-Reranker-8B on DeepInfra scored 155/155 and 0.923 (2026-09-29,
p50 1.6 s, p90 4.7 s, max 9.3 s) but its endpoint stalled for over four hours on
2026-09-30 at 30-60 s a call; Qwen3-Reranker-4B scored 153/155 and 0.903, Cohere
rerank-v4.0-fast 152/155 and 0.897, and no rerank 148/155 and 0.832.

`provider` selects the request and response shape: `voyage` posts one query with
its documents and reads `data[].relevance_score`, `deepinfra` posts to
`<api_url>/<model>` and reads `scores`. A Voyage key issued by MongoDB Atlas is
served by ai.mongodb.com; a Voyage-native key uses api.voyageai.com.

Reranking fails open: a missing key, a timeout, an HTTP error or a malformed
reply keeps the RRF order, and the reason is logged and put in telemetry.
There is no retry, since a second try at an overloaded service only doubles
the wait.
"""
from __future__ import annotations

import logging
import math
import os
import time
from dataclasses import dataclass
from typing import Any, Callable

import requests

from src.common.env_loader import env_bool

logger = logging.getLogger("student_handbook_rag.retrieval.reranker")


@dataclass(frozen=True)
class RerankerConfig:
    enabled: bool = True
    provider: str = "voyage"
    model: str = "rerank-3"
    api_url: str = "https://ai.mongodb.com/v1/rerank"
    api_key_env_var: str = "VOYAGE_API_KEY"
    instruction: str = "Given a student question, retrieve handbook passages that answer it"
    timeout_seconds: float = 10.0

    @classmethod
    def from_config(cls, value: dict[str, Any] | None) -> "RerankerConfig":
        config = dict(value or {})
        provider = str(config.get("provider") or cls.provider).strip().lower()
        if provider not in _PROVIDERS:
            raise ValueError(
                f"Unknown reranker provider {provider!r}; expected one of {sorted(_PROVIDERS)}"
            )
        return cls(
            enabled=env_bool("STUDENT_RAG_RERANKER_ENABLED", bool(config.get("enabled", True))),
            provider=provider,
            model=str(config.get("model") or cls.model),
            api_url=str(config.get("api_url") or cls.api_url),
            api_key_env_var=str(config.get("api_key_env_var") or cls.api_key_env_var),
            instruction=str(config.get("instruction") or cls.instruction),
            timeout_seconds=max(0.1, float(config.get("timeout_seconds", cls.timeout_seconds))),
        )


def _rerank_text(chunk: dict[str, Any]) -> str:
    """The chunk text, after its "document › article" line when it has one.

    Structure chunks keep that line out of their content (so BM25 and citations
    use the handbook's words) but the reranker needs it to tell apart articles
    whose clauses read alike, such as Điều 12 and Điều 13 of the training rules.
    """
    content = str(chunk.get("content") or "")
    header = str((chunk.get("metadata") or {}).get("context_header") or "").strip()
    return f"{header}\n{content}" if header else content


def _deepinfra_call(config: RerankerConfig, query: str, documents: list[str]) -> tuple[str, dict[str, Any]]:
    return f"{config.api_url}/{config.model}", {
        "queries": [query],
        "documents": documents,
        "instruction": config.instruction,
    }


def _deepinfra_scores(body: Any, count: int) -> tuple[list[float], int, float | None]:
    """DeepInfra returns one score per document, in the order sent, and reports its price."""

    scores = [float(score) for score in body["scores"]]
    status = body.get("inference_status") if isinstance(body.get("inference_status"), dict) else {}
    tokens = int(body.get("input_tokens") or status.get("tokens_input") or 0)
    cost = status.get("cost")
    return scores, tokens, (float(cost) if isinstance(cost, (int, float)) else None)


def _voyage_call(config: RerankerConfig, query: str, documents: list[str]) -> tuple[str, dict[str, Any]]:
    return config.api_url, {
        "query": query,
        "documents": documents,
        "model": config.model,
        # Documents are parent-bound handbook chunks; truncating one is better
        # than losing the whole ranking to a length error.
        "truncation": True,
    }


def _voyage_scores(body: Any, count: int) -> tuple[list[float], int, float | None]:
    """Voyage returns the documents it scored, each carrying its own index."""

    data = body["data"]
    if len(data) != count:
        raise ValueError("voyage returned a different number of documents")
    scores = [0.0] * count
    seen: set[int] = set()
    for item in data:
        index = item["index"]
        if type(index) is not int or not 0 <= index < count or index in seen:
            raise ValueError("voyage returned invalid or duplicate document indices")
        seen.add(index)
        scores[index] = float(item["relevance_score"])
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    return scores, int(usage.get("total_tokens") or 0), None


_PROVIDERS: dict[str, tuple[Callable[..., Any], Callable[..., Any], str]] = {
    "deepinfra": (_deepinfra_call, _deepinfra_scores, "qwen3_reranker"),
    "voyage": (_voyage_call, _voyage_scores, "voyage_reranker"),
}


class Reranker:
    def __init__(self, config: RerankerConfig, *, api_key: str | None = None,
                 post: Callable[..., requests.Response] = requests.post) -> None:
        self.config = config
        if api_key is None:
            api_key = os.environ.get(config.api_key_env_var) or ""
        self.api_key = api_key.strip()
        self._post = post
        if config.enabled and not self.api_key:
            logger.warning("Reranker is enabled but %s is missing; retrieval will use RRF.",
                           config.api_key_env_var)

    @classmethod
    def from_runtime_config(cls, runtime_config: dict[str, Any]) -> "Reranker":
        return cls(RerankerConfig.from_config(runtime_config.get("reranker")))

    def rerank(
        self, query: str, scored_chunks: list[tuple[float, dict[str, Any]]],
    ) -> tuple[list[tuple[float, dict[str, Any]]], dict[str, Any]]:
        telemetry: dict[str, Any] = {
            "ranking_method": "rrf",
            "reranker_enabled": self.config.enabled,
            "reranker_applied": False,
            "reranker_model": self.config.model,
            "reranker_provider": self.config.provider,
            "reranker_candidate_chunks": len(scored_chunks),
            "reranker_latency_ms": 0.0,
            "reranker_fallback_reason": None,
        }

        def fall_back(reason: str) -> tuple[list[tuple[float, dict[str, Any]]], dict[str, Any]]:
            telemetry["reranker_fallback_reason"] = reason
            if reason not in {"disabled", "insufficient_candidates"}:
                logger.warning("Rerank skipped (%s); retrieval keeps the RRF order.", reason)
            return list(scored_chunks), telemetry

        if not self.config.enabled:
            return fall_back("disabled")
        if not self.api_key:
            return fall_back("missing_api_key")
        if len(scored_chunks) < 2:
            return fall_back("insufficient_candidates")

        build_call, parse_scores, ranking_method = _PROVIDERS[self.config.provider]
        documents = [_rerank_text(chunk) for _, chunk in scored_chunks]
        url, payload = build_call(self.config, query, documents)
        started = time.perf_counter()
        try:
            response = self._post(
                url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
                timeout=self.config.timeout_seconds,
            )
        except requests.RequestException as exc:
            telemetry["reranker_latency_ms"] = (time.perf_counter() - started) * 1000
            return fall_back(f"request_error:{type(exc).__name__}")
        telemetry["reranker_latency_ms"] = (time.perf_counter() - started) * 1000
        if response.status_code != 200:
            return fall_back(f"http_{response.status_code}")
        try:
            body = response.json()
            scores, tokens, cost = parse_scores(body, len(scored_chunks))
        except (KeyError, IndexError, TypeError, ValueError):
            return fall_back("invalid_response")
        telemetry["reranker_input_tokens"] = tokens
        telemetry["reranker_cost"] = cost
        if len(scores) != len(scored_chunks) or not all(math.isfinite(score) for score in scores):
            return fall_back("invalid_response")

        # Sorted by score; a tie keeps the RRF order.
        order = sorted(range(len(scores)), key=lambda index: (-scores[index], index))
        telemetry.update({"ranking_method": ranking_method, "reranker_applied": True})
        return [(scores[index], scored_chunks[index][1]) for index in order], telemetry
