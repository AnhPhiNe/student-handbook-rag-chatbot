import hashlib
import json
from pathlib import Path
from typing import Any


class ResponseCache:
    def __init__(self, path: str | Path, enabled: bool = True) -> None:
        self.path = Path(path)
        self.enabled = bool(enabled)
        self._data: dict[str, Any] = {}
        self._load()

    def get(self, key: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        value = self._data.get(key)
        return value if isinstance(value, dict) else None

    def set(self, key: str, value: dict[str, Any]) -> None:
        if not self.enabled:
            return
        self._data[key] = value
        self.save()

    def save(self) -> None:
        if not self.enabled:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2, default=str)

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
            with self.path.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
        except (json.JSONDecodeError, OSError):
            self._data = {}
            return

        self._data = loaded if isinstance(loaded, dict) else {}
