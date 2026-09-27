from __future__ import annotations

import os
import queue
import threading
from collections.abc import Generator
from typing import Any

from src.common.env_loader import load_project_env
from src.common.key_pool import KeyPool, KeyPoolConfig

from .llm_client import PooledLLMClient


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


class GeminiClient(PooledLLMClient):
    """Generate grounded answers through a quota-aware Gemini key pool."""

    provider_label = "Gemini"

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
