from __future__ import annotations

from typing import Any

from .session_manager import (
    clear_pending_clarification,
    get_pending_clarification,
    set_pending_clarification,
)


def build_pipeline_query(user_query: str) -> tuple[str, bool]:
    """Combine a clarification answer with the previous ambiguous query."""
    pending = get_pending_clarification()
    cleaned_query = user_query.strip()

    if not pending:
        return cleaned_query, False

    previous_query = str(pending.get("original_query") or "").strip()
    clear_pending_clarification()

    if not previous_query:
        return cleaned_query, True

    return f"{previous_query} {cleaned_query}".strip(), True


def update_clarification_state(pipeline_query: str, result: dict[str, Any]) -> None:
    if _needs_clarification(result):
        set_pending_clarification(
            original_query=pipeline_query,
            question=str(result.get("answer") or "").strip(),
        )
    else:
        clear_pending_clarification()


def _needs_clarification(result: dict[str, Any]) -> bool:
    return (
        result.get("status") == "needs_clarification"
        or result.get("clarification_needed") is True
    )
