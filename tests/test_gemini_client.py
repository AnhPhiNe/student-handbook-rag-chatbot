from __future__ import annotations

import time
import unittest

from src.generation.gemini_client import GeminiClient, GeminiKeyPool


class _SlowStreamModels:
    def generate_content_stream(self, **kwargs):
        time.sleep(0.05)
        yield type("Chunk", (), {"text": "late"})()


class _FakeClient:
    models = _SlowStreamModels()


class _FakeGenAI:
    @staticmethod
    def Client(api_key: str):
        return {"api_key": api_key}


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


class GeminiClientTest(unittest.TestCase):
    def test_streaming_call_times_out_without_chunks(self) -> None:
        client = object.__new__(GeminiClient)
        client._client = _FakeClient()
        client._config = object()
        client.model_name = "fake-model"
        client.request_timeout_seconds = 0.01

        with self.assertRaises(TimeoutError):
            list(client._generate_stream_once("prompt"))

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
        client._config = object()

        calls = {"count": 0}

        def generate_once(prompt: str) -> str:
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("429 rate limit")
            return "ok"

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
        client._config = object()

        calls = {"count": 0}

        def stream_once(prompt: str):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("429 resource_exhausted")
            yield "chunk"

        client._generate_stream_once = stream_once

        chunks = list(client.generate_stream("prompt"))

        self.assertEqual(chunks, ["chunk"])
        self.assertEqual(fake_pool.rate_limited, [("fp-one", "rate_limit")])
        self.assertEqual(fake_pool.successes, ["fp-two"])


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
