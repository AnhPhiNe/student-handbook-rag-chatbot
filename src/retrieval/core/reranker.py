"""Rerank the RRF children with Qwen3-Reranker-8B on DeepInfra; fall back to RRF.

Measured on official_v1 with the same 24 BGE-M3 v35 candidates (2026-09-29):
the gold parent reached the top 5 for 155/155 questions and ranked first for
0.923, against Cohere rerank-v4.0-fast 152/155 and 0.897, and no rerank
148/155 and 0.832. A call took p50 1.6 s, p90 4.7 s, max 9.3 s.

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
    model: str = "Qwen/Qwen3-Reranker-8B"
    api_url: str = "https://api.deepinfra.com/v1/inference"
    api_key_env_var: str = "DEEPINFRA_API_KEY"
    instruction: str = "Given a student question, retrieve handbook passages that answer it"
    timeout_seconds: float = 10.0

    @classmethod
    def from_config(cls, value: dict[str, Any] | None) -> "RerankerConfig":
        config = dict(value or {})
        return cls(
            enabled=env_bool("STUDENT_RAG_RERANKER_ENABLED", bool(config.get("enabled", True))),
            model=str(config.get("model") or cls.model),
            api_url=str(config.get("api_url") or cls.api_url),
            api_key_env_var=str(config.get("api_key_env_var") or cls.api_key_env_var),
            instruction=str(config.get("instruction") or cls.instruction),
            timeout_seconds=max(0.1, float(config.get("timeout_seconds", cls.timeout_seconds))),
        )


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

        started = time.perf_counter()
        try:
            response = self._post(
                f"{self.config.api_url}/{self.config.model}",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"queries": [query],
                      "documents": [str(chunk.get("content") or "") for _, chunk in scored_chunks],
                      "instruction": self.config.instruction},
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
            scores = [float(score) for score in body["scores"]]
        except (KeyError, TypeError, ValueError):
            return fall_back("invalid_response")
        # DeepInfra reports the tokens it read and the price it charged.
        status = body.get("inference_status") if isinstance(body.get("inference_status"), dict) else {}
        telemetry["reranker_input_tokens"] = int(body.get("input_tokens") or status.get("tokens_input") or 0)
        cost = status.get("cost")
        telemetry["reranker_cost"] = float(cost) if isinstance(cost, (int, float)) else None
        if len(scores) != len(scored_chunks) or not all(math.isfinite(score) for score in scores):
            return fall_back("invalid_response")

        # Sorted by score; a tie keeps the RRF order.
        order = sorted(range(len(scores)), key=lambda index: (-scores[index], index))
        telemetry.update({"ranking_method": "qwen3_reranker", "reranker_applied": True})
        return [(scores[index], scored_chunks[index][1]) for index in order], telemetry
