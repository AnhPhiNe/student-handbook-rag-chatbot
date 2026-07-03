from __future__ import annotations

import re
from typing import Any


def extract_regulation_highlights(section: dict[str, Any]) -> list[dict[str, Any]]:
    """Trích các câu quy định giàu tín hiệu để tạo chunk riêng cho truy vấn chính xác."""

    content = str(section.get("content") or "")
    if not content:
        return []

    source_pages = list(
        range(int(section["page_start"]), int(section["page_end"]) + 1)
    )
    highlights: list[dict[str, Any]] = []
    highlights.extend(_extract_period_schedule_highlights(section, content, source_pages))
    return highlights


def build_regulation_highlight_chunk_content(
    section: dict[str, Any],
    highlight: dict[str, Any],
) -> str:
    parts = [
        f"Tài liệu: {section.get('document_title') or ''}",
        f"Điều: {section.get('article') or ''}",
        f"Tiêu đề: {section.get('title') or ''}",
        f"Thông tin trọng tâm: {highlight['highlight_name']}",
        f"Nội dung: {highlight['text']}",
    ]
    return "\n".join(part for part in parts if part and part.strip())


def highlight_metadata_payload(highlight: dict[str, Any]) -> dict[str, Any]:
    return {
        "highlight_id": highlight["highlight_id"],
        "highlight_name": highlight["highlight_name"],
        "highlight_kind": highlight["highlight_kind"],
        "text": highlight["text"],
    }


def _extract_period_schedule_highlights(
    section: dict[str, Any],
    content: str,
    source_pages: list[int],
) -> list[dict[str, Any]]:
    normalized = _collapse_space(content)
    pattern = re.compile(
        r"((?:\d+\.\s*)?[^.]{0,180}?\bcó\s+\d+\s+đợt\s+[^.]{0,240}?"
        r"(?:tháng\s+\d+[^.]{0,80}?){2,}\.)",
        flags=re.IGNORECASE,
    )
    highlights: list[dict[str, Any]] = []
    for index, match in enumerate(pattern.finditer(normalized), start=1):
        text = _collapse_space(match.group(1))
        if not text:
            continue
        highlights.append(
            {
                "highlight_id": f"{section['section_id']}_period_schedule_{index}",
                "highlight_name": "Lịch/đợt thực hiện theo quy định",
                "highlight_kind": "period_schedule",
                "text": text,
                "source_pages": source_pages,
                "source_section": section.get("title") or section.get("article"),
            }
        )
    return highlights


def _collapse_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()
