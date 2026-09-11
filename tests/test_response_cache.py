from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.generation.response_cache import (
    RedisResponseCache,
    ResponseCache,
    get_response_cache,
    make_cache_key,
)


class ResponseCacheTest(unittest.TestCase):
    def test_required_redis_without_url_raises(self) -> None:
        with patch.dict(os.environ, {"STUDENT_RAG_REQUIRE_REDIS": "true"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "REDIS_URL is not configured"):
                get_response_cache()

    def test_required_redis_cannot_be_disabled(self) -> None:
        with patch.dict(
            os.environ,
            {"STUDENT_RAG_REQUIRE_REDIS": "true", "STUDENT_RAG_DISABLE_REDIS": "true"},
            clear=True,
        ):
            with self.assertRaisesRegex(RuntimeError, "Redis is required but disabled"):
                get_response_cache()

    def test_optional_redis_without_url_uses_in_memory_cache(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            cache = get_response_cache()

        self.assertIsInstance(cache, ResponseCache)

    def test_required_redis_connection_failure_raises(self) -> None:
        client = Mock()
        client.ping.side_effect = ConnectionError("unavailable")
        redis_module = SimpleNamespace(from_url=Mock(return_value=client))
        with (
            patch.dict(sys.modules, {"redis": redis_module}),
            patch.dict(
                os.environ,
                {"STUDENT_RAG_REQUIRE_REDIS": "true", "REDIS_URL": "redis://example"},
                clear=True,
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "Redis is required but unavailable"):
                get_response_cache()

    def test_redis_cache_round_trips_the_wrapped_value(self) -> None:
        stored: dict[str, str] = {}
        client = Mock()
        client.set.side_effect = lambda key, value, ex: stored.__setitem__(key, value)
        client.get.side_effect = stored.get
        redis_module = SimpleNamespace(from_url=Mock(return_value=client))
        with patch.dict(sys.modules, {"redis": redis_module}):
            cache = RedisResponseCache("redis://example", ttl_seconds=60)
            cache.set("key", {"answer": "ok"})

        self.assertEqual(cache.get("key"), {"answer": "ok"})
        self.assertEqual(client.set.call_args.kwargs["ex"], 60)

    def test_in_memory_cache_returns_stored_values(self) -> None:
        cache = ResponseCache()
        cache.set("key", {"answer": "ok"})
        self.assertEqual(cache.get("key"), {"answer": "ok"})

    def test_in_memory_cache_expires_stale_entries(self) -> None:
        cache = ResponseCache(ttl_seconds=10)
        with patch("src.generation.response_cache.time.time", return_value=1000.0):
            cache.set("key", {"answer": "ok"})
        with patch("src.generation.response_cache.time.time", return_value=1011.0):
            self.assertIsNone(cache.get("key"))

    def test_in_memory_cache_evicts_oldest_entry_at_max_entries(self) -> None:
        cache = ResponseCache(max_entries=2)
        cache.set("first", {"answer": "one"})
        cache.set("second", {"answer": "two"})
        cache.set("third", {"answer": "three"})

        self.assertIsNone(cache.get("first"))
        self.assertEqual(cache.get("second"), {"answer": "two"})
        self.assertEqual(cache.get("third"), {"answer": "three"})

    def test_disabled_cache_stores_nothing(self) -> None:
        cache = ResponseCache(enabled=False)
        cache.set("key", {"answer": "ok"})
        self.assertIsNone(cache.get("key"))

    def test_cache_key_changes_with_context_fingerprint(self) -> None:
        retrieval_result = {"retrieval_query": "qua mon"}
        citations = [{"chunk_id": "chunk-1", "title": "Title"}]
        key_v1 = make_cache_key(
            query="may diem qua mon",
            retrieval_result=retrieval_result,
            selected_citations=citations,
            cohort="K50-K51",
            context_fingerprint={"strategy": "score_weighted"},
        )
        key_v2 = make_cache_key(
            query="may diem qua mon",
            retrieval_result=retrieval_result,
            selected_citations=citations,
            cohort="K50-K51",
            context_fingerprint={"strategy": "equal_split"},
        )
        self.assertNotEqual(key_v1, key_v2)

    def test_cache_key_changes_with_namespace(self) -> None:
        kwargs = {
            "query": "dieu kien hoc bong",
            "retrieval_result": {"retrieval_query": "hoc bong"},
            "selected_citations": [],
            "cohort": "K50",
        }
        with patch.dict("os.environ", {"STUDENT_RAG_RESPONSE_CACHE_NAMESPACE": "a"}):
            key_a = make_cache_key(**kwargs)
        with patch.dict("os.environ", {"STUDENT_RAG_RESPONSE_CACHE_NAMESPACE": "b"}):
            key_b = make_cache_key(**kwargs)
        self.assertNotEqual(key_a, key_b)

    def test_cache_key_changes_with_answer_prompt_version(self) -> None:
        kwargs = {
            "query": "điều kiện học bổng",
            "retrieval_result": {"retrieval_query": "học bổng"},
            "selected_citations": [{"chunk_id": "p1"}],
            "cohort": "K51",
            "pipeline_version": "same-pipeline",
        }
        self.assertNotEqual(
            make_cache_key(**kwargs, answer_prompt_version="answer-v1"),
            make_cache_key(**kwargs, answer_prompt_version="answer-v2"),
        )

    def test_both_caches_expose_the_same_key_function(self) -> None:
        self.assertIs(ResponseCache.make_cache_key, RedisResponseCache.make_cache_key)


if __name__ == "__main__":
    unittest.main()
