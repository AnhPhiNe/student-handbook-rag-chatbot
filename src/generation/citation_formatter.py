import re
from typing import Any


INTENT_CHUNK_PRIORITY = {
    "form_query": ["form"],
    "office_query": ["office_directory"],
    "faculty_query": ["program_directory", "faculty_directory", "faculty_program_directory"],
    "procedure_query": ["procedure"],
    "regulation_query": ["regulation"],
    "score_lookup_query": ["structured_lookup"],
    "structured_lookup": ["structured_lookup"],
    "formula_query": ["formula"],
    "calculation_query": ["formula", "tool"],
    "mixed_query": [
        "form",
        "procedure",
        "regulation",
        "office_directory",
        "program_directory",
        "faculty_directory",
        "faculty_program_directory",
    ],
}


def parse_source_pages(value: Any) -> list[int]:
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


def deduplicate_citations(
    citations: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not citations:
        return []

    seen: set[tuple[str, tuple[int, ...]]] = set()
    deduped: list[dict[str, Any]] = []

    for citation in citations:
        title = _citation_title(citation).strip().lower()
        pages = tuple(parse_source_pages(citation.get("source_pages")))
        key = (title, pages)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(citation)

    return deduped


def select_relevant_citations(
    citations: list[dict[str, Any]] | None,
    intent: str | None,
    retrieval_result: dict[str, Any] | None = None,
    max_sources: int = 1,
) -> list[dict[str, Any]]:
    deduped = deduplicate_citations(citations)
    if not deduped or max_sources <= 0:
        return []

    retrieval_result = retrieval_result or {}

    if (
        _has_result(retrieval_result.get("tool_result"))
        or intent == "calculation_query"
    ):
        return []

    if _has_result(retrieval_result.get("structured_result")) or intent in {
        "score_lookup_query",
        "structured_lookup",
    }:
        structured_chunk_types = {
            "structured_lookup",
            "program_directory",
            "form",
            "form_template",
        }
        lookup_citations = [
            citation
            for citation in deduped
            if _chunk_type(citation) in structured_chunk_types
        ]
        return lookup_citations[:max_sources]

    if any(_chunk_type(citation) in {"tool", "formula"} for citation in deduped):
        tool_citations = [
            citation
            for citation in deduped
            if _chunk_type(citation) in {"tool", "formula"}
        ]
        return tool_citations[:1]

    if intent == "mixed_query":
        return _select_distinct_chunk_types(deduped, max_sources=min(max_sources, 2))

    priorities = INTENT_CHUNK_PRIORITY.get(intent or "", [])
    ranked = sorted(
        enumerate(deduped),
        key=lambda item: (
            _priority_index(item[1], priorities),
            -_metadata_match_score(item[1], retrieval_result),
            _distance_score(item[1]),
            item[0],
        ),
    )
    return [citation for _, citation in ranked[:max_sources]]


def format_sources_text(citations: list[dict[str, Any]] | None) -> str:
    if not citations:
        return ""

    lines: list[str] = []
    seen: set[str] = set()
    for citation in deduplicate_citations(citations):
        item = format_citation(citation)
        if not item or item in seen:
            continue
        seen.add(item)
        lines.append(f"- {item}")

    if not lines:
        return ""

    return "Nguồn:\n" + "\n".join(lines)


def build_sources_text(citations: list[dict[str, Any]] | None) -> str:
    return format_sources_text(citations)


def format_pages(pages: Any) -> str:
    parsed_pages = parse_source_pages(pages)
    if not parsed_pages:
        return ""

    ranges: list[str] = []
    start = previous = parsed_pages[0]

    for page in parsed_pages[1:]:
        if page == previous + 1:
            previous = page
            continue

        ranges.append(_format_page_range(start, previous))
        start = previous = page

    ranges.append(_format_page_range(start, previous))
    return ", ".join(ranges)


def format_citation(citation: dict[str, Any]) -> str:
    title = _citation_title(citation)
    pages_text = format_pages(citation.get("source_pages"))

    if title and pages_text:
        return f"{title}, trang {pages_text}"
    if pages_text:
        return f"Trang {pages_text}"
    return title


def _priority_index(citation: dict[str, Any], priorities: list[str]) -> int:
    chunk_type = _chunk_type(citation)
    purpose = str(citation.get("retrieval_purpose") or citation.get("purpose") or "")
    for index, preferred in enumerate(priorities):
        if chunk_type == preferred or purpose == preferred:
            return index
    return len(priorities) + 1


def _select_distinct_chunk_types(
    citations: list[dict[str, Any]],
    max_sources: int,
) -> list[dict[str, Any]]:
    if max_sources <= 0:
        return []

    priorities = INTENT_CHUNK_PRIORITY["mixed_query"]
    ranked = sorted(
        enumerate(citations),
        key=lambda item: (
            _priority_index(item[1], priorities),
            _distance_score(item[1]),
            item[0],
        ),
    )

    selected: list[dict[str, Any]] = []
    seen_chunk_types: set[str] = set()

    for _, citation in ranked:
        chunk_type = _chunk_type(citation)
        if chunk_type in seen_chunk_types:
            continue
        selected.append(citation)
        seen_chunk_types.add(chunk_type)
        if len(selected) >= max_sources:
            break

    if selected:
        return selected

    return [citation for _, citation in ranked[:max_sources]]


def _distance_score(citation: dict[str, Any]) -> float:
    rerank = citation.get("rerank")
    if isinstance(rerank, dict):
        final_score = rerank.get("final_score")
        if isinstance(final_score, int | float):
            return -float(final_score)

    distance = citation.get("distance")
    if isinstance(distance, int | float):
        return float(distance)
    return 999.0


def _metadata_match_score(
    citation: dict[str, Any],
    retrieval_result: dict[str, Any],
) -> float:
    score = 0.0

    expected_cohort = str(retrieval_result.get("selected_cohort") or "").strip()
    citation_cohort = str(citation.get("cohort") or "").strip()
    if expected_cohort and citation_cohort == expected_cohort:
        score += 2.0

    target_chunk_types = {
        str(item).strip()
        for item in retrieval_result.get("target_chunk_types") or []
        if str(item).strip()
    }
    if target_chunk_types and _chunk_type(citation) in target_chunk_types:
        score += 1.5

    source_section = str(citation.get("source_section") or "").strip()
    if source_section:
        score += 0.25

    pages = parse_source_pages(citation.get("source_pages"))
    if pages:
        score += 0.25

    return score


def _chunk_type(citation: dict[str, Any]) -> str:
    return str(citation.get("chunk_type") or "").strip()


def _has_result(value: Any) -> bool:
    return isinstance(value, dict) and value.get("result") is not None


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


def _format_page_range(start: int, end: int) -> str:
    if start == end:
        return str(start)
    return f"{start}-{end}"
