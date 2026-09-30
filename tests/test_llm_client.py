"""Retry and key rotation shared by the LLM clients, with a fake provider.

PooledLLMClient owns the retry rules; a provider only supplies one request,
one stream and its own error classification. The fake below classifies by
message so each rule can be driven without an SDK.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from unittest import mock

import pytest

from src.common.key_pool import NoAvailableKey
from src.generation.llm_client import PooledLLMClient

KEYS = [("secret-one", "fp-one", 0), ("secret-two", "fp-two", 1)]


class _FakePool:
    def __init__(self) -> None:
        self.index = 0
        self.lock = Lock()
        self.rate_limited: list[str] = []
        self.successes: list[str] = []
        self.failures: list[tuple[str, str | None]] = []

    def acquire(self):
        with self.lock:
            key = KEYS[self.index % len(KEYS)]
            self.index += 1
            return key

    def record_rate_limit(self, key_id: str, retry_after_seconds: float | None = None) -> None:
        self.rate_limited.append(key_id)

    def record_success(self, key_id: str) -> None:
        self.successes.append(key_id)

    def record_failure(self, key_id: str, error_type: str | None = None) -> None:
        self.failures.append((key_id, error_type))


class _ExhaustedPool:
    def acquire(self):
        raise NoAvailableKey("all_fake_keys_daily_request_quota_exhausted")


class _FakeProvider(PooledLLMClient):
    provider_label = "Fake"

    def __init__(self, *, max_retries: int = 1, retry_base_delay_seconds: float = 0) -> None:
        self.model_name = "fake-model"
        self.key_pool = _FakePool()
        self.max_retries = max_retries
        self.retry_base_delay_seconds = retry_base_delay_seconds
        self.retry_max_delay_seconds = 20
        self.request_timeout_seconds = 1

    def _create_client(self, api_key: str) -> str:
        return api_key

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        text = str(exc)
        if isinstance(exc, NoAvailableKey):
            return "quota_exhausted"
        if "429" in text:
            return "rate_limit"
        if "disconnected" in text:
            return "transient_error"
        return "unknown"


def _answer(text: str = "ok") -> tuple[str, dict[str, int]]:
    return text, {"input": 1, "output": 1, "total": 2}


def test_generate_moves_to_the_next_key_after_a_rate_limit() -> None:
    client = _FakeProvider()
    replies = iter([RuntimeError("429 rate limit"), _answer()])

    def generate_once(prompt, *, client=None):
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    client._generate_once = generate_once
    result = client.generate("prompt")

    assert result["ok"] and result["text"] == "ok"
    assert client.key_pool.rate_limited == ["fp-one"]
    assert client.key_pool.successes == ["fp-two"]
    assert "secret-one" not in str(result)


def test_stream_moves_to_the_next_key_after_a_rate_limit() -> None:
    client = _FakeProvider()
    calls = {"count": 0}

    def stream_once(prompt, *, client=None):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("429 resource exhausted")
        yield "chunk"

    client._generate_stream_once = stream_once

    assert list(client.generate_stream("prompt")) == ["chunk"]
    assert client.key_pool.rate_limited == ["fp-one"]
    assert client.key_pool.successes == ["fp-two"]


def test_stream_is_not_retried_after_a_chunk_was_sent() -> None:
    client = _FakeProvider()

    def stream_once(prompt, *, client=None):
        yield "partial"
        raise RuntimeError("Server disconnected without sending a response.")

    client._generate_stream_once = stream_once
    stream = client.generate_stream("prompt")

    assert next(stream) == "partial"
    with pytest.raises(RuntimeError, match="disconnected"):
        next(stream)
    assert client.key_pool.index == 1
    assert client.key_pool.failures == [("fp-one", "transient_error")]


def test_generate_does_not_sleep_after_the_last_attempt() -> None:
    client = _FakeProvider(max_retries=2, retry_base_delay_seconds=2)

    def generate_once(prompt, *, client=None):
        raise RuntimeError("Server disconnected without sending a response.")

    client._generate_once = generate_once
    with mock.patch("src.generation.llm_client.time.sleep") as sleep:
        result = client.generate("prompt")

    assert not result["ok"] and result["attempts"] == 3
    # Three attempts need two waits between them, none after the last.
    assert [call.args[0] for call in sleep.call_args_list] == [2, 4]


def test_stream_does_not_sleep_after_the_last_attempt() -> None:
    client = _FakeProvider(max_retries=2, retry_base_delay_seconds=2)

    def stream_once(prompt, *, client=None):
        raise RuntimeError("Server disconnected without sending a response.")
        yield

    client._generate_stream_once = stream_once
    with mock.patch("src.generation.llm_client.time.sleep") as sleep:
        with pytest.raises(RuntimeError):
            list(client.generate_stream("prompt"))

    assert client.key_pool.index == 3
    assert [call.args[0] for call in sleep.call_args_list] == [2, 4]


def test_generate_reports_an_exhausted_pool_as_a_structured_failure() -> None:
    client = _FakeProvider(max_retries=3)
    client.key_pool = _ExhaustedPool()

    result = client.generate("prompt")

    assert not result["ok"]
    assert result["error_type"] == "quota_exhausted"
    assert result["attempts"] == 0


def test_an_empty_answer_is_a_failure() -> None:
    client = _FakeProvider(max_retries=0)
    client._generate_once = lambda prompt, *, client=None: _answer("  ")

    result = client.generate("prompt")

    assert not result["ok"]
    assert "empty response" in result["error_message"]
    assert client.key_pool.successes == []


@pytest.mark.parametrize("chunks", [[], ["", " \n\t"]])
def test_an_empty_stream_is_a_failure(chunks) -> None:
    client = _FakeProvider(max_retries=0)
    client._generate_stream_once = lambda prompt, *, client=None: iter(chunks)

    with pytest.raises(RuntimeError):
        list(client.generate_stream("prompt"))
    assert client.key_pool.successes == []
    assert len(client.key_pool.failures) == 1


def test_concurrent_calls_use_their_own_key_and_usage() -> None:
    client = _FakeProvider(max_retries=0)
    barrier = Barrier(2)

    def generate_once(prompt, *, client=None):
        barrier.wait(timeout=1)
        return f"{prompt}:{client}", {"input": len(prompt), "output": 1, "total": len(prompt) + 1}

    client._generate_once = generate_once
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(client.generate, ["first", "second"]))

    secret_by_fingerprint = {fingerprint: secret for secret, fingerprint, _ in KEYS}
    for prompt, result in zip(("first", "second"), results, strict=True):
        assert result["text"] == f"{prompt}:{secret_by_fingerprint[result['key_fingerprint']]}"
        assert result["usage"]["input"] == len(prompt)
