from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

from src.common.env_loader import load_project_env
from src.common.key_pool import KeyPool, KeyPoolConfig

from .deepseek_client import DeepSeekClient
from .llm_client import PooledLLMClient

OPENAI_BASE_URL = "https://api.openai.com/v1"
REASONING_EFFORTS = {"none", "low", "medium", "high", "xhigh", "max"}


class IncompleteComposerResponse(RuntimeError):
    """The API did not finish the answer; do not report partial text as success."""

    def __init__(self, reason: str | None, usage: dict[str, int]) -> None:
        self.error_type = "output_truncated" if reason == "max_output_tokens" else "incomplete_response"
        self.usage = usage
        super().__init__(f"OpenAI composer response did not complete ({reason or 'unknown'}).")


class OpenAIComposerClient(PooledLLMClient):
    """Luna composer over Responses, sharing bounded retries with other clients."""

    provider_label = "OpenAI"

    def __init__(
        self,
        model_name: str = "gpt-6-luna",
        reasoning_effort: str = "medium",
        verbosity: str = "medium",
        max_output_tokens: int | None = None,
        max_retries: int = 2,
        retry_base_delay_seconds: float = 2,
        retry_max_delay_seconds: float = 20,
        request_timeout_seconds: float = 60,
        api_keys_env_var: str = "OPENAI_API_KEY",
        key_pool_config: KeyPoolConfig | dict[str, Any] | None = None,
    ) -> None:
        load_project_env()
        self.available_keys = [
            key.strip()
            for key in (os.environ.get(api_keys_env_var) or "").split(",")
            if key.strip()
        ]
        if not self.available_keys:
            raise RuntimeError(f"Missing {api_keys_env_var} for OpenAI composer.")
        self.model_name = model_name
        self.reasoning_effort = str(reasoning_effort).strip().lower()
        if self.reasoning_effort not in REASONING_EFFORTS:
            raise ValueError("Unsupported OpenAI composer reasoning effort.")
        self.verbosity = str(verbosity).strip().lower()
        if self.verbosity not in {"low", "medium", "high"}:
            raise ValueError("Unsupported OpenAI composer verbosity.")
        self.max_output_tokens = int(max_output_tokens) if max_output_tokens is not None else None
        self.max_retries = max(0, int(max_retries))
        self.retry_base_delay_seconds = float(retry_base_delay_seconds)
        self.retry_max_delay_seconds = float(retry_max_delay_seconds)
        self.request_timeout_seconds = float(request_timeout_seconds)
        if not isinstance(key_pool_config, KeyPoolConfig):
            config = key_pool_config or {}
            key_pool_config = KeyPoolConfig(
                name="openai_composer",
                rpm_limit_per_key=max(1, int(config.get("rpm_limit_per_key", 60))),
                cooldown_seconds=max(1.0, float(config.get("cooldown_on_rate_limit_seconds", 30))),
                state_path=config.get("state_path"),
                wait_when_limited=bool(config.get("wait_when_all_keys_limited", False)),
            )
        self.key_pool = KeyPool(
            self.available_keys, key_pool_config, scope=f"composer:{model_name}"
        )

    def _create_client(self, api_key: str) -> Any:
        from openai import OpenAI

        return OpenAI(
            api_key=api_key,
            base_url=OPENAI_BASE_URL,
            timeout=self.request_timeout_seconds,
            max_retries=0,
        )

    def _request(self, prompt: str, client: Any, *, stream: bool = False) -> Any:
        # Medium reasoning does not accept temperature/top_p. Reasoning and
        # answer detail are separate controls; neither changes the evidence.
        return client.responses.create(
            model=self.model_name,
            input=[{"role": "user", "content": prompt}],
            reasoning={"effort": self.reasoning_effort},
            text={"verbosity": self.verbosity},
            **({"max_output_tokens": self.max_output_tokens} if self.max_output_tokens is not None else {}),
            store=False,
            stream=stream,
        )

    @staticmethod
    def _usage(usage: Any) -> dict[str, int]:
        if usage is None:
            return {}
        inp = int(getattr(usage, "input_tokens", 0) or 0)
        out = int(getattr(usage, "output_tokens", 0) or 0)
        counts = {
            "input": inp,
            "output": out,
            "total": int(getattr(usage, "total_tokens", 0) or inp + out),
        }
        for key, detail, field in (
            ("cache_read", "input_tokens_details", "cached_tokens"),
            ("reasoning", "output_tokens_details", "reasoning_tokens"),
        ):
            value = getattr(getattr(usage, detail, None), field, None)
            if isinstance(value, int) and not isinstance(value, bool):
                counts[key] = value
        return counts

    @staticmethod
    def _require_completed(response: Any) -> None:
        if getattr(response, "status", None) != "completed":
            reason = getattr(getattr(response, "incomplete_details", None), "reason", None)
            raise IncompleteComposerResponse(reason, OpenAIComposerClient._usage(getattr(response, "usage", None)))

    def _generate_once(self, prompt: str, *, client: Any | None = None) -> tuple[str, dict[str, int]]:
        response = self._request(
            prompt, client or self._create_client(self.available_keys[0])
        )
        self._require_completed(response)
        return (response.output_text or "").strip(), self._usage(response.usage)

    def _generate_stream_once(
        self, prompt: str, *, client: Any | None = None
    ) -> Generator[str, None, dict[str, int]]:
        stream = self._request(
            prompt, client or self._create_client(self.available_keys[0]), stream=True
        )
        completed = None
        try:
            for event in stream:
                if event.type == "response.output_text.delta":
                    if event.delta:
                        yield event.delta
                elif event.type == "response.completed":
                    self._require_completed(event.response)
                    completed = event.response
                elif event.type == "response.incomplete":
                    self._require_completed(event.response)
                elif event.type in {"response.failed", "error"}:
                    raise RuntimeError("OpenAI composer stream failed.")
                # Reasoning and tool-related events are never user-visible.
            if completed is None:
                raise ConnectionError("OpenAI composer stream ended without completion.")
            return self._usage(getattr(completed, "usage", None))
        finally:
            stream.close()

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        if isinstance(exc, IncompleteComposerResponse):
            return exc.error_type
        return DeepSeekClient._classify_error(exc)
