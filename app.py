import os
from pathlib import Path
from typing import TYPE_CHECKING

import streamlit as st

from src.ui.streamlit.api_client import ChatApiClient
from src.ui.streamlit.chat_app import render_chat_app
from src.ui.streamlit.theme import apply_theme
from src.ui.streamlit.ui_components import (
    render_execution_mode_controls,
    render_sidebar,
    render_footer,
)
from src.common.env_loader import load_project_env

if TYPE_CHECKING:
    from src.services import AnswerService

load_project_env()


APP_TITLE = "Chatbot sổ tay sinh viên HCMUE"
APP_SUBTITLE = "Hỗ trợ tra cứu nhanh các thông tin cần thiết có trong sổ tay"
DEFAULT_CONFIG_PATH = Path("configs/answer_generation.yaml")
DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_EXECUTION_MODE = "Local"


def get_runtime_setting(name: str, default: str) -> str:
    env_value = os.getenv(name)
    if env_value:
        return env_value

    try:
        secret_value = st.secrets.get(name)
    except Exception:
        secret_value = None

    return str(secret_value) if secret_value else default


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
        initial_sidebar_state="expanded",
    )
    apply_theme()

    render_sidebar()

    default_api_base_url = get_runtime_setting(
        "STUDENT_RAG_API_BASE_URL",
        DEFAULT_API_BASE_URL,
    )
    default_execution_mode = get_runtime_setting(
        "STUDENT_RAG_EXECUTION_MODE",
        DEFAULT_EXECUTION_MODE,
    )
    execution_mode, api_base_url = render_execution_mode_controls(
        default_api_base_url=default_api_base_url,
        default_execution_mode=default_execution_mode,
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

    render_footer("A Fee - Khoa Công nghệ thông tin")


if __name__ == "__main__":
    main()
