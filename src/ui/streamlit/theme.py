import streamlit as st


def apply_theme() -> None:
    st.markdown(
        """
        <style>
            .block-container {
                max-width: 980px;
                padding-top: 2rem;
                padding-bottom: 5rem;
            }

            .phase9-header {
                display: flex;
                gap: 1rem;
                align-items: center;
                padding: 0.25rem 0 1.25rem 0;
                border-bottom: 1px solid rgba(125, 135, 155, 0.18);
                margin-bottom: 1.25rem;
            }

            .phase9-avatar {
                width: 3rem;
                height: 3rem;
                border-radius: 8px;
                display: grid;
                place-items: center;
                background: #e9f2ff;
                color: #0f5ea8;
                font-size: 1.45rem;
            }

            .phase9-header h1 {
                font-size: 1.65rem;
                line-height: 1.2;
                margin: 0;
                letter-spacing: 0;
            }

            .phase9-header p {
                margin: 0.25rem 0 0 0;
                color: #5d6778;
                font-size: 0.98rem;
            }

            .phase9-empty-state {
                border: 1px solid rgba(45, 92, 140, 0.18);
                background: #f7fbff;
                border-radius: 8px;
                padding: 0.9rem 1rem;
                margin: 0.5rem 0 1rem 0;
                color: #233247;
            }

            .phase9-empty-state span {
                display: block;
                color: #687487;
                margin-top: 0.25rem;
            }

            .phase9-source-card {
                border: 1px solid rgba(120, 132, 150, 0.22);
                border-radius: 8px;
                padding: 0.85rem 0.95rem;
                margin: 0.55rem 0;
                background: #ffffff;
            }

            .phase9-source-title {
                font-weight: 700;
                color: #1d2b3d;
                margin-bottom: 0.45rem;
            }

            .phase9-source-meta {
                display: flex;
                flex-wrap: wrap;
                gap: 0.5rem;
                color: #536174;
                font-size: 0.9rem;
            }

            .phase9-source-meta span {
                background: #eef5fb;
                border-radius: 8px;
                padding: 0.15rem 0.45rem;
            }

            .phase9-source-id {
                margin-top: 0.45rem;
                color: #7a8493;
                font-size: 0.78rem;
                font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
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
