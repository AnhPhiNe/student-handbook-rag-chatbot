import streamlit as st


def apply_theme() -> None:
    st.markdown(
        """
        <style>
            :root {
                --ep-bg: #f7f8fb;
                --ep-panel: #ffffff;
                --ep-panel-soft: #fbfdff;
                --ep-user: #eef6ff;
                --ep-navy: #102a43;
                --ep-blue: #2563eb;
                --ep-blue-soft: #eaf2ff;
                --ep-text: #1f2937;
                --ep-muted: #667085;
                --ep-border: #e4eaf2;
                --ep-border-strong: #b9cbe5;
                --ep-danger: #b42318;
                --ep-shadow: 0 14px 36px rgba(16, 42, 67, 0.08);
                --ep-shadow-soft: 0 8px 20px rgba(16, 42, 67, 0.055);
            }

            html, body, [class*="css"] {
                font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                letter-spacing: 0;
            }

            .stApp {
                background:
                    radial-gradient(circle at 50% 0%, rgba(37, 99, 235, 0.06), transparent 28rem),
                    var(--ep-bg);
                color: var(--ep-text);
            }

            .block-container {
                max-width: 930px;
                padding: 1rem 1.25rem 5.75rem;
            }

            header[data-testid="stHeader"] {
                background: transparent;
            }

            footer {
                visibility: hidden;
            }

            [data-testid="stSidebar"],
            [data-testid="collapsedControl"] {
                display: none;
            }

            [data-testid="stPopover"] {
                position: fixed;
                top: 0.72rem;
                left: 1rem;
                z-index: 2147483647;
                width: fit-content !important;
                max-width: fit-content !important;
                pointer-events: auto;
            }

            [data-testid="stPopover"] button {
                width: auto !important;
                min-height: 2.25rem;
                padding-left: 0.9rem;
                padding-right: 0.9rem;
                border: 1px solid var(--ep-border);
                border-radius: 999px;
                background: rgba(255, 255, 255, 0.9);
                color: #3f4652;
                font-weight: 650;
                box-shadow: none;
                pointer-events: auto;
            }

            [data-testid="stPopover"] button:hover {
                border-color: #c7d6eb;
                background: #ffffff;
                color: var(--ep-blue);
            }

            .ep-settings-title {
                display: grid;
                gap: 0.18rem;
                margin-bottom: 0.8rem;
            }

            .ep-settings-title strong {
                color: var(--ep-navy);
                font-size: 0.98rem;
            }

            .ep-settings-title span {
                color: var(--ep-muted);
                font-size: 0.84rem;
                line-height: 1.45;
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
                background: var(--ep-navy);
                color: #ffffff;
                font-weight: 850;
                box-shadow: var(--ep-shadow-soft);
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
                color: var(--ep-blue);
                font-size: 0.9rem;
            }

            .ep-sidebar-note {
                display: grid;
                gap: 0.25rem;
                margin-bottom: 0.85rem;
                padding: 0.72rem 0.78rem;
                border: 1px solid #cfe0f5;
                border-radius: 12px;
                background: var(--ep-blue-soft);
            }

            .ep-sidebar-note strong {
                color: var(--ep-navy);
                font-size: 0.9rem;
            }

            .ep-sidebar-note span {
                color: #315675;
                font-size: 0.84rem;
                line-height: 1.45;
            }

            [data-testid="stSidebar"] .stButton > button {
                min-height: 2.55rem;
                border: 1px solid #ead4d1;
                border-radius: 12px;
                background: #ffffff;
                color: var(--ep-danger);
                font-weight: 720;
                box-shadow: none;
            }

            [data-testid="stSidebar"] .stButton > button:hover {
                border-color: #f0b6b1;
                background: #fff7f6;
                color: #912018;
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
                border-radius: 999px;
                color: var(--ep-muted);
            }

            .ep-assistant-mark {
                position: relative;
                width: 3.9rem;
                height: 3.9rem;
                margin-bottom: 1.55rem;
            }

            .ep-assistant-mark:before,
            .ep-assistant-mark:after {
                content: "";
                position: absolute;
                left: 50%;
                top: 50%;
                width: 3.15rem;
                height: 1px;
                background: #3f4652;
                transform-origin: center;
            }

            .ep-assistant-mark:after {
                transform: translate(-50%, -50%) rotate(90deg);
            }

            .ep-assistant-mark:before {
                transform: translate(-50%, -50%);
                box-shadow:
                    0 0 0 #3f4652,
                    0 0 0 #3f4652;
            }

            .ep-assistant-mark span {
                position: absolute;
                left: 50%;
                top: 50%;
                width: 0.72rem;
                height: 0.72rem;
                background: #3f4652;
                border-radius: 999px;
                transform: translate(-50%, -50%);
            }

            .ep-assistant-mark span:nth-child(1) { transform: translate(-50%, -50%) rotate(0deg) translateX(1.58rem); }
            .ep-assistant-mark span:nth-child(2) { transform: translate(-50%, -50%) rotate(45deg) translateX(1.58rem); }
            .ep-assistant-mark span:nth-child(3) { transform: translate(-50%, -50%) rotate(90deg) translateX(1.58rem); }
            .ep-assistant-mark span:nth-child(4) { transform: translate(-50%, -50%) rotate(135deg) translateX(1.58rem); }
            .ep-assistant-mark span:nth-child(5) { transform: translate(-50%, -50%) rotate(180deg) translateX(1.58rem); }
            .ep-assistant-mark span:nth-child(6) { transform: translate(-50%, -50%) rotate(225deg) translateX(1.58rem); }
            .ep-assistant-mark span:nth-child(7) { transform: translate(-50%, -50%) rotate(270deg) translateX(1.58rem); }
            .ep-assistant-mark span:nth-child(8) { transform: translate(-50%, -50%) rotate(315deg) translateX(1.58rem); }

            .ep-landing h1 {
                max-width: 780px;
                color: #3f4652;
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
                color: #465b70;
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
                border-radius: 999px !important;
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
                border-color: #c8d5e6 !important;
                box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.08) !important;
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
                border-radius: 999px !important;
                background: #eef3f8 !important;
                color: #6b7280 !important;
                box-shadow: none !important;
            }

            [data-testid="stChatInputSubmitButton"]:hover {
                background: var(--ep-blue-soft) !important;
                color: var(--ep-blue) !important;
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
                border: 1px solid var(--ep-border);
                background: rgba(255, 255, 255, 0.86);
                color: #26384d;
                border-radius: 999px;
                min-height: 2.18rem;
                font-weight: 560;
                box-shadow: none;
                transition: 140ms ease;
            }

            [data-testid="stPills"] button:hover {
                border-color: #9fc0f3;
                background: var(--ep-blue-soft);
                color: #1d4ed8;
                transform: translateY(-1px);
            }

            [data-testid="stPills"] button[aria-selected="true"] {
                border-color: #8bb8ff;
                background: #eef5ff;
                color: var(--ep-blue);
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
                box-shadow: var(--ep-shadow-soft);
            }

            [data-testid="stChatMessage"]:has(.ep-message-user) {
                background: var(--ep-user);
                border-color: #cfe4fb;
            }

            [data-testid="stChatMessage"]:has(.ep-message-assistant) {
                background: #ffffff;
            }

            .ep-message-label {
                color: var(--ep-muted);
                font-size: 0.78rem;
                font-weight: 780;
                margin-bottom: 0.2rem;
            }

            .ep-message-user {
                color: #1c5c9e;
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
                color: #173a5b;
            }

            .ep-status-card {
                display: grid;
                gap: 0.22rem;
                margin: 0.2rem 0 0.6rem;
                padding: 0.78rem 0.88rem;
                border-radius: 12px;
                border: 1px solid var(--ep-border);
                background: #f8fbff;
            }

            .ep-status-card strong {
                color: var(--ep-navy);
                font-size: 0.94rem;
            }

            .ep-status-card span {
                color: #425b72;
                font-size: 0.9rem;
                line-height: 1.5;
            }

            .ep-status-error {
                border-color: #f2c7c3;
                background: #fff8f7;
            }

            .ep-status-warning {
                border-color: #f2d7a0;
                background: #fffaf0;
            }

            .ep-status-clarify {
                border-color: #b8d6f7;
                background: #edf6ff;
            }

            .source-card {
                border: 1px solid var(--ep-border);
                border-radius: 12px;
                padding: 0.72rem 0.82rem;
                margin: 0.52rem 0;
                background: var(--ep-panel-soft);
                box-shadow: 0 5px 12px rgba(16, 42, 67, 0.035);
            }

            .source-title {
                font-weight: 760;
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
                background: var(--ep-blue-soft);
                color: #184d8f;
                border-radius: 999px;
                padding: 0.18rem 0.5rem;
                font-weight: 650;
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
                font-weight: 720;
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
                box-shadow: var(--ep-shadow-soft);
            }

            textarea,
            input,
            button[kind="primary"],
            .stButton > button {
                border-radius: 12px;
            }

            .stChatInputContainer textarea {
                border-radius: 999px;
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
