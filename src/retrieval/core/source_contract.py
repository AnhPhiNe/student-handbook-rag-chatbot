from __future__ import annotations

import re
from typing import Any, Literal, TypedDict


SourceKind = Literal["table", "catalog", "article", "formula"]


class StructuredSourceRef(TypedDict, total=False):
    source_kind: SourceKind
    document_id: str
    cohort: str | None
    table_id: str | None
    source_record_id: str | None
    table_name: str | None
    parent_section_id: str | None
    source_pages: list[int]
    source_url: str | None
    applicability: str | None
    applicable_cohorts: list[str]


_GENERIC_SOURCE_SECTIONS = {
    "formula_rule",
    "program_directory",
    "scoring_table",
    "student_faculty_profiles",
    "student_office_profiles",
    "student_service_directory",
    "study_duration",
}


def parse_source_pages(value: Any) -> list[int]:
    if value is None:
        return []
    if isinstance(value, (int, str)):
        value = [value]
    if not isinstance(value, list):
        return []

    pages = {
        int(item)
        for item in value
        if str(item).strip().isdigit()
    }
    return sorted(pages)


def parse_applicable_cohorts(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list | tuple | set):
        return []
    return sorted(
        {str(cohort).strip() for cohort in value if str(cohort).strip()}
    )


def source_ref_from_record(
    record: dict[str, Any],
    *,
    source_kind: SourceKind,
    table_id: str | None = None,
    table_name: str | None = None,
    parent_section_id: str | None = None,
    source_record_id: str | None = None,
) -> StructuredSourceRef | None:
    provenance = record.get("source_provenance") or {}
    if not isinstance(provenance, dict):
        provenance = {}

    document_ids = record.get("document_ids") or []
    if isinstance(document_ids, str):
        document_ids = [document_ids]
    document_id = (
        record.get("document_id")
        or record.get("source_document_id")
        or provenance.get("document_id")
        or (document_ids[0] if len(document_ids) == 1 else None)
    )
    resolved_parent_id = (
        parent_section_id
        or record.get("source_parent_id")
        or record.get("parent_section_id")
        or record.get("source_section_id")
    )
    ref: StructuredSourceRef = {
        "source_kind": source_kind,
        "document_id": str(document_id).strip() if document_id else "",
        "cohort": record.get("source_cohort") or record.get("cohort"),
        "table_id": table_id or record.get("table_id"),
        "source_record_id": source_record_id
        or record.get("source_record_id")
        or record.get("record_id")
        or record.get("rule_id")
        or record.get("service_id")
        or record.get("office_profile_id")
        or record.get("faculty_profile_id")
        or provenance.get("source_record_id")
        or provenance.get("record_id"),
        "table_name": table_name or record.get("table_name") or record.get("source_title"),
        "parent_section_id": resolved_parent_id,
        "source_pages": parse_source_pages(
            record.get("source_pages") or provenance.get("source_pages")
        ),
        "source_url": record.get("source_url")
        or record.get("url")
        or record.get("document_url"),
        "applicability": record.get("applicability"),
        "applicable_cohorts": parse_applicable_cohorts(
            record.get("applicable_cohorts")
            or provenance.get("applicable_cohorts")
            or []
        ),
    }
    return normalize_source_ref(ref)


def normalize_source_ref(
    value: dict[str, Any],
) -> StructuredSourceRef | None:
    source_kind = str(value.get("source_kind") or "").strip()
    if source_kind not in {"table", "catalog", "article", "formula"}:
        return None

    document_id = str(value.get("document_id") or "").strip()
    parent_section_id = str(value.get("parent_section_id") or "").strip() or None
    table_id = str(value.get("table_id") or "").strip() or None
    source_record_id = str(value.get("source_record_id") or "").strip() or None
    source_url = str(value.get("source_url") or "").strip() or None
    if not document_id or not any(
        (parent_section_id, table_id, source_record_id, source_url)
    ):
        return None

    return {
        "source_kind": source_kind,
        "document_id": document_id,
        "cohort": value.get("cohort"),
        "table_id": table_id,
        "source_record_id": source_record_id,
        "table_name": str(value.get("table_name") or "").strip() or None,
        "parent_section_id": parent_section_id,
        "source_pages": parse_source_pages(value.get("source_pages")),
        "source_url": source_url,
        "applicability": str(value.get("applicability") or "").strip() or None,
        "applicable_cohorts": parse_applicable_cohorts(
            value.get("applicable_cohorts")
        ),
    }


