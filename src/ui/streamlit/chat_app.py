from __future__ import annotations

import re
from inspect import Parameter, signature
from typing import Any, Protocol

import streamlit as st

from .clarification_handler import build_pipeline_query, update_clarification_state
from .debug_renderer import render_debug_info
from .session_manager import (
    append_message,
    get_chat_history,
    initialize_session_state,
    is_debug_enabled,
    set_last_result,
)
from .source_renderer import render_sources
from .ui_components import (
    build_unhandled_error_result,
    render_empty_state,
    render_header,
    render_sidebar,
    render_status_notice,
    should_render_answer_body,
)


class AnswerClient(Protocol):
    def answer(self, query: str, include_debug: bool = False) -> dict[str, Any]:
        ...


def render_chat_app(answer_client: AnswerClient, title: str, subtitle: str) -> None:
    initialize_session_state()

    quick_query = render_sidebar()
    render_header(title=title, subtitle=subtitle)

    chat_history = get_chat_history()
    if not chat_history:
        render_empty_state()

    for message in chat_history:
        _render_chat_message(message)

    typed_query = st.chat_input("Nhập câu hỏi về Sổ tay sinh viên...")
    submitted_query = quick_query or typed_query

    if submitted_query:
        _handle_submit(submitted_query, answer_client)
        st.rerun()


def _handle_submit(user_query: str, answer_client: AnswerClient) -> None:
    display_query = user_query.strip()
    if not display_query:
        return

    pipeline_query, _ = build_pipeline_query(display_query)
    append_message("user", display_query, pipeline_query=pipeline_query)

    with st.spinner("Đang tìm thông tin trong sổ tay sinh viên..."):
        try:
            result = _call_answer_client(answer_client, pipeline_query)
        except Exception as exc:
            result = build_unhandled_error_result(exc)

    result["answer"] = _clean_answer_for_chat(str(result.get("answer") or ""))
    update_clarification_state(pipeline_query, result)
    set_last_result(result)
    append_message("assistant", result["answer"], result=result, pipeline_query=pipeline_query)


def _call_answer_client(answer_client: AnswerClient, query: str) -> dict[str, Any]:
    answer_method = answer_client.answer
    if _accepts_include_debug(answer_method):
        return answer_method(query, include_debug=is_debug_enabled())
    return answer_method(query)


def _accepts_include_debug(answer_method: Any) -> bool:
    try:
        parameters = signature(answer_method).parameters
    except (TypeError, ValueError):
        return False

    if "include_debug" in parameters:
        return True
    return any(parameter.kind == Parameter.VAR_KEYWORD for parameter in parameters.values())


def _render_chat_message(message: dict[str, Any]) -> None:
    role = str(message.get("role") or "assistant")
    avatar = "🎓" if role == "assistant" else "👤"
    with st.chat_message(role, avatar=avatar):
        content = str(message.get("content") or "").strip()
        result = message.get("result") if isinstance(message.get("result"), dict) else None

        render_status_notice(result)
        if should_render_answer_body(result):
            fallback = "Mình chưa có nội dung trả lời cho câu này."
            if result and result.get("status") == "needs_clarification" and content:
                st.markdown(f"**{content}**")
            else:
                st.markdown(content or fallback)

        if result:
            render_sources(
                citations=result.get("citations_used") or [],
                intent=result.get("intent"),
            )
            if is_debug_enabled():
                render_debug_info(result)


def _clean_answer_for_chat(answer: str) -> str:
    cleaned = answer.replace("structured_result", "").replace("tool_result", "")
    cleaned = re.split(
        r"\n\s*Ngu(?:ồn|on|á»“n|Ã¡Â»â€œn)\s*:",
        cleaned,
        maxsplit=1,
    )[0]
    return cleaned.strip()
