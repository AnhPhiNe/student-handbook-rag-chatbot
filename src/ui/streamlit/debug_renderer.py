from __future__ import annotations

from html import escape
from typing import Any

import streamlit as st

DEBUG_FIELDS = [
    "status",
    "intent",
    "strategy",
    "effective_query",
    "query_rewrite",
    "retrieval_query",
    "rewrite_llm_called",
    "answer_llm_called",
    "used_cache",
    "error_type",
]


def render_debug_info(result: dict[str, Any] | None) -> None:
    if not result:
        return

    debug_payload = result.get("debug") if isinstance(result.get("debug"), dict) else None

    with st.expander("Debug", expanded=False):
        rows = []
        for field in DEBUG_FIELDS:
            value = _get_debug_value(field, result, debug_payload)
            rows.append((field, _format_debug_value(value)))

        html_rows = "".join(
            f"<div><span>{escape(field)}</span><strong>{escape(value)}</strong></div>"
            for field, value in rows
        )
        st.markdown(f'<div class="ep-debug-grid">{html_rows}</div>', unsafe_allow_html=True)


def _get_debug_value(
    field: str,
    result: dict[str, Any],
    debug_payload: dict[str, Any] | None,
) -> Any:
    if field == "rewrite_llm_called":
        rewrite = _get_debug_value("query_rewrite", result, debug_payload)
        if isinstance(rewrite, dict):
            return bool(rewrite.get("llm_called", False))
        return False

    if field == "answer_llm_called":
        value = result.get("llm_called")
        if value is None and debug_payload:
            value = debug_payload.get("llm_called")
        return value

    value = result.get(field)
    if value is None and debug_payload:
        value = debug_payload.get(field)
    return value


def _format_debug_value(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict) and "effective_query" in value:
        parts = [
            f"changed={str(value.get('changed')).lower()}",
            f"confidence={value.get('confidence')}",
            f"reason={value.get('reason')}",
        ]
        rewritten_query = value.get("rewritten_query")
        if rewritten_query:
            parts.append(f"rewritten={rewritten_query}")
        error_type = value.get("error_type")
        if error_type:
            parts.append(f"error={error_type}")
        return "; ".join(parts)
    if isinstance(value, (list, tuple, set, dict)):
        return f"{type(value).__name__}({len(value)})"
    return str(value)
