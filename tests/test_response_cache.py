from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.generation.response_cache import ResponseCache


class ResponseCacheTest(unittest.TestCase):
    def test_set_writes_valid_json_and_get_reads_dict_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.json"
            cache = ResponseCache(cache_path)

            cache.set("key", {"answer": "ok"})

            self.assertEqual(cache.get("key"), {"answer": "ok"})
            self.assertEqual(json.loads(cache_path.read_text(encoding="utf-8")), {"key": {"answer": "ok"}})

    def test_corrupt_cache_file_starts_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.json"
            cache_path.write_text("{bad json", encoding="utf-8")

            cache = ResponseCache(cache_path)

            self.assertIsNone(cache.get("missing"))


if __name__ == "__main__":
    unittest.main()
