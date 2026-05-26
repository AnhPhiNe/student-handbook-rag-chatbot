import streamlit as st


def apply_theme() -> None:
    st.markdown(
        """
        <style>
            :root {
                --ep-bg: #ffffff;
                --ep-panel: #ffffff;
                --ep-panel-soft: #fafafa;
                --ep-user: #fafafa;
                --ep-navy: #000000;
                --ep-blue: #000000;
                --ep-blue-soft: #fafafa;
                --ep-text: #000000;
                --ep-muted: #737373;
                --ep-border: #e5e5e5;
                --ep-border-strong: #d4d4d4;
                --ep-danger: #ff5f56;
                --ep-shadow: none;
                --ep-shadow-soft: none;
            }

            html, body, [class*="css"] {
                font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                letter-spacing: 0;
            }

            h1, h2, h3, h4, h5, h6, .ep-landing h1, .ep-chat-header h1 {
                font-family: "SF Pro Rounded", "Nunito", -apple-system, BlinkMacSystemFont, system-ui, sans-serif !important;
                font-weight: 500;
            }

            .stApp {
                background: var(--ep-bg);
                color: var(--ep-text);
            }

            .block-container {
                max-width: 720px;
                padding: 1rem 1.25rem 5.75rem;
            }

            header[data-testid="stHeader"] {
                background: transparent;
            }

            [data-testid="stSidebar"] {
                background: #ffffff;
                border-right: 1px solid var(--ep-border);
            }

            [data-testid="stSidebar"] > div:first-child {
                padding: 1rem 1rem 1.25rem;
            }

            [data-testid="stSidebar"] label,
            [data-testid="stSidebar"] p {
                color: var(--ep-text);
                letter-spacing: 0;
            }

            .ep-sidebar-brand {
                display: flex;
                align-items: center;
                gap: 0.72rem;
                padding: 0.15rem 0 1rem;
            }

            .ep-logo-mark,
            .ep-mini-mark {
                display: grid;
                place-items: center;
                border-radius: 12px;
                background: var(--ep-panel-soft);
                color: #000000;
                font-size: 20px;
                border: 1px solid var(--ep-border);
                box-shadow: none;
            }

            .ep-logo-mark {
                width: 2.35rem;
                height: 2.35rem;
            }

            .ep-mini-mark {
                width: 2.15rem;
                height: 2.15rem;
                flex: 0 0 auto;
            }

            .ep-sidebar-brand strong {
                display: block;
                color: var(--ep-navy);
                font-size: 1rem;
                line-height: 1.18;
            }

            .ep-sidebar-brand span {
                display: block;
                color: var(--ep-muted);
                font-size: 0.78rem;
                margin-top: 0.16rem;
            }

            .ep-mode-status {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 0.75rem;
                margin: 0.7rem 0 0.85rem;
                padding: 0.7rem 0.78rem;
                border: 1px solid var(--ep-border);
                border-radius: 12px;
                background: var(--ep-panel-soft);
            }

            .ep-mode-status span {
                color: var(--ep-muted);
                font-size: 0.84rem;
            }

            .ep-mode-status strong {
                color: var(--ep-navy);
                font-size: 0.9rem;
            }

            .ep-sidebar-note {
                display: grid;
                gap: 0.25rem;
                margin-bottom: 0.85rem;
                padding: 0.72rem 0.78rem;
                border: 1px solid var(--ep-border);
                border-radius: 12px;
                background: var(--ep-panel-soft);
            }

            .ep-sidebar-note strong {
                color: var(--ep-navy);
                font-size: 0.9rem;
            }

            .ep-sidebar-note span {
                color: var(--ep-muted);
                font-size: 0.84rem;
                line-height: 1.45;
            }

            [data-testid="stSidebar"] .stButton > button {
                min-height: 2.55rem;
                border: 1px solid var(--ep-border);
                border-radius: 9999px;
                background: #ffffff;
                color: var(--ep-text);
                font-weight: 500;
                box-shadow: none;
            }

            [data-testid="stSidebar"] .stButton > button:hover {
                border-color: var(--ep-border-strong);
                background: var(--ep-panel-soft);
                color: #000000;
            }

            .ep-landing {
                display: grid;
                justify-items: center;
                text-align: center;
                padding: clamp(3rem, 8vh, 5rem) 0 1rem;
            }

            .st-key-hcmue_restart_row {
                width: 100%;
                max-width: none;
                margin: -0.8rem 0 0.35rem;
            }

            .st-key-hcmue_restart_row button {
                min-height: 1.9rem;
                padding: 0.15rem 0.55rem;
                border-radius: 9999px;
                color: var(--ep-muted);
                border: 1px solid var(--ep-border);
            }

            .ep-assistant-mark {
                font-size: 64px;
                line-height: 1;
                margin-bottom: 16px;
            }

            .ep-landing h1 {
                max-width: 780px;
                color: #000000;
                font-size: clamp(2rem, 4.6vw, 3.05rem);
                line-height: 1.08;
                margin: 0;
                letter-spacing: 0;
            }

            .ep-landing p {
                max-width: 650px;
                color: var(--ep-muted);
                font-size: 1rem;
                line-height: 1.58;
                margin: 0.72rem 0 0;
            }

            .ep-chat-header {
                display: flex;
                align-items: center;
                gap: 0.75rem;
                padding: 0.65rem 0 0.35rem;
                margin-bottom: 0.7rem;
            }

            .ep-chat-header h1 {
                color: var(--ep-navy);
                font-size: 1.18rem;
                line-height: 1.2;
                margin: 0;
                letter-spacing: 0;
            }

            .ep-chat-header p {
                color: var(--ep-muted);
                font-size: 0.86rem;
                line-height: 1.4;
                margin: 0.14rem 0 0;
            }

            .ep-guide-card {
                max-width: 760px;
                margin: 0.35rem auto 0.7rem;
                padding: 0;
                border: 0;
                border-radius: 0;
                background: transparent;
                color: var(--ep-muted);
                line-height: 1.55;
                text-align: center;
            }

            [data-testid="stChatInput"] {
                position: relative;
                width: calc(100% + 1.36rem) !important;
                max-width: calc(100% + 1.36rem) !important;
                margin: 1.35rem -0.68rem 0 !important;
                background: transparent !important;
                border: 0 !important;
                box-sizing: border-box !important;
                box-shadow: none !important;
                padding: 0 !important;
            }

            [data-testid="stChatInput"]:has(textarea:disabled),
            [data-testid="stChatInput"]:has(textarea[disabled]),
            [data-testid="stChatInput"]:has(textarea[aria-disabled="true"]) {
                display: none !important;
            }

            .stApp:has(.ep-chat-mode-marker) [data-testid="stChatInput"]:has(textarea[placeholder^="Nhập câu hỏi"]) {
                display: none !important;
            }

            .stApp:has(.ep-pending-response-marker) [data-testid="stChatInput"] {
                display: none !important;
            }

            .stApp:has(.ep-pending-response-marker) .st-key-hcmue_followup_input [data-testid="stChatInput"] {
                display: block !important;
            }

            .st-key-hcmue_followup_input [data-testid="stChatInput"]:has(~ [data-testid="stChatInput"]) {
                display: none !important;
            }

            [data-testid="stChatInput"] > div {
                width: 100% !important;
                max-width: 100% !important;
                background: transparent !important;
                border: 0 !important;
                box-sizing: border-box !important;
                box-shadow: none !important;
                padding: 0 !important;
            }

            [data-testid="stChatInput"] > div > div,
            [data-testid="stChatInput"] [data-baseweb="textarea"],
            [data-testid="stChatInput"] [data-baseweb="base-input"],
            [data-testid="stChatInput"] div:has(> textarea) {
                width: 100% !important;
                max-width: 100% !important;
                background: transparent !important;
                border: 0 !important;
                box-sizing: border-box !important;
                box-shadow: none !important;
                padding: 0 !important;
            }

            [data-testid="stChatInput"] textarea {
                width: 100% !important;
                max-width: 100% !important;
                box-sizing: border-box !important;
                min-height: 2.75rem !important;
                border-radius: 9999px !important;
                border: 1px solid var(--ep-border) !important;
                background: #ffffff !important;
                box-shadow: none !important;
                color: var(--ep-text);
                padding-left: 1.05rem !important;
                padding-right: 3.25rem !important;
                padding-top: 0.72rem !important;
                padding-bottom: 0.72rem !important;
                line-height: 1.35 !important;
            }

            [data-testid="stChatInput"] textarea:focus {
                border-color: #000000 !important;
                box-shadow: 0 0 0 1px #000000 !important;
            }

            [data-testid="stChatInputSubmitButton"] {
                position: absolute !important;
                top: 50% !important;
                right: 0.7rem !important;
                width: 2.05rem !important;
                height: 2.05rem !important;
                min-height: 2.05rem !important;
                padding: 0 !important;
                transform: translateY(-50%);
                border: 0 !important;
                border-radius: 9999px !important;
                background: #fafafa !important;
                color: #a3a3a3 !important;
                box-shadow: none !important;
            }

            [data-testid="stChatInputSubmitButton"]:hover {
                background: #000000 !important;
                color: #ffffff !important;
            }

            [data-testid="stChatFloatingInputContainer"] {
                background: transparent;
                border-top: 0;
            }

            [data-testid="stPills"] {
                max-width: 780px;
                margin: 0.15rem auto 1rem;
            }

            [data-testid="stPills"] > label {
                display: none;
            }

            [data-testid="stPills"] button {
                border: none;
                background: var(--ep-panel-soft);
                color: var(--ep-text);
                border-radius: 9999px;
                min-height: 2.18rem;
                font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace !important;
                font-size: 14px;
                font-weight: 400;
                box-shadow: none;
                transition: 140ms ease;
            }

            [data-testid="stPills"] button:hover {
                background: #ffffff;
                color: #000000;
                border: 1px solid #000000;
            }

            [data-testid="stPills"] button[aria-selected="true"] {
                background: #000000;
                color: #ffffff;
            }

            .ep-followup-strip {
                max-width: 780px;
                margin: 0 auto 0.45rem;
                color: var(--ep-muted);
                font-size: 0.84rem;
                font-weight: 740;
            }

            .ep-followup-strip {
                margin-top: 0.25rem;
            }

            [data-testid="stChatMessage"] {
                border: 1px solid var(--ep-border);
                border-radius: 12px;
                padding: 0.55rem 0.68rem;
                margin: 0.46rem 0;
                background: #ffffff;
                box-shadow: none;
            }

            [data-testid="stChatMessage"]:has(.ep-message-user) {
                background: var(--ep-user);
                border-color: var(--ep-border);
            }

            [data-testid="stChatMessage"]:has(.ep-message-assistant) {
                background: #ffffff;
            }

            .ep-message-label {
                color: var(--ep-muted);
                font-size: 0.78rem;
                font-weight: 500;
                margin-bottom: 0.2rem;
            }

            .ep-message-user {
                color: var(--ep-muted);
            }

            .ep-message-assistant {
                color: var(--ep-navy);
            }

            .ep-chat-bubble {
                color: var(--ep-text);
                line-height: 1.66;
                white-space: pre-wrap;
                overflow-wrap: anywhere;
            }

            .ep-chat-bubble-user {
                color: #525252;
            }

            .ep-status-card {
                display: grid;
                gap: 0.22rem;
                margin: 0.2rem 0 0.6rem;
                padding: 0.78rem 0.88rem;
                border-radius: 12px;
                border: 1px solid var(--ep-border);
                background: var(--ep-panel-soft);
            }

            .ep-status-card strong {
                color: var(--ep-navy);
                font-size: 0.94rem;
            }

            .ep-status-card span {
                color: var(--ep-muted);
                font-size: 0.9rem;
                line-height: 1.5;
            }

            .ep-status-error {
                border-color: #ff5f56;
                background: #fffafa;
            }

            .ep-status-warning {
                border-color: #ffbd2e;
                background: #fffdfa;
            }

            .ep-status-clarify {
                border-color: var(--ep-border);
                background: var(--ep-panel-soft);
            }

            .source-card {
                border: 1px solid var(--ep-border);
                border-radius: 12px;
                padding: 0.72rem 0.82rem;
                margin: 0.52rem 0;
                background: var(--ep-panel-soft);
                box-shadow: none;
            }

            .source-title {
                font-weight: 500;
                color: var(--ep-text);
                margin-bottom: 0.42rem;
                line-height: 1.35;
            }

            .source-meta {
                display: flex;
                flex-wrap: wrap;
                gap: 0.42rem;
                color: var(--ep-muted);
                font-size: 0.82rem;
            }

            .source-meta span {
                background: #ffffff;
                color: #525252;
                border: 1px solid var(--ep-border);
                border-radius: 9999px;
                padding: 0.18rem 0.5rem;
                font-weight: 500;
            }

            .ep-debug-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 0.5rem;
            }

            .ep-debug-grid div {
                display: grid;
                gap: 0.16rem;
                padding: 0.55rem 0.62rem;
                border: 1px solid var(--ep-border);
                border-radius: 12px;
                background: var(--ep-panel-soft);
            }

            .ep-debug-grid span {
                color: var(--ep-muted);
                font-size: 0.76rem;
                font-weight: 500;
            }

            .ep-debug-grid strong {
                color: var(--ep-text);
                font-size: 0.86rem;
                overflow-wrap: anywhere;
            }

            div[data-testid="stAlert"],
            [data-testid="stExpander"] {
                border-radius: 12px;
                border: 1px solid var(--ep-border);
                box-shadow: none;
            }

            textarea,
            input,
            button[kind="primary"],
            .stButton > button {
                border-radius: 9999px; /* All primary interactive elements are pills */
            }

            .stChatInputContainer textarea {
                border-radius: 9999px;
            }

            .ep-footer {
                position: fixed;
                bottom: 0;
                left: 0;
                right: 0;
                text-align: center;
                padding: 0.5rem;
                background: rgba(255, 255, 255, 0.9);
                backdrop-filter: blur(4px);
                color: var(--ep-muted);
                font-size: 0.8rem;
                border-top: 1px solid var(--ep-border);
                z-index: 1000;
            }

            @media (max-width: 760px) {
                .block-container {
                    padding-left: 0.85rem;
                    padding-right: 0.85rem;
                }

                .ep-landing {
                    padding-top: 2.5rem;
                }

                .ep-chat-header {
                    align-items: flex-start;
                }

                [data-testid="stPills"] button {
                    min-height: 2.35rem;
                }

                .ep-debug-grid {
                    grid-template-columns: 1fr;
                }
            }
        </style>
        """,
        unsafe_allow_html=True,
    )
