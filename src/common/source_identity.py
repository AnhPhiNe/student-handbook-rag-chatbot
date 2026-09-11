from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

from src.common.cohort import normalize_cohort
from src.common.legal_reference import normalize_article_label


def canonical_article_source_id(
    *,
    document_identity: Any,
    cohort: Any,
    article_label: Any,
) -> str | None:
    """Return a stable ID for one article in one document and cohort."""
    document = _normalize_text(document_identity)
    normalized_cohort = normalize_cohort(cohort) or _normalize_text(cohort)
    article = normalize_article_label(article_label)
    if not document or not normalized_cohort or not article:
        return None

    payload = json.dumps(
        [document, normalized_cohort.casefold(), article.casefold()],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"article-source-{digest}"


def _normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFC", str(value or "")).strip().casefold()
    return re.sub(r"\s+", " ", text)


def parse_source_pages(value: Any) -> list[int]:
    """Normalize citation page metadata into sorted page numbers."""

    if value is None:
        return []

    if isinstance(value, int):
        return [value]

    if isinstance(value, float) and value.is_integer():
        return [int(value)]

    if isinstance(value, list | tuple | set):
        pages: list[int] = []
        for item in value:
            pages.extend(parse_source_pages(item))
        return sorted(dict.fromkeys(pages))

    if isinstance(value, str):
        normalized = value.replace("–", "-").replace("—", "-")
        pages: list[int] = []
        for start, end in re.findall(r"(\d+)\s*-\s*(\d+)", normalized):
            start_int = int(start)
            end_int = int(end)
            if start_int <= end_int:
                pages.extend(range(start_int, end_int + 1))

        text_without_ranges = re.sub(r"\d+\s*-\s*\d+", " ", normalized)
        pages.extend(int(item) for item in re.findall(r"\d+", text_without_ranges))
        return sorted(dict.fromkeys(pages))

    return []
