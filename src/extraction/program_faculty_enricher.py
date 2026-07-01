from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Any

import yaml


PROGRAM_OVERRIDES_PATH = Path("configs/program_overrides.yaml")


def load_program_faculty_overrides(path: Path = PROGRAM_OVERRIDES_PATH) -> dict[str, str]:
    if not path.exists():
        return MANUAL_PROGRAM_FACULTY
    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    overrides = config.get("program_faculty_overrides") or {}
    if not isinstance(overrides, dict):
        return MANUAL_PROGRAM_FACULTY
    return {fold_text(key): str(value) for key, value in overrides.items()}


MANUAL_PROGRAM_FACULTY = {
    "cong nghe giao duc": "Khoa Công nghệ Thông tin",
    "cong nghe thong tin": "Khoa Công nghệ Thông tin",
    "dia ly hoc": "Khoa Địa lý",
    "du lich": "Khoa Địa lý",
    "giao duc chinh tri": "Khoa Giáo dục Chính trị",
    "giao duc cong dan": "Khoa Giáo dục Chính trị",
    "giao duc dac biet": "Khoa Giáo dục Đặc biệt",
    "giao duc hoc": "Khoa Khoa học Giáo dục",
    "giao duc mam non trinh do cao dang va dai hoc": "Khoa Giáo dục Mầm non",
    "giao duc quoc phong an ninh": "Khoa Giáo dục Quốc phòng",
    "giao duc the chat": "Khoa Giáo dục Thể chất",
    "giao duc tieu hoc": "Khoa Giáo dục Tiểu học",
    "hoa hoc": "Khoa Hóa học",
    "ngon ngu han quoc": "Khoa Tiếng Hàn Quốc",
    "ngon ngu nhat": "Khoa Tiếng Nhật",
    "quan ly giao duc": "Khoa Khoa học Giáo dục",
    "sinh hoc ung dung": "Khoa Sinh học",
    "su pham cong nghe": "Khoa Vật lý",
    "su pham dia ly": "Khoa Địa lý",
    "su pham lich su dia ly": "Khoa Địa lý",
    "su pham hoa hoc": "Khoa Hóa học",
    "su pham sinh hoc": "Khoa Sinh học",
    "su pham tin hoc": "Khoa Công nghệ Thông tin",
    "su pham toan hoc": "Khoa Toán – Tin học",
    "su pham toan hoc tieng viet va song ngu viet anh": "Khoa Toán – Tin học",
    "su pham vat ly": "Khoa Vật lý",
    "tam ly hoc": "Khoa Tâm lý học",
    "tam ly hoc giao duc": "Khoa Tâm lý học",
    "toan ung dung": "Khoa Toán – Tin học",
    "vat ly hoc": "Khoa Vật lý",
}


def fold_text(text: str | None) -> str:
    text = str(text or "").lower().replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def clean_faculty_name(name: str | None) -> str:
    return re.sub(r"^\d+\.\s*", "", str(name or "")).strip()


def resolve_faculty_name(
    candidate: str,
    faculty_records: list[dict[str, Any]],
) -> str:
    folded_candidate = fold_text(clean_faculty_name(candidate))
    for faculty in faculty_records:
        faculty_name = clean_faculty_name(faculty.get("faculty_or_unit_name"))
        if fold_text(faculty_name) == folded_candidate:
            return faculty_name
    return clean_faculty_name(candidate)


def enrich_program_faculty_names(
    program_records: list[dict[str, Any]],
    faculty_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Bổ sung khoa phụ trách cho ngành khi sổ tay không ghi trực tiếp cạnh ngành."""
    program_faculty_overrides = load_program_faculty_overrides()
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
