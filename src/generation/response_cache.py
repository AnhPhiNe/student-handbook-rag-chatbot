import hashlib
import json
import logging
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

if os.name == "nt":
    import msvcrt
else:
    import fcntl


LOCK_POLL_SECONDS = 0.05
LOCK_TIMEOUT_SECONDS = 5.0
DEFAULT_CACHE_TTL_SECONDS = 86400
DEFAULT_CACHE_MAX_ENTRIES = 1000
DEFAULT_CACHE_NAMESPACE = "v44-answer-anchor-citation-order"


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class ResponseCache:
    """Provide a bounded process-local JSON cache for single-instance deployments."""

    def __init__(
        self,
        path: str | Path,
        enabled: bool = True,
        ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
        max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
    ) -> None:
        self.path = Path(path)
        self.enabled = bool(enabled)
        self.ttl_seconds = max(1, int(ttl_seconds))
        self.max_entries = max(1, int(max_entries))
        self._data: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._load()

    def get(self, key: str) -> dict[str, Any] | None:
        """Return a non-expired local response, if present."""

        if not self.enabled:
            return None
        with self._lock:
            changed = self._prune_expired_entries()
            value = self._data.get(key)
            cached = self._unwrap_entry(value)
            if cached is None and key in self._data:
                self._data.pop(key, None)
                changed = True
            if changed:
                self.save()
        return cached

    def set(self, key: str, value: dict[str, Any]) -> None:
        """Store one response in the process-local cache."""

        if not self.enabled:
            return
        with self._lock:
            self._prune_expired_entries()
            self._data[key] = {
                "created_at": time.time(),
                "value": value,
            }
            self._evict_oldest_entries()
            self.save()

    def save(self) -> None:
        """Persist the in-memory cache atomically when local storage is enabled."""

        if not self.enabled:
            return
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._file_lock():
                fd, tmp_name = tempfile.mkstemp(
                    dir=self.path.parent,
                    prefix=f".{self.path.name}.",
                    suffix=".tmp",
                    text=True,
                )
                try:
                    with os.fdopen(fd, "w", encoding="utf-8") as f:
                        json.dump(
                            self._data, f, ensure_ascii=False, indent=2, default=str
                        )
                        f.write("\n")
                    os.replace(tmp_name, self.path)
                except Exception:
                    try:
                        os.unlink(tmp_name)
                    except OSError:
                        pass
                    raise

    def make_cache_key(
        self,
        query: str,
        retrieval_result: dict[str, Any],
        selected_citations: list[dict[str, Any]] | None,
        cohort: str | None = None,
        context_fingerprint: dict[str, Any] | None = None,
        pipeline_version: str | None = None,
        answer_prompt_version: str | None = None,
    ) -> str:
        """Build a stable key from query, cohort, history, and runtime identity."""

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
        stable_json = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, default=str
        )
        return hashlib.sha256(stable_json.encode("utf-8")).hexdigest()

    def _load(self) -> None:
        """Load valid cache entries from disk and discard malformed state."""

        if not self.enabled or not self.path.exists():
            self._data = {}
            return

        try:
            with self._lock:
                with self._file_lock():
                    with self.path.open("r", encoding="utf-8") as f:
                        loaded = json.load(f)
        except (json.JSONDecodeError, OSError, TimeoutError):
            self._data = {}
            return

        self._data = loaded if isinstance(loaded, dict) else {}
        with self._lock:
            changed = self._prune_expired_entries()
            changed = self._evict_oldest_entries() or changed
            if changed:
                self.save()

    def _prune_expired_entries(self) -> bool:
        """Remove expired or malformed versioned entries from local state."""

        stale_keys = [
            key
            for key, entry in self._data.items()
            if not isinstance(entry, dict)
            or (
                "created_at" in entry
                and "value" in entry
                and self._unwrap_entry(entry) is None
            )
        ]
        for key in stale_keys:
            self._data.pop(key, None)
        return bool(stale_keys)

    def _evict_oldest_entries(self) -> bool:
        """Keep the local fallback bounded by evicting its oldest entries."""

        evicted = False
        while len(self._data) > self.max_entries:
            oldest_key = min(
                self._data,
                key=lambda key: self._entry_created_at(self._data[key]),
            )
            self._data.pop(oldest_key, None)
            evicted = True
        return evicted

    @staticmethod
    def _entry_created_at(entry: Any) -> float:
        """Return an entry timestamp, treating legacy entries as the oldest."""

        if not isinstance(entry, dict):
            return float("-inf")
        try:
            return float(entry.get("created_at"))
        except (TypeError, ValueError):
            return float("-inf")

    def _unwrap_entry(self, entry: Any) -> dict[str, Any] | None:
        """Return the payload only when a cache entry has not expired."""

        if not isinstance(entry, dict):
            return None

        if "created_at" not in entry or "value" not in entry:
            # Backward compatible with cache files written before TTL metadata.
            return entry

        value = entry.get("value")
        if not isinstance(value, dict):
            return None

        try:
            age_seconds = time.time() - float(entry.get("created_at"))
        except (TypeError, ValueError):
            return None

        if age_seconds > self.ttl_seconds:
            return None
        return value

    @contextmanager
    def _file_lock(self) -> Any:
        """Serialize local cache reads and writes across processes."""

        lock_path = self.path.with_suffix(f"{self.path.suffix}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as lock_file:
            _acquire_file_lock(lock_file)
            try:
                yield
            finally:
                _release_file_lock(lock_file)


def _acquire_file_lock(lock_file: Any) -> None:
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    while True:
        try:
            if os.name == "nt":
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError:
            if time.monotonic() >= deadline:
                raise TimeoutError("Timed out waiting for response cache lock")
            time.sleep(LOCK_POLL_SECONDS)


def _release_file_lock(lock_file: Any) -> None:
    if os.name == "nt":
        lock_file.seek(0)
        msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


class RedisResponseCache(ResponseCache):
    """Store shared answer results in Redis for multi-replica deployments."""

    def __init__(
        self,
        redis_url: str,
        path: str | Path,
        enabled: bool = True,
        ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
        max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
    ) -> None:
        # Reuse key/TTL helpers without loading or writing process-local JSON.
        super().__init__(
            path=path,
            enabled=False,
            ttl_seconds=ttl_seconds,
            max_entries=max_entries,
        )
        self.enabled = bool(enabled)
        self.redis_url = redis_url
        import redis

        self.client = redis.from_url(self.redis_url)

    def get(self, key: str) -> dict[str, Any] | None:
        """Return a non-expired shared response, treating Redis errors as misses."""

        if not self.enabled:
            return None
        try:
            cached_json = self.client.get(key)
            if cached_json:
                print(f"[Redis Cache] HIT for key {key[:8]}...")
                entry = json.loads(cached_json)
                return self._unwrap_entry(entry)
        except Exception as e:
            logging.warning("Redis get failed; treating as cache miss: %s", e)

        return None

    def set(self, key: str, value: dict[str, Any]) -> None:
        """Store one response in Redis with the configured TTL."""

        if not self.enabled:
            return

        entry = {
            "created_at": time.time(),
            "value": value,
        }
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
    path: str | Path,
    enabled: bool = True,
    ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
    max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
) -> ResponseCache:
    """Create the configured Redis cache or the bounded local fallback."""

    require_redis = _env_bool("STUDENT_RAG_REQUIRE_REDIS")
    redis_disabled = _env_bool("STUDENT_RAG_DISABLE_REDIS")
    redis_url = os.environ.get("REDIS_URL")

    if require_redis and redis_disabled:
        raise RuntimeError(
            "Redis is required but disabled by STUDENT_RAG_DISABLE_REDIS"
        )
    if require_redis and not redis_url:
        raise RuntimeError("Redis is required but REDIS_URL is not configured")

    if redis_disabled:
        print("[Cache] Redis disabled by STUDENT_RAG_DISABLE_REDIS. Using Local JSON.")
        return ResponseCache(path, enabled, ttl_seconds, max_entries)

    if redis_url:
        try:
            import redis

            r = redis.from_url(redis_url)
            r.ping()
            print("[Cache] Connected to Redis. Using Redis-only caching.")
            return RedisResponseCache(
                redis_url,
                path,
                enabled,
                ttl_seconds,
                max_entries,
            )
        except Exception as e:
            if require_redis:
                raise RuntimeError("Redis is required but unavailable") from e
            print(f"[Cache] Redis connection failed: {e}. Falling back to Local JSON.")

    print("[Cache] Using Local JSON Caching.")
    return ResponseCache(path, enabled, ttl_seconds, max_entries)
