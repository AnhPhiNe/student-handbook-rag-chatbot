from __future__ import annotations

import os
import queue
import threading
import time
from collections.abc import Generator
from typing import Any

from src.common.env_loader import load_project_env
from src.common.key_pool import KeyPool, KeyPoolConfig


def gemini_key_pool_config(config: dict[str, Any] | None) -> KeyPoolConfig:
    """Gemini key limits from the key_pool section of configs/answer_generation.yaml."""

    config = config or {}
    return KeyPoolConfig(
        name="gemini",
        rpm_limit_per_key=max(1, int(config.get("rpm_limit_per_key", 12))),
        rpd_limit_per_key=max(1, int(config.get("rpd_limit_per_key", 450))),
        cooldown_seconds=max(
            1.0, float(config.get("cooldown_on_rate_limit_seconds", 65.0))
        ),
        state_path=str(config.get("state_path", "data/cache/gemini_key_state.json")),
        wait_when_limited=bool(config.get("wait_when_all_keys_limited", False)),
    )


class GeminiClient:
    """Generate grounded answers through a quota-aware Gemini key pool."""

    def __init__(
        self,
        model_name: str = "gemini-3.1-flash-lite",
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
        max_retries: int = 3,
        retry_base_delay_seconds: float = 2,
        retry_max_delay_seconds: float = 20,
        request_timeout_seconds: float = 60,
        api_keys_env_var: str = "GEMINI_API_KEYS",
        key_pool_config: KeyPoolConfig | dict[str, Any] | None = None,
    ) -> None:
        load_project_env()
        self.api_keys_env_var = api_keys_env_var

        keys_str = os.environ.get(api_keys_env_var)
        if not keys_str:
            raise RuntimeError(
                f"Missing {api_keys_env_var}. Add a comma-separated key pool "
                "to .env or set this environment variable before running Gemini calls."
            )
        self.available_keys = [
            key.strip() for key in keys_str.split(",") if key.strip()
        ]

        try:
            from google import genai
            from google.genai import types

            self._types = types
            self._genai = genai
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency google-genai. Install it with: pip install google-genai"
            ) from exc

        self.model_name = model_name
        self.max_retries = max(0, int(max_retries))
        self.retry_base_delay_seconds = float(retry_base_delay_seconds)
        self.retry_max_delay_seconds = float(retry_max_delay_seconds)
        self.request_timeout_seconds = float(request_timeout_seconds)
        if not isinstance(key_pool_config, KeyPoolConfig):
            key_pool_config = gemini_key_pool_config(key_pool_config)
        self.key_pool = KeyPool(
            self.available_keys, key_pool_config, scope=self.model_name
        )

        self._client = self._create_client(self.available_keys[0])
        self._config = self._types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
    def _create_client(self, api_key: str) -> Any:
        """Create a request client whose transport enforces the configured timeout."""

        timeout_ms = max(1, int(round(self.request_timeout_seconds * 1000)))
        return self._genai.Client(
            api_key=api_key,
            http_options=self._types.HttpOptions(timeout=timeout_ms),
        )

    def generate(self, prompt: str) -> dict[str, Any]:
        """Generate one complete grounded answer with bounded retries."""

        attempts = 0
        max_attempts = max(1, self.max_retries + 1)
        last_error_type = None
        last_error_message = None

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
                if not text:
                    raise RuntimeError("Gemini API returned an empty response.")

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
                        "[GeminiClient] Key "
                        f"{key_index}:{key_id} hit rate limit; cooling down."
                    )
                    self.key_pool.record_rate_limit(key_id)
                    continue

                self.key_pool.record_failure(key_id, last_error_type)
                if not self._should_retry(last_error_type):
                    break

                delay = self._retry_delay(attempts)
                print(
                    f"[GeminiClient] Retriable error ({last_error_type}) on "
                    f"key {key_index}:{key_id}. Sleeping {delay:.2f}s."
                )
                time.sleep(delay)

        return {
            "ok": False,
            "text": "",
            "error_type": last_error_type or "unknown",
            "error_message": last_error_message or "Unknown Gemini API error.",
            "attempts": attempts,
            "model_used": self.model_name,
        }

    def _generate_once(
        self,
        prompt: str,
        *,
        client: Any | None = None,
    ) -> tuple[str, dict[str, int]]:
        """Return generated text and usage owned by this invocation."""

        request_client = client or self._client
        response = request_client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=self._config,
        )

        text = (getattr(response, "text", None) or "").strip()
        usage_obj = getattr(response, "usage_metadata", None)
        if usage_obj:
            inp = int(getattr(usage_obj, "prompt_token_count", 0) or 0)
            out = int(getattr(usage_obj, "candidates_token_count", 0) or 0)
            tot = int(getattr(usage_obj, "total_token_count", 0) or (inp + out))
            usage = {"input": inp, "output": out, "total": tot}
        else:
            inp = max(1, len(prompt) // 4)
            out = max(1, len(text) // 4)
            usage = {"input": inp, "output": out, "total": inp + out}

        return text, usage

    def _retry_delay(self, attempt_index: int) -> float:
        capped_attempt = max(0, attempt_index - 1)
        delay = self.retry_base_delay_seconds * (2**capped_attempt)
        return min(self.retry_max_delay_seconds, delay)

    @staticmethod
    def _should_retry(error_type: str | None) -> bool:
        return error_type in {"rate_limit", "timeout", "api_error", "transient_error"}

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        if isinstance(exc, TimeoutError):
            return "timeout"

        text = f"{type(exc).__name__}: {exc}".lower()
        if "all_gemini_keys_daily" in text and "quota_exhausted" in text:
            return "quota_exhausted"
        if any(
            token in text
            for token in [
                "429",
                "resource_exhausted",
                "quota",
                "rate limit",
                "ratelimit",
            ]
        ):
            return "rate_limit"
        if any(
            token in text
            for token in ["503", "unavailable", "deadline", "temporarily", "transient"]
        ):
            return "api_error"
        if any(
            token in text
            for token in [
                "disconnected",
                "connection reset",
                "connection aborted",
                "connecterror",
                "remoteprotocolerror",
                "network error",
            ]
        ):
            return "transient_error"
        if any(token in text for token in ["timeout", "timed out"]):
            return "timeout"
        if any(token in text for token in ["api", "google", "gemini"]):
            return "api_error"
        return "unknown"

    def generate_stream(self, prompt: str) -> Generator[str, None, dict[str, Any]]:
        """Yield chunks and return request-local usage when streaming completes."""

        attempts = 0
        max_attempts = max(1, self.max_retries + 1)
        while attempts < max_attempts:
            current_key, key_id, key_index = self.key_pool.acquire()
            attempts += 1
            emitted_any = False
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
                    yield chunk
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
                        "[GeminiClient] Streaming key "
                        f"{key_index}:{key_id} hit rate limit; cooling down."
                    )
                    self.key_pool.record_rate_limit(key_id)
                    if emitted_any:
                        raise
                    continue

                self.key_pool.record_failure(key_id, error_type)
                if emitted_any or not self._should_retry(error_type):
                    raise
                delay = self._retry_delay(attempts)
                print(
                    f"[GeminiClient] Streaming retryable error ({error_type}) on "
                    f"key {key_index}:{key_id}. Sleeping {delay:.2f}s."
                )
                time.sleep(delay)
        raise RuntimeError("Gemini streaming failed after all retry attempts.")

    def _generate_stream_once(
        self,
        prompt: str,
        *,
        client: Any | None = None,
    ) -> Generator[str, None, dict[str, int]]:
        """Yield one provider stream and return its request-local usage."""

        request_client = client or self._client
        output_queue: queue.Queue[
            tuple[str, str | dict[str, int] | Exception | None]
        ] = queue.Queue()
        completed_usage: dict[str, int] | None = None

        def worker() -> None:
            captured_usage = None
            accumulated_text = ""
            try:
                response = request_client.models.generate_content_stream(
                    model=self.model_name,
                    contents=prompt,
                    config=self._config,
                )
                for chunk in response:
                    text = getattr(chunk, "text", None) or ""
                    if text:
                        accumulated_text += text
                        output_queue.put(("text", text))
                    u = getattr(chunk, "usage_metadata", None)
                    if u:
                        inp = int(getattr(u, "prompt_token_count", 0) or 0)
                        out = int(getattr(u, "candidates_token_count", 0) or 0)
                        tot = int(getattr(u, "total_token_count", 0) or (inp + out))
                        if tot:
                            captured_usage = {"input": inp, "output": out, "total": tot}

                if not captured_usage:
                    inp = max(1, len(prompt) // 4)
                    out = max(1, len(accumulated_text) // 4)
                    captured_usage = {"input": inp, "output": out, "total": inp + out}

                output_queue.put(("usage", captured_usage))
                output_queue.put(("done", None))
            except Exception as exc:
                output_queue.put(("error", exc))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        while True:
            try:
                item_type, payload = output_queue.get(
                    timeout=self.request_timeout_seconds,
                )
            except queue.Empty as exc:
                raise TimeoutError(
                    "Gemini streaming request timed out after "
                    f"{self.request_timeout_seconds} seconds without a chunk."
                ) from exc

            if item_type == "text":
                yield str(payload)
            elif item_type == "usage":
                if isinstance(payload, dict):
                    completed_usage = payload
            elif item_type == "error":
                if isinstance(payload, Exception):
                    raise payload
                raise RuntimeError("Unknown Gemini streaming error.")
            elif item_type == "done":
                return completed_usage or {}
