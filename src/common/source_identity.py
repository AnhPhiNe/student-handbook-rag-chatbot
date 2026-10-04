from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from typing import Any

from src.common.cohort import normalize_cohort
from src.common.legal_reference import normalize_article_label


def directory_evidence_identity(entry: dict[str, Any]) -> tuple[Any, ...] | None:
    """Distinguish record lists within a catalog; missing IDs stay task-local.

    A catalog ID identifies the source, not its selected records. Only a complete
    list of record IDs permits sharing across tasks. Other evidence retains its
    existing parent/table identity; no record ID is invented from a unit name.
    """
    metadata = entry.get("metadata") or {}
    chunk_type = entry.get("chunk_type") or metadata.get("chunk_type")
    if entry.get("evidence_kind") != "structured_result" and chunk_type not in {
        "office_directory", "faculty_directory", "program_directory",
        "student_office_profile", "student_faculty_profile", "student_service_directory",
    }:
        return None
    try:
        payload = json.loads(str(entry.get("content") or ""))
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, list):
        return None
    record_ids = [
        str(record.get("record_id") or "").strip() if isinstance(record, dict) else ""
        for record in payload
    ]
    if record_ids and all(record_ids):
        return "records", tuple(sorted(record_ids))
    supports = entry.get("supports_task_ids") or metadata.get("supports_task_ids") or []
    return (
        "task_local",
        tuple(sorted(supports)),
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str),
    )


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
