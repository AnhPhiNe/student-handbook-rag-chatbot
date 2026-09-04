from __future__ import annotations

from typing import Any


RAG_INDEX = "rag_index"
STRUCTURED_ONLY = "structured_only"
ARCHIVE_ONLY = "archive_only"


ARCHIVE_ONLY_TYPES = {
    "cover_page",
    "low_text_or_blank",
    "abbreviation",
    "general_info",
    "ktx_procedure_archive",
    "toc_or_index",
    "reference_directory",
}

STRUCTURED_ONLY_TYPES = {
    "formula_rule",
    "scoring_table",
    "threshold_rule",
}

RAG_INDEX_TYPES = {
    "regulation_text",
    "office_directory",
    "faculty_directory",
    "program_directory",
    "faculty_program_directory",
    "faculty_student_services",
    "scoring_form_table",
}


def get_content_mode(content_type: str | None) -> str:
    """Resolve the default processing mode for one handbook content type."""
    if content_type in STRUCTURED_ONLY_TYPES:
        return STRUCTURED_ONLY
    if content_type in ARCHIVE_ONLY_TYPES:
        return ARCHIVE_ONLY
    if content_type in RAG_INDEX_TYPES:
        return RAG_INDEX
    return ARCHIVE_ONLY


def apply_record_defaults(
    record: dict[str, Any],
    *,
    document_id: str | None = None,
    cohort: str | None = None,
    source_section: str | None = None,
    content_mode: str | None = None,
) -> dict[str, Any]:
    """Attach canonical routing metadata so downstream stages need no inference."""
    content_type = record.get("content_type")
    record.setdefault("document_id", document_id)
    record.setdefault("cohort", cohort)
    record.setdefault("source_section", source_section or content_type)
    record.setdefault("content_mode", content_mode or get_content_mode(content_type))
    return record
