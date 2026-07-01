from __future__ import annotations

import re
from typing import Any

from .directory_parser import is_faculty_heading
from .text_utils import get_pages_by_type, normalize_text


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


def extract_program_directory(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Trích xuất ngành đào tạo từ layout ngành trong từng sổ tay."""
    target_pages = get_pages_by_type(pages, "faculty_program_directory")
    records: list[dict[str, Any]] = []
    current_program: dict[str, Any] | None = None
    current_faculty: str | None = None
    record_counter = 1

    for page in target_pages:
        page_number = page["page_number"]

        for line in _lines_from_page(page):
            if is_faculty_heading(line):
                _close_program(current_program, records)
                current_program = None
                current_faculty = normalize_text(line)
                continue

            program_name = _program_heading(line)
            if program_name:
                _close_program(current_program, records)
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
    return records
