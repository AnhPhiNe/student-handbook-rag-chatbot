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


class ResponseCache:
    def __init__(
        self,
        path: str | Path,
        enabled: bool = True,
        ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        self.path = Path(path)
        self.enabled = bool(enabled)
        self.ttl_seconds = max(1, int(ttl_seconds))
        self._data: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._load()

    def get(self, key: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        with self._lock:
            value = self._data.get(key)
            cached = self._unwrap_entry(value)
            if cached is None and key in self._data:
                self._data.pop(key, None)
                self.save()
        return cached

    def set(self, key: str, value: dict[str, Any]) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._data[key] = {
                "created_at": time.time(),
                "value": value,
            }
            self.save()

    def save(self) -> None:
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
    ) -> str:
        payload = {
            "query": query,
            "cohort": cohort,
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

    def _unwrap_entry(self, entry: Any) -> dict[str, Any] | None:
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
    def __init__(
        self,
        redis_url: str,
        path: str | Path,
        enabled: bool = True,
        ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        super().__init__(path=path, enabled=enabled, ttl_seconds=ttl_seconds)
        self.redis_url = redis_url
        import redis

        self.client = redis.from_url(self.redis_url)

    def get(self, key: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        try:
            cached_json = self.client.get(key)
            if cached_json:
                print(f"[Redis Cache] HIT for key {key[:8]}...")
                entry = json.loads(cached_json)
                return self._unwrap_entry(entry)
        except Exception as e:
            logging.warning(f"Redis get failed: {e}. Falling back to local cache.")

        # If not in Redis (or Redis failed), fallback to local
        return super().get(key)

    def set(self, key: str, value: dict[str, Any]) -> None:
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
            logging.warning(f"Redis set failed: {e}. Falling back to local cache.")

        # Write to local cache as well (Two-Tier caching)
        super().set(key, value)


def get_response_cache(
    path: str | Path,
    enabled: bool = True,
    ttl_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
) -> ResponseCache:
    if os.environ.get("STUDENT_RAG_DISABLE_REDIS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        print("[Cache] Redis disabled by STUDENT_RAG_DISABLE_REDIS. Using Local JSON.")
        return ResponseCache(path, enabled, ttl_seconds)

    redis_url = os.environ.get("REDIS_URL")
    if redis_url:
        try:
            import redis

            r = redis.from_url(redis_url)
            r.ping()
            print("[Cache] Connected to Redis. Enabling Two-Tier Caching.")
            return RedisResponseCache(redis_url, path, enabled, ttl_seconds)
        except Exception as e:
            print(f"[Cache] Redis connection failed: {e}. Falling back to Local JSON.")

    print("[Cache] Using Local JSON Caching.")
    return ResponseCache(path, enabled, ttl_seconds)
