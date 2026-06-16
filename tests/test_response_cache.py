from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.generation.response_cache import ResponseCache


class ResponseCacheTest(unittest.TestCase):
    def test_set_writes_valid_json_and_get_reads_dict_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.json"
            cache = ResponseCache(cache_path)

            cache.set("key", {"answer": "ok"})

            self.assertEqual(cache.get("key"), {"answer": "ok"})
            stored = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual(stored["key"]["value"], {"answer": "ok"})
            self.assertIn("created_at", stored["key"])

    def test_local_cache_expires_stale_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.json"
            cache = ResponseCache(cache_path, ttl_seconds=10)

            with patch("src.generation.response_cache.time.time", return_value=1000.0):
                cache.set("key", {"answer": "ok"})

            with patch("src.generation.response_cache.time.time", return_value=1011.0):
                self.assertIsNone(cache.get("key"))

            self.assertEqual(json.loads(cache_path.read_text(encoding="utf-8")), {})

    def test_legacy_local_cache_entries_still_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.json"
            cache_path.write_text(
                json.dumps({"legacy": {"answer": "old"}}),
                encoding="utf-8",
            )

            cache = ResponseCache(cache_path)

            self.assertEqual(cache.get("legacy"), {"answer": "old"})

    def test_corrupt_cache_file_starts_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.json"
            cache_path.write_text("{bad json", encoding="utf-8")

            cache = ResponseCache(cache_path)

            self.assertIsNone(cache.get("missing"))


if __name__ == "__main__":
    unittest.main()
