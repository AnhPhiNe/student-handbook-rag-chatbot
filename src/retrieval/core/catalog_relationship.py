"""One-hop joins over reviewed, cohort-scoped catalog keys."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from src.common.cohort import is_validated_source_applicable, normalize_cohort

from .office_lookup import office_lookup


def identity(value: Any) -> str:
    """Keep accents significant; aliases, not folding, authorize variants."""

    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(value or ""))
                  .casefold()).strip()


def _values(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def _keys(record: dict[str, Any], fields: list[str]) -> set[str]:
    return {
        normalized
        for field in fields
        for value in _values(record.get(field))
        if (normalized := identity(value))
    }


def _declared_alias_span(source_keys: set[str], target: dict[str, Any]) -> bool:
    """A reviewed multi-word alias may name a span of an organization label.

    For example the catalog's `Tâm lý` alias covers the same faculty when a
    program names it `Khoa Tâm lý học`. This fallback never strips accents or
    invents an alias, and a non-unique match is rejected by cardinality below.
    """

    for alias in _keys(target, ["aliases"]):
        if len(alias.split()) < 2:
            continue
        # Only an interior alias is safe here. A prefix such as "Khoa Tiếng
        # Trung" must not identify "Khoa Tiếng Trung Quốc" by truncation.
        if any(f" {alias} " in f" {key} " and not key.startswith(alias + " ")
               and not key.endswith(" " + alias) for key in source_keys):
            return True
    return False


def _has_field(record: dict[str, Any], field: str) -> bool:
    keys = {
        "email": ("email", "emails"),
        "phone": ("phone", "phones"),
        "website": ("website", "websites"),
        "office": ("office", "offices"),
        # Profile responsibilities are not the complete linked service list.
        "services": ("services",),
    }.get(field, (field,))
    return any(record.get(key) for key in keys)


def resolve_relationship(
    source_result: dict[str, Any], *, source_lookup: str,
    requested_field: Any, cohort: str | None,
    relationships: dict[str, Any], catalogs: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Join only a unique source to declared target keys within one cohort."""

    spec = relationships.get(source_lookup)
    if not isinstance(spec, dict):
        return source_result
    requested = {str(value) for value in _values(requested_field)}
    if not requested.intersection(spec.get("requested_fields") or []):
        return source_result
    source_items = source_result.get("result")
    if not isinstance(source_items, list) or not source_items:
        return source_result
    if len(source_items) != 1:
        return {
            "lookup_type": source_lookup,
            "needs_clarification": True,
            "clarification_question": "Có nhiều mục phù hợp. Bạn vui lòng cho biết tên cụ thể cần tra cứu.",
            "content_type": "structured_lookup_clarification",
            "cohort": cohort,
        }
    source_item = source_items[0]
    if not isinstance(source_item, dict):
        return source_result
    fields_needed = requested & set(spec["requested_fields"])
    if fields_needed != {"all"} and all(_has_field(source_item, field) for field in fields_needed):
        return source_result
    if "all" in fields_needed and source_lookup != "program" and any(
        _has_field(source_item, field) for field in ("email", "phone", "office")
    ):
        return source_result

    source_keys = _keys(source_item, [spec["source_key"]])
    if not source_keys:
        # Office summaries expose responsibilities but not service_ids. Read
        # the unique already-selected source record, never infer it from target.
        source_catalog = catalogs.get(source_lookup) or []
        source_names = _keys(source_item, ["unit_name"])
        source_records = [item for item in source_catalog
                          if is_validated_source_applicable(item, cohort)
                          and _keys(item, ["unit_name"]) & source_names]
        if len(source_records) == 1:
            source_keys = _keys(source_records[0], [spec["source_key"]])
    if not source_keys:
        return source_result
    target_catalog = catalogs.get(str(spec["target"])) or []
    scoped_targets = [item for item in target_catalog
                      if is_validated_source_applicable(item, cohort)]
    matches = [item for item in scoped_targets
               if _keys(item, spec["target_keys"]) & source_keys]
    if not matches and spec["cardinality"] == "one":
        matches = [item for item in scoped_targets
                   if _declared_alias_span(source_keys, item)]
    if spec["cardinality"] == "many":
        matched_keys = set().union(
            *(_keys(item, spec["target_keys"]) & source_keys for item in matches)
        ) if matches else set()
        missing_keys = source_keys - matched_keys
        if missing_keys:
            return {
                "lookup_type": source_lookup,
                "relationship_status": "target_unavailable",
                "missing_target_keys": sorted(missing_keys),
                "result": source_result.get("result"),
                "sub_lookups": [source_result],
                "cohort": normalize_cohort(cohort),
                "content_type": "catalog_relationship",
            }
    if spec["cardinality"] == "one" and len(matches) > 1:
        return {
            "lookup_type": source_lookup,
            "needs_clarification": True,
            "clarification_question": "Có nhiều hồ sơ liên hệ phù hợp. Bạn vui lòng xác định đơn vị cụ thể.",
            "content_type": "structured_lookup_clarification",
            "cohort": cohort,
        }
    if not matches:
        return {
            "lookup_type": source_lookup,
            "relationship_status": "target_unavailable",
            "missing_field": sorted(fields_needed),
            "result": source_result.get("result"),
            "sub_lookups": [source_result],
            "cohort": normalize_cohort(cohort),
            "content_type": "catalog_relationship",
        }
    # Matching was completed above by exact catalog identities. Formatting
    # each single-record result cannot introduce another target.
    targets = [office_lookup(
        str(source_item.get("unit_name") or source_item.get("faculty_name") or "catalog"),
        [match], candidate_text=str(match.get("unit_name") or match.get("service") or
                                    match.get("service_id") or "catalog"),
        cohort=cohort, top_k=1, model=None,
    ) for match in matches]
    targets = [target for target in targets if target is not None]
    return {
        "lookup_type": source_lookup,
        "relationship_status": "resolved",
        "requested_field": requested_field,
        "result": {"source": source_item, "targets": [target["result"][0] for target in targets]},
        "sub_lookups": [source_result, *targets],
        "cohort": normalize_cohort(cohort),
        "content_type": "catalog_relationship",
    }
