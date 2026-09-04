from __future__ import annotations

import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

from src.generation.gemini_client import GeminiClient, GeminiKeyPool


class _SlowStreamModels:
    def generate_content_stream(self, **kwargs):
        time.sleep(0.05)
        yield type("Chunk", (), {"text": "late"})()


class _StallingStreamModels:
    def generate_content_stream(self, **kwargs):
        yield type("Chunk", (), {"text": "first"})()
        time.sleep(0.05)
        yield type("Chunk", (), {"text": "late"})()


class _FakeClient:
    models = _SlowStreamModels()


class _StallingClient:
    models = _StallingStreamModels()


class _FakeHttpOptions:
    def __init__(self, *, timeout: int) -> None:
        self.timeout = timeout


class _FakeTypes:
    HttpOptions = _FakeHttpOptions


class _FakeGenAI:
    calls: list[dict] = []

    @staticmethod
    def Client(api_key: str, http_options=None):
        _FakeGenAI.calls.append(
            {"api_key": api_key, "http_options": http_options}
        )
        return {"api_key": api_key, "http_options": http_options}


class _FakePool:
    def __init__(self) -> None:
        self.keys = [
            ("secret-one", "fp-one", 0),
            ("secret-two", "fp-two", 1),
        ]
        self.index = 0
        self.rate_limited: list[tuple[str, str | None]] = []
        self.successes: list[str] = []
        self.failures: list[tuple[str, str | None]] = []

    def acquire_key(self):
        key = self.keys[self.index]
        self.index += 1
        return key

    def record_rate_limit(self, key_id: str, error_type: str | None = None) -> None:
        self.rate_limited.append((key_id, error_type))

    def record_success(self, key_id: str) -> None:
        self.successes.append(key_id)

    def record_failure(self, key_id: str, error_type: str | None = None) -> None:
        self.failures.append((key_id, error_type))


class _UnavailablePool:
    def acquire_key(self):
        raise RuntimeError("all_gemini_keys_daily_quota_exhausted")


class GeminiClientTest(unittest.TestCase):
    def test_request_clients_use_sdk_transport_timeout_in_milliseconds(self) -> None:
        client = object.__new__(GeminiClient)
        client._genai = _FakeGenAI()
        client._types = _FakeTypes()
        client.request_timeout_seconds = 2.5
        _FakeGenAI.calls.clear()

        request_client = client._create_client("secret")

        self.assertEqual(request_client["api_key"], "secret")
        self.assertEqual(request_client["http_options"].timeout, 2500)

    def test_streaming_call_times_out_without_chunks(self) -> None:
        client = object.__new__(GeminiClient)
        client._client = _FakeClient()
        client._config = object()
        client.model_name = "fake-model"
        client.request_timeout_seconds = 0.01

        with self.assertRaises(TimeoutError):
            list(client._generate_stream_once("prompt"))

    def test_streaming_call_times_out_when_stream_stalls_between_chunks(self) -> None:
        client = object.__new__(GeminiClient)
        client._client = _StallingClient()
        client._config = object()
        client.model_name = "fake-model"
        client.request_timeout_seconds = 0.01

        stream = client._generate_stream_once("prompt")

        self.assertEqual(next(stream), "first")
        with self.assertRaises(TimeoutError):
            next(stream)

    def test_generate_retries_next_key_after_rate_limit(self) -> None:
        client = object.__new__(GeminiClient)
        fake_pool = _FakePool()
        client.available_keys = ["secret-one", "secret-two"]
        client.model_name = "fake-model"
        client.max_retries = 1
        client.retry_base_delay_seconds = 0
        client.retry_max_delay_seconds = 0
        client.key_pool = fake_pool
        client._genai = _FakeGenAI()
        client._types = _FakeTypes()
        client.request_timeout_seconds = 1
        client._config = object()

        calls = {"count": 0}

        def generate_once(
            prompt: str,
            *,
            client=None,
        ) -> tuple[str, dict[str, int]]:
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("429 rate limit")
            return "ok", {"input": 1, "output": 1, "total": 2}

        client._generate_once = generate_once

        result = client.generate("prompt")

        self.assertTrue(result["ok"])
        self.assertEqual(result["text"], "ok")
        self.assertEqual(fake_pool.rate_limited, [("fp-one", "rate_limit")])
        self.assertEqual(fake_pool.successes, ["fp-two"])
        self.assertNotIn("secret-one", str(result))

    def test_generate_stream_retries_next_key_after_rate_limit(self) -> None:
        client = object.__new__(GeminiClient)
        fake_pool = _FakePool()
        client.available_keys = ["secret-one", "secret-two"]
        client.model_name = "fake-model"
        client.max_retries = 1
        client.retry_base_delay_seconds = 0
        client.retry_max_delay_seconds = 0
        client.key_pool = fake_pool
        client._genai = _FakeGenAI()
        client._types = _FakeTypes()
        client.request_timeout_seconds = 1
        client._config = object()

        calls = {"count": 0}

        def stream_once(prompt: str, *, client=None):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("429 resource_exhausted")
            yield "chunk"

        client._generate_stream_once = stream_once

        chunks = list(client.generate_stream("prompt"))

        self.assertEqual(chunks, ["chunk"])
        self.assertEqual(fake_pool.rate_limited, [("fp-one", "rate_limit")])
        self.assertEqual(fake_pool.successes, ["fp-two"])

    def test_generate_stream_does_not_retry_after_emitting_a_chunk(self) -> None:
        client = object.__new__(GeminiClient)
        fake_pool = _FakePool()
        client.available_keys = ["secret-one", "secret-two"]
        client.model_name = "fake-model"
        client.max_retries = 1
        client.retry_base_delay_seconds = 0
        client.retry_max_delay_seconds = 0
        client.key_pool = fake_pool
        client._genai = _FakeGenAI()
        client._types = _FakeTypes()
        client.request_timeout_seconds = 1
        client._config = object()

        def stream_once(prompt: str, *, client=None):
            yield "partial"
            raise RuntimeError("Server disconnected without sending a response.")

        client._generate_stream_once = stream_once
        stream = client.generate_stream("prompt")

        self.assertEqual(next(stream), "partial")
        with self.assertRaisesRegex(RuntimeError, "disconnected"):
            next(stream)
        self.assertEqual(fake_pool.index, 1)
        self.assertEqual(fake_pool.failures, [("fp-one", "transient_error")])

    def test_generate_returns_structured_failure_when_all_keys_are_exhausted(
        self,
    ) -> None:
        client = object.__new__(GeminiClient)
        client.available_keys = ["secret-one"]
        client.model_name = "fake-model"
        client.max_retries = 3
        client.key_pool = _UnavailablePool()

        result = client.generate("prompt")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "quota_exhausted")
        self.assertEqual(result["attempts"], 0)

    def test_disconnect_is_classified_as_transient(self) -> None:
        error_type = GeminiClient._classify_error(
            RuntimeError("Server disconnected without sending a response.")
        )

        self.assertEqual(error_type, "transient_error")
        self.assertTrue(GeminiClient._should_retry(error_type))

    def test_concurrent_generate_uses_request_local_clients(self) -> None:
        client = object.__new__(GeminiClient)
        fake_pool = _FakePool()
        fake_pool_lock = Lock()
        original_acquire_key = fake_pool.acquire_key

        def acquire_key():
            with fake_pool_lock:
                return original_acquire_key()

        fake_pool.acquire_key = acquire_key
        client.available_keys = ["secret-one", "secret-two"]
        client.model_name = "fake-model"
        client.max_retries = 0
        client.retry_base_delay_seconds = 0
        client.retry_max_delay_seconds = 0
        client.key_pool = fake_pool
        client._genai = _FakeGenAI()
        client._types = _FakeTypes()
        client.request_timeout_seconds = 1
        client._config = object()
        barrier = Barrier(2)

        def generate_once(prompt: str, *, client=None) -> tuple[str, dict[str, int]]:
            barrier.wait(timeout=1)
            text = f"{prompt}:{client['api_key']}"
            usage = {
                "input": len(prompt),
                "output": len(text),
                "total": len(prompt) + len(text),
            }
            return text, usage

        client._generate_once = generate_once

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(client.generate, ["first", "second"]))

        key_by_fingerprint = {
            "fp-one": "secret-one",
            "fp-two": "secret-two",
        }
        for prompt, result in zip(("first", "second"), results, strict=True):
            self.assertTrue(result["ok"])
            self.assertTrue(
                result["text"].endswith(key_by_fingerprint[result["key_fingerprint"]])
            )
            self.assertEqual(result["usage"]["input"], len(prompt))

    def test_concurrent_streams_return_request_local_usage(self) -> None:
        client = object.__new__(GeminiClient)
        fake_pool = _FakePool()
        fake_pool_lock = Lock()
        original_acquire_key = fake_pool.acquire_key

        def acquire_key():
            with fake_pool_lock:
                return original_acquire_key()

        fake_pool.acquire_key = acquire_key
        client.available_keys = ["secret-one", "secret-two"]
        client.model_name = "fake-model"
        client.max_retries = 0
        client.key_pool = fake_pool
        client._genai = _FakeGenAI()
        client._types = _FakeTypes()
        client.request_timeout_seconds = 1
        client._config = object()
        barrier = Barrier(2)

        def stream_once(prompt: str, *, client=None):
            barrier.wait(timeout=1)
            yield prompt
            return {
                "input": len(prompt),
                "output": len(prompt) + 1,
                "total": len(prompt) * 2 + 1,
            }

        def consume(prompt: str):
            stream = client.generate_stream(prompt)
            chunks: list[str] = []
            while True:
                try:
                    chunks.append(next(stream))
                except StopIteration as completed:
                    return chunks, completed.value

        client._generate_stream_once = stream_once
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(consume, ["one", "second"]))

        for prompt, (chunks, metadata) in zip(
            ("one", "second"),
            results,
            strict=True,
        ):
            self.assertEqual(chunks, [prompt])
            self.assertEqual(metadata["usage"]["input"], len(prompt))


