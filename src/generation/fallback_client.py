"""Try one provider, then another serving the same model, on provider failures.

The DeepSeek API ran out of balance on 2026-10-04 and took the live answers down
with it. DeepInfra serves the same DeepSeek-V4.1-Flash weights, so it can take
over without changing answers in kind. A provider failure (no balance, a bad or
expired key, rate limits, timeouts, server or connection errors) moves to the
fallback. A failure of the answer itself (cut off, filtered, a rejected request)
does not: the other provider would fail the same way.
"""
from __future__ import annotations

from collections.abc import Generator
from typing import Any

# Errors that describe the request or its answer, not the provider.
ANSWER_ERRORS = frozenset({
    "output_truncated", "content_filtered", "incomplete_stream",
    "invalid_completion", "invalid_request",
})


class FallbackLLMClient:
    """Same interface as a pooled client; the primary answers unless it cannot."""

    def __init__(self, primary: Any, fallback: Any) -> None:
        self.primary = primary
        self.fallback = fallback

    def __getattr__(self, name: str) -> Any:
        # model_name, reasoning_effort, max_output_tokens… describe the primary.
        return getattr(self.primary, name)

    def generate(self, prompt: str) -> dict[str, Any]:
        result = self.primary.generate(prompt)
        if result.get("ok") or result.get("error_type") in ANSWER_ERRORS:
            return result
        backup = self.fallback.generate(prompt)
        return {**backup, "fallback_from": {"model": self.primary.model_name,
                                            "error_type": result.get("error_type")}}

    def generate_stream(self, prompt: str) -> Generator[str, None, dict[str, Any]]:
        stream = self.primary.generate_stream(prompt)
        emitted = False
        try:
            while True:
                try:
                    chunk = next(stream)
                except StopIteration as completed:
                    return completed.value
                emitted = True
                yield chunk
        except Exception as exc:
            error_type = getattr(exc, "error_type", None) or self.primary._classify_error(exc)
            # Text already shown cannot be continued by another provider.
            if emitted or error_type in ANSWER_ERRORS:
                raise
            failed = {"model": self.primary.model_name, "error_type": error_type}
        result = yield from self.fallback.generate_stream(prompt)
        return {**(result or {}), "fallback_from": failed}
