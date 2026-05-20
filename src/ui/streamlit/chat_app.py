from __future__ import annotations

import re
import time
from inspect import Parameter, signature
from collections.abc import Iterator
from typing import Any, Protocol

import streamlit as st

from .clarification_handler import build_pipeline_query, update_clarification_state
from .debug_renderer import render_debug_info
from .session_manager import (
    append_message,
    clear_chat_history,
    get_chat_history,
    initialize_session_state,
    is_debug_enabled,
    set_last_result,
)
from .source_renderer import render_sources
from .ui_components import (
    build_unhandled_error_result,
    render_chat_header_actions,
    render_followup_chat_input,
    render_header,
    render_initial_prompt_panel,
    render_status_notice,
    should_render_answer_body,
)


class AnswerClient(Protocol):
    def answer(self, query: str, include_debug: bool = False) -> dict[str, Any]:
        ...


CHAT_INPUT_KEY = "hcmue_chat_input"
INITIAL_QUESTION_KEY = CHAT_INPUT_KEY
SELECTED_SUGGESTION_KEY = "hcmue_selected_suggestion"
PENDING_RESPONSE_KEY = "hcmue_pending_response"


def render_chat_app(answer_client: AnswerClient, title: str, subtitle: str) -> None:
    initialize_session_state()

    chat_history = get_chat_history()
    initial_question = _session_text(INITIAL_QUESTION_KEY)
    selected_suggestion = _session_text(SELECTED_SUGGESTION_KEY)
    user_first_interaction = bool(initial_question or selected_suggestion)

    if not user_first_interaction and not chat_history:
        render_header(title=title, subtitle=subtitle, compact=False)
        render_initial_prompt_panel(
            initial_question_key=INITIAL_QUESTION_KEY,
            selected_suggestion_key=SELECTED_SUGGESTION_KEY,
        )
        st.stop()

    render_header(title=title, subtitle=subtitle, compact=False)
    st.markdown('<div class="ep-chat-mode-marker"></div>', unsafe_allow_html=True)
    if render_chat_header_actions():
        _clear_conversation()
        st.rerun()

    pending_responses = _pending_responses()
    active_pending_response = pending_responses[0] if pending_responses else None
    pending_status_slot = None

    for message in chat_history:
        _render_chat_message(message)
        if (
            active_pending_response
            and message.get("message_id") == active_pending_response.get("message_id")
        ):
            pending_status_slot = st.empty()

    first_interaction_message = initial_question or selected_suggestion
    if active_pending_response:
        st.markdown('<div class="ep-pending-response-marker"></div>', unsafe_allow_html=True)

    if first_interaction_message:
        _queue_user_message(first_interaction_message)
        st.rerun()

    if pending_status_slot is None:
        pending_status_slot = st.empty()

    followup_message = render_followup_chat_input(input_key=CHAT_INPUT_KEY)
    if followup_message:
        _queue_user_message(followup_message)
        st.rerun()

    if active_pending_response:
        with pending_status_slot.container():
            _handle_pending_response(active_pending_response, answer_client)
        st.rerun()


def _queue_user_message(user_query: str) -> None:
    display_query = user_query.strip()
    if not display_query:
        return

    message_id = f"msg_{time.time_ns()}"
    pipeline_query, _ = build_pipeline_query(display_query)
    append_message(
        "user",
        display_query,
        pipeline_query=pipeline_query,
        message_id=message_id,
    )

    pending_responses = _pending_responses()
    pending_responses.append({
        "message_id": message_id,
        "display_query": display_query,
        "pipeline_query": pipeline_query,
    })
    st.session_state[PENDING_RESPONSE_KEY] = pending_responses
    _clear_first_interaction()


def _handle_pending_response(
    pending_response: dict[str, str],
    answer_client: AnswerClient,
) -> None:
    pipeline_query = pending_response.get("pipeline_query") or pending_response.get("display_query") or ""
    result = _build_answer_result(pipeline_query, answer_client)

    with st.chat_message("assistant"):
        _render_assistant_result(content=result["answer"], result=result, stream=True)

    _insert_assistant_after_user(
        user_message_id=str(pending_response.get("message_id") or ""),
        content=result["answer"],
        result=result,
        pipeline_query=pipeline_query,
    )
    _remove_pending_response(str(pending_response.get("message_id") or ""))


def _insert_assistant_after_user(
    user_message_id: str,
    content: str,
    result: dict[str, Any],
    pipeline_query: str,
) -> None:
    assistant_message = {
        "role": "assistant",
        "content": content,
        "result": result,
        "pipeline_query": pipeline_query,
        "message_id": f"answer_{user_message_id}" if user_message_id else f"answer_{time.time_ns()}",
    }
    history = get_chat_history()
    for index, message in enumerate(history):
        if message.get("role") == "user" and message.get("message_id") == user_message_id:
            history.insert(index + 1, assistant_message)
            return

    history.append(assistant_message)


def _build_answer_result(
    pipeline_query: str,
    answer_client: AnswerClient,
) -> dict[str, Any]:
    with st.spinner("Đang tra cứu Sổ tay và đối chiếu nguồn phù hợp..."):
        try:
            result = _call_answer_client(answer_client, pipeline_query)
        except Exception as exc:
            result = build_unhandled_error_result(exc)

    result["answer"] = _clean_answer_for_chat(str(result.get("answer") or ""))
    update_clarification_state(pipeline_query, result)
    set_last_result(result)
    return result


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
    message_context = st.chat_message("user") if role == "user" else st.chat_message("assistant")
    with message_context:
        content = str(message.get("content") or "").strip()
        result = message.get("result") if isinstance(message.get("result"), dict) else None
        label = "Trợ lý" if role == "assistant" else "Bạn"
        st.markdown(
            f'<div class="ep-message-label ep-message-{role}">{label}</div>',
            unsafe_allow_html=True,
        )

        if role == "assistant":
            _render_assistant_result(content=content, result=result)
        else:
            st.text(content)


def _render_assistant_result(
    content: str,
    result: dict[str, Any] | None,
    stream: bool = False,
) -> None:
    render_status_notice(result)
    if should_render_answer_body(result):
        fallback = "Mình chưa có câu trả lời phù hợp cho câu hỏi này."
        if result and result.get("status") == "needs_clarification" and content:
            st.markdown(f"**{content}**")
        elif stream and content:
            st.write_stream(_stream_text(content))
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
        r"\n\s*Ngu(?:ồn|on)\s*:",
        cleaned,
        maxsplit=1,
    )[0]
    return cleaned.strip()


def _stream_text(text: str) -> Iterator[str]:
    tokens = re.split(r"(\s+)", text)
    for token in tokens:
        if token:
            yield token
            time.sleep(0.012)


def _session_text(key: str) -> str:
    value = st.session_state.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else ""


def _clear_first_interaction() -> None:
    st.session_state[INITIAL_QUESTION_KEY] = None
    st.session_state[SELECTED_SUGGESTION_KEY] = None


def _clear_conversation() -> None:
    clear_chat_history()
    _clear_first_interaction()
    st.session_state[PENDING_RESPONSE_KEY] = []


def _pending_responses() -> list[dict[str, str]]:
    pending = st.session_state.get(PENDING_RESPONSE_KEY)
    if isinstance(pending, list):
        return [item for item in pending if isinstance(item, dict)]
    if isinstance(pending, dict):
        return [pending]
    return []


def _remove_pending_response(message_id: str) -> None:
    st.session_state[PENDING_RESPONSE_KEY] = [
        pending
        for pending in _pending_responses()
        if pending.get("message_id") != message_id
    ]
