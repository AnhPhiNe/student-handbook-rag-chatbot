from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any, Callable


_PROBE_CACHE_LOCK = Lock()
_PROBE_CACHE: dict[tuple[str, str, str], tuple[float, dict[str, Any]]] = {}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _cached_probe(
    cache_key: tuple[str, str, str],
    probe: Callable[[], None],
) -> dict[str, Any]:
    ttl_seconds = max(0, _env_int("STUDENT_RAG_READINESS_CACHE_SECONDS", 30))
    now = time.monotonic()
    with _PROBE_CACHE_LOCK:
        cached = _PROBE_CACHE.get(cache_key)
        if cached and now - cached[0] <= ttl_seconds:
            return dict(cached[1])

    started = time.perf_counter()
    try:
        probe()
        result = {
            "status": "ready",
            "error_type": None,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
    except Exception as exc:
        result = {
            "status": "degraded",
            "error_type": type(exc).__name__,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    with _PROBE_CACHE_LOCK:
        _PROBE_CACHE[cache_key] = (time.monotonic(), dict(result))
    return result


def _not_configured() -> dict[str, Any]:
    return {"status": "not_configured", "error_type": None, "latency_ms": None}


def probe_qdrant() -> dict[str, Any]:
    url = str(os.environ.get("QDRANT_URL") or "").strip()
    collection = str(
        os.environ.get("STUDENT_RAG_HYBRID_COLLECTION")
        or os.environ.get("QDRANT_COLLECTION_NAME")
        or ""
    ).strip()
    if not url or not collection:
        return _not_configured()

    timeout_seconds = max(
        0.1,
        _env_int("STUDENT_RAG_READINESS_PROBE_TIMEOUT_MS", 1500) / 1000,
    )

    def _probe() -> None:
        from qdrant_client import QdrantClient

        client = QdrantClient(
            url=url,
            api_key=os.environ.get("QDRANT_API_KEY"),
            timeout=timeout_seconds,
        )
        try:
            client.get_collection(collection)
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

    return _cached_probe(("qdrant", url, collection), _probe)


def probe_mongodb() -> dict[str, Any]:
    uri = str(os.environ.get("MONGODB_URL") or "").strip()
    collection = str(os.environ.get("MONGODB_PARENT_COLLECTION") or "").strip()
    if not uri or not collection:
        return _not_configured()

    timeout_ms = max(
        100,
        _env_int("STUDENT_RAG_READINESS_PROBE_TIMEOUT_MS", 1500),
    )
    database = str(os.environ.get("MONGODB_DB_NAME") or "chatbotHCMUE").strip()

    def _probe() -> None:
        from pymongo import MongoClient

        client = MongoClient(
            uri,
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
            socketTimeoutMS=timeout_ms,
        )
        try:
            client[database][collection].find_one({}, {"_id": 1})
        finally:
            client.close()

    return _cached_probe(("mongodb", uri, f"{database}/{collection}"), _probe)


def get_dependency_runtime_statuses() -> dict[str, dict[str, Any]]:
    """Probe both stores concurrently; each probe is bounded and cached."""

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="readiness") as pool:
        qdrant_future = pool.submit(probe_qdrant)
        mongodb_future = pool.submit(probe_mongodb)
        return {
            "qdrant": qdrant_future.result(),
            "mongodb": mongodb_future.result(),
        }


def reset_dependency_probe_cache() -> None:
    """Clear cached probe snapshots for deterministic tests."""

    with _PROBE_CACHE_LOCK:
        _PROBE_CACHE.clear()
