from __future__ import annotations

from html import escape
from typing import Any

import streamlit as st

from .session_manager import (
    DEBUG_TOGGLE_KEY,
    clear_chat_history,
    get_pending_clarification,
    is_debug_available,
)


QUICK_QUESTIONS = [
    "Email của khoa tiếng Anh là gì?",
    "Khoa công nghệ thông tin ở đâu?",
    "Khoa tiếng Anh có những ngành gì?",
    "Mẫu đơn xin học lại nằm ở đâu?",
    "Trường có bán bánh tráng trộn không?",
    "Điều kiện xét tốt nghiệp là gì?",
    "Điều kiện xét học bổng là gì?",
    "Học bổng KKHT có những mức nào?",
]

API_CLIENT_ERROR_STATUSES = {
    "api_connection_error",
    "api_timeout",
    "api_request_error",
    "api_http_error",
    "api_invalid_json",
}

BODYLESS_STATUS_MESSAGES = {
    "api_error",
    "fallback",
    "gemini_disabled",
    "low_confidence",
    "out_of_domain",
    "rate_limited",
    "retrieval_error",
    "ui_error",
    *API_CLIENT_ERROR_STATUSES,
}

def render_execution_mode_controls(
    default_api_base_url: str,
    default_execution_mode: str = "Local",
) -> tuple[str, str]:
    api_base_url = default_api_base_url
    default_mode = default_execution_mode.strip().upper()
    default_index = 1 if default_mode == "API" else 0
    execution_mode = "API" if default_index == 1 else "Local"

    with st.popover("Settings"):
        st.markdown(
            """
            <div class="ep-settings-title">
                <strong>Cài đặt</strong>
                <span>Ẩn các tuỳ chọn vận hành của chatbot.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        execution_mode = st.radio(
            "Execution mode",
            options=("Local", "API"),
            index=default_index,
            horizontal=True,
            help="Local dùng AnswerService trong app. API dùng máy chủ FastAPI.",
        )

        st.markdown(
            f"""
            <div class="ep-mode-status">
                <span>Mode đang dùng</span>
                <strong>{escape(execution_mode)}</strong>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if execution_mode == "API":
            api_base_url = (
                st.text_input(
                    "API base URL",
                    value=default_api_base_url,
                    help="Chỉ dùng khi chạy ở API mode.",
                ).strip()
                or default_api_base_url
            )

        if is_debug_available():
            st.toggle("Debug mode", key=DEBUG_TOGGLE_KEY)

        pending = get_pending_clarification()
        if pending:
            st.markdown(
                """
                <div class="ep-sidebar-note">
                    <strong>Cần làm rõ</strong>
                    <span>Trợ lý đang chờ bạn trả lời câu hỏi làm rõ trong khung chat.</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if st.button("Xóa cuộc trò chuyện", use_container_width=True):
            clear_chat_history()
            st.rerun()

    return execution_mode, api_base_url


def render_header(title: str, subtitle: str, compact: bool = False) -> None:
    safe_title = escape(title)
    safe_subtitle = escape(subtitle)
    if compact:
        st.markdown(
            f"""
            <section class="ep-chat-header">
                <div class="ep-mini-mark">H</div>
                <div>
                    <h1>{safe_title}</h1>
                    <p>{safe_subtitle}</p>
                </div>
            </section>
            """,
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f"""
        <section class="ep-landing">
            <div class="ep-assistant-mark" aria-hidden="true">
                <span></span><span></span><span></span><span></span>
                <span></span><span></span><span></span><span></span>
            </div>
            <h1>{safe_title}</h1>
            <p>{safe_subtitle}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_initial_prompt_panel(
    *,
    initial_question_key: str,
    selected_suggestion_key: str,
) -> None:
    st.markdown(
        """
        <div class="ep-guide-card">
            Bạn có thể hỏi về học bổng, học lại, điểm rèn luyện, biểu mẫu, email phòng ban...
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.pills(
        "Câu hỏi nhanh",
        options=QUICK_QUESTIONS,
        selection_mode="single",
        key=selected_suggestion_key,
        label_visibility="collapsed",
    )

    with st.container():
        st.chat_input(
            "Nhập câu hỏi về Sổ tay sinh viên HCMUE...",
            key=initial_question_key,
        )


def render_followup_chat_input(input_key: str | None = None) -> str | None:
    with st.container(key="hcmue_followup_input"):
        query = st.chat_input(
            "Hỏi tiếp về Sổ tay sinh viên HCMUE...",
            key=input_key,
        )
    return query.strip() if query and query.strip() else None


def render_chat_header_actions() -> bool:
    with st.container(
        key="hcmue_restart_row",
        horizontal=True,
        horizontal_alignment="right",
        vertical_alignment="center",
        gap=None,
    ):
        return st.button("Restart", type="tertiary", width="content")


def render_status_banner(result: dict[str, Any] | None) -> None:
    if not result:
        return

    status = str(result.get("status") or "")
    has_citations = bool(result.get("citations_used") or [])

    if status == "answered":
        return

    if status == "needs_clarification":
        _render_notice(
            "clarify",
            "Cần làm rõ thêm",
            "Mình cần thêm một chi tiết để tìm đúng phần trong Sổ tay.",
        )
        return

    if status == "out_of_domain":
        _render_notice(
            "info",
            "Ngoài phạm vi Sổ tay",
            "Mình chỉ hỗ trợ các câu hỏi liên quan đến Sổ tay sinh viên HCMUE.",
        )
        return

    if status in API_CLIENT_ERROR_STATUSES:
        _render_notice(
            "error",
            "Chưa kết nối được API",
            "Kiểm tra lại API base URL hoặc thử chuyển sang Local mode.",
        )
        return

    if status == "rate_limited":
        _render_notice(
            "warning",
            "Tạm giới hạn lượt hỏi",
            "Bạn thử lại sau ít phút nhé.",
        )
        return

    if status == "gemini_disabled":
        _render_notice(
            "warning",
            "Tạm tắt phần tạo câu trả lời",
            "Bạn vẫn có thể xem các nguồn liên quan nếu hệ thống tìm thấy.",
        )
        return

    if status == "api_error":
        body = (
            "Mình đã tìm thấy nguồn liên quan, nhưng phần diễn giải đang tạm gián đoạn."
            if has_citations
            else "Hệ thống đang bận hoặc tạm thời gián đoạn. Bạn thử lại sau nhé."
        )
        _render_notice("warning", "Chưa tạo được câu trả lời", body)
        return

    if status in {"fallback", "low_confidence"}:
        body = (
            "Mình tìm thấy một vài nguồn có thể liên quan, nhưng chưa đủ chắc để trả lời khẳng định."
            if has_citations
            else "Mình chưa tìm thấy thông tin đủ rõ trong Sổ tay sinh viên cho câu hỏi này."
        )
        _render_notice("warning", "Chưa đủ thông tin", body)
        return

    if status == "retrieval_error":
        _render_notice(
            "warning",
            "Tra cứu tạm gián đoạn",
            "Mình chưa tìm được thông tin phù hợp do hệ thống tra cứu đang gặp sự cố.",
        )
        return

    if status == "ui_error":
        _render_notice(
            "error",
            "Giao diện gặp lỗi",
            "Bạn thử gửi lại câu hỏi sau nhé.",
        )


def render_status_notice(result: dict[str, Any] | None) -> None:
    render_status_banner(result)


def should_render_answer_body(result: dict[str, Any] | None) -> bool:
    if not result:
        return True
    return str(result.get("status") or "") not in BODYLESS_STATUS_MESSAGES


def build_unhandled_error_result(error: Exception) -> dict[str, Any]:
    return {
        "answer": "Giao diện đang gặp lỗi tạm thời. Bạn thử lại sau nhé.",
        "status": "ui_error",
        "error_type": "ui_error",
        "error_message": str(error),
        "intent": None,
        "strategy": None,
        "retrieval_query": None,
        "llm_called": False,
        "used_cache": False,
        "clarification_needed": False,
        "citations_used": [],
        "citations": [],
        "context_used": "",
    }


def _render_notice(kind: str, title: str, body: str) -> None:
    st.markdown(
        f"""
        <div class="ep-status-card ep-status-{escape(kind)}">
            <strong>{escape(title)}</strong>
            <span>{escape(body)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
