import streamlit as st


def apply_theme() -> None:
    st.markdown(
        """
        <style>
            :root {
                --app-bg: #f6f8fb;
                --panel-bg: #ffffff;
                --text-main: #182230;
                --text-muted: #667085;
                --border-soft: #d9e2ec;
                --blue-main: #155eef;
                --blue-soft: #eef4ff;
                --green-soft: #eefaf3;
                --green-main: #087443;
            }

            .stApp {
                background: var(--app-bg);
            }

            .block-container {
                max-width: 1040px;
                padding-top: 1.4rem;
                padding-bottom: 5rem;
            }

            [data-testid="stSidebar"] {
                background: #ffffff;
                border-right: 1px solid var(--border-soft);
            }

            [data-testid="stSidebar"] h3 {
                color: var(--text-main);
                font-size: 1rem;
                letter-spacing: 0;
            }

            [data-testid="stSidebar"] .stButton > button {
                border: 1px solid var(--border-soft);
                background: #ffffff;
                color: var(--text-main);
                border-radius: 8px;
                min-height: 2.45rem;
                text-align: left;
                justify-content: flex-start;
                white-space: normal;
                line-height: 1.25;
                box-shadow: none;
            }

            [data-testid="stSidebar"] .stButton > button:hover {
                border-color: #9db7d8;
                background: #f8fbff;
                color: #0b4ea2;
            }

            [data-testid="stSidebar"] .stAlert {
                font-size: 0.9rem;
            }

            [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
                color: var(--text-muted);
            }

            .phase9-header {
                display: flex;
                gap: 1rem;
                align-items: center;
                padding: 1rem 0 1.15rem 0;
                border-bottom: 1px solid var(--border-soft);
                margin-bottom: 1.25rem;
            }

            .phase9-avatar {
                width: 3.1rem;
                height: 3.1rem;
                border-radius: 8px;
                display: grid;
                place-items: center;
                background: var(--blue-soft);
                color: #1849a9;
                font-size: 0.95rem;
                font-weight: 800;
                border: 1px solid #c7d7fe;
            }

            .phase9-header h1 {
                color: var(--text-main);
                font-size: 1.7rem;
                line-height: 1.2;
                margin: 0;
                letter-spacing: 0;
            }

            .phase9-header p {
                margin: 0.25rem 0 0 0;
                color: var(--text-muted);
                font-size: 0.98rem;
            }

            .phase9-empty-state {
                border: 1px solid #c7d7fe;
                background: #ffffff;
                border-radius: 8px;
                padding: 1rem 1.1rem;
                margin: 0.5rem 0 1.1rem 0;
                color: var(--text-main);
                box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
            }

            .phase9-empty-state span {
                display: block;
                color: var(--text-muted);
                margin-top: 0.25rem;
            }

            .phase9-question-group {
                margin: 1.1rem 0 0.45rem 0;
                color: var(--text-muted);
                font-size: 0.88rem;
                font-weight: 700;
                text-transform: uppercase;
            }

            .block-container div[data-testid="column"] .stButton > button {
                min-height: 3.4rem;
                border: 1px solid var(--border-soft);
                background: #ffffff;
                color: var(--text-main);
                border-radius: 8px;
                white-space: normal;
                line-height: 1.25;
                justify-content: flex-start;
                text-align: left;
                box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
            }

            .block-container div[data-testid="column"] .stButton > button:hover {
                border-color: #9db7d8;
                background: #f8fbff;
                color: #0b4ea2;
            }

            [data-testid="stChatMessage"] {
                background: #ffffff;
                border: 1px solid var(--border-soft);
                border-radius: 8px;
                padding: 0.35rem 0.5rem;
                box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
            }

            [data-testid="stChatMessage"] p {
                color: var(--text-main);
                line-height: 1.6;
            }

            .phase9-source-card {
                border: 1px solid var(--border-soft);
                border-radius: 8px;
                padding: 0.85rem 0.95rem;
                margin: 0.55rem 0;
                background: #fcfdff;
            }

            .phase9-source-title {
                font-weight: 700;
                color: var(--text-main);
                margin-bottom: 0.45rem;
            }

            .phase9-source-meta {
                display: flex;
                flex-wrap: wrap;
                gap: 0.5rem;
                color: var(--text-muted);
                font-size: 0.9rem;
            }

            .phase9-source-meta span {
                background: var(--blue-soft);
                color: #1849a9;
                border-radius: 8px;
                padding: 0.15rem 0.45rem;
            }

            div[data-testid="stAlert"] {
                border-radius: 8px;
                border: 1px solid var(--border-soft);
            }

            .stChatInputContainer textarea {
                border-radius: 8px;
            }

            button[kind="primary"], .stButton > button {
                border-radius: 8px;
            }

            @media (max-width: 720px) {
                .block-container {
                    padding-left: 1rem;
                    padding-right: 1rem;
                }

                .phase9-header {
                    align-items: flex-start;
                }

                .phase9-header h1 {
                    font-size: 1.35rem;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )
