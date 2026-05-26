from __future__ import annotations

from html import escape
from typing import Any

import streamlit as st


CHUNK_TYPE_LABELS = {
    "form": "Biểu mẫu",
    "office_directory": "Phòng ban",
    "faculty_program_directory": "Khoa/ngành",
    "procedure": "Quy trình",
    "regulation": "Quy định",
    "structured_lookup": "Bảng tra cứu",
    "formula": "Cách tính",
    "tool": "Tra cứu tự động",
}


def render_sources(
    citations: list[dict[str, Any]] | None,
    intent: str | None = None,
) -> None:
    del intent
    visible_citations = _dedupe_citations(citations or [])
    if not visible_citations:
        return

    source_count = len(visible_citations)
    label = "📚 Xem nguồn trích dẫn từ Sổ tay" if source_count == 1 else f"📚 Xem nguồn trích dẫn ({source_count} tài liệu)"
    _, source_col, _ = st.columns([0.06, 0.88, 0.06])
    with source_col:
        with st.expander(label, expanded=False):
            for citation in visible_citations:
                _render_source_card(citation)


def summarize_citation(citation: dict[str, Any]) -> str:
    title = _citation_title(citation)
    pages = _format_pages(citation.get("source_pages"))
    chunk_label = _chunk_type_label(citation)

    details = []
    if pages:
        details.append(f"Trang: {pages}")
    if chunk_label:
        details.append(f"Loại: {chunk_label}")

    suffix = f" | {'; '.join(details)}" if details else ""
    return f"{title}{suffix}".strip()


def _render_source_card(citation: dict[str, Any]) -> None:
    title = escape(_citation_title(citation))
    pages = escape(_format_pages(citation.get("source_pages")) or "Không rõ")
    chunk_label = escape(_chunk_type_label(citation) or "Thông tin")

    st.markdown(
        f"""
        <div class="source-card">
            <div class="source-title">{title}</div>
            <div class="source-meta">
                <span>Trang: {pages}</span>
                <span>Loại: {chunk_label}</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _dedupe_citations(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()

    for citation in citations:
        if not isinstance(citation, dict):
            continue
        key = _citation_key(citation)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(citation)

    return deduped


def _citation_key(citation: dict[str, Any]) -> tuple[str, str, str, str]:
    chunk_id = str(citation.get("chunk_id") or "").strip()
    if chunk_id:
        return ("chunk_id", chunk_id, "", "")
    return (
        "metadata",
        _citation_title(citation).lower(),
        _format_pages(citation.get("source_pages")).lower(),
        str(citation.get("chunk_type") or "").strip().lower(),
    )


def _citation_title(citation: dict[str, Any]) -> str:
    title = (
        citation.get("article")
        or citation.get("title")
        or citation.get("form_name")
        or citation.get("unit_name")
        or citation.get("faculty_or_unit_name")
        or citation.get("procedure_name")
        or "Nguồn trong Sổ tay sinh viên"
    )
    return str(title).strip()


def _chunk_type_label(citation: dict[str, Any]) -> str:
    chunk_type = str(citation.get("chunk_type") or "").strip()
    return CHUNK_TYPE_LABELS.get(chunk_type, chunk_type)


def _format_pages(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list | tuple | set):
        pages = []
        for item in value:
            if isinstance(item, int):
                pages.append(str(item))
            elif isinstance(item, float) and item.is_integer():
                pages.append(str(int(item)))
            elif isinstance(item, str) and item.strip():
                pages.append(item.strip())
        return ", ".join(dict.fromkeys(pages))
    return ""
