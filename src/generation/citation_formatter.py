import re
from collections import defaultdict
from typing import Any


INTENT_CHUNK_PRIORITY = {
    "office_query": ["office_directory"],
    "faculty_query": ["program_directory", "faculty_directory", "faculty_program_directory"],
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

    seen: set[tuple[tuple[str, str] | None, str, tuple[int, ...], str]] = set()
    deduped: list[dict[str, Any]] = []

    for citation in citations:
        title = _citation_title(citation).strip().lower()
        pages = tuple(parse_source_pages(citation.get("source_pages")))
        # A child chunk is a distinct source even when siblings share their
        # parent article, title, and pages.  Retaining it is necessary for
        # request-scoped evidence binding; legacy citations without a chunk id
        # retain the former title/page de-duplication behavior.
        chunk_id = str(citation.get("chunk_id") or "").strip()
        key = (_request_scope(citation), title, pages, chunk_id)
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

    scopes = _request_scopes(deduped)
    # Atomic-plan evidence is fail-closed: once any citation has a request
    # owner, unscoped candidates cannot be allowed into its answer context.
    # Legacy flows remain compatible because they have no request scopes.
    if scopes:
        deduped = [
            citation for citation in deduped if _request_scope(citation) is not None
        ]
        return _select_request_scoped_citations(
            deduped,
            intent=intent,
            retrieval_result=retrieval_result,
            max_sources=max_sources,
        )

    if _has_result(retrieval_result.get("tool_result")):
        return []

    if _has_result(retrieval_result.get("structured_result")) or intent in {
        "score_lookup_query",
        "structured_lookup",
    }:
        structured_chunk_types = {
            "formula",
            "structured_lookup",
            "program_directory",
            "office_directory",
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

    ranked = _rank_citations(deduped, intent, retrieval_result)
    return ranked[:max_sources]


def _rank_citations(
    citations: list[dict[str, Any]],
    intent: str | None,
    retrieval_result: dict[str, Any],
) -> list[dict[str, Any]]:
    priorities = INTENT_CHUNK_PRIORITY.get(intent or "", [])
    ranked = sorted(
        enumerate(citations),
        key=lambda item: (
            _priority_index(item[1], priorities),
            -_metadata_match_score(item[1], retrieval_result),
            _request_retrieval_rank(item[1]),
            _distance_score(item[1]),
            item[0],
        ),
    )
    return [citation for _, citation in ranked]


def _select_request_scoped_citations(
    citations: list[dict[str, Any]],
    *,
    intent: str | None,
    retrieval_result: dict[str, Any],
    max_sources: int,
) -> list[dict[str, Any]]:
    """Preserve independently retrieved evidence for every atomic request.

    ``max_sources`` is a display budget for one semantic retrieval request.
    Structured lookups remain one source per request; a RAG request retains up
    to the configured budget so a valid source is not dropped merely because a
    sibling request consumed the shared global budget.  This is source coverage,
    not a fallback or re-routing mechanism.
    """

    grouped: dict[tuple[str, str] | None, list[dict[str, Any]]] = defaultdict(list)
    for citation in citations:
        grouped[_request_scope(citation)].append(citation)

    selected: list[dict[str, Any]] = []
    for candidates in grouped.values():
        scoped_context = _request_citation_context(candidates, retrieval_result)
        scoped_intent = _request_intent(candidates, intent)
        ranked = _rank_citations(candidates, scoped_intent, scoped_context)
        per_scope_limit = (
            max_sources
            if any(str(item.get("request_kind") or "").strip() == "rag" for item in candidates)
            else 1
        )
        selected.extend(ranked[: max(1, per_scope_limit)])
    return selected


def _request_citation_context(
    citations: list[dict[str, Any]],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    context = dict(fallback)
    for citation in citations:
        cohort = str(citation.get("request_cohort") or "").strip()
        if cohort:
            context["selected_cohort"] = cohort
            break
    for citation in citations:
        target_chunk_types = citation.get("request_target_chunk_types")
        if isinstance(target_chunk_types, list) and target_chunk_types:
            context["target_chunk_types"] = target_chunk_types
            break
    return context


def _request_intent(
    citations: list[dict[str, Any]],
    fallback: str | None,
) -> str | None:
    for citation in citations:
        value = citation.get("request_intent")
        if value is not None and str(value).strip():
            return str(value).strip()
    return fallback


def _select_with_request_coverage(
    ranked: list[dict[str, Any]],
    max_sources: int,
) -> list[dict[str, Any]]:
    """Select citations without dropping evidence from a sibling request.

    ``max_sources`` remains the normal display budget. For a multi-request plan,
    request-scope completeness takes precedence and can raise the effective
    budget up to the number of represented requests (at most the planner limit).
    """
    scopes = _request_scopes(ranked)
    if not scopes:
        return ranked[:max_sources]

    effective_limit = max(max_sources, len(scopes))
    selected: list[dict[str, Any]] = []
    selected_ids: set[int] = set()
    covered: set[tuple[str, str]] = set()

    for citation in ranked:
        scope = _request_scope(citation)
        if scope is None or scope in covered:
            continue
        selected.append(citation)
        selected_ids.add(id(citation))
        covered.add(scope)

    for citation in ranked:
        if len(selected) >= effective_limit:
            break
        if id(citation) in selected_ids:
            continue
        selected.append(citation)
        selected_ids.add(id(citation))

    return selected


def _request_scopes(
    citations: list[dict[str, Any]],
) -> set[tuple[str, str]]:
    return {
        scope
        for citation in citations
        if (scope := _request_scope(citation)) is not None
    }


def _request_scope(citation: dict[str, Any]) -> tuple[str, str] | None:
    request_id = citation.get("request_id")
    if request_id is not None and str(request_id).strip():
        return ("request_id", str(request_id).strip())

    request_index = citation.get("request_index")
    if request_index is not None:
        return ("request_index", str(request_index))

    return None


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


def _request_retrieval_rank(citation: dict[str, Any]) -> int:
    value = citation.get("request_retrieval_rank")
    if isinstance(value, int) and value > 0:
        return value
    return 999


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
