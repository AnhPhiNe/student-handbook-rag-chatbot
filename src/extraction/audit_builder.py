from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from src.common.content_modes import get_content_mode


def _page_span(pages: list[int]) -> dict[str, int | None]:
    if not pages:
        return {"page_start": None, "page_end": None}
    return {"page_start": min(pages), "page_end": max(pages)}


def build_content_audit(
    pages: list[dict[str, Any]],
    sections: list[dict[str, Any]],
) -> dict[str, Any]:
    """Sinh báo cáo audit nội dung cho một sổ tay sau bước phân vùng trang."""
    pages_by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for page in pages:
        pages_by_type[page.get("content_type", "unknown")].append(page)

    section_counts = Counter(section.get("content_type", "unknown") for section in sections)
    page_mode_counts = Counter(
        get_content_mode(page.get("content_type")) for page in pages
    )

    content_types = []
    for content_type in sorted(pages_by_type):
        related_pages = pages_by_type[content_type]
        page_numbers = [page["page_number"] for page in related_pages]
        mode = get_content_mode(content_type)
        content_types.append(
            {
                "content_type": content_type,
                "content_mode": mode,
                "page_count": len(related_pages),
                "section_count": section_counts.get(content_type, 0),
                "pages": page_numbers,
                **_page_span(page_numbers),
                "needs_embedding": mode == "rag_index",
                "needs_structured_lookup": mode == "structured_only",
            }
        )

    low_value_pages = [
        {
            "page_number": page["page_number"],
            "content_type": page.get("content_type"),
            "content_mode": get_content_mode(page.get("content_type")),
            "cleaned_char_count": page.get("cleaned_char_count", 0),
            "section_description": page.get("section_description"),
        }
        for page in pages
        if get_content_mode(page.get("content_type")) == "archive_only"
    ]

    return {
        "document_id": pages[0].get("document_id") if pages else None,
        "file_name": pages[0].get("file_name") if pages else None,
        "total_pages": len(pages),
        "content_type_count": dict(Counter(page.get("content_type") for page in pages)),
        "content_mode_count": dict(page_mode_counts),
        "content_types": content_types,
        "archive_only_pages": low_value_pages,
        "validation_notes": [
            "Các section archive_only không được đưa vào semantic embedding.",
            "Các section structured_only chỉ nên tạo lookup record ngắn, không chunk toàn văn.",
            "Các section rag_index cần có citation theo cohort/document_id/source_pages.",
        ],
    }

