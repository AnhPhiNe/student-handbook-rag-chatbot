from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COHORT_REGISTRY_PATH = ROOT / "configs" / "cohort_registry.yaml"

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


@dataclass(frozen=True)
class CohortMention:
    cohort: str
    span: str
    start: int
    end: int


@lru_cache(maxsize=4)
def load_cohort_registry(
    path: str | Path = DEFAULT_COHORT_REGISTRY_PATH,
) -> dict[str, Any]:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    version = payload.get("version")
    cohorts = payload.get("cohorts")
    if not isinstance(version, int) or version < 1:
        raise ValueError("Cohort registry requires a positive integer version.")
    if not isinstance(cohorts, dict) or not cohorts:
        raise ValueError("Cohort registry must define at least one cohort.")
    return payload


def cohort_registry_digest(
    registry: dict[str, Any] | None = None,
) -> str:
    payload = registry or load_cohort_registry()
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def cohort_registry_version(registry: dict[str, Any] | None = None) -> int:
    return int((registry or load_cohort_registry())["version"])


def _normalized_alias(value: str) -> str:
    return (
        value.strip()
        .upper()
        .replace("_", "-")
        .replace("–", "-")
        .replace(" ", "")
    )


def _build_cohort_alias_map(payload: dict[str, Any]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for cohort, spec in payload["cohorts"].items():
        canonical = str(cohort)
        for alias in [canonical, *((spec or {}).get("aliases") or [])]:
            aliases[_normalized_alias(str(alias))] = canonical
    for alias, cohort in (payload.get("legacy_aliases") or {}).items():
        aliases[_normalized_alias(str(alias))] = str(cohort)
    return aliases


@lru_cache(maxsize=1)
def _default_cohort_alias_map() -> dict[str, str]:
    return _build_cohort_alias_map(load_cohort_registry())


def _cohort_alias_map(
    registry: dict[str, Any] | None = None,
) -> dict[str, str]:
    return (
        _build_cohort_alias_map(registry)
        if registry is not None
        else _default_cohort_alias_map()
    )


def normalize_cohort(cohort: Any) -> str | None:
    """Normalize a cohort label and fail closed for non-scalar input."""

    if not isinstance(cohort, str) or not cohort:
        return None

    value = cohort.strip().upper().replace("_", "-")
    if value in {"NULL", "NONE", "N/A", "NA", "UNRESOLVED"}:
        return None
    compact = _normalized_alias(value)
    if compact in {"48-49", "K48K49"}:
        return "K48-K49"
    return _cohort_alias_map().get(compact)


def _cohort_alias_pattern(alias: str) -> re.Pattern[str]:
    compact = _normalized_alias(alias)
    if re.fullmatch(r"K\d{2}", compact):
        body = rf"K\s*{compact[1:]}"
    elif re.fullmatch(r"K\d{2}-K?\d{2}", compact):
        left, right = compact.split("-", 1)
        body = rf"K\s*{left[1:]}\s*[-–]\s*K?\s*{right.removeprefix('K')}"
    else:
        body = re.escape(alias).replace(r"\ ", r"\s*")
    return re.compile(
        rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


@lru_cache(maxsize=4)
def _cohort_patterns(
    registry_path: str = str(DEFAULT_COHORT_REGISTRY_PATH),
) -> tuple[tuple[str, re.Pattern[str]], ...]:
    registry = load_cohort_registry(registry_path)
    patterns: list[tuple[str, re.Pattern[str]]] = []
    seen: set[tuple[str, str]] = set()
    for cohort, spec in registry["cohorts"].items():
        aliases = [str(cohort), *((spec or {}).get("aliases") or [])]
        for alias in sorted({str(value) for value in aliases}, key=len, reverse=True):
            key = (str(cohort), _normalized_alias(alias))
            if key in seen:
                continue
            seen.add(key)
            patterns.append((str(cohort), _cohort_alias_pattern(alias)))
    return tuple(patterns)


def extract_cohort_mentions(value: Any) -> tuple[CohortMention, ...]:
    """Extract literal, registry-backed cohort spans in source order."""

    if not isinstance(value, str) or not value:
        return ()
    candidates: list[CohortMention] = []
    for cohort, pattern in _cohort_patterns():
        for match in pattern.finditer(value):
            candidates.append(
                CohortMention(
                    cohort=cohort,
                    span=match.group(0),
                    start=match.start(),
                    end=match.end(),
                )
            )
    selected: list[CohortMention] = []
    for mention in sorted(
        candidates,
        key=lambda item: (item.start, -(item.end - item.start)),
    ):
        if any(
            mention.start < existing.end and existing.start < mention.end
            for existing in selected
        ):
            continue
        selected.append(mention)
    return tuple(sorted(selected, key=lambda item: item.start))


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

    raw_target = str(target_cohort or "").strip().lower()
    if raw_target in {"", "all", "general", "shared", "*"}:
        return True
    norm_target = normalize_cohort(target_cohort)
    if not norm_target:
        return False

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

