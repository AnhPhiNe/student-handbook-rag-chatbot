from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.common.io import load_yaml
from src.common.text import fold_text


PROGRAM_OVERRIDES_PATH = Path("configs/program_overrides.yaml")

FACULTY_NAME_ALIASES = {
    "khoa tam li hoc": "Khoa Tâm lý học",
    "khoa tam ly hoc": "Khoa Tâm lý học",
}


def load_program_overrides(path: Path = PROGRAM_OVERRIDES_PATH) -> dict[str, Any]:
    """Load curated program corrections: canonical names, faculties and legacy IDs."""

    return load_yaml(path) or {}


def _by_folded_name(mapping: Any) -> dict[str, str]:
    if not isinstance(mapping, dict):
        return {}
    return {fold_text(key): str(value) for key, value in mapping.items()}


def clean_faculty_name(name: str | None) -> str:
    """Normalize a faculty name for output."""

    cleaned = re.sub(r"^\d+\.\s*", "", str(name or "")).strip()
    return FACULTY_NAME_ALIASES.get(fold_text(cleaned), cleaned)


def resolve_faculty_name(
    candidate: str,
    faculty_records: list[dict[str, Any]],
) -> str:
    """Prefer the faculty's name as written in the faculty directory."""

    folded_candidate = fold_text(clean_faculty_name(candidate))
    for faculty in faculty_records:
        faculty_name = clean_faculty_name(faculty.get("faculty_or_unit_name"))
        if fold_text(faculty_name) == folded_candidate:
            return faculty_name
    return clean_faculty_name(candidate)


def enrich_program_faculty_names(
    program_records: list[dict[str, Any]],
    faculty_records: list[dict[str, Any]],
    overrides: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Infer a program faculty only when the handbook omits the direct mapping."""

    if overrides is None:
        overrides = load_program_overrides()
    program_name_overrides = _by_folded_name(overrides.get("program_name_overrides"))
    for program in program_records:
        program_key = fold_text(program.get("program_name"))
        canonical_name = program_name_overrides.get(program_key)
        if canonical_name and canonical_name != program.get("program_name"):
            program["raw_program_name"] = program.get("program_name")
            program["program_name"] = canonical_name
            program["program_name_source"] = "canonical_program_name_rule"
        if program.get("faculty_name"):
            program["faculty_name"] = clean_faculty_name(program.get("faculty_name"))

    program_faculty_overrides = _by_folded_name(
        overrides.get("program_faculty_overrides")
    )
    known_by_program: dict[str, str] = {}
    for program in program_records:
        faculty_name = program.get("faculty_name")
        if faculty_name:
            known_by_program.setdefault(
                fold_text(program.get("program_name")),
                clean_faculty_name(faculty_name),
            )

    for program in program_records:
        if program.get("faculty_name"):
            continue
        program_key = fold_text(program.get("program_name"))
        candidate = known_by_program.get(program_key) or program_faculty_overrides.get(
            program_key
        )
        if not candidate:
            continue
        program["faculty_name"] = resolve_faculty_name(candidate, faculty_records)
        program["faculty_name_source"] = (
            "matched_existing_program"
            if program_key in known_by_program
            else "manual_program_faculty_rule"
        )

    return program_records


def attach_program_legacy_record_ids(
    program_records: list[dict[str, Any]],
    cohort: str | None,
    overrides: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Attach explicit aliases for IDs used by older frozen catalogs."""

    if not cohort:
        return program_records
    if overrides is None:
        overrides = load_program_overrides()
    cohort_map = (overrides.get("legacy_record_ids_by_cohort") or {}).get(cohort)
    aliases_by_name: dict[str, list[str]] = {}
    for program_name, aliases in (cohort_map or {}).items():
        if isinstance(aliases, str):
            aliases = [aliases]
        if isinstance(aliases, list):
            aliases_by_name[fold_text(program_name)] = [
                str(alias).strip() for alias in aliases if str(alias).strip()
            ]

    for program in program_records:
        aliases = aliases_by_name.get(fold_text(program.get("program_name")))
        if not aliases:
            continue
        existing = program.get("legacy_record_ids") or []
        if isinstance(existing, str):
            existing = [existing]
        program["legacy_record_ids"] = list(dict.fromkeys([*existing, *aliases]))
    return program_records
