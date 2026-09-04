from __future__ import annotations

from typing import Any


class UsageTracker:
    """Collect per-step model usage for observability without depending on API code."""

    def __init__(self) -> None:
        self._steps: list[dict[str, Any]] = []

    def record(
        self,
        step_name: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        total_tokens: int,
        start_time: str,
        end_time: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record one timed pipeline step and its token usage."""

        self._steps.append(
            {
                "step_name": step_name,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "start_time": start_time,
                "end_time": end_time,
                "metadata": metadata or {},
            }
        )

    def get_steps(self) -> list[dict[str, Any]]:
        """Return defensive copies of all recorded pipeline steps."""

        return self._steps

    def total_tokens(self) -> int:
        """Return the aggregate token count across recorded steps."""

        return sum(int(step.get("total_tokens") or 0) for step in self._steps)

    def get_total_usage(self) -> dict[str, int]:
        """Return aggregate input, output, and total token usage."""

        input_tokens = sum(int(step.get("input_tokens") or 0) for step in self._steps)
        output_tokens = sum(int(step.get("output_tokens") or 0) for step in self._steps)
        total_tokens = sum(int(step.get("total_tokens") or 0) for step in self._steps)
        if total_tokens == 0 and (input_tokens > 0 or output_tokens > 0):
            total_tokens = input_tokens + output_tokens
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }
