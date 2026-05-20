from __future__ import annotations

from html import escape
from typing import Any

import streamlit as st

DEBUG_FIELDS = [
    "status",
    "intent",
    "strategy",
    "llm_called",
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
            value = result.get(field)
            if value is None and debug_payload:
                value = debug_payload.get(field)
            rows.append((field, _format_debug_value(value)))

        html_rows = "".join(
            f"<div><span>{escape(field)}</span><strong>{escape(value)}</strong></div>"
            for field, value in rows
        )
        st.markdown(f'<div class="ep-debug-grid">{html_rows}</div>', unsafe_allow_html=True)


def _format_debug_value(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set, dict)):
        return f"{type(value).__name__}({len(value)})"
    return str(value)
