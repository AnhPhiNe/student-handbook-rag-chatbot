from __future__ import annotations

import hashlib
import logging
import math
import os
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable

import requests

from src.common.env_loader import env_bool

logger = logging.getLogger("student_handbook_rag.retrieval.cohere_reranker")
COHERE_RERANK_URL = "https://api.cohere.com/v2/rerank"


def _cohere_api_keys() -> list[str]:
    raw = os.environ.get("COHERE_API_KEYS") or os.environ.get("COHERE_API_KEY") or ""
    keys: list[str] = []
    for value in raw.split(","):
        key = value.strip()
        if key and key not in keys:
            keys.append(key)
    return keys


@dataclass(frozen=True)
class CohereRerankerConfig:
    """Runtime contract for the optional Cohere child reranker."""

    enabled: bool = True
    model: str = "rerank-v4.0-fast"
    candidate_count: int = 16
    max_tokens_per_doc: int = 4096
    timeout_seconds: float = 5.0
    rpm_limit_per_key: int = 10
    cooldown_seconds: float = 65.0

    @classmethod
    def from_config(cls, value: dict[str, Any] | None) -> "CohereRerankerConfig":
        config = dict(value or {})
        key_pool = dict(config.get("key_pool") or {})
        enabled = env_bool(
            "STUDENT_RAG_COHERE_RERANKER_ENABLED",
            bool(config.get("enabled", True)),
        )
        return cls(
            enabled=enabled,
            model=str(config.get("model") or cls.model).strip(),
            candidate_count=max(1, int(config.get("candidate_count", 16))),
            max_tokens_per_doc=max(1, int(config.get("max_tokens_per_doc", 4096))),
            timeout_seconds=max(0.1, float(config.get("timeout_seconds", 5.0))),
            rpm_limit_per_key=max(
                1,
                int(
                    os.environ.get("STUDENT_RAG_COHERE_RPM_LIMIT_PER_KEY")
                    or key_pool.get("rpm_limit_per_key", 10)
                ),
            ),
            cooldown_seconds=max(
                1.0, float(key_pool.get("cooldown_seconds", 65.0))
            ),
        )


class NoAvailableCohereKey(RuntimeError):
    """Raised when every configured Cohere key is temporarily unavailable."""


class CohereKeyPool:
    """Process-local, non-blocking key rotation for Cohere Rerank."""

    def __init__(
        self,
        keys: list[str],
        *,
        rpm_limit_per_key: int,
        cooldown_seconds: float,
    ) -> None:
        self.keys = list(dict.fromkeys(key for key in keys if key))
        self.rpm_limit_per_key = max(1, int(rpm_limit_per_key))
        self.cooldown_seconds = max(1.0, float(cooldown_seconds))
        self._lock = threading.Lock()
        self._cursor = 0
        self._state = {
            self.fingerprint(key): {
                "request_timestamps": [],
                "cooldown_until": 0.0,
            }
            for key in self.keys
        }

    @property
    def key_count(self) -> int:
        return len(self.keys)

    @staticmethod
    def fingerprint(key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]

    def acquire_key(self, *, excluded: set[str] | None = None) -> tuple[str, str, int]:
        excluded_ids = excluded or set()
        with self._lock:
            now = time.time()
            for offset in range(len(self.keys)):
                index = (self._cursor + offset) % len(self.keys)
                key = self.keys[index]
                key_id = self.fingerprint(key)
                if key_id in excluded_ids:
                    continue
                state = self._state[key_id]
                timestamps = [
                    float(timestamp)
                    for timestamp in state["request_timestamps"]
                    if now - float(timestamp) < 60.0
                ]
                state["request_timestamps"] = timestamps
                if float(state["cooldown_until"]) > now:
                    continue
                if len(timestamps) >= self.rpm_limit_per_key:
                    continue
                timestamps.append(now)
                self._cursor = (index + 1) % len(self.keys)
                return key, key_id, index
        raise NoAvailableCohereKey("all_cohere_keys_temporarily_limited")

    def record_rate_limit(self, key_id: str, *, retry_after_seconds: float | None) -> None:
        with self._lock:
            state = self._state.get(key_id)
            if state is None:
                return
            cooldown = max(
                self.cooldown_seconds,
                float(retry_after_seconds or 0.0),
            )
            state["cooldown_until"] = time.time() + cooldown


def _retry_after_seconds(response: requests.Response) -> float | None:
    value = response.headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(0.0, retry_at.timestamp() - time.time())