def deduplicate_source_records(
    records: list[dict[str, Any]],
) -> list[StructuredSourceRef]:
    deduplicated: dict[tuple[Any, ...], StructuredSourceRef] = {}
    for record in records:
        normalized = normalize_source_ref(record)
        if normalized is None:
            continue
        key = (
            normalized.get("source_kind"),
            normalized.get("document_id"),
            normalized.get("cohort"),
            normalized.get("table_id"),
            normalized.get("source_record_id"),
            normalized.get("parent_section_id"),
        )
        existing = deduplicated.get(key)
        if existing is not None:
            existing["source_pages"] = sorted(
                set(existing.get("source_pages") or [])
                | set(normalized.get("source_pages") or [])
            )
            for field in (
                "table_id",
                "source_record_id",
                "table_name",
                "parent_section_id",
                "source_url",
                "applicability",
            ):
                if not existing.get(field) and normalized.get(field):
                    existing[field] = normalized[field]
            existing["applicable_cohorts"] = sorted(
                set(existing.get("applicable_cohorts") or [])
                | set(normalized.get("applicable_cohorts") or [])
            )
            continue
        deduplicated[key] = normalized
    return list(deduplicated.values())


def source_records_from_records(
    records: list[dict[str, Any]],
    *,
    source_kind: SourceKind,
    table_name: str | None = None,
    table_id: str | None = None,
    group_catalog: bool = False,
) -> list[StructuredSourceRef]:
    if not group_catalog:
        return deduplicate_source_records(
            [
                source_ref
                for record in records
                if (
                    source_ref := source_ref_from_record(
                        record,
                        source_kind=source_kind,
                        table_id=table_id,
                        table_name=table_name,
                    )
                )
            ]
        )

    grouped: dict[tuple[str, Any], dict[str, Any]] = {}
    for record in records:
        source_ref = source_ref_from_record(
            record,
            source_kind=source_kind,
            table_id=table_id,
            table_name=table_name,
        )
        if source_ref is None:
            continue
        key = (str(source_ref.get("document_id")), source_ref.get("cohort"))
        bucket = grouped.setdefault(
            key,
            {
                "document_id": source_ref.get("document_id"),
                "cohort": source_ref.get("cohort"),
                "table_id": table_id,
                "table_name": table_name,
                "source_pages": [],
                "source_kind": source_kind,
            },
        )
        bucket["source_pages"] = sorted(
            set(bucket["source_pages"]) | set(source_ref.get("source_pages") or [])
        )
        if not bucket.get("source_url") and source_ref.get("source_url"):
            bucket["source_url"] = source_ref["source_url"]
    return deduplicate_source_records(list(grouped.values()))


