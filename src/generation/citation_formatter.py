import re
from typing import Any

from src.common.source_identity import parse_source_pages

INTENT_CHUNK_PRIORITY = {
    "office_query": ["office_directory"],
    "faculty_query": [
        "program_directory",
        "faculty_directory",
        "faculty_program_directory",
    ],
    "regulation_query": ["regulation"],
    "score_lookup_query": ["structured_lookup"],
    "structured_lookup": ["structured_lookup"],
    "formula_query": ["formula"],
    "calculation_query": ["formula", "tool"],
    "mixed_query": [
        "regulation",
        "office_directory",
        "program_directory",
        "faculty_directory",
        "faculty_program_directory",
    ],
}

_ARTICLE_REFERENCE_PATTERN = re.compile(
    r"(?<!\w)điều\s+(\d+[a-zđ]?)(?!\w)",
    flags=re.IGNORECASE,
)


def deduplicate_citations(
    citations: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Deduplicate citations by stable source identity."""

    if not citations:
        return []

    seen: set[tuple[Any, ...]] = set()
    deduped: list[dict[str, Any]] = []

    for citation in citations:
        key = _canonical_citation_identity(citation)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(citation)

    return deduped


def prioritize_citations_by_answer_anchors(
    citations: list[dict[str, Any]] | None,
    answer_text: str | None,
    *,
    max_sources: int = 10,
) -> list[dict[str, Any]]:
    """Move answer-anchored citations forward without dropping other evidence."""
    if max_sources <= 0:
        return []

    deduped = deduplicate_citations(citations)
    answer_articles = _extract_article_references(answer_text)
    if not answer_articles:
        return deduped[:max_sources]

    anchored: list[dict[str, Any]] = []
    unanchored: list[dict[str, Any]] = []
    for citation in deduped:
        label = (
            citation.get("article_label")
            or citation.get("parent_article")
            or _citation_title(citation)
        )
        target = (
            anchored
            if answer_articles.intersection(_extract_article_references(label))
            else unanchored
        )
        target.append(citation)

    return (anchored + unanchored)[:max_sources]


def _citation_title(citation: dict[str, Any]) -> str:
    title = (
        citation.get("article")
        or citation.get("title")
        or citation.get("form_name")
        or citation.get("unit_name")
        or citation.get("faculty_or_unit_name")
        or citation.get("program_name")
        or citation.get("faculty_name")
        or citation.get("procedure_name")
        or citation.get("rule_name")
        or citation.get("chunk_id")
        or ""
    )
    return str(title).strip()


def _canonical_citation_identity(citation: dict[str, Any]) -> tuple[Any, ...]:
    for field in (
        "canonical_source_id",
        "source_parent_id",
        "parent_section_id",
        "source_section",
        "section_id",
        "chunk_id",
    ):
        value = str(citation.get(field) or "").strip()
        if value:
            return (field, value.casefold())

    title = _citation_title(citation).strip().casefold()
    pages = tuple(parse_source_pages(citation.get("source_pages")))
    cohort = str(citation.get("cohort") or "").strip().casefold()
    return ("title_pages", cohort, title, pages)


def _extract_article_references(value: Any) -> set[str]:
    return {
        match.casefold()
        for match in _ARTICLE_REFERENCE_PATTERN.findall(str(value or ""))
    }
