from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any


class UsageTracker:
    """Collect one request's model calls and counters for observability.

    Every LLM call made for the request (planner, directory selector, composer)
    is one step with its model, provider, token usage and timing; counters hold
    request-level events such as corrected identifiers. The API sends the steps
    to LangSmith as child runs of the request.
    """

    def __init__(self) -> None:
        self._steps: list[dict[str, Any]] = []
        self.counters: Counter[str] = Counter()

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
        *,
        cache_read_tokens: int | None = None,
        reasoning_tokens: int | None = None,
    ) -> None:
        """Record one timed model call and its token usage."""

        self._steps.append(
            {
                "step_name": step_name,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "cache_read_tokens": cache_read_tokens,
                "reasoning_tokens": reasoning_tokens,
                "start_time": start_time,
                "end_time": end_time,
                "metadata": metadata or {},
            }
        )

    def record_call(
        self,
        step_name: str,
        *,
        model: str,
        usage: dict[str, Any] | None,
        start_time: str,
        end_time: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Record a call from a client usage dict (input, output, total, cache_read, reasoning)."""

        usage = usage or {}
        self.record(
            step_name,
            model,
            int(usage.get("input") or 0),
            int(usage.get("output") or 0),
            int(usage.get("total") or 0),
            start_time,
            end_time,
            metadata,
            cache_read_tokens=usage.get("cache_read"),
            reasoning_tokens=usage.get("reasoning"),
        )

    def get_steps(self) -> list[dict[str, Any]]:
        """Return the recorded pipeline steps."""

        return self._steps

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


def utc_now() -> str:
    """The timestamp format of recorded steps."""

    return datetime.now(timezone.utc).isoformat()


# The tracker of the request being planned and executed. Components deep in the
# pipeline (the directory selector) record their calls here instead of taking a
# tracker argument through every layer; outside a request it is None.
_current_tracker: ContextVar[UsageTracker | None] = ContextVar("usage_tracker", default=None)


@contextmanager
def tracking(tracker: UsageTracker | None) -> Iterator[None]:
    """Make ``tracker`` the current request's tracker within the block."""

    token = _current_tracker.set(tracker)
    try:
        yield
    finally:
        _current_tracker.reset(token)


def current_tracker() -> UsageTracker | None:
    """The tracker of the request in progress, if any."""

    return _current_tracker.get()
