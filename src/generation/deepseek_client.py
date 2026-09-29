from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

from src.common.env_loader import load_project_env
from src.common.key_pool import KeyPool, KeyPoolConfig, NoAvailableKey

from .llm_client import PooledLLMClient

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
# DeepSeek thinks by default: "none" turns thinking off, the others set how
# much it thinks before answering.
REASONING_EFFORTS = ("none", "low", "high", "max")


def deepseek_key_pool_config(config: dict[str, Any] | None) -> KeyPoolConfig:
    """DeepSeek key limits; it caps concurrency, so only a request rate applies."""

    config = config or {}
    return KeyPoolConfig(
        name="deepseek",
        rpm_limit_per_key=max(1, int(config.get("rpm_limit_per_key", 60))),
        cooldown_seconds=max(1.0, float(config.get("cooldown_on_rate_limit_seconds", 30.0))),
        state_path=config.get("state_path"),
        wait_when_limited=bool(config.get("wait_when_all_keys_limited", False)),
    )


class DeepSeekClient(PooledLLMClient):
    """Call DeepSeek's OpenAI-compatible Chat API (composer and directory selector)."""

    provider_label = "DeepSeek"

    def __init__(
        self,
        model_name: str = "deepseek-flash",
        reasoning_effort: str = "none",
        temperature: float = 0.0,
        max_output_tokens: int = 8192,
        max_retries: int = 2,
        retry_base_delay_seconds: float = 2,
        retry_max_delay_seconds: float = 20,
        request_timeout_seconds: float = 30,
        api_keys_env_var: str = "DEEPSEEK_API_KEY",
        key_pool_config: KeyPoolConfig | dict[str, Any] | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> None:
        load_project_env()
        self.available_keys = [
            key.strip()
            for key in (os.environ.get(api_keys_env_var) or "").split(",")
            if key.strip()
        ]
        if not self.available_keys:
            raise RuntimeError(f"Missing {api_keys_env_var} for DeepSeek.")
        effort = str(reasoning_effort or "none").strip().lower()
        if effort not in REASONING_EFFORTS:
            raise ValueError(f"Unsupported DeepSeek reasoning effort: {effort}")
        self.model_name = model_name
        self.reasoning_effort = effort
        self.temperature = float(temperature)
        self.max_output_tokens = int(max_output_tokens)
        self.max_retries = max(0, int(max_retries))
        self.retry_base_delay_seconds = float(retry_base_delay_seconds)
        self.retry_max_delay_seconds = float(retry_max_delay_seconds)
        self.request_timeout_seconds = float(request_timeout_seconds)
        # {"type": "json_object"} makes DeepSeek return one JSON object.
        self.response_format = response_format
        if not isinstance(key_pool_config, KeyPoolConfig):
            key_pool_config = deepseek_key_pool_config(key_pool_config)
        self.key_pool = KeyPool(self.available_keys, key_pool_config, scope=self.model_name)

    def _create_client(self, api_key: str) -> Any:
        """One request client per key; the pool owns retries, not the SDK.

        The SDK timeout bounds each network read, so a stream that stalls
        between chunks fails instead of hanging.
        """
        from openai import OpenAI

        return OpenAI(api_key=api_key, base_url=DEEPSEEK_BASE_URL,
                      timeout=self.request_timeout_seconds, max_retries=0)

    def _request(self, prompt: str, client: Any, **options: Any) -> Any:
        thinking = (
            {"thinking": {"type": "disabled"}}
            if self.reasoning_effort == "none"
            else {"reasoning_effort": self.reasoning_effort}
        )
        return client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=self.temperature,
            max_tokens=self.max_output_tokens,
            extra_body=thinking,
            **({"response_format": self.response_format} if self.response_format else {}),
            **options,
        )

    @staticmethod
    def _usage(usage: Any, prompt: str, text: str) -> dict[str, int]:
        if usage is not None:
            inp = int(getattr(usage, "prompt_tokens", 0) or 0)
            out = int(getattr(usage, "completion_tokens", 0) or 0)
            return {"input": inp, "output": out,
                    "total": int(getattr(usage, "total_tokens", 0) or (inp + out))}
        inp, out = max(1, len(prompt) // 4), max(1, len(text) // 4)
        return {"input": inp, "output": out, "total": inp + out}

    def _generate_once(self, prompt: str, *, client: Any | None = None) -> tuple[str, dict[str, int]]:
        """Return the answer text only; the model's reasoning is never shown."""
        response = self._request(prompt, client or self._create_client(self.available_keys[0]))
        choice = response.choices[0]
        text = (choice.message.content or "").strip()
        if not text and choice.finish_reason == "length":
            # Thinking counts toward max_tokens; a long think leaves no answer.
            raise RuntimeError(f"DeepSeek used all {self.max_output_tokens} output tokens before answering.")
        return text, self._usage(getattr(response, "usage", None), prompt, text)

    def _generate_stream_once(
        self, prompt: str, *, client: Any | None = None
    ) -> Generator[str, None, dict[str, int]]:
        """Yield answer chunks and return request-local usage."""
        stream = self._request(prompt, client or self._create_client(self.available_keys[0]),
                               stream=True, stream_options={"include_usage": True})
        usage_obj = None
        text = ""
        try:
            for chunk in stream:
                if getattr(chunk, "usage", None) is not None:
                    usage_obj = chunk.usage
                for choice in getattr(chunk, "choices", None) or []:
                    # delta.reasoning_content carries thinking; only content is the answer.
                    content = getattr(choice.delta, "content", None)
                    if content:
                        text += content
                        yield content
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
        return self._usage(usage_obj, prompt, text)

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        if isinstance(exc, NoAvailableKey):
            return "rate_limit"
        if isinstance(exc, TimeoutError):
            return "timeout"
        status = getattr(exc, "status_code", None)
        if status is None:
            status = getattr(getattr(exc, "response", None), "status_code", None)
        if isinstance(status, int):
            if status in {401, 403}:
                return "auth_error"
            if status == 402:  # DeepSeek: insufficient balance
                return "quota_exhausted"
            if status == 429:
                return "rate_limit"
            if status in {408, 504}:
                return "timeout"
            if status >= 500:
                return "transient_error"
            return "invalid_request"
        name = type(exc).__name__.lower()
        text = f"{name}: {exc}".lower()
        if "timeout" in name or "timed out" in text:
            return "timeout"
        if "connection" in name or any(
            token in text for token in ("disconnected", "connection reset", "remoteprotocolerror")
        ):
            return "transient_error"
        return "unknown"
