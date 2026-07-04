from __future__ import annotations

import re
import os
from pathlib import Path
from typing import Any

import yaml

from .directory_parser import clean_heading_name, is_faculty_heading
from .program_faculty_enricher import clean_faculty_name, fold_text
from .text_utils import get_pages_by_type, normalize_text

PROGRAM_OVERRIDES_PATH = Path("configs/program_overrides.yaml")


PROGRAM_HEADING_PATTERNS = [
    re.compile(r"^\s*(?:\d+\.\s*)?Ngành\s+(.+)$"),
    re.compile(r"^\s*NGÀNH\s+(.+)$"),
]

PROGRAM_FALSE_STARTS = (
    "gần ",
    "liên quan",
    "khác ",
    "phù hợp",
)


def _clean_program_name(line: str) -> str:
    cleaned = normalize_text(line)
    cleaned = re.sub(r"^\d+\.\s*", "", cleaned)
    cleaned = re.sub(r"^(?:Ngành|NGÀNH)\s+", "", cleaned)
    return cleaned.strip()


def _program_heading(line: str) -> str | None:
    line = normalize_text(line)
    if len(line) > 120:
        return None

    for pattern in PROGRAM_HEADING_PATTERNS:
        match = pattern.match(line)
        if not match:
            continue
        program_name = _clean_program_name(match.group(0))
        if _looks_like_program_name(program_name):
            return program_name

    return None


def _looks_like_program_name(program_name: str) -> bool:
    if not program_name:
        return False
    lower = program_name.lower()
    if lower.startswith(PROGRAM_FALSE_STARTS):
        return False
    if len(program_name.split()) > 12:
        return False
    return True


def _lines_from_page(page: dict[str, Any]) -> list[str]:
    text = normalize_text(page.get("text", ""))
    return [line.strip() for line in text.splitlines() if line.strip()]


def _load_implicit_program_rules(
    cohort: str | None,
    path: Path = PROGRAM_OVERRIDES_PATH,
) -> dict[str, list[str]]:
    if not cohort or not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    by_cohort = config.get("implicit_programs_by_cohort") or {}
    cohort_rules = by_cohort.get(cohort) or {}
    if not isinstance(cohort_rules, dict):
        return {}

    normalized_rules: dict[str, list[str]] = {}
    for faculty_name, program_names in cohort_rules.items():
        if isinstance(program_names, str):
            program_names = [program_names]
        if not isinstance(program_names, list):
            continue
        normalized_rules[fold_text(clean_faculty_name(str(faculty_name)))] = [
            str(program_name)
            for program_name in program_names
            if str(program_name).strip()
        ]
    return normalized_rules


def _close_program(
    current: dict[str, Any] | None,
    records: list[dict[str, Any]],
) -> None:
    if not current:
        return
    raw_text = normalize_text("\n".join(current.pop("_raw_lines", [])))
    if not raw_text:
        return
    current["raw_text"] = raw_text
    current["summary"] = current.get("program_name", "")
    current["needs_manual_review"] = not bool(raw_text and current.get("source_pages"))
    records.append(current)


def _append_implicit_programs(
    *,
    faculty_name: str | None,
    faculty_lines: list[str],
    faculty_pages: list[int],
    implicit_rules: dict[str, list[str]],
    existing_programs: set[tuple[str, str]],
    records: list[dict[str, Any]],
    record_counter: int,
) -> int:
    if not faculty_name or not faculty_lines or not faculty_pages:
        return record_counter

    faculty_key = fold_text(clean_faculty_name(faculty_name))
    program_names = implicit_rules.get(faculty_key, [])
    if not program_names:
        return record_counter

    raw_text = normalize_text("\n".join(faculty_lines))
    if not raw_text:
        return record_counter

    for program_name in program_names:
        program_key = fold_text(program_name)
        if (faculty_key, program_key) in existing_programs:
            continue
        records.append(
            {
                "record_id": f"program_{record_counter}",
                "content_type": "program_directory",
                "program_name": program_name,
                "faculty_name": clean_faculty_name(faculty_name),
                "source_pages": list(dict.fromkeys(faculty_pages)),
                "raw_text": raw_text,
                "summary": program_name,
                "extraction_method": "implicit_faculty_program_rule",
            }
        )
        existing_programs.add((faculty_key, program_key))
        record_counter += 1

    return record_counter


def extract_program_directory(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Trích xuất ngành đào tạo từ layout ngành trong từng sổ tay."""
    target_pages = get_pages_by_type(pages, "faculty_program_directory")
    implicit_rules = _load_implicit_program_rules(os.environ.get("COHORT"))
    records: list[dict[str, Any]] = []
    current_program: dict[str, Any] | None = None
    current_faculty: str | None = None
    current_faculty_lines: list[str] = []
    current_faculty_pages: list[int] = []
    existing_programs: set[tuple[str, str]] = set()
    record_counter = 1

    for page in target_pages:
        page_number = page["page_number"]

        for line in _lines_from_page(page):
            if is_faculty_heading(line):
                _close_program(current_program, records)
                record_counter = _append_implicit_programs(
                    faculty_name=current_faculty,
                    faculty_lines=current_faculty_lines,
                    faculty_pages=current_faculty_pages,
                    implicit_rules=implicit_rules,
                    existing_programs=existing_programs,
                    records=records,
                    record_counter=record_counter,
                )
                current_program = None
                current_faculty = clean_heading_name(line)
                current_faculty_lines = [line]
                current_faculty_pages = [page_number]
                continue

            if current_faculty:
                current_faculty_lines.append(line)
                if page_number not in current_faculty_pages:
                    current_faculty_pages.append(page_number)

            program_name = _program_heading(line)
            if program_name:
                _close_program(current_program, records)
                faculty_key = fold_text(clean_faculty_name(current_faculty))
                existing_programs.add((faculty_key, fold_text(program_name)))
                current_program = {
                    "record_id": f"program_{record_counter}",
                    "content_type": "program_directory",
                    "program_name": program_name,
                    "faculty_name": current_faculty,
                    "source_pages": [page_number],
                    "_raw_lines": [line],
                }
                record_counter += 1
                continue

            if current_program:
                current_program["_raw_lines"].append(line)
                if page_number not in current_program["source_pages"]:
                    current_program["source_pages"].append(page_number)

    _close_program(current_program, records)
    record_counter = _append_implicit_programs(
        faculty_name=current_faculty,
        faculty_lines=current_faculty_lines,
        faculty_pages=current_faculty_pages,
        implicit_rules=implicit_rules,
        existing_programs=existing_programs,
        records=records,
        record_counter=record_counter,
    )
    return records