class CohereReranker:
    """Rerank a bounded RRF child prefix and fail open to the full RRF list."""

    def __init__(
        self,
        config: CohereRerankerConfig,
        *,
        keys: list[str] | None = None,
        post: Callable[..., requests.Response] = requests.post,
    ) -> None:
        self.config = config
        self._post = post
        resolved_keys = _cohere_api_keys() if keys is None else keys
        self.key_pool = CohereKeyPool(
            resolved_keys,
            rpm_limit_per_key=config.rpm_limit_per_key,
            cooldown_seconds=config.cooldown_seconds,
        )
        if config.enabled and not resolved_keys:
            logger.warning(
                "Cohere reranker is enabled but COHERE_API_KEYS/COHERE_API_KEY is missing; "
                "retrieval will use RRF."
            )

    @classmethod
    def from_runtime_config(cls, runtime_config: dict[str, Any]) -> "CohereReranker":
        return cls(
            CohereRerankerConfig.from_config(runtime_config.get("cohere_reranker"))
        )

    def rerank(
        self,
        query: str,
        scored_chunks: list[tuple[float, dict[str, Any]]],
    ) -> tuple[list[tuple[float, dict[str, Any]]], dict[str, Any]]:
        fallback = list(scored_chunks)
        telemetry: dict[str, Any] = {
            "ranking_method": "rrf",
            "cohere_reranker_enabled": self.config.enabled,
            "cohere_reranker_applied": False,
            "cohere_reranker_model": self.config.model,
            "cohere_candidate_chunks": 0,
            "cohere_attempts": 0,
            "cohere_latency_ms": 0.0,
            "cohere_fallback_reason": None,
        }
        if not self.config.enabled:
            telemetry["cohere_fallback_reason"] = "disabled"
            return fallback, telemetry
        if self.key_pool.key_count == 0:
            telemetry["cohere_fallback_reason"] = "missing_api_keys"
            return fallback, telemetry

        candidates = fallback[: self.config.candidate_count]
        telemetry["cohere_candidate_chunks"] = len(candidates)
        if len(candidates) < 2:
            telemetry["cohere_fallback_reason"] = "insufficient_candidates"
            return fallback, telemetry

        documents = [str(chunk.get("content") or "") for _, chunk in candidates]
        payload = {
            "model": self.config.model,
            "query": query,
            "documents": documents,
            "top_n": len(documents),
            "max_tokens_per_doc": self.config.max_tokens_per_doc,
        }
        excluded: set[str] = set()
        total_latency_ms = 0.0

        while len(excluded) < self.key_pool.key_count:
            try:
                key, key_id, key_index = self.key_pool.acquire_key(excluded=excluded)
            except NoAvailableCohereKey:
                telemetry["cohere_fallback_reason"] = "all_keys_temporarily_limited"
                telemetry["cohere_latency_ms"] = total_latency_ms
                return fallback, telemetry

            excluded.add(key_id)
            telemetry["cohere_attempts"] = int(telemetry["cohere_attempts"]) + 1
            started = time.perf_counter()
            try:
                response = self._post(
                    COHERE_RERANK_URL,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                        "X-Client-Name": "hcmue-student-handbook-rag",
                    },
                    json=payload,
                    timeout=self.config.timeout_seconds,
                )
            except requests.RequestException as exc:
                total_latency_ms += (time.perf_counter() - started) * 1000
                telemetry["cohere_latency_ms"] = total_latency_ms
                telemetry["cohere_fallback_reason"] = "request_error"
                logger.warning("Cohere rerank failed open after request error: %s", exc)
                return fallback, telemetry

            total_latency_ms += (time.perf_counter() - started) * 1000
            if response.status_code == 429:
                self.key_pool.record_rate_limit(
                    key_id,
                    retry_after_seconds=_retry_after_seconds(response),
                )
                logger.info(
                    "Cohere key slot %s reached a rate limit; rotating without waiting.",
                    key_index,
                )
                continue
            if response.status_code != 200:
                telemetry["cohere_latency_ms"] = total_latency_ms
                telemetry["cohere_fallback_reason"] = (
                    f"http_{int(response.status_code)}"
                )
                logger.warning(
                    "Cohere rerank failed open after HTTP %s on key slot %s.",
                    response.status_code,
                    key_index,
                )
                return fallback, telemetry

            try:
                body = response.json()
                if not isinstance(body, Mapping):
                    raise ValueError("Cohere response body is not an object")
                results = list(body.get("results") or [])
                indices = [int(item["index"]) for item in results]
                scores = [float(item["relevance_score"]) for item in results]
                if len(indices) != len(candidates) or set(indices) != set(
                    range(len(candidates))
                ):
                    raise ValueError("Cohere response is not a complete permutation")
                if any(
                    not math.isfinite(score) or not 0.0 <= score <= 1.0
                    for score in scores
                ):
                    raise ValueError("Cohere response contains an invalid score")
            except (KeyError, TypeError, ValueError) as exc:
                telemetry["cohere_latency_ms"] = total_latency_ms
                telemetry["cohere_fallback_reason"] = "invalid_response"
                logger.warning("Cohere rerank returned an invalid response: %s", exc)
                return fallback, telemetry

            telemetry.update(
                {
                    "ranking_method": "cohere_rerank_v4_fast",
                    "cohere_reranker_applied": True,
                    "cohere_latency_ms": total_latency_ms,
                    "cohere_key_index": key_index,
                }
            )
            return (
                [
                    (score, candidates[index][1])
                    for index, score in zip(indices, scores)
                ],
                telemetry,
            )

        telemetry["cohere_latency_ms"] = total_latency_ms
        telemetry["cohere_fallback_reason"] = "all_keys_rate_limited"
        return fallback, telemetry
