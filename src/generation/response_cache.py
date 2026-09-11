"""Answer cache: Redis when configured, otherwise a bounded in-process fallback."""

import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from typing import Any

DEFAULT_CACHE_TTL_SECONDS = 86400
DEFAULT_CACHE_MAX_ENTRIES = 1000
DEFAULT_CACHE_NAMESPACE = "v44-answer-anchor-citation-order"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def make_cache_key(
    query: str,
    retrieval_result: dict[str, Any],
    selected_citations: list[dict[str, Any]] | None,
    cohort: str | None = None,
    context_fingerprint: dict[str, Any] | None = None,
    pipeline_version: str | None = None,
    answer_prompt_version: str | None = None,
) -> str:
    """Build a stable key from query, cohort, evidence, and runtime identity."""

    payload = {
        "query": query,
        "cohort": cohort,
        "cache_namespace": os.getenv(
            "STUDENT_RAG_RESPONSE_CACHE_NAMESPACE", DEFAULT_CACHE_NAMESPACE
        ),
        "pipeline_version": pipeline_version,
        "answer_prompt_version": answer_prompt_version,
        "context_fingerprint": context_fingerprint or {},
        "retrieval_query": retrieval_result.get("retrieval_query"),
        "citations": [
            {
                "chunk_id": citation.get("chunk_id"),
                "title": citation.get("title"),
                "chunk_type": citation.get("chunk_type"),
                "source_pages": citation.get("source_pages"),
            }
            for citation in (selected_citations or [])
        ],
        "structured_result": retrieval_result.get("structured_result"),
        "tool_result": retrieval_result.get("tool_result"),
    }
    stable_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(stable_json.encode("utf-8")).hexdigest()


class ResponseCache:
    """Bounded in-process cache used when Redis is not configured or unreachable."""

    make_cache_key = staticmethod(make_cache_key)

    def __init__(
        self,
        enabled: bool = True,
        ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
        max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
    ) -> None:
        self.enabled = bool(enabled)
        self.ttl_seconds = max(1, int(ttl_seconds))
        self.max_entries = max(1, int(max_entries))
        self._entries: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            created_at, value = entry
            if time.time() - created_at > self.ttl_seconds:
                del self._entries[key]
                return None
            return value

    def set(self, key: str, value: dict[str, Any]) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._entries[key] = (time.time(), value)
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)


class RedisResponseCache:
    """Answer cache shared across restarts and replicas; Redis errors are misses."""

    make_cache_key = staticmethod(make_cache_key)

    def __init__(
        self,
        redis_url: str,
        enabled: bool = True,
        ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        import redis

        self.enabled = bool(enabled)
        self.ttl_seconds = max(1, int(ttl_seconds))
        self.client = redis.from_url(redis_url)

    def get(self, key: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        try:
            cached_json = self.client.get(key)
            if cached_json:
                print(f"[Redis Cache] HIT for key {key[:8]}...")
                value = json.loads(cached_json).get("value")
                return value if isinstance(value, dict) else None
        except Exception as e:
            logging.warning("Redis get failed; treating as cache miss: %s", e)
        return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        if not self.enabled:
            return
        entry = {"created_at": time.time(), "value": value}
        try:
            self.client.set(
                key,
                json.dumps(entry, ensure_ascii=False, default=str),
                ex=self.ttl_seconds,
            )
            print(f"[Redis Cache] Wrote key {key[:8]}...")
        except Exception as e:
            logging.warning("Redis set failed; response was not cached: %s", e)


def get_response_cache(
    enabled: bool = True,
    ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
    max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
) -> ResponseCache | RedisResponseCache:
    """Create the configured Redis cache or the bounded in-process fallback."""

    require_redis = _env_bool("STUDENT_RAG_REQUIRE_REDIS")
    redis_disabled = _env_bool("STUDENT_RAG_DISABLE_REDIS")
    redis_url = os.environ.get("REDIS_URL")

    if require_redis and redis_disabled:
        raise RuntimeError("Redis is required but disabled by STUDENT_RAG_DISABLE_REDIS")
    if require_redis and not redis_url:
        raise RuntimeError("Redis is required but REDIS_URL is not configured")

    if redis_disabled:
        print("[Cache] Redis disabled by STUDENT_RAG_DISABLE_REDIS. Using in-memory cache.")
        return ResponseCache(enabled, ttl_seconds, max_entries)

    if redis_url:
        try:
            import redis

            redis.from_url(redis_url).ping()
            print("[Cache] Connected to Redis. Using Redis-only caching.")
            return RedisResponseCache(redis_url, enabled, ttl_seconds)
        except Exception as e:
            if require_redis:
                raise RuntimeError("Redis is required but unavailable") from e
            print(f"[Cache] Redis connection failed: {e}. Falling back to in-memory cache.")

    print("[Cache] Using in-memory cache.")
    return ResponseCache(enabled, ttl_seconds, max_entries)
