from __future__ import annotations

from html import escape
from typing import Any

import streamlit as st

from .session_manager import (
    DEBUG_TOGGLE_KEY,
    clear_chat_history,
    get_pending_clarification,
    is_debug_available,
    get_chat_history,
)
import json

QUICK_QUESTIONS = [
    "🎓 Điều kiện để xét Học bổng KKHT?",
    "📚 Muốn xin bảng điểm thì đến phòng nào?",
    "📝 Quy định về thời gian đào tạo tối đa?",
    "🏛️ Trường hợp nào bị cảnh cáo học vụ?",
    "📧 Trường hợp nào bị buộc thôi học?",
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

    with st.sidebar:
        st.divider()
        st.markdown(
            """
            <div class="ep-settings-title" style="margin-bottom: 8px;">
                <strong>⚙️ Cài đặt hệ thống</strong>
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
            <h1><span style="color:var(--ep-coral)">✳</span> Trợ lý Sổ tay sinh viên</h1>
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
            Hỏi mình bất cứ điều gì về Quy chế, Điểm rèn luyện, hoặc Học bổng nhé.
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
            "💡 Nhập câu hỏi (VD: Điều kiện xét học bổng Khuyến khích học tập là gì?)...",
            key=initial_question_key,
        )


def render_followup_chat_input(input_key: str | None = None) -> str | None:
    with st.container(key="hcmue_followup_input"):
        query = st.chat_input(
            "💬 Hỏi thêm hoặc yêu cầu làm rõ...",
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
        return st.button("🔄 Trò chuyện mới", type="tertiary", width="content")


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
            "Câu hỏi hơi rộng quá, bạn cho mình xin thêm chút chi tiết nhé!",
        )
        return

    if status == "out_of_domain":
        _render_notice(
            "info",
            "Câu hỏi ngoài lề",
            "Hmm... Mình chỉ được huấn luyện để trả lời các quy định trong Sổ tay sinh viên HCMUE thôi.",
        )
        return

    if status in API_CLIENT_ERROR_STATUSES:
        _render_notice(
            "error",
            "Úi, không kết nối được máy chủ",
            "Bạn kiểm tra lại API base URL hoặc thử chuyển sang Local mode xem sao nhé.",
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
            "Mình đã tìm thấy tài liệu liên quan bên dưới, nhưng phần tóm tắt tự động đang bị gián đoạn 🥲 Bạn đọc tạm các nguồn nhé!"
            if has_citations
            else "Úi, máy chủ đang bận chút xíu. Bạn đợi một lát rồi hỏi lại nha."
        )
        _render_notice("warning", "Gián đoạn kết nối", body)
        return

    if status in {"fallback", "low_confidence"}:
        body = (
            "Mình tìm thấy vài đoạn tài liệu có vẻ liên quan ở dưới, nhưng chưa dám khẳng định chắc chắn 100%."
            if has_citations
            else "Mình lật nát cuốn Sổ tay rồi nhưng chưa thấy thông tin nào khớp với câu hỏi này. Bạn thử dùng từ khóa khác xem sao!"
        )
        _render_notice("warning", "Chưa tìm thấy thông tin chính xác", body)
        return

    if status == "retrieval_error":
        _render_notice(
            "warning",
            "Lỗi tìm kiếm",
            "Hệ thống tìm kiếm tài liệu đang gặp sự cố nhỏ. Bạn kiên nhẫn thử lại sau nhé.",
        )
        return

    if status == "ui_error":
        _render_notice(
            "error",
            "Úi, giao diện bị vấp mạng 🥲",
            "Có lỗi bất ngờ xảy ra ở trình duyệt. Bạn tải lại trang (F5) hoặc gửi lại câu hỏi nha.",
        )


def render_status_notice(result: dict[str, Any] | None) -> None:
    render_status_banner(result)


def should_render_answer_body(result: dict[str, Any] | None) -> bool:
    if not result:
        return True
    return str(result.get("status") or "") not in BODYLESS_STATUS_MESSAGES


def build_unhandled_error_result(error: Exception) -> dict[str, Any]:
    return {
        "answer": "Giao diện đang gặp sự cố bất ngờ. Bạn thử tải lại trang nhé.",
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


import base64
from pathlib import Path

def get_image_base64(path: str) -> str:
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        return ""

def render_sidebar() -> None:
    logo_base64 = get_image_base64("assets/logo_hcmue.png")
    logo_img_tag = f'<img src="data:image/png;base64,{logo_base64}" style="width:100%; height:100%; object-fit:contain;" />' if logo_base64 else '🦉'
    
    with st.sidebar:
        st.markdown(
            f"""
            <div class="ep-sidebar-brand">
                <div class="ep-logo-mark">{logo_img_tag}</div>
                <div>
                    <strong>Sổ tay HCMUE</strong>
                    <span>Phiên bản 2024-2025</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            "Chatbot hỗ trợ giải đáp quy chế, học bổng, điểm rèn luyện... Dữ liệu được trích xuất từ Sổ tay sinh viên HCMUE chính thức."
        )

        st.divider()
        st.markdown("**Tiện ích**")
        
        chat_history = get_chat_history()
        if chat_history:
            # Drop un-serializable objects from history before exporting
            export_list = []
            for msg in chat_history:
                export_list.append({
                    "role": msg.get("role"),
                    "content": msg.get("content"),
                    "message_id": msg.get("message_id"),
                })
            export_data = json.dumps(export_list, ensure_ascii=False, indent=2)
            st.download_button(
                label="📥 Tải xuống lịch sử",
                data=export_data,
                file_name="hcmue_chat_history.json",
                mime="application/json",
                use_container_width=True,
            )

        if st.button("🗑️ Xóa lịch sử", use_container_width=True):
            clear_chat_history()
            st.rerun()

        st.divider()
        st.markdown("**Liên kết hữu ích**")
        st.markdown("[📕 **Sổ tay sinh viên HCMUE (Bản gốc)**](https://ctsv.hcmue.edu.vn/vi/thu-vien/van-ban/hcmue/so-tay-sinh-vien-hcmue/so-tay-sinh-vien-truong-dai-hoc-su-pham-thanh-pho-ho-chi-minh-2024-2025)")
        st.markdown("[🌐 Trang chủ HCMUE](https://hcmue.edu.vn)")
        st.markdown("[📧 Phòng Công tác sinh viên](https://ctsv.hcmue.edu.vn)")


def render_footer(author_name: str) -> None:
    st.markdown(
        f"""
        <div class="ep-footer">
            Được phát triển với ❤️ bởi <strong>{escape(author_name)}</strong> - Nguồn dữ liệu: Sổ tay sinh viên HCMUE 2024-2025
        </div>
        """,
        unsafe_allow_html=True,
    )