def legacy_source_records(
    lookup_result: dict[str, Any],
) -> list[StructuredSourceRef]:
    document_id = str(lookup_result.get("document_id") or "").strip()
    if not document_id:
        return []

    lookup_type = str(lookup_result.get("lookup_type") or "")
    if lookup_type == "formula":
        source_kind: SourceKind = "formula"
    elif lookup_type in {"program", "program_directory", "office_directory"}:
        source_kind = "catalog"
    else:
        source_kind = "table"

    source_section = str(lookup_result.get("source_section") or "").strip()
    parent_section_id = (
        source_section
        if source_section and source_section not in _GENERIC_SOURCE_SECTIONS
        else None
    )
    legacy_table_id = lookup_result.get("table_id")
    legacy_source_record_id = lookup_result.get("source_record_id")
    if source_kind == "catalog" and not legacy_table_id:
        legacy_table_id = source_section or lookup_type
    elif source_kind == "table" and not legacy_table_id:
        legacy_table_id = lookup_type or None
    elif source_kind == "formula" and not legacy_source_record_id:
        legacy_source_record_id = lookup_result.get("rule_id")

    ref = normalize_source_ref(
        {
            "source_kind": source_kind,
            "document_id": document_id,
            "cohort": lookup_result.get("cohort"),
            "table_id": legacy_table_id,
            "source_record_id": legacy_source_record_id,
            "table_name": lookup_result.get("table_name")
            or lookup_result.get("rule_name"),
            "parent_section_id": lookup_result.get("source_parent_id")
            or lookup_result.get("parent_section_id")
            or parent_section_id,
            "source_pages": lookup_result.get("source_pages"),
            "source_url": lookup_result.get("source_url"),
            "applicability": lookup_result.get("applicability"),
        }
    )
    return [ref] if ref else []


def source_records_from_result(
    lookup_result: dict[str, Any],
) -> list[StructuredSourceRef]:
    if "source_records" not in lookup_result:
        return legacy_source_records(lookup_result)

    records = lookup_result.get("source_records") or []
    if isinstance(records, dict):
        records = [records]
    if isinstance(records, list):
        return deduplicate_source_records(
            [record for record in records if isinstance(record, dict)]
        )
    return []


def enrich_source_records_from_registry(
    records: list[dict[str, Any]],
    registry: list[dict[str, Any]],
) -> list[StructuredSourceRef]:
    enriched = []
    for raw_record in records:
        record = normalize_source_ref(raw_record)
        if record is None or record.get("source_kind") != "table":
            if record is not None:
                enriched.append(record)
            continue

        candidates = _registry_candidates(record, registry)
        if len(candidates) == 1:
            table = candidates[0]
            record = {
                **record,
                "table_id": table.get("table_id") or record.get("table_id"),
                "table_name": table.get("table_name") or record.get("table_name"),
                "parent_section_id": table.get("source_parent_id")
                or table.get("source_section_id")
                or record.get("parent_section_id"),
                "source_pages": parse_source_pages(table.get("source_pages"))
                or record.get("source_pages", []),
                "applicability": table.get("applicability")
                or record.get("applicability"),
            }
        enriched.append(record)
    return deduplicate_source_records(enriched)


def _registry_candidates(
    record: StructuredSourceRef,
    registry: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    document_id = record.get("document_id")
    cohort = record.get("cohort")
    table_id = record.get("table_id")
    source_record_id = record.get("source_record_id")
    pages = set(record.get("source_pages") or [])

    candidates = [
        table
        for table in registry
        if str(table.get("document_id") or "") == document_id
        and (not cohort or table.get("cohort") == cohort)
    ]
    exact_identifiers = {
        str(identifier).strip()
        for identifier in (table_id, source_record_id)
        if identifier
    }
    exact = [
        table
        for table in candidates
        if exact_identifiers
        & {
            str(identifier).strip()
            for identifier in (
                table.get("table_id"),
                table.get("source_record_id"),
                table.get("record_id"),
            )
            if identifier
        }
    ]
    if exact:
        return exact

    normalized_identifiers = {
        re.sub(r"[^a-z0-9]+", "", value.casefold()) for value in exact_identifiers
    }
    subtype_candidates = [
        table
        for table in candidates
        if re.sub(
            r"[^a-z0-9]+", "", str(table.get("table_subtype") or "").casefold()
        )
        in normalized_identifiers
    ]
    if len(subtype_candidates) <= 1:
        return subtype_candidates

    if not pages:
        return subtype_candidates

    overlap_by_id = {
        id(table): len(pages & set(parse_source_pages(table.get("source_pages"))))
        for table in subtype_candidates
    }
    best_overlap = max(overlap_by_id.values(), default=0)
    if best_overlap == 0:
        return subtype_candidates
    return [
        table
        for table in subtype_candidates
        if overlap_by_id[id(table)] == best_overlap
    ]
