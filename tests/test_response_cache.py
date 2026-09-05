from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.generation.response_cache import (
    RedisResponseCache,
    ResponseCache,
    get_response_cache,
)


class ResponseCacheTest(unittest.TestCase):
    def test_required_redis_without_url_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {"STUDENT_RAG_REQUIRE_REDIS": "true"},
                clear=True,
            ):
                with self.assertRaisesRegex(RuntimeError, "REDIS_URL is not configured"):
                    get_response_cache(Path(tmpdir) / "cache.json")

    def test_required_redis_cannot_be_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(
                os.environ,
                {
                    "STUDENT_RAG_REQUIRE_REDIS": "true",
                    "STUDENT_RAG_DISABLE_REDIS": "true",
                },
                clear=True,
            ):
                with self.assertRaisesRegex(RuntimeError, "Redis is required but disabled"):
                    get_response_cache(Path(tmpdir) / "cache.json")

    def test_optional_redis_without_url_uses_local_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {}, clear=True):
                cache = get_response_cache(Path(tmpdir) / "cache.json")

            self.assertIsInstance(cache, ResponseCache)
            self.assertNotIsInstance(cache, RedisResponseCache)

    def test_required_redis_connection_failure_raises(self) -> None:
        client = Mock()
        client.ping.side_effect = ConnectionError("unavailable")
        redis_module = SimpleNamespace(from_url=Mock(return_value=client))
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch.dict(sys.modules, {"redis": redis_module}),
                patch.dict(
                    os.environ,
                    {
                        "STUDENT_RAG_REQUIRE_REDIS": "true",
                        "REDIS_URL": "redis://example",
                    },
                    clear=True,
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "Redis is required but unavailable"):
                    get_response_cache(Path(tmpdir) / "cache.json")

    def test_redis_cache_does_not_write_local_json(self) -> None:
        client = Mock()
        redis_module = SimpleNamespace(from_url=Mock(return_value=client))
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.json"
            with patch.dict(sys.modules, {"redis": redis_module}):
                cache = RedisResponseCache("redis://example", cache_path)
                cache.set("key", {"answer": "ok"})

            self.assertFalse(cache_path.exists())
            client.set.assert_called_once()

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

    def test_local_cache_prunes_unrelated_expired_entries_before_writing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.json"
            cache = ResponseCache(cache_path, ttl_seconds=10)

            with patch("src.generation.response_cache.time.time", return_value=1000.0):
                cache.set("stale", {"answer": "old"})

            with patch("src.generation.response_cache.time.time", return_value=1011.0):
                cache.set("fresh", {"answer": "new"})

            stored = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual(set(stored), {"fresh"})

    def test_local_cache_evicts_oldest_entry_at_max_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "cache.json"
            cache = ResponseCache(cache_path, max_entries=2)

            with patch("src.generation.response_cache.time.time", return_value=1000.0):
                cache.set("first", {"answer": "one"})
            with patch("src.generation.response_cache.time.time", return_value=1001.0):
                cache.set("second", {"answer": "two"})
            with patch("src.generation.response_cache.time.time", return_value=1002.0):
                cache.set("third", {"answer": "three"})

            with patch("src.generation.response_cache.time.time", return_value=1003.0):
                self.assertIsNone(cache.get("first"))
                self.assertEqual(cache.get("second"), {"answer": "two"})
                self.assertEqual(cache.get("third"), {"answer": "three"})

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

    def test_cache_key_changes_with_context_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ResponseCache(Path(tmpdir) / "cache.json")
            retrieval_result = {
                "retrieval_query": "qua mon",
                "structured_result": None,
                "tool_result": None,
            }
            citations = [{"chunk_id": "chunk-1", "title": "Title"}]

            key_v1 = cache.make_cache_key(
                query="may diem qua mon",
                retrieval_result=retrieval_result,
                selected_citations=citations,
                cohort="K50-K51",
                context_fingerprint={
                    "strategy": "score_weighted",
                    "cache_version": "context_alloc_v1",
                },
            )
            key_v2 = cache.make_cache_key(
                query="may diem qua mon",
                retrieval_result=retrieval_result,
                selected_citations=citations,
                cohort="K50-K51",
                context_fingerprint={
                    "strategy": "equal_split",
                    "cache_version": "context_alloc_v2",
                },
            )

            self.assertNotEqual(key_v1, key_v2)

    def test_cache_key_changes_with_namespace(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ResponseCache(Path(tmpdir) / "cache.json")
            retrieval_result = {
                "retrieval_query": "hoc bong",
                "structured_result": None,
                "tool_result": None,
            }

            with patch.dict(
                "os.environ",
                {"STUDENT_RAG_RESPONSE_CACHE_NAMESPACE": "production-eval-a"},
            ):
                key_a = cache.make_cache_key(
                    query="dieu kien hoc bong",
                    retrieval_result=retrieval_result,
                    selected_citations=[],
                    cohort="K50",
                )
            with patch.dict(
                "os.environ",
                {"STUDENT_RAG_RESPONSE_CACHE_NAMESPACE": "production-eval-b"},
            ):
                key_b = cache.make_cache_key(
                    query="dieu kien hoc bong",
                    retrieval_result=retrieval_result,
                    selected_citations=[],
                    cohort="K50",
                )

            self.assertNotEqual(key_a, key_b)

    def test_cache_key_changes_with_answer_prompt_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = ResponseCache(Path(tmpdir) / "cache.json")
            kwargs = {
                "query": "điều kiện học bổng",
                "retrieval_result": {"retrieval_query": "học bổng"},
                "selected_citations": [{"chunk_id": "p1"}],
                "cohort": "K51",
                "pipeline_version": "same-pipeline",
            }

            key_v1 = cache.make_cache_key(
                **kwargs,
                answer_prompt_version="answer-v1",
            )
            key_v2 = cache.make_cache_key(
                **kwargs,
                answer_prompt_version="answer-v2",
            )

            self.assertNotEqual(key_v1, key_v2)


if __name__ == "__main__":
    unittest.main()
