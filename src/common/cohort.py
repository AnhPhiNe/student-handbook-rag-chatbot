from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


# The only source of truth for supported cohorts. Add a cohort here and the
# normalizer, router schemas, planner schemas, and task-merging regex all see it.
COHORT_REGISTRY: dict[str, dict[str, Any]] = {
    "K48-K49": {
        "aliases": (
            "K48-K49",
            "K48/K49",
            "K48_K49",
            "K48-49",
            "K48/49",
            "K48_49",
            "K48K49",
            "K48",
            "K49",
            "48-49",
            "48/49",
            "48_49",
        ),
        "admission_years": (2022, 2023),
    },
    "K50": {
        "aliases": ("K50",),
        "admission_years": (2024,),
    },
    "K51": {
        "aliases": ("K51",),
        "legacy_aliases": ("K50-K51", "50-51", "K50K51"),
        "admission_years": (2025,),
    },
}


def valid_cohorts(
    registry: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[str, ...]:
    """Return canonical cohort labels in stable registry order."""

    return tuple((registry or COHORT_REGISTRY).keys())


def _alias_key(value: str) -> str:
    return value.strip().upper().replace("_", "-").replace("/", "-").replace(" ", "")


def cohort_alias_map(
    registry: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, str]:
    """Map every declared alias to its canonical cohort."""

    source = registry or COHORT_REGISTRY
    aliases: dict[str, str] = {}
    for canonical, spec in source.items():
        declared = (
            canonical,
            *(spec.get("aliases") or ()),
            *(spec.get("legacy_aliases") or ()),
        )
        aliases.update({_alias_key(str(alias)): canonical for alias in declared})
    return aliases


def cohort_admission_years(
    registry: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, tuple[int, ...]]:
    """Build admission-year metadata from the cohort registry."""

    source = registry or COHORT_REGISTRY
    return {
        canonical: tuple(int(year) for year in (spec.get("admission_years") or ()))
        for canonical, spec in source.items()
    }


def build_cohort_token_regex(
    registry: Mapping[str, Mapping[str, Any]] | None = None,
) -> re.Pattern[str]:
    """Build a query-token regex from declared aliases, escaping every literal."""

    source = registry or COHORT_REGISTRY
    direct_aliases: set[str] = set()
    human_aliases: set[str] = set()
    for canonical, spec in source.items():
        declared = {
            canonical,
            *(str(alias) for alias in (spec.get("aliases") or ())),
            *(str(alias) for alias in (spec.get("legacy_aliases") or ())),
        }
        for alias in declared:
            compact = alias.strip()
            if not compact:
                continue
            if compact.upper().startswith("K"):
                direct_aliases.add(compact)
                human_aliases.add(compact[1:])
            else:
                human_aliases.add(compact)

    direct_pattern = "|".join(
        re.escape(alias) for alias in sorted(direct_aliases, key=len, reverse=True)
    )
    human_pattern = "|".join(
        re.escape(alias) for alias in sorted(human_aliases, key=len, reverse=True)
    )
    alternatives = [
        pattern
        for pattern in (direct_pattern, rf"kh[oó]a\s*(?:{human_pattern})")
        if pattern
    ]
    if not alternatives:
        return re.compile(r"(?!x)x")
    return re.compile(rf"(?<!\w)(?:{'|'.join(alternatives)})(?!\w)", re.IGNORECASE)


# Backward-compatible derived views. Runtime code should prefer the functions
# above so tests or applications can supply an extended registry dynamically.
VALID_COHORTS = set(valid_cohorts())
COHORT_ADMISSION_YEARS = cohort_admission_years()
COHORT_GROUPS = {
    alias: canonical
    for alias, canonical in cohort_alias_map().items()
    if alias not in VALID_COHORTS
}
LEGACY_COHORTS = {
    _alias_key(str(alias)): canonical
    for canonical, spec in COHORT_REGISTRY.items()
    for alias in (spec.get("legacy_aliases") or ())
}


def normalize_cohort(cohort: str | None) -> str | None:
    if not cohort:
        return None

    value = _alias_key(cohort)
    return cohort_alias_map().get(value, value)


def admission_years_for_cohort(cohort: str | None) -> tuple[int, ...]:
    """Return every admission year represented by a normalized cohort label."""

    normalized = normalize_cohort(cohort)
    return cohort_admission_years().get(normalized or "", ())


def resolve_cohort_from_query(query: str, fallback: str | None = None) -> str | None:
    cohort = normalize_cohort(fallback)
    match = re.search(r"(?i)\bk(?:h[oó][aá])?[\s:._-]*k?[\s:._-]*(\d{2})\b", query)
    if match:
        return normalize_cohort(f"K{match.group(1)}")
    return cohort


def extract_cohorts_from_query(query: str) -> list[str]:
    """Extract supported cohort aliases from a query in mention order."""

    extracted: list[str] = []
    supported = set(valid_cohorts())
    for match in build_cohort_token_regex().finditer(query):
        token = re.sub(r"^kh[oó]a\s*", "K", match.group(0), flags=re.IGNORECASE)
        normalized = normalize_cohort(token)
        if normalized in supported and normalized not in extracted:
            extracted.append(normalized)
    return extracted


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

    meta = (
        record_or_table.get("metadata")
        if isinstance(record_or_table.get("metadata"), dict)
        else {}
    )
    applicable_raw = (
        record_or_table.get("applicable_cohorts")
        or meta.get("applicable_cohorts")
        or []
    )
    if isinstance(applicable_raw, list):
        applicable_normalized = {
            normalize_cohort(c) for c in applicable_raw if c is not None
        }
        if norm_target in applicable_normalized:
            return True

    record_cohort = normalize_cohort(
        record_or_table.get("cohort")
        or meta.get("cohort")
        or record_or_table.get("source_cohort")
        or meta.get("source_cohort")
    )
    if not record_cohort or str(record_cohort).lower() in {
        "",
        "all",
        "general",
        "shared",
        "*",
    }:
        return True

    return record_cohort == norm_target


def is_validated_source_applicable(
    record_or_citation: dict[str, Any] | None,
    target_cohort: str | None,
) -> bool:
    """Validate a source before exposing it as evidence for a cohort.

    Same-cohort and shared sources are accepted directly. A source owned by a
    different cohort is accepted only when its cross-cohort applicability was
    explicitly declared and validated during ingestion.
    """

    if not isinstance(record_or_citation, dict):
        return False
    if not is_cohort_applicable(record_or_citation, target_cohort):
        return False

    norm_target = normalize_cohort(target_cohort)
    if not norm_target or str(norm_target).lower() in {
        "",
        "all",
        "general",
        "shared",
        "*",
    }:
        return True

    metadata = (
        record_or_citation.get("metadata")
        if isinstance(record_or_citation.get("metadata"), dict)
        else {}
    )
    source_cohort = normalize_cohort(
        record_or_citation.get("source_cohort")
        or metadata.get("source_cohort")
        or record_or_citation.get("cohort")
        or metadata.get("cohort")
    )
    if not source_cohort:
        return False
    if str(source_cohort).lower() in {
        "all",
        "general",
        "shared",
        "*",
    }:
        return True
    if source_cohort == norm_target:
        return True

    return bool(
        record_or_citation.get("applicability_validated")
        or metadata.get("applicability_validated")
    )
