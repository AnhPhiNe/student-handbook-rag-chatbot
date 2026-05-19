from __future__ import annotations

from typing import Any

import streamlit as st

from .source_renderer import summarize_citation


DEBUG_FIELDS = [
    "status",
    "intent",
    "strategy",
    "retrieval_query",
    "llm_called",
    "used_cache",
    "clarification_needed",
    "error_type",
    "error_message",
]


def render_debug_info(result: dict[str, Any] | None) -> None:
    if not result:
        return

    debug_payload = result.get("debug") if isinstance(result.get("debug"), dict) else None

    with st.expander("Debug info", expanded=False):
        for field in DEBUG_FIELDS:
            value = result.get(field)
            if value is None and debug_payload:
                value = debug_payload.get(field)
            st.markdown(f"**{field}:** `{_format_debug_value(value)}`")

        citations_used = _as_list(result.get("citations_used"))
        all_citations = _as_list(result.get("citations"))
        retrieved_sources = _first_list_value(
            result,
            ("retrieved_items", "context_sources", "sources", "retrieval_sources"),
        )

        st.markdown(f"**number of citations:** `{_citation_count(all_citations, citations_used)}`")
        st.markdown(f"**number of citations_used:** `{len(citations_used)}`")
        st.markdown(
            f"**number of retrieved/context sources:** `{_source_count(retrieved_sources, all_citations)}`"
        )

        retrieval_plan = result.get("retrieval_plan")
        if retrieval_plan:
            st.markdown("**retrieval_plan:**")
            st.json(retrieval_plan, expanded=False)

        if debug_payload:
            st.markdown("**api debug payload:**")
            st.json(debug_payload, expanded=False)

        st.markdown("**citations_used:**")
        if citations_used:
            for index, citation in enumerate(citations_used, start=1):
                if isinstance(citation, dict):
                    st.caption(f"{index}. {summarize_citation(citation)}")
                else:
                    st.caption(f"{index}. {_format_debug_value(citation)}")
        else:
            st.caption("Không có citation được chọn.")

        with st.expander("Raw response", expanded=False):
            st.json(result, expanded=False)


def _format_debug_value(value: Any) -> str:
    if value is None:
        return "None"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set, dict)):
        return f"{type(value).__name__}({len(value)})"
    return str(value)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _first_list_value(result: dict[str, Any], keys: tuple[str, ...]) -> list[Any]:
    for key in keys:
        value = result.get(key)
        if isinstance(value, list):
            return value
    return []


def _source_count(retrieved_sources: list[Any], all_citations: list[Any]) -> int:
    if retrieved_sources:
        return len(retrieved_sources)
    return len(all_citations)


def _citation_count(all_citations: list[Any], citations_used: list[Any]) -> int:
    if all_citations:
        return len(all_citations)
    return len(citations_used)
