from __future__ import annotations

import time
from collections.abc import Generator
from typing import Any

from src.common.key_pool import KeyPool


class PooledLLMClient:
    """Bounded retries and key rotation shared by the composer providers.

    A provider supplies one request (`_generate_once`), one stream
    (`_generate_stream_once`), a request client per key and its own error
    classification. The retry, cooldown and no-retry-after-output rules live
    here once, so every composer behaves the same way under failure.
    """

    provider_label = "LLM"
    model_name: str
    key_pool: KeyPool
    max_retries: int
    retry_base_delay_seconds: float
    retry_max_delay_seconds: float
    request_timeout_seconds: float

    def _create_client(self, api_key: str) -> Any:
        raise NotImplementedError

    def _generate_once(self, prompt: str, *, client: Any | None = None) -> tuple[str, dict[str, int]]:
        raise NotImplementedError

    def _generate_stream_once(
        self, prompt: str, *, client: Any | None = None
    ) -> Generator[str, None, dict[str, int]]:
        raise NotImplementedError

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        raise NotImplementedError

    def generate(self, prompt: str) -> dict[str, Any]:
        """Generate one complete grounded answer with bounded retries."""

        attempts = 0
        max_attempts = max(1, self.max_retries + 1)
        last_error_type = None
        last_error_message = None
        name = type(self).__name__

        while attempts < max_attempts:
            try:
                current_key, key_id, key_index = self.key_pool.acquire()
            except Exception as exc:
                last_error_type = self._classify_error(exc)
                last_error_message = str(exc)
                break
            attempts += 1
            try:
                request_client = self._create_client(current_key)
                text, usage_dict = self._generate_once(
                    prompt,
                    client=request_client,
                )
                if not text.strip():
                    raise RuntimeError(f"{self.provider_label} API returned an empty response.")

                self.key_pool.record_success(key_id)
                return {
                    "ok": True,
                    "text": text,
                    "error_type": None,
                    "error_message": None,
                    "attempts": attempts,
                    "model_used": self.model_name,
                    "key_fingerprint": key_id,
                    "usage": usage_dict,
                }
            except Exception as exc:
                last_error_type = self._classify_error(exc)
                last_error_message = str(exc)

                if last_error_type == "rate_limit":
                    print(
                        f"[{name}] Key "
                        f"{key_index}:{key_id} hit rate limit; cooling down."
                    )
                    self.key_pool.record_rate_limit(key_id)
                    continue

                self.key_pool.record_failure(key_id, last_error_type)
                if not self._should_retry(last_error_type) or attempts >= max_attempts:
                    break

                delay = self._retry_delay(attempts)
                print(
                    f"[{name}] Retriable error ({last_error_type}) on "
                    f"key {key_index}:{key_id}. Sleeping {delay:.2f}s."
                )
                time.sleep(delay)

        return {
            "ok": False,
            "text": "",
            "error_type": last_error_type or "unknown",
            "error_message": last_error_message or f"Unknown {self.provider_label} API error.",
            "attempts": attempts,
            "model_used": self.model_name,
        }

    def _retry_delay(self, attempt_index: int) -> float:
        capped_attempt = max(0, attempt_index - 1)
        delay = self.retry_base_delay_seconds * (2**capped_attempt)
        return min(self.retry_max_delay_seconds, delay)

    @staticmethod
    def _should_retry(error_type: str | None) -> bool:
        return error_type in {"rate_limit", "timeout", "api_error", "transient_error"}

    def generate_stream(self, prompt: str) -> Generator[str, None, dict[str, Any]]:
        """Yield chunks and return request-local usage when streaming completes."""

        attempts = 0
        max_attempts = max(1, self.max_retries + 1)
        name = type(self).__name__
        while attempts < max_attempts:
            current_key, key_id, key_index = self.key_pool.acquire()
            attempts += 1
            emitted_any = False
            has_text = False
            try:
                request_client = self._create_client(current_key)
                request_stream = self._generate_stream_once(
                    prompt,
                    client=request_client,
                )
                usage: dict[str, int] = {}
                while True:
                    try:
                        chunk = next(request_stream)
                    except StopIteration as completed:
                        if isinstance(completed.value, dict):
                            usage = completed.value
                        break
                    emitted_any = True
                    has_text = has_text or bool(chunk.strip())
                    yield chunk
                if not has_text:
                    raise RuntimeError(f"{self.provider_label} API returned an empty response.")
                self.key_pool.record_success(key_id)
                return {
                    "model_used": self.model_name,
                    "key_fingerprint": key_id,
                    "attempts": attempts,
                    "usage": usage,
                }
            except Exception as exc:
                error_type = self._classify_error(exc)
                if error_type == "rate_limit":
                    print(
                        f"[{name}] Streaming key "
                        f"{key_index}:{key_id} hit rate limit; cooling down."
                    )
                    self.key_pool.record_rate_limit(key_id)
                    if emitted_any:
                        raise
                    continue

                self.key_pool.record_failure(key_id, error_type)
                if emitted_any or not self._should_retry(error_type):
                    raise
                if attempts >= max_attempts:
                    break
                delay = self._retry_delay(attempts)
                print(
                    f"[{name}] Streaming retryable error ({error_type}) on "
                    f"key {key_index}:{key_id}. Sleeping {delay:.2f}s."
                )
                time.sleep(delay)
        raise RuntimeError(f"{self.provider_label} streaming failed after all retry attempts.")
