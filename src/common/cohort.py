from __future__ import annotations

import re
from typing import Any


COHORT_GROUPS = {
    "K48": "K48-K49",
    "K49": "K48-K49",
    "K50": "K50",
    "K51": "K51",
}

VALID_COHORTS = {"K48-K49", "K50", "K51"}
COHORT_ADMISSION_YEARS = {
    "K48-K49": (2022, 2023),
    "K50": (2024,),
    "K51": (2025,),
}
LEGACY_COHORTS = {
    "K50-K51": "K51",
    "50-51": "K51",
    "K50K51": "K51",
}


def normalize_cohort(cohort: str | None) -> str | None:
    if not cohort:
        return None

    value = cohort.strip().upper().replace("_", "-")
    if value in {"NULL", "NONE", "N/A", "NA", "UNRESOLVED"}:
        return None
    if value in VALID_COHORTS:
        return value
    if value in LEGACY_COHORTS:
        return LEGACY_COHORTS[value]

    compact = value.replace(" ", "")
    if compact in {"48-49", "K48K49"}:
        return "K48-K49"
    if compact in LEGACY_COHORTS:
        return LEGACY_COHORTS[compact]

    return COHORT_GROUPS.get(value, value)


def admission_years_for_cohort(cohort: str | None) -> tuple[int, ...]:
    """Return every admission year represented by a normalized cohort label."""

    normalized = normalize_cohort(cohort)
    return COHORT_ADMISSION_YEARS.get(normalized or "", ())


def resolve_cohort_from_query(query: str, fallback: str | None = None) -> str | None:
    cohort = normalize_cohort(fallback)
    match = re.search(r"(?i)\bk(?:h[oó][aá])?[\s:._-]*k?[\s:._-]*(\d{2})\b", query)
    if match:
        return normalize_cohort(f"K{match.group(1)}")
    return cohort


def is_cohort_applicable(
    record_or_table: dict[str, Any] | None,
    target_cohort: str | None,
) -> bool:
    """Check if a table or directory record is applicable to target_cohort.

    Supports:
    - Direct cohort match (record.cohort == target_cohort)
    - Multi-cohort list (target_cohort in record.applicable_cohorts)
    - Shared / wildcard cohorts (record.cohort in {'all', 'general', 'shared', '*'})
    - Global queries (target_cohort in {None, '', 'all', 'general', 'shared', '*'})
    """
    if not isinstance(record_or_table, dict):
        return False

    norm_target = normalize_cohort(target_cohort)
    if not norm_target or str(norm_target).lower() in {"", "all", "general", "shared", "*"}:
        return True

    meta = record_or_table.get("metadata") if isinstance(record_or_table.get("metadata"), dict) else {}
    applicable_raw = record_or_table.get("applicable_cohorts") or meta.get("applicable_cohorts") or []
    if isinstance(applicable_raw, list):
        applicable_normalized = {
            normalize_cohort(c)
            for c in applicable_raw
            if c is not None
        }
        if norm_target in applicable_normalized:
            return True

    record_cohort = normalize_cohort(
        record_or_table.get("cohort")
        or meta.get("cohort")
        or record_or_table.get("source_cohort")
        or meta.get("source_cohort")
    )
    if not record_cohort or str(record_cohort).lower() in {"", "all", "general", "shared", "*"}:
        return True

    return record_cohort == norm_target

