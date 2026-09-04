"""Create a small, public UI projection for deterministic lookup results.

The retrieval packet contains source anchors, ranking signals and raw text that are
useful to the answer pipeline but should not be exposed as a regulation citation.
This module keeps that internal packet intact and derives a display-only table.
"""

from __future__ import annotations

from typing import Any, Iterator

from src.retrieval.core.structured_routing import load_lookup_registry


_INTERNAL_FIELDS = {
    "applicable_cohorts",
    "content_type",
    "document_id",
    "faculty_name_source",
    "lexical_score",
    "quality_status",
    "raw_text",
    "score",
    "selection_method",
    "semantic_score",
    "source_cohort",
    "source_pages",
    "source_parent_id",
    "source_parent_ids",
    "source_section",
    "source_section_id",
    "table_id",
}

_CONTEXT_FIELDS = {
    "category",
    "classification",
    "cohort",
    "group",
    "level",
    "matched_level",
    "matched_value",
    "table_name",
    "training_mode",
}

_PRESENTATION_TYPES = {"table", "contact_card"}
_CONTACT_CARD_FIELDS: dict[str, tuple[str, ...]] = {
    "unit_name": ("unit_name", "unit"),
    "address": ("address", "office", "offices"),
    "phone": ("phone", "phones"),
    "email": ("email", "emails"),
    "website": ("website", "websites"),
}


def _iter_leaf_lookups(value: Any) -> Iterator[dict[str, Any]]:
    if not isinstance(value, dict):
        return

    sub_lookups = value.get("sub_lookups")
    if isinstance(sub_lookups, list) and sub_lookups:
        for item in sub_lookups:
            yield from _iter_leaf_lookups(item)
        return

    yield value


def _display_value(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list) and all(
        item is None or isinstance(item, (str, int, float, bool)) for item in value
    ):
        return "; ".join(str(item) for item in value if item is not None)
    return None


