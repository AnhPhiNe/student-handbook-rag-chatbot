from __future__ import annotations

import os
from typing import Any

import streamlit as st


CHAT_HISTORY_KEY = "chat_history"
PENDING_CLARIFICATION_KEY = "pending_clarification"
LAST_RESULT_KEY = "last_result"
DEBUG_TOGGLE_KEY = "show_debug"


def initialize_session_state() -> None:
    st.session_state.setdefault(CHAT_HISTORY_KEY, [])
    st.session_state.setdefault(PENDING_CLARIFICATION_KEY, None)
    st.session_state.setdefault(LAST_RESULT_KEY, None)
    st.session_state.setdefault(DEBUG_TOGGLE_KEY, False)


def get_chat_history() -> list[dict[str, Any]]:
    initialize_session_state()
    return st.session_state[CHAT_HISTORY_KEY]


def append_message(
    role: str,
    content: str,
    result: dict[str, Any] | None = None,
    pipeline_query: str | None = None,
    message_id: str | None = None,
) -> None:
    message = {
        "role": role,
        "content": content,
        "result": result,
        "pipeline_query": pipeline_query,
    }
    if message_id:
        message["message_id"] = message_id
    get_chat_history().append(message)


def clear_chat_history() -> None:
    st.session_state[CHAT_HISTORY_KEY] = []
    clear_pending_clarification()
    st.session_state[LAST_RESULT_KEY] = None


def get_pending_clarification() -> dict[str, str] | None:
    initialize_session_state()
    pending = st.session_state[PENDING_CLARIFICATION_KEY]
    return pending if isinstance(pending, dict) else None


def set_pending_clarification(original_query: str, question: str) -> None:
    st.session_state[PENDING_CLARIFICATION_KEY] = {
        "original_query": original_query,
        "question": question,
    }


def clear_pending_clarification() -> None:
    st.session_state[PENDING_CLARIFICATION_KEY] = None


def set_last_result(result: dict[str, Any] | None) -> None:
    st.session_state[LAST_RESULT_KEY] = result


def get_last_result() -> dict[str, Any] | None:
    initialize_session_state()
    result = st.session_state[LAST_RESULT_KEY]
    return result if isinstance(result, dict) else None


def is_debug_enabled() -> bool:
    initialize_session_state()
    return is_debug_available() and bool(st.session_state[DEBUG_TOGGLE_KEY])


def is_debug_available() -> bool:
    value = os.getenv("STUDENT_RAG_SHOW_DEBUG", "false")
    return value.strip().lower() in {"1", "true", "yes", "on"}