class GeminiKeyPoolTest(unittest.TestCase):
    def test_key_pool_load_balances_between_keys(self) -> None:
        pool = GeminiKeyPool(
            ["key-one", "key-two"],
            model_name="fake-model",
            config={
                "rpm_limit_per_key": 12,
                "rpd_limit_per_key": 450,
                "state_path": "",
                "wait_when_all_keys_limited": False,
            },
        )

        acquired = [pool.acquire_key()[1] for _ in range(4)]

        self.assertEqual(acquired[0], acquired[2])
        self.assertEqual(acquired[1], acquired[3])
        self.assertNotEqual(acquired[0], acquired[1])

    def test_key_pool_skips_key_in_cooldown(self) -> None:
        pool = GeminiKeyPool(
            ["key-one", "key-two"],
            model_name="fake-model",
            config={
                "rpm_limit_per_key": 12,
                "rpd_limit_per_key": 450,
                "cooldown_on_rate_limit_seconds": 65,
                "state_path": "",
                "wait_when_all_keys_limited": False,
            },
        )

        _, first_key_id, _ = pool.acquire_key()
        pool.record_rate_limit(first_key_id)
        _, second_key_id, _ = pool.acquire_key()

        self.assertNotEqual(first_key_id, second_key_id)

    def test_key_pool_blocks_daily_exhausted_keys(self) -> None:
        pool = GeminiKeyPool(
            ["key-one"],
            model_name="fake-model",
            config={
                "rpm_limit_per_key": 12,
                "rpd_limit_per_key": 1,
                "state_path": "",
                "wait_when_all_keys_limited": False,
            },
        )

        pool.acquire_key()

        with self.assertRaisesRegex(RuntimeError, "daily_quota"):
            pool.acquire_key()


if __name__ == "__main__":
    unittest.main()