def _safe_row(value: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key, raw_value in {**context, **value}.items():
        if key in _INTERNAL_FIELDS or key in {
            "display_rows",
            "display_tables",
            "rows",
            "tables",
        }:
            continue
        display_value = _display_value(raw_value)
        if display_value is not None and display_value != "":
            row[key] = display_value
    return row


def _flatten_rows(
    value: Any, context: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    context = dict(context or {})
    if isinstance(value, list):
        rows: list[dict[str, Any]] = []
        for item in value:
            rows.extend(_flatten_rows(item, context))
        return rows

    if not isinstance(value, dict):
        return []

    next_context = dict(context)
    for key in _CONTEXT_FIELDS:
        display_value = _display_value(value.get(key))
        if display_value is not None and display_value != "":
            next_context[key] = display_value

    nested_rows = value.get("rows")
    if isinstance(nested_rows, list):
        return _flatten_rows(nested_rows, next_context)

    nested_tables = value.get("tables")
    if isinstance(nested_tables, list):
        return _flatten_rows(nested_tables, next_context)

    row = _safe_row(value, context)
    return [row] if row else []


def _lookup_rows(lookup: dict[str, Any]) -> list[dict[str, Any]]:
    display_rows = lookup.get("display_rows")
    if isinstance(display_rows, list) and display_rows:
        rows = _flatten_rows(display_rows)
        if rows:
            return rows

    display_tables = lookup.get("display_tables")
    if isinstance(display_tables, list) and display_tables:
        rows = _flatten_rows(display_tables)
        if rows:
            return rows

    items = lookup.get("items")
    if isinstance(items, list) and items:
        rows = _flatten_rows(items)
        if rows:
            return rows
    return _flatten_rows(lookup.get("result"))


def _presentation_type(lookup: dict[str, Any]) -> str:
    explicit = str(lookup.get("presentation_type") or "")
    if explicit in _PRESENTATION_TYPES:
        return explicit

    lookup_scope = str(lookup.get("lookup_scope") or "")
    registry = load_lookup_registry()
    tool = (registry.get("tools") or {}).get(lookup_scope) or {}
    configured = str(tool.get("presentation_type") or "table")
    return configured if configured in _PRESENTATION_TYPES else "table"


def _first_display_value(record: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = _display_value(record.get(key))
        if value is not None and value != "":
            return value
    return None


def _contact_card_rows(lookup: dict[str, Any]) -> list[dict[str, Any]]:
    raw_records = lookup.get("items") or lookup.get("result") or []
    records = raw_records if isinstance(raw_records, list) else [raw_records]
    rows: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        row = {
            field: value
            for field, aliases in _CONTACT_CARD_FIELDS.items()
            if (value := _first_display_value(record, aliases)) is not None
        }
        if row:
            rows.append(row)
    return rows


def _field_provenance(lookup: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw_rows = lookup.get("items") or lookup.get("result") or []
    candidates = raw_rows if isinstance(raw_rows, list) else [raw_rows]
    mapping_sources = sorted(
        {
            str(row.get("faculty_name_source"))
            for row in candidates
            if isinstance(row, dict) and row.get("faculty_name_source")
        }
    )
    if not mapping_sources:
        return {}
    return {
        "faculty_name": {
            "source_type": "curated_registry",
            "source_label": "Danh mục ánh xạ ngành–khoa đã chuẩn hóa",
            "registry": "configs/program_overrides.yaml",
            "mapping_methods": mapping_sources,
        }
    }


def _public_source_reference(
    lookup: dict[str, Any],
    citations: list[dict[str, Any]],
) -> dict[str, Any] | None:
    parent_id = str(
        lookup.get("source_parent_id")
        or lookup.get("parent_section_id")
        or lookup.get("source_section")
        or ""
    ).strip()
    cohort = str(lookup.get("cohort") or "").strip()
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        citation_parent_id = str(
            citation.get("source_parent_id")
            or citation.get("parent_section_id")
            or citation.get("source_section")
            or citation.get("chunk_id")
            or ""
        ).strip()
        citation_cohort = str(citation.get("cohort") or "").strip()
        if parent_id and citation_parent_id != parent_id:
            continue
        if cohort and citation_cohort and citation_cohort != cohort:
            continue
        content = str(
            citation.get("parent_content") or citation.get("content") or ""
        ).strip()
        article_label = citation.get("article_label") or citation.get("parent_article")
        if not content or not article_label:
            continue
        return {
            "chunk_id": citation_parent_id,
            "title": citation.get("parent_title") or citation.get("title"),
            "content": content,
            "relevant_excerpt": citation.get("content"),
            "source_pages": citation.get("source_pages") or [],
            "source_url": citation.get("source_url"),
            "cohort": citation.get("cohort"),
            "article_label": article_label,
            "detail_kind": citation.get("detail_kind") or "table",
            "table_name": citation.get("table_name") or citation.get("title"),
        }
    return None


def build_structured_results(
    structured_result: Any,
    citations: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return display-safe tables without changing the retrieval evidence packet."""
    results: list[dict[str, Any]] = []
    for index, lookup in enumerate(_iter_leaf_lookups(structured_result)):
        presentation_type = _presentation_type(lookup)
        rows = (
            _contact_card_rows(lookup)
            if presentation_type == "contact_card"
            else _lookup_rows(lookup)
        )
        if not rows:
            continue

        columns: list[str] = []
        for row in rows:
            for key in row:
                if key not in columns:
                    columns.append(key)

        source_reference = _public_source_reference(lookup, citations or [])
        results.append(
            {
                "id": f"{lookup.get('lookup_type') or 'structured'}:{lookup.get('cohort') or 'default'}:{index}",
                "lookup_type": str(lookup.get("lookup_type") or "structured_lookup"),
                "presentation_type": presentation_type,
                "title": str(
                    lookup.get("table_name")
                    or lookup.get("source_label")
                    or "Kết quả tra cứu"
                ),
                "cohort": lookup.get("cohort"),
                "applicability": lookup.get("applicability"),
                "columns": columns,
                "rows": rows,
                "provenance": {
                    "source_type": "structured_dataset",
                    "source_label": lookup.get("source_label")
                    or "Dữ liệu có cấu trúc từ Sổ tay sinh viên",
                    "document_id": lookup.get("document_id"),
                    "source_pages": lookup.get("source_pages") or [],
                    **(
                        {"source_reference": source_reference}
                        if source_reference
                        else {}
                    ),
                },
                "field_provenance": _field_provenance(lookup),
            }
        )
    return results


def is_structured_result_citation(citation: Any) -> bool:
    """Identify citations created from a deterministic lookup, not PDF RAG."""
    return (
        isinstance(citation, dict)
        and citation.get("evidence_kind") == "structured_result"
    )


def public_regulation_citations(citations: Any) -> list[Any]:
    """Project internal citations onto the public regulation schema."""

    if not isinstance(citations, list):
        return []
    return [item for item in citations if not is_structured_result_citation(item)]
