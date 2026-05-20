import hashlib
import json
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


class ResponseCache:
    def __init__(self, path: str | Path, enabled: bool = True) -> None:
        self.path = Path(path)
        self.enabled = bool(enabled)
        self._data: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._load()

    def get(self, key: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        with self._lock:
            value = self._data.get(key)
        return value if isinstance(value, dict) else None

    def set(self, key: str, value: dict[str, Any]) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._data[key] = value
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
                        json.dump(self._data, f, ensure_ascii=False, indent=2, default=str)
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
    ) -> str:
        payload = {
            "query": query,
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
