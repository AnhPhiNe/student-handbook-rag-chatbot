from __future__ import annotations

from html import escape
from typing import Any

import streamlit as st

from .session_manager import clear_chat_history, get_pending_clarification


SUGGESTED_QUESTION_GROUPS = {
    "Học tập": [
        "Điều kiện xét học bổng là gì?",
        "Có thể học vượt để ra trường sớm không?",
        "Một học phần có thể học lại mấy lần?",
    ],
    "Biểu mẫu": [
        "Muốn tạm nghỉ học cần mẫu đơn nào?",
        "Muốn quay lại học sau bảo lưu thì dùng đơn gì?",
        "Có mẫu đơn xin trợ cấp xã hội không?",
    ],
    "Liên hệ": [
        "Email phòng Đào tạo là gì?",
        "Website phòng CNTT là gì?",
        "Phòng CTCT-HSSV ở tầng mấy?",
    ],
    "Ký túc xá": [
        "Quy trình vào ký túc xá như thế nào?",
        "Ai được ưu tiên vào ký túc xá?",
        "Muốn xin vào KTX thì liên hệ phòng nào?",
    ],
    "Điểm số": [
        "Điểm rèn luyện 85 là loại gì?",
        "GPA 2.95 được xếp loại học lực gì?",
        "Điểm B+ quy đổi sang hệ 4 bao nhiêu?",
    ],
}

ERROR_STATUSES = {
    "api_error",
    "fallback",
    "gemini_disabled",
    "low_confidence",
    "out_of_domain",
    "rate_limited",
    "retrieval_error",
    "ui_error",
}
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


def render_execution_mode_controls(default_api_base_url: str) -> tuple[str, str]:
    st.sidebar.markdown("### Trợ lý Sổ tay")
    st.sidebar.caption("Hỏi đáp từ Sổ tay sinh viên HCMUE, có nguồn tham khảo.")
    st.sidebar.success("Đang dùng bản online")
    st.sidebar.info(
        "Nếu máy chủ trả lời tạm thời gián đoạn, ứng dụng sẽ báo lỗi để bạn thử lại sau."
    )

    st.sidebar.divider()
    return "API", default_api_base_url


def render_sidebar() -> str | None:
    pending = get_pending_clarification()
    if pending:
        st.sidebar.info("Mình đang chờ bạn làm rõ câu hỏi trong khung chat.")

    if st.sidebar.button("Xóa cuộc trò chuyện", use_container_width=True):
        clear_chat_history()
        st.rerun()

    return None


def render_header(title: str, subtitle: str) -> None:
    safe_title = escape(title)
    safe_subtitle = escape(subtitle)
    st.markdown(
        f"""
        <div class="phase9-header">
            <div class="phase9-avatar">ST</div>
            <div>
                <h1>{safe_title}</h1>
                <p>{safe_subtitle}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_empty_state() -> str | None:
    st.markdown(
        """
        <div class="phase9-empty-state">
            <strong>Bạn có thể hỏi về học vụ, biểu mẫu, phòng ban, ký túc xá hoặc điểm rèn luyện.</strong>
            <span>Chọn một câu hỏi bên dưới hoặc tự nhập câu hỏi của bạn.</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return render_suggested_questions()


def render_suggested_questions() -> str | None:
    st.markdown("### Câu hỏi thường gặp")
    selected_question = None

    for group_name, questions in SUGGESTED_QUESTION_GROUPS.items():
        st.markdown(f'<div class="phase9-question-group">{escape(group_name)}</div>', unsafe_allow_html=True)
        columns = st.columns(3)
        for index, question in enumerate(questions):
            with columns[index % len(columns)]:
                if st.button(
                    question,
                    key=f"suggested_question_{group_name}_{index}",
                    use_container_width=True,
                ):
                    selected_question = question

    return selected_question


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

    if status == "rate_limited":
        st.warning("Bản demo đang tạm giới hạn lượt hỏi. Bạn thử lại sau ít phút nhé.")
        return

    if status == "gemini_disabled":
        st.warning("Phần tạo câu trả lời đang tạm tắt để bảo vệ giới hạn sử dụng của bản demo.")
        return

    if status == "out_of_domain":
        st.info("Mình chỉ hỗ trợ các câu hỏi liên quan đến Sổ tay sinh viên HCMUE.")
        return

    if status == "api_error":
        if has_citations:
            st.warning(
                "Mình đã tìm thấy nguồn liên quan trong Sổ tay, nhưng phần diễn giải câu trả lời "
                "đang tạm thời gián đoạn. Bạn có thể xem nguồn tham khảo bên dưới."
            )
        else:
            st.warning("Hệ thống đang bận hoặc tạm thời gián đoạn. Bạn thử lại sau nhé.")
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
        st.warning("Mình chưa tìm được thông tin phù hợp do hệ thống tra cứu đang tạm thời gián đoạn.")
        return

    if status == "ui_error":
        st.warning("Giao diện đang gặp lỗi tạm thời. Bạn thử lại sau nhé.")


    if status in API_CLIENT_ERROR_STATUSES:
        message = str(result.get("answer") or "").strip()
        st.warning(message or "Hiện chưa kết nối được máy chủ trả lời. Bạn thử lại sau nhé.")
        return


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
