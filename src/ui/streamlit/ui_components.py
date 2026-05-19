from __future__ import annotations

from html import escape
from typing import Any

import streamlit as st

from .session_manager import (
    DEBUG_TOGGLE_KEY,
    clear_chat_history,
    get_pending_clarification,
)


QUICK_QUESTIONS = [
    "Điều kiện học bổng",
    "Mẫu đơn tạm nghỉ học",
    "Email phòng Đào tạo",
    "Quy trình vào KTX",
    "Điểm rèn luyện 85 là loại gì",
]

ERROR_STATUSES = {"api_error", "fallback", "low_confidence", "retrieval_error", "ui_error"}
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
    "low_confidence",
    "retrieval_error",
    "ui_error",
    *API_CLIENT_ERROR_STATUSES,
}


def render_execution_mode_controls(default_api_base_url: str) -> tuple[str, str]:
    st.sidebar.markdown("### Execution")
    execution_mode = st.sidebar.radio(
        "Execution mode",
        options=("Local", "API"),
        horizontal=True,
    )

    api_base_url = default_api_base_url
    if execution_mode == "API":
        api_base_url = st.sidebar.text_input(
            "API base URL",
            value=default_api_base_url,
        ).strip() or default_api_base_url

    st.sidebar.divider()
    return execution_mode, api_base_url


def render_sidebar() -> str | None:
    st.sidebar.markdown("### HCMUE Assistant")
    st.sidebar.caption("Tra cứu nhanh thông tin trong Sổ tay sinh viên.")

    st.sidebar.checkbox("Show debug info", key=DEBUG_TOGGLE_KEY)
    pending = get_pending_clarification()
    if pending:
        st.sidebar.info("Đang chờ bạn trả lời câu hỏi làm rõ trong khung chat.")

    if st.sidebar.button("Xóa hội thoại", use_container_width=True):
        clear_chat_history()
        st.rerun()

    st.sidebar.divider()
    st.sidebar.markdown("### Câu hỏi nhanh")

    selected_question = None
    for question in QUICK_QUESTIONS:
        if st.sidebar.button(question, use_container_width=True):
            selected_question = question

    st.sidebar.divider()
    st.sidebar.caption("Phase 9 · Streamlit Chat UI")
    return selected_question


def render_header(title: str, subtitle: str) -> None:
    safe_title = escape(title)
    safe_subtitle = escape(subtitle)
    st.markdown(
        f"""
        <div class="phase9-header">
            <div class="phase9-avatar">🎓</div>
            <div>
                <h1>{safe_title}</h1>
                <p>{safe_subtitle}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state() -> None:
    st.markdown(
        """
        <div class="phase9-empty-state">
            <strong>Bạn có thể hỏi về học bổng, biểu mẫu, phòng ban, KTX hoặc điểm rèn luyện.</strong>
            <span>Ví dụ: “Mẫu đơn tạm nghỉ học nằm ở đâu?”</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_status_banner(result: dict[str, Any] | None) -> None:
    if not result:
        return

    status = str(result.get("status") or "")
    has_citations = bool(result.get("citations_used") or [])

    if status == "answered":
        return

    if status == "needs_clarification":
        st.info("Mình cần bạn làm rõ thêm một chút để tìm đúng thông tin.")
        return

    if status == "api_error":
        if has_citations:
            st.warning(
                "Đã tìm thấy thông tin liên quan trong sổ tay, nhưng hiện tại chưa thể "
                "gọi Gemini để diễn giải câu trả lời. Bạn có thể xem nguồn tham khảo bên dưới."
            )
        else:
            st.warning("Hệ thống đang gặp lỗi tạm thời khi gọi Gemini. Bạn thử lại sau nhé.")
        return

    if status in {"fallback", "low_confidence"}:
        if has_citations:
            st.warning(
                "Mình tìm thấy một vài nguồn có thể liên quan, nhưng chưa đủ chắc để trả lời "
                "khẳng định. Bạn có thể xem nguồn bên dưới hoặc hỏi cụ thể hơn."
            )
        else:
            st.warning("Mình chưa tìm thấy thông tin đủ rõ trong Sổ tay sinh viên cho câu hỏi này.")
        return

    if status == "retrieval_error":
        st.warning("Mình chưa tìm thấy thông tin phù hợp do bước tra cứu dữ liệu đang gặp lỗi tạm thời.")
        return

    if status == "ui_error":
        st.warning("Hệ thống giao diện gặp lỗi tạm thời. Bạn thử lại sau nhé.")


    if status in API_CLIENT_ERROR_STATUSES:
        message = str(result.get("answer") or "").strip()
        st.warning(message or "Không kết nối được API backend. Bạn thử lại sau nhé.")
        return


def render_status_notice(result: dict[str, Any] | None) -> None:
    render_status_banner(result)


def should_render_answer_body(result: dict[str, Any] | None) -> bool:
    if not result:
        return True
    return str(result.get("status") or "") not in BODYLESS_STATUS_MESSAGES


def build_unhandled_error_result(error: Exception) -> dict[str, Any]:
    return {
        "answer": "Hệ thống giao diện gặp lỗi tạm thời. Bạn thử lại sau nhé.",
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
