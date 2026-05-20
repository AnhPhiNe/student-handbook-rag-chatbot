import os
from pathlib import Path
from typing import TYPE_CHECKING

import streamlit as st

from src.ui.streamlit.api_client import ChatApiClient
from src.ui.streamlit.chat_app import render_chat_app
from src.ui.streamlit.theme import apply_theme
from src.ui.streamlit.ui_components import render_execution_mode_controls
from src.common.env_loader import load_project_env

if TYPE_CHECKING:
    from src.services import AnswerService

load_project_env()


APP_TITLE = "Chatbot sổ tay sinh viên HCMUE"
APP_SUBTITLE = "Hỗ trợ tra cứu nhanh các thông tin cần thiết có trong sổ tay"
DEFAULT_CONFIG_PATH = Path("configs/phase8_answer_generation.yaml")
DEFAULT_API_BASE_URL = os.getenv("STUDENT_RAG_API_BASE_URL", "http://127.0.0.1:8000")


@st.cache_resource(show_spinner="Đang chuẩn bị trợ lý...")
def load_answer_service(config_path: str = str(DEFAULT_CONFIG_PATH)) -> "AnswerService":
    """Load the shared answer service once per Streamlit process."""
    from src.services import AnswerService

    return AnswerService(config_path=config_path)


@st.cache_resource(show_spinner=False)
def load_api_client(base_url: str) -> ChatApiClient:
    """Load an API client for the selected backend URL."""
    return ChatApiClient(base_url=base_url)


def main() -> None:
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="assets/chatbot.png",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    apply_theme()

    execution_mode, api_base_url = render_execution_mode_controls(
        default_api_base_url=DEFAULT_API_BASE_URL
    )
    answer_client = (
        load_api_client(api_base_url)
        if execution_mode == "API"
        else load_answer_service()
    )
    render_chat_app(
        answer_client=answer_client,
        title=APP_TITLE,
        subtitle=APP_SUBTITLE,
    )


if __name__ == "__main__":
    main()
