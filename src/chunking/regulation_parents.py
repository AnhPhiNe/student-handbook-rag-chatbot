"""Build full parent documents (one per regulation article) from parsed sections.

Retrieval children are not built here: scripts/build_child_parent_index.py splits
these parents into the narrative chunks that are embedded.
"""

import re
from typing import Any

from .regulation_highlight_extractor import (
    extract_regulation_highlights,
    highlight_metadata_payload,
)
from .regulation_table_extractor import (
    extract_regulation_tables,
    format_tables_for_parent,
    table_metadata_payload,
)
from .text_utils import join_non_empty, source_page_range


BOUNDARY_STOP_MARKERS = (
    "THÔNG TIN TRỌNG TÂM",
    "THONG TIN TRONG TAM",
    "ĐÃ TÁCH TỪ NGUỒN",
    "DA TACH TU NGUON",
    "Nơi nhận:",
    "CÁC HƯỚNG DẪN LIÊN QUAN",
    "CAC HUONG DAN LIEN QUAN",
    "Phần 3\nCÁC QUY TRÌNH",
    "PHẦN 3\nCÁC QUY TRÌNH",
    "CÁC QUY TRÌNH, BIỂU MẪU",
    "QUY TRÌNH XÉT SINH VIÊN VÀO Ở KÝ TÚC XÁ",
    "THÔNG BÁO\nV/v thực hiện",
    "THÔNG BÁO\nVề việc thực hiện",
    "Sinh viên có thể quét mã QR",
    "Sinh viên tải mẫu đơn tại",
)
LOW_VALUE_LINK_PATTERNS = (
    r"\([^)]*(?:mã\s*qr|qr|https?://|đường\s+dẫn|link)[^)]*\)",
    r"https?://\S+",
    r"\b\S*bit\.ly/\S+",
    r"\b\S*forms\.gle/\S+",
    r"\b\S*google\.com/forms\S*",
    r"\s*(?:hoặc\s+)?quét\s+mã\s*qr\b.*$",
    r"\s*(?:hoặc\s+)?truy\s+cập\s+(?:vào\s+)?(?:đường\s+dẫn|link)\b.*$",
    r"\s*xem\s+trong\s+(?:đường\s+dẫn|link)\b.*$",
    r"\s*(?:thông\s+qua|qua|trong)?\s*(?:đường\s+)?dẫn\s+hoặc\s+mã\s*qr\b.*$",
)
LOW_VALUE_LINK_TERMS = (
    "mã qr",
    " qr",
    "http://",
    "https://",
    "bit.ly",
    "forms.gle",
    "google.com/forms",
    "đường dẫn",
)


def build_section_content(section: dict[str, Any], content: str) -> str:
    """Render section metadata and source text into retrievable content."""

    raw_title = str(section.get("title") or "").strip()
    article = str(section.get("article") or "").strip()
    clean_title = raw_title
    if article and clean_title.lower().startswith(article.lower()):
        clean_title = clean_title[len(article) :].lstrip(" .:-")

    return join_non_empty(
        [
            f"Tài liệu: {section.get('document_title') or ''}",
            f"Phần: {section.get('part') or ''}",
            f"Chương: {section.get('chapter') or ''}",
            f"Điều: {article}" if article else "",
            f"Tiêu đề: {clean_title}" if clean_title else "",
            "Nội dung:",
            content,
        ]
    )


def clean_regulation_source_content(content: str) -> str:
    """Remove generated notes, layout lines, and leaked appendix documents."""

    cleaned = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    upper_cleaned = cleaned.upper()
    stop_positions = [
        upper_cleaned.find(marker.upper())
        for marker in BOUNDARY_STOP_MARKERS
        if upper_cleaned.find(marker.upper()) > 0
    ]
    if stop_positions:
        cleaned = cleaned[: min(stop_positions)].strip()

    lines = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if re.fullmatch(
            r"\d*\s*SỔ TAY SINH VIÊN KHÓA\s+\d+(?:\s+\d+)?",
            stripped,
            flags=re.IGNORECASE,
        ):
            continue
        stripped = _strip_low_value_link_text(stripped)
        if stripped:
            lines.append(stripped)
    return "\n".join(lines).strip()


def _strip_low_value_link_text(text: str) -> str:
    stripped = text.strip()
    for pattern in LOW_VALUE_LINK_PATTERNS:
        stripped = re.sub(pattern, "", stripped, flags=re.IGNORECASE).strip()
    stripped = re.sub(r"\s+([,.;:])", r"\1", stripped)
    stripped = re.sub(r"\s{2,}", " ", stripped).strip()
    stripped = re.sub(r"\(\s*\)", "", stripped).strip()
    if any(term in stripped.lower() for term in LOW_VALUE_LINK_TERMS):
        return ""
    return stripped


def build_parent_doc_content(
    section: dict[str, Any],
    content: str,
    tables: list[dict[str, Any]],
    highlights: list[dict[str, Any]] | None = None,
) -> str:
    """Build parent context with normalized tables and extracted highlights."""

    normalized_tables = format_tables_for_parent(tables)
    normalized_highlights = format_highlights_for_parent(highlights or [])
    return join_non_empty(
        [
            build_section_content(section, content),
            normalized_tables,
            normalized_highlights,
        ]
    )


def format_highlights_for_parent(highlights: list[dict[str, Any]]) -> str:
    """Render extracted highlights as a compact parent-document appendix."""

    if not highlights:
        return ""
    lines = ["THÔNG TIN TRỌNG TÂM ĐÃ TÁCH TỪ NGUỒN:"]
    for highlight in highlights:
        lines.append(f"- {highlight['highlight_name']}: {highlight['text']}")
    return "\n".join(lines).strip()


def build_regulation_parents(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build one full parent document per regulation section."""

    docstore_items = []
    for section in sections:
        if section.get("content_type") != "regulation_text":
            continue

        content = clean_regulation_source_content(section.get("content", ""))
        if not content:
            continue

        cleaned_section = {**section, "content": content}
        extracted_tables = extract_regulation_tables(cleaned_section)
        extracted_highlights = extract_regulation_highlights(cleaned_section)
        full_content = build_parent_doc_content(
            cleaned_section,
            content,
            extracted_tables,
            extracted_highlights,
        )
        docstore_items.append(
            {
                "_id": section["section_id"],
                "content": full_content,
                "normalized_content": full_content,
                "tables": [table_metadata_payload(table) for table in extracted_tables],
                "highlights": [
                    highlight_metadata_payload(highlight)
                    for highlight in extracted_highlights
                ],
                "metadata": {
                    "source_type": "structured_section",
                    "document_title": section.get("document_title"),
                    "part": section.get("part"),
                    "chapter": section.get("chapter"),
                    "article": section.get("article"),
                    "title": section.get("title"),
                    "source_pages": source_page_range(
                        section["page_start"], section["page_end"]
                    ),
                    "content_type": section.get("content_type"),
                    "has_table": section.get("has_table"),
                    "has_formula": section.get("has_formula"),
                    "has_scoring_rule": section.get("has_scoring_rule"),
                    "has_thresholds": section.get("has_thresholds"),
                },
            }
        )
    return docstore_items
