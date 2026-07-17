from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

import fitz
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.extraction.directory_parser import extract_office_directory
from src.chunking.regulation_table_extractor import (
    extract_pass_fail_ungraded_table,
    table_metadata_payload,
)


DOCSTORE_PATH = Path("data/processed/chunks/all_docstore_items.json")
TABLE_DIR = Path("data/processed/tables")
DIRECTORY_DIR = Path("data/processed/directories")
RAW_DIR = Path("data/raw")
OFFICE_ALIAS_CONFIG_PATH = Path("configs/office_aliases.yaml")
OFFICE_SOURCE_CONFIGS = (
    ("K48-K49", Path("configs/document_sections.yaml")),
    ("K50", Path("configs/document_sections_k50.yaml")),
    ("K51", Path("configs/document_sections_k51.yaml")),
)

STRUCTURED_TABLE_REGISTRY_PATH = TABLE_DIR / "structured_tables_registry.json"
FOREIGN_LANGUAGE_TABLE_PATH = TABLE_DIR / "foreign_language_equivalency_table.json"
SCORING_TABLES_PATH = TABLE_DIR / "scoring_tables.json"
STRUCTURED_DATA_MANIFEST_PATH = Path("data/processed/metadata/structured_data_manifest.json")
STUDENT_SERVICE_DIRECTORY_PATH = DIRECTORY_DIR / "student_service_directory.json"
STUDENT_OFFICE_PROFILES_PATH = DIRECTORY_DIR / "student_office_profiles.json"
STUDENT_FACULTY_PROFILES_PATH = DIRECTORY_DIR / "student_faculty_profiles.json"
PROGRAM_DIRECTORY_PATH = DIRECTORY_DIR / "program_directory.json"

REGULATION_TABLE_TYPE_MAP = {
    "study_duration": "study_duration",
    "foreign_language": "foreign_language",
    "foreign_language_equivalency": "foreign_language",
    "scholarship": "scholarship",
    "scholarship_classification": "scholarship",
    "conduct": "conduct",
    "conduct_classification": "conduct",
    "grade_scale": "scoring",
    "grade_10_to_letter": "scoring",
    "pass_fail_ungraded": "scoring",
    "letter_to_grade4": "scoring",
    "letter_to_grade_4": "scoring",
    "academic_classification": "scoring",
}

BOUNDARY_SIGNATURE_PATTERNS = (
    re.compile(r"^Nơi nhận:\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^TM\.\s*CHÍNH PHỦ\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^HIỆU TRƯỞNG\s*$", re.IGNORECASE | re.MULTILINE),
)
BOUNDARY_DOCUMENT_HEADER = re.compile(
    r"^BỘ GIÁO DỤC VÀ ĐÀO TẠO\s*$", re.IGNORECASE | re.MULTILINE
)
BOUNDARY_NOTICE_HEADER = re.compile(r"^THÔNG BÁO\s*$", re.IGNORECASE | re.MULTILINE)
HANDBOOK_FOOTER_PATTERN = re.compile(
    r"^(?:\d+\s+)?SỔ TAY SINH VIÊN KHÓA\s+\d+(?:\s+\d+)?\s*$",
    re.IGNORECASE,
)

FOREIGN_LANGUAGE_SECTION_MARKER = "QuyDinhChuanDauRaNgoaiNgu"
FOREIGN_LANGUAGE_COLUMNS = [
    "language",
    "certificate",
    "level_or_scale",
    "equivalent_level_3",
    "equivalent_level_4",
]
FOREIGN_LANGUAGE_ROWS = [
    {
        "language": "Tiếng Anh",
        "certificate": "TOEFL iBT",
        "level_or_scale": "TOEFL iBT",
        "equivalent_level_3": "30 - 45",
        "equivalent_level_4": "46 - 93",
    },
    {
        "language": "Tiếng Anh",
        "certificate": "TOEFL ITP",
        "level_or_scale": "TOEFL ITP",
        "equivalent_level_3": "450 - 499",
        "equivalent_level_4": "",
    },
    {
        "language": "Tiếng Anh",
        "certificate": "IELTS",
        "level_or_scale": "IELTS",
        "equivalent_level_3": "4.0 - 5.0",
        "equivalent_level_4": "5.5 - 6.5",
    },
    {
        "language": "Tiếng Anh",
        "certificate": "Cambridge Assessment English / Linguaskill",
        "level_or_scale": "Cambridge/Linguaskill",
        "equivalent_level_3": "B1 Preliminary; B1 Business Preliminary; Linguaskill 140 - 159",
        "equivalent_level_4": "B2 First; B2 Business Vantage; Linguaskill 160 - 179",
    },
    {
        "language": "Tiếng Anh",
        "certificate": "TOEIC (4 kỹ năng)",
        "level_or_scale": "Nghe, Đọc, Nói, Viết",
        "equivalent_level_3": "Nghe 275 - 399; Đọc 275 - 384; Nói 120 - 159; Viết 120 - 149",
        "equivalent_level_4": "Nghe 400 - 489; Đọc 385 - 454; Nói 160 - 179; Viết 150 - 179",
    },
    {
        "language": "Tiếng Pháp",
        "certificate": "TCF / DELF",
        "level_or_scale": "TCF, DELF",
        "equivalent_level_3": "TCF 300 - 399; DELF B1",
        "equivalent_level_4": "TCF 400 - 499; DELF B2",
    },
    {
        "language": "Tiếng Trung Quốc",
        "certificate": "Hanyu Shuiping Kaoshi (HSK)",
        "level_or_scale": "HSK",
        "equivalent_level_3": "HSK bậc 3",
        "equivalent_level_4": "HSK bậc 4",
    },
    {
        "language": "Tiếng Nhật",
        "certificate": "Japanese Language Proficiency Test (JLPT)",
        "level_or_scale": "JLPT",
        "equivalent_level_3": "N4",
        "equivalent_level_4": "N3",
    },
    {
        "language": "Tiếng Nga",
        "certificate": "ТРКИ - Тест по русскому языку как иностранному",
        "level_or_scale": "ТРКИ",
        "equivalent_level_3": "ТРКИ-1",
        "equivalent_level_4": "ТРКИ-2",
    },
    {
        "language": "Tiếng Hàn Quốc",
        "certificate": "TOPIK II",
        "level_or_scale": "TOPIK II",
        "equivalent_level_3": "TOPIK II (120)",
        "equivalent_level_4": "TOPIK II (150)",
    },
]

def load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@lru_cache(maxsize=1)
def load_office_alias_config() -> dict[str, Any]:
    if not OFFICE_ALIAS_CONFIG_PATH.is_file():
        return {"unit_aliases": {}, "service_aliases": []}
    value = yaml.safe_load(OFFICE_ALIAS_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    return value if isinstance(value, dict) else {"unit_aliases": {}, "service_aliases": []}


def normalize_text(value: Any) -> str:
    text = str(value or "").lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", text)
    text = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    text = re.sub(r"[^a-z0-9@._+-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def metadata(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("metadata")
    return value if isinstance(value, dict) else {}


def cohort_of(item: dict[str, Any]) -> str:
    meta = metadata(item)
    return str(item.get("cohort") or meta.get("cohort") or "")


def document_id_of(item: dict[str, Any]) -> str:
    meta = metadata(item)
    return str(item.get("document_id") or meta.get("document_id") or "")


def _layout_cleaned(text: str) -> str:
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if HANDBOOK_FOOTER_PATTERN.fullmatch(stripped):
            continue
        if normalize_text(stripped) in {"ma qr", "qr"}:
            continue
        lines.append(line.rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def _supplement_title(text: str, index: int) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    title_positions = [
        position
        for position, line in enumerate(lines)
        if any(
            marker in line.upper()
            for marker in ("THÔNG BÁO", "QUY TRÌNH", "QUY ĐỊNH", "HƯỚNG DẪN")
        )
    ]
    if title_positions:
        position = min(title_positions)
        return compact_text(" ".join(lines[position : position + 3]))[:240]
    return compact_text(" ".join(lines[:3]))[:240] or f"Văn bản bổ sung {index}"


def _is_excluded_boundary_content(text: str) -> bool:
    normalized = normalize_text(text)
    return "quy trinh xet sinh vien vao o ky tuc xa" in normalized


def _supplement_starts(text: str, tail_start: int) -> list[int]:
    starts = [
        match.start()
        for match in BOUNDARY_DOCUMENT_HEADER.finditer(text)
        if match.start() >= tail_start
    ]
    for match in BOUNDARY_NOTICE_HEADER.finditer(text):
        if match.start() < tail_start:
            continue
        previous_header = max((start for start in starts if start < match.start()), default=-1)
        if previous_header < 0 or match.start() - previous_header > 700:
            starts.append(match.start())
    return sorted(set([tail_start, *starts]))


def repair_boundary_leaks(
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Detach documents appended after a regulation article into stable parents."""
    existing_supplements = [
        item
        for item in items
        if (
            isinstance(item, dict)
            and metadata(item).get("boundary_repair_generated")
            and not _is_excluded_boundary_content(str(item.get("content") or ""))
        )
    ]
    base_items = [
        item
        for item in items
        if not (
            isinstance(item, dict)
            and metadata(item).get("boundary_repair_generated")
        )
    ]
    supplements: list[dict[str, Any]] = list(existing_supplements)
    repaired_parent_ids: list[str] = []

    for item in base_items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("content") or "")
        if len(text) < 5000 or not metadata(item).get("article"):
            continue

        signature_positions = [
            match.start()
            for pattern in BOUNDARY_SIGNATURE_PATTERNS
            for match in pattern.finditer(text)
            if match.start() > 300
        ]
        if not signature_positions:
            continue
        signature_start = min(signature_positions)
        document_starts = [
            match.start()
            for pattern in (BOUNDARY_DOCUMENT_HEADER, BOUNDARY_NOTICE_HEADER)
            for match in pattern.finditer(text)
            if match.start() > signature_start + 100
        ]
        if not document_starts:
            continue

        tail_start = min(document_starts)
        starts = _supplement_starts(text, tail_start)
        starts.append(len(text))
        parent_id = str(item.get("_id") or "")
        parent_meta = dict(metadata(item))
        supplements = [
            supplement
            for supplement in supplements
            if metadata(supplement).get("boundary_source_parent_id") != parent_id
        ]
        generated_for_parent = 0
        for index, (start, end) in enumerate(zip(starts, starts[1:]), start=1):
            segment = _layout_cleaned(text[start:end])
            if len(segment) < 300 or _is_excluded_boundary_content(segment):
                continue
            generated_for_parent += 1
            supplement_id = f"{parent_id}_Supplement_{generated_for_parent:02d}"
            supplement_meta = {
                **parent_meta,
                "source_type": "supplemental_regulation",
                "content_type": "regulation_text",
                "part": None,
                "chapter": None,
                "article": None,
                "title": _supplement_title(segment, generated_for_parent),
                "has_table": False,
                "boundary_repair_generated": True,
                "boundary_source_parent_id": parent_id,
                "boundary_segment_index": generated_for_parent,
                "boundary_quality_status": "approved",
            }
            supplements.append(
                {
                    "_id": supplement_id,
                    "content": segment,
                    "normalized_content": segment,
                    "tables": [],
                    "highlights": [],
                    "metadata": supplement_meta,
                    "cohort": cohort_of(item),
                    "document_id": document_id_of(item),
                }
            )

        if generated_for_parent:
            cleaned_main = _layout_cleaned(text[:signature_start])
            item["content"] = cleaned_main
            item["normalized_content"] = cleaned_main
            parent_meta["boundary_repaired"] = True
            parent_meta["boundary_quality_status"] = "approved"
            parent_meta["detached_supplement_count"] = generated_for_parent
            item["metadata"] = parent_meta
            repaired_parent_ids.append(parent_id)

    supplement_counts: dict[str, int] = {}
    for supplement in supplements:
        source_parent_id = str(metadata(supplement).get("boundary_source_parent_id") or "")
        if source_parent_id:
            supplement_counts[source_parent_id] = supplement_counts.get(source_parent_id, 0) + 1
    for item in base_items:
        item_meta = metadata(item)
        if not item_meta.get("boundary_repaired"):
            continue
        item_meta["detached_supplement_count"] = supplement_counts.get(
            str(item.get("_id") or ""), 0
        )
        item["metadata"] = item_meta

    return base_items + supplements, {
        "repaired_parent_count": len(repaired_parent_ids),
        "repaired_parent_ids": repaired_parent_ids,
        "supplement_parent_count": len(supplements),
    }


def is_foreign_language_article_8(item: dict[str, Any]) -> bool:
    item_id = str(item.get("_id") or "")
    article = str(metadata(item).get("article") or "")
    return FOREIGN_LANGUAGE_SECTION_MARKER in item_id and article.startswith("Điều 8")


def make_foreign_language_table(item: dict[str, Any]) -> dict[str, Any]:
    cohort = cohort_of(item)
    item_id = str(item.get("_id") or "")
    source_pages = metadata(item).get("source_pages") or []
    table_id = f"{cohort.replace('-', '_')}_foreign_language_equivalency_dieu8"
    table = {
        "table_id": table_id,
        "table_name": "Bảng tham chiếu quy đổi chứng chỉ ngoại ngữ tương đương bậc 3 và bậc 4",
        "table_kind": "foreign_language_equivalency",
        "table_type": "foreign_language",
        "table_subtype": "foreign_language_equivalency",
        "data_category": "regulation_table",
        "columns": FOREIGN_LANGUAGE_COLUMNS,
        "rows": [dict(row) for row in FOREIGN_LANGUAGE_ROWS],
        "source_pages": source_pages,
        "source_parent_id": item_id,
        "source_section_id": item_id,
        "cohort": cohort,
        "document_id": document_id_of(item),
        "review_status": "approved",
        "quality_status": "approved",
        "note": "Structured from the foreign-language equivalency appendix attached to Article 8.",
    }
    if metadata(item).get("derived_from_cohort"):
        table["derived_from"] = {
            "cohort": metadata(item).get("derived_from_cohort"),
            "document_id": metadata(item).get("derived_from_document_id"),
            "source_section_id": metadata(item).get("derived_from_parent_section_id"),
        }
    return table


def attach_foreign_language_tables(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for item in items:
        if (
            not isinstance(item, dict)
            or metadata(item).get("synthetic_source")
            or not is_foreign_language_article_8(item)
        ):
            continue
        table = make_foreign_language_table(item)
        existing = [
            table
            for table in item.get("tables") or []
            if isinstance(table, dict)
            and table.get("table_kind") != "foreign_language_equivalency"
            and table.get("table_subtype") != "foreign_language_equivalency"
        ]
        item["tables"] = existing + [table]
        meta = dict(metadata(item))
        meta["has_table"] = True
        meta["table_quality_status"] = "approved"
        item["metadata"] = meta
    return items


def _table_fingerprint(record: dict[str, Any]) -> str:
    payload = {
        "cohort": record.get("cohort"),
        "document_id": record.get("document_id"),
        "table_type": record.get("table_type"),
        "table_subtype": record.get("table_subtype"),
        "columns": record.get("columns") or [],
        "rows": record.get("rows") or [],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _find_scholarship_parent(
    items: list[dict[str, Any]], cohort: str
) -> dict[str, Any] | None:
    for item in items:
        if not isinstance(item, dict) or cohort_of(item) != cohort:
            continue
        title = normalize_text(metadata(item).get("title"))
        if "tieu chuan muc quy hoc bong khuyen khich hoc tap" in title:
            return item
    return None


def _build_scholarship_records(
    items: list[dict[str, Any]], scoring_tables_path: Path
) -> list[dict[str, Any]]:
    scoring_tables = load_json(scoring_tables_path, [])
    records: list[dict[str, Any]] = []
    for table in scoring_tables if isinstance(scoring_tables, list) else []:
        if not isinstance(table, dict) or table.get("table_id") != "scholarship_classification":
            continue
        cohort = str(table.get("cohort") or "")
        parent = _find_scholarship_parent(items, cohort)
        if parent is None:
            continue
        parent_meta = metadata(parent)
        records.append(
            {
                "table_id": "scholarship_classification",
                "data_category": "regulation_table",
                "table_type": "scholarship",
                "table_subtype": "scholarship_classification",
                "table_name": table.get("table_name"),
                "cohort": cohort,
                "document_id": document_id_of(parent),
                "source_parent_id": parent.get("_id"),
                "source_section_id": parent.get("_id"),
                "title": parent_meta.get("title"),
                "columns": table.get("columns") or [],
                "rows": table.get("rows") or [],
                "source_pages": parent_meta.get("source_pages") or [],
                "derived_from": table.get("derived_from"),
                "quality_status": "approved",
                "used_by_runtime": True,
            }
        )
    return records


def attach_scholarship_tables(
    items: list[dict[str, Any]], scoring_tables_path: Path
) -> None:
    for record in _build_scholarship_records(items, scoring_tables_path):
        parent_id = str(record.get("source_parent_id") or "")
        parent = next(
            (
                item
                for item in items
                if isinstance(item, dict) and str(item.get("_id") or "") == parent_id
            ),
            None,
        )
        if parent is None:
            continue
        tables = [
            table
            for table in parent.get("tables") or []
            if not (
                isinstance(table, dict)
                and str(table.get("table_subtype") or table.get("table_type") or "")
                == "scholarship_classification"
            )
        ]
        parent["tables"] = [*tables, dict(record)]
        parent_meta = dict(metadata(parent))
        parent_meta["has_table"] = True
        parent_meta["table_quality_status"] = "approved"
        parent["metadata"] = parent_meta


def build_registry(
    items: list[dict[str, Any]],
    scoring_tables_path: Path = SCORING_TABLES_PATH,
) -> list[dict[str, Any]]:
    docstore_ids = {
        str(item.get("_id")) for item in items if isinstance(item, dict) and item.get("_id")
    }
    registry_by_fingerprint: dict[str, dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        meta = metadata(item)
        for table in item.get("tables") or []:
            if not isinstance(table, dict):
                continue
            raw_table_type = str(
                table.get("table_type") or table.get("table_kind") or "table"
            )
            table_subtype = str(table.get("table_subtype") or raw_table_type)
            table_type = REGULATION_TABLE_TYPE_MAP.get(
                table_subtype, REGULATION_TABLE_TYPE_MAP.get(raw_table_type, "")
            )
            if not table_type:
                continue
            cohort = str(table.get("cohort") or cohort_of(item))
            document_id = str(table.get("document_id") or document_id_of(item))
            source_parent_id = (
                table.get("source_parent_id")
                or table.get("source_section_id")
                or item.get("_id")
            )
            if not source_parent_id or str(source_parent_id) not in docstore_ids:
                continue
            table_id = str(table.get("table_id") or f"{source_parent_id}_{table_subtype}")
            table.update(
                {
                    "table_id": table_id,
                    "data_category": "regulation_table",
                    "table_type": table_type,
                    "table_subtype": table_subtype,
                    "cohort": cohort,
                    "document_id": document_id,
                    "source_parent_id": source_parent_id,
                    "source_section_id": source_parent_id,
                    "quality_status": "approved",
                }
            )
            record = {
                "table_id": table_id,
                "data_category": "regulation_table",
                "table_type": table_type,
                "table_subtype": table_subtype,
                "table_name": table.get("table_name"),
                "cohort": cohort,
                "document_id": document_id,
                "source_parent_id": source_parent_id,
                "source_section_id": source_parent_id,
                "title": meta.get("title"),
                "applicability": table.get("applicability"),
                "columns": table.get("columns") or [],
                "rows": table.get("rows") or [],
                "source_pages": table.get("source_pages")
                or meta.get("source_pages")
                or [],
                "quality_status": "approved",
                "derived_from": table.get("derived_from"),
                "used_by_runtime": bool(table.get("lookup_preferred", True)),
            }
            registry_by_fingerprint.setdefault(_table_fingerprint(record), record)

    for record in _build_scholarship_records(items, scoring_tables_path):
        registry_by_fingerprint.setdefault(_table_fingerprint(record), record)
    return sorted(
        registry_by_fingerprint.values(),
        key=lambda record: (
            str(record.get("cohort") or ""),
            str(record.get("table_type") or ""),
            str(record.get("table_id") or ""),
        ),
    )


def attach_pass_fail_ungraded_tables(items: list[dict[str, Any]]) -> int:
    """Attach pass/fail-only tables extracted from authoritative parent text."""

    attached_count = 0
    for item in items:
        if not isinstance(item, dict) or not item.get("_id"):
            continue
        meta = metadata(item)
        source_pages = [
            int(page)
            for page in (meta.get("source_pages") or [])
            if isinstance(page, int) or str(page).isdigit()
        ]
        table = extract_pass_fail_ungraded_table(
            {
                "section_id": str(item["_id"]),
                "title": meta.get("title"),
                "article": meta.get("article"),
            },
            str(item.get("content") or ""),
            source_pages,
        )
        if table is None:
            continue

        tables = [table for table in item.get("tables") or [] if isinstance(table, dict)]
        if any(existing.get("table_id") == table["table_id"] for existing in tables):
            continue
        item["tables"] = [*tables, table_metadata_payload(table)]
        updated_meta = dict(meta)
        updated_meta["has_table"] = True
        updated_meta["table_quality_status"] = "approved"
        item["metadata"] = updated_meta
        attached_count += 1
    return attached_count


def strip_order_prefix(value: Any) -> str:
    return re.sub(r"^\s*\d+\.\s*", "", str(value or "")).strip()


def extract_emails(raw_text: str) -> list[str]:
    return sorted(set(re.findall(r"[A-Za-z0-9._%+-]+@hcmue\.edu\.vn", raw_text)))


def extract_phones(raw_text: str) -> list[str]:
    phones = re.findall(r"\(?0\d{2,3}\)?[ .-]?\d{3,4}[ .-]?\d{3,4}", raw_text)
    return sorted(set(phone.strip() for phone in phones))


def extract_internal_numbers(raw_text: str) -> list[str]:
    numbers: set[str] = set()
    for line in raw_text.splitlines():
        if "nội bộ" not in line.lower() and "noi bo" not in normalize_text(line):
            continue
        numbers.update(re.findall(r"\b\d{2,4}\b", line))
    return sorted(numbers)


def extract_websites(raw_text: str) -> list[str]:
    matches = re.findall(r"(?:https?://)?[A-Za-z0-9.-]+\.hcmue\.edu\.vn", raw_text)
    return sorted(set(match.rstrip(".,;") for match in matches))


def extract_office(raw_text: str) -> str:
    lines = [line.strip(" :") for line in raw_text.splitlines() if line.strip()]
    office_lines: list[str] = []
    capture = False
    for line in lines:
        norm = normalize_text(line)
        if "van phong lam viec" in norm:
            capture = True
            inline_value = re.split(
                r"văn phòng làm việc\s*:?",
                line,
                maxsplit=1,
                flags=re.IGNORECASE,
            )[-1].strip(" :")
            if inline_value and normalize_text(inline_value) != norm:
                office_lines.append(inline_value)
            continue
        if capture and (
            "nhung cong viec" in norm
            or "dien thoai" in norm
            or "email" in norm
            or "website" in norm
            or norm.startswith("nganh ")
            or "co hoi nghe nghiep" in norm
            or "vi tri viec lam" in norm
            or "muc tieu dao tao" in norm
            or "so tay sinh vien khoa" in norm
        ):
            break
        if capture:
            office_lines.append(line)
    return compact_text(" ".join(office_lines))


def extract_responsibilities(raw_text: str) -> list[str]:
    marker = re.search(
        r"Những công việc của đơn vị liên quan đến sinh viên\s*:?",
        raw_text,
        flags=re.IGNORECASE,
    )
    body = raw_text[marker.end() :] if marker else raw_text
    matches = re.findall(
        r"(?:^|\n)\s*[–−-]\s+(.+?)(?=(?:\n\s*[–−-]\s+)|\Z)",
        body,
        flags=re.DOTALL,
    )
    responsibilities = [compact_text(match.strip(" ;.")) for match in matches]
    return [item for item in responsibilities if len(item) >= 12]


def trim_service_source(raw_text: str) -> str:
    markers = [
        r"\n\s*\d+\.\s*Phân hiệu\b",
        r"\n\s*MỘT SỐ CÔNG VIỆC CỦA CÁC PHÒNG",
        r"\n\s*TT\s*\n\s*Nội dung\s*\n\s*Đơn vị\s*\n\s*Liên hệ",
    ]
    cut_at = len(raw_text)
    for pattern in markers:
        match = re.search(pattern, raw_text, flags=re.IGNORECASE)
        if match:
            cut_at = min(cut_at, match.start())
    return raw_text[:cut_at].strip()


def trim_cross_unit_leak(raw_text: str) -> str:
    unit_heading = re.search(
        r"\s+\d+\.\s*(Phong|Trung tam|Vien|Khoa|Ban|Bo mon|Thu vien|Ky tuc xa|Phan hieu)\b",
        normalize_text(raw_text),
        flags=re.IGNORECASE,
    )
    if not unit_heading:
        return raw_text
    normalized_prefix = normalize_text(raw_text)[: unit_heading.start()]
    if not normalized_prefix:
        return raw_text
    # Map the normalized cut approximately back to the original text by ratio.
    cut_ratio = len(normalized_prefix) / max(len(normalize_text(raw_text)), 1)
    cut_at = int(len(raw_text) * cut_ratio)
    return raw_text[:cut_at].strip()


def load_primary_office_records() -> list[dict[str, Any]]:
    """Extract clean office records from the authoritative directory PDF ranges."""
    records: list[dict[str, Any]] = []
    for cohort, config_path in OFFICE_SOURCE_CONFIGS:
        if not config_path.is_file():
            continue
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        sections = [
            section
            for section in config.get("sections") or []
            if section.get("content_type") == "office_directory"
            and "danh sách" in str(section.get("description") or "").lower()
        ]
        source_path = RAW_DIR / str(config.get("file_name") or "")
        if not sections or not source_path.is_file():
            continue

        section = sections[0]
        with fitz.open(source_path) as document:
            pages = [
                {
                    "page_number": page_number,
                    "content_type": "office_directory",
                    "text": document[page_number - 1].get_text(),
                }
                for page_number in range(
                    int(section["page_start"]), int(section["page_end"]) + 1
                )
            ]

        for record in extract_office_directory(pages):
            unit = strip_order_prefix(record.get("unit_name"))
            if not unit:
                continue
            record.update(
                {
                    "record_id": (
                        f"{cohort}_{normalize_text(unit).replace(' ', '_')}"
                    ),
                    "unit_name": unit,
                    "cohort": cohort,
                    "document_id": config.get("document_id"),
                    "source_section": "office_directory",
                    "source_file": config.get("file_name"),
                }
            )
            records.append(record)
    return records


def aliases_for_service(service: str) -> list[str]:
    norm = normalize_text(service)
    aliases: list[str] = []
    for rule in load_office_alias_config().get("service_aliases") or []:
        keyword = str(rule.get("match") or "")
        keyword_aliases = [str(alias) for alias in rule.get("aliases") or []]
        if normalize_text(keyword) in norm or any(
            normalize_text(alias) in norm for alias in keyword_aliases
        ):
            aliases.extend([keyword, *keyword_aliases])
    deduped = []
    seen = set()
    for alias in aliases:
        key = normalize_text(alias)
        if key and key not in seen:
            deduped.append(alias)
            seen.add(key)
    return deduped


def build_student_service_directory(
    directory_dir: Path = DIRECTORY_DIR,
    source_records: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    services: list[dict[str, Any]] = []
    record_groups: list[list[dict[str, Any]]] = []
    if source_records:
        record_groups.append(source_records)
    else:
        for path in sorted(directory_dir.glob("*_office_directory.json")):
            records = load_json(path, [])
            if isinstance(records, list):
                record_groups.append(records)

    source_by_unit: dict[str, list[dict[str, Any]]] = {}
    for records in record_groups:
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            raw_text = trim_cross_unit_leak(
                trim_service_source(str(record.get("raw_text") or ""))
            )
            responsibilities = extract_responsibilities(raw_text) or [
                f"Liên hệ {strip_order_prefix(record.get('unit_name'))}"
            ]
            unit = strip_order_prefix(record.get("unit_name"))
            cohort = str(record.get("cohort") or "")
            source_by_unit.setdefault(normalize_text(unit), []).append(record)
            for index, responsibility in enumerate(responsibilities, start=1):
                service_id = f"{cohort}_{record.get('record_id')}_service_{index}"
                aliases = aliases_for_service(responsibility)
                service_text = compact_text(responsibility)
                summary = f"{service_text} - đơn vị phụ trách: {unit}"
                services.append(
                    {
                        "service_id": service_id,
                        "cohort": cohort,
                        "service": service_text,
                        "aliases": aliases,
                        "unit": unit,
                        "unit_name": unit,
                        "phone": "; ".join(extract_phones(raw_text)),
                        "phones": extract_phones(raw_text),
                        "internal_numbers": extract_internal_numbers(raw_text),
                        "email": "; ".join(extract_emails(raw_text)),
                        "emails": extract_emails(raw_text),
                        "website": "; ".join(extract_websites(raw_text)),
                        "websites": extract_websites(raw_text),
                        "office": extract_office(raw_text),
                        "source_pages": record.get("source_pages") or [],
                        "source_record_id": record.get("record_id"),
                        "document_id": record.get("document_id"),
                        "source_section": record.get("source_section")
                        or "student_service_directory",
                        "content_type": "student_service_directory",
                        "summary": summary,
                        "raw_text": "\n".join(
                            [
                                f"Dịch vụ: {service_text}",
                                f"Đơn vị: {unit}",
                                f"Alias: {', '.join(aliases)}",
                                raw_text,
                            ]
                        ),
                    }
                )
    unit_bindings = load_office_alias_config().get("unit_service_aliases") or {}
    for configured_unit, bindings in unit_bindings.items():
        for record in source_by_unit.get(normalize_text(configured_unit), []):
            raw_text = trim_cross_unit_leak(
                trim_service_source(str(record.get("raw_text") or ""))
            )
            cohort = str(record.get("cohort") or "")
            unit = strip_order_prefix(record.get("unit_name"))
            for index, binding in enumerate(bindings or [], start=1):
                service_text = compact_text(binding.get("service"))
                aliases = _dedupe(
                    [service_text, *(binding.get("aliases") or [])]
                )
                if not service_text or not aliases:
                    continue
                services.append(
                    {
                        "service_id": (
                            f"{cohort}_{record.get('record_id')}_catalog_service_{index}"
                        ),
                        "cohort": cohort,
                        "service": service_text,
                        "aliases": aliases,
                        "unit": unit,
                        "unit_name": unit,
                        "phone": "; ".join(extract_phones(raw_text)),
                        "phones": extract_phones(raw_text),
                        "internal_numbers": extract_internal_numbers(raw_text),
                        "email": "; ".join(extract_emails(raw_text)),
                        "emails": extract_emails(raw_text),
                        "website": "; ".join(extract_websites(raw_text)),
                        "websites": extract_websites(raw_text),
                        "office": extract_office(raw_text),
                        "source_pages": record.get("source_pages") or [],
                        "source_record_id": record.get("record_id"),
                        "document_id": record.get("document_id"),
                        "source_section": "student_service_directory",
                        "content_type": "student_service_directory",
                        "summary": f"{service_text} - đơn vị phụ trách: {unit}",
                        "raw_text": "\n".join(
                            [
                                f"Dịch vụ: {service_text}",
                                f"Đơn vị: {unit}",
                                f"Alias: {', '.join(aliases)}",
                                raw_text,
                            ]
                        ),
                    }
                )
    return services


def _dedupe(values: list[Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = compact_text(value)
        key = normalize_text(text)
        if text and key and key not in seen:
            result.append(text)
            seen.add(key)
    return result


def _extend_unique(target: list[Any], values: Any) -> None:
    if isinstance(values, list):
        target.extend(values)
    elif values:
        target.append(values)


def _generated_unit_aliases(unit: str) -> list[str]:
    normalized = normalize_text(unit)
    tokens = [token for token in normalized.split() if token not in {"va", "cua"}]
    aliases = [unit, normalized]
    if len(tokens) >= 2:
        aliases.append("".join(token[0] for token in tokens).upper())

    prefix_lengths = {
        ("phong",): 1,
        ("ban",): 1,
        ("tram",): 1,
        ("vien",): 1,
        ("truong",): 1,
        ("doan",): 1,
        ("khoa",): 1,
        ("trung", "tam"): 2,
        ("nha", "xuat", "ban"): 3,
    }
    for prefix, length in prefix_lengths.items():
        if tuple(tokens[:length]) != prefix or len(tokens) <= length:
            continue
        remainder = tokens[length:]
        aliases.extend(
            [
                " ".join(remainder),
                "".join(token[0] for token in remainder).upper(),
            ]
        )
    return _dedupe(aliases)


def _curated_unit_aliases(unit: str) -> list[str]:
    unit_norm = normalize_text(unit)
    aliases = load_office_alias_config().get("unit_aliases") or {}
    for configured_unit, values in aliases.items():
        if normalize_text(configured_unit) == unit_norm:
            return [str(value) for value in values or []]
    return []


def _office_aliases(unit: str, services: list[str]) -> list[str]:
    aliases = [*_generated_unit_aliases(unit), *_curated_unit_aliases(unit)]
    for service in services:
        aliases.extend(aliases_for_service(service))
    return _dedupe(aliases)


def build_student_office_profiles(services: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for service in services:
        unit = compact_text(service.get("unit") or service.get("unit_name"))
        if not unit:
            continue
        cohort = compact_text(service.get("cohort"))
        key = (cohort, normalize_text(unit))
        profile = grouped.setdefault(
            key,
            {
                "office_profile_id": f"{cohort}_{normalize_text(unit).replace(' ', '_')}",
                "cohort": cohort,
                "unit": unit,
                "unit_name": unit,
                "aliases": [],
                "services": [],
                "service_ids": [],
                "phones": [],
                "emails": [],
                "websites": [],
                "internal_numbers": [],
                "offices": [],
                "source_pages": [],
                "source_service_ids": [],
                "document_ids": [],
                "content_type": "student_office_profile",
                "source_section": "student_office_profiles",
            },
        )
        _extend_unique(profile["services"], service.get("service"))
        _extend_unique(profile["service_ids"], service.get("service_id"))
        _extend_unique(profile["source_service_ids"], service.get("service_id"))
        _extend_unique(profile["phones"], service.get("phones") or service.get("phone"))
        _extend_unique(profile["emails"], service.get("emails") or service.get("email"))
        _extend_unique(profile["websites"], service.get("websites") or service.get("website"))
        _extend_unique(profile["internal_numbers"], service.get("internal_numbers"))
        _extend_unique(profile["offices"], service.get("office"))
        _extend_unique(profile["source_pages"], service.get("source_pages"))
        _extend_unique(profile["document_ids"], service.get("document_id"))

    profiles: list[dict[str, Any]] = []
    for profile in grouped.values():
        profile["services"] = _dedupe(profile["services"])
        profile["service_ids"] = _dedupe(profile["service_ids"])
        profile["source_service_ids"] = _dedupe(profile["source_service_ids"])
        profile["phones"] = _dedupe(profile["phones"])
        profile["emails"] = _dedupe(profile["emails"])
        profile["websites"] = _dedupe(profile["websites"])
        profile["internal_numbers"] = _dedupe(profile["internal_numbers"])
        profile["offices"] = _dedupe(profile["offices"])
        profile["source_pages"] = sorted(
            {
                int(page)
                for page in profile["source_pages"]
                if str(page).isdigit()
            }
        )
        profile["document_ids"] = _dedupe(profile["document_ids"])
        profile["aliases"] = _office_aliases(profile["unit"], profile["services"])
        profile["phone"] = "; ".join(profile["phones"])
        profile["email"] = "; ".join(profile["emails"])
        profile["website"] = "; ".join(profile["websites"])
        profile["office"] = "; ".join(profile["offices"])
        profile["summary"] = (
            f"{profile['unit']} phu trach: "
            + "; ".join(profile["services"][:8])
        )
        profile["raw_text"] = "\n".join(
            [
                f"Don vi: {profile['unit']}",
                f"Alias: {', '.join(profile['aliases'])}",
                f"Dich vu phu trach: {'; '.join(profile['services'])}",
                f"Email: {profile['email']}",
                f"Dien thoai: {profile['phone']}",
                f"Dia diem: {profile['office']}",
            ]
        )
        profiles.append(profile)
    return sorted(profiles, key=lambda item: (item.get("cohort") or "", item.get("unit") or ""))


def build_student_faculty_profiles(
    directory_dir: Path = DIRECTORY_DIR,
) -> list[dict[str, Any]]:
    records = load_json(directory_dir / "faculty_directory.json", [])
    profiles: list[dict[str, Any]] = []
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict):
            continue
        faculty = strip_order_prefix(record.get("faculty_or_unit_name"))
        cohort = compact_text(record.get("cohort"))
        raw_text = str(record.get("raw_text") or "")
        if not faculty or not cohort:
            continue
        emails = extract_emails(raw_text)
        normalized_raw = normalize_text(raw_text)
        if any(email.lower().startswith("longan.") for email in emails):
            campus = "Phân hiệu Long An"
        elif any(email.lower().startswith("gialai.") for email in emails):
            campus = "Phân hiệu Gia Lai"
        elif "tinh gia lai" in normalized_raw:
            campus = "Phân hiệu Gia Lai"
        else:
            campus = None
        display_unit = f"{faculty} ({campus})" if campus else faculty
        aliases = _generated_unit_aliases(faculty)
        if campus:
            aliases = _dedupe(
                [
                    *aliases,
                    display_unit,
                    f"{faculty} {campus}",
                    f"{faculty} {campus.removeprefix('Phân hiệu ')}",
                ]
            )
        profiles.append(
            {
                "faculty_profile_id": (
                    f"{cohort}_{record.get('record_id')}_"
                    f"{normalize_text(faculty).replace(' ', '_')}"
                ),
                "cohort": cohort,
                "unit": display_unit,
                "unit_name": display_unit,
                "faculty_name": faculty,
                "campus": campus,
                "aliases": aliases,
                "phones": extract_phones(raw_text),
                "emails": emails,
                "websites": extract_websites(raw_text),
                "internal_numbers": extract_internal_numbers(raw_text),
                "office": extract_office(raw_text),
                "source_pages": record.get("source_pages") or [],
                "source_record_id": record.get("record_id"),
                "document_id": record.get("document_id"),
                "content_type": "student_faculty_profile",
                "source_section": "student_faculty_profiles",
                "summary": f"Thông tin liên hệ {faculty}",
                "raw_text": raw_text,
            }
        )
    return sorted(
        profiles,
        key=lambda item: (item.get("cohort") or "", item.get("unit_name") or ""),
    )


def normalize_directory_catalog(
    records: list[dict[str, Any]], catalog_name: str
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    id_fields = (
        "service_id",
        "office_profile_id",
        "faculty_profile_id",
        "record_id",
    )
    for source in records:
        if not isinstance(source, dict):
            continue
        record = dict(source)
        record_id = next(
            (str(record.get(field)) for field in id_fields if record.get(field)), ""
        )
        if not record_id:
            continue
        record["data_category"] = "directory_table"
        record["quality_status"] = "approved"
        record["embedding_enabled"] = False
        record["retrieval_mode"] = "deterministic"
        record["source_provenance"] = {
            "catalog": catalog_name,
            "record_id": record_id,
            "cohort": record.get("cohort"),
            "document_id": record.get("document_id")
            or (record.get("document_ids") or [None])[0],
            "source_pages": record.get("source_pages") or [],
            "source_record_id": record.get("source_record_id"),
        }
        normalized.append(record)
    return sorted(
        normalized,
        key=lambda record: (
            str(record.get("cohort") or ""),
            str(record.get("unit_name") or record.get("program_name") or record.get("service") or ""),
        ),
    )


def _count_by(records: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        value = str(record.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def clean_formula_catalogs(table_dir: Path) -> dict[str, int]:
    cleaned_files = 0
    removed_fields = 0
    for path in table_dir.glob("*formula_rules.json"):
        records = load_json(path, [])
        if not isinstance(records, list):
            continue
        changed = False
        for record in records:
            if isinstance(record, dict) and "calculator_function" in record:
                record.pop("calculator_function", None)
                removed_fields += 1
                changed = True
        if changed:
            save_json(path, records)
            cleaned_files += 1
    return {
        "cleaned_file_count": cleaned_files,
        "removed_calculator_field_count": removed_fields,
    }


def build_structured_data_manifest(
    registry: list[dict[str, Any]],
    directory_catalogs: dict[str, list[dict[str, Any]]],
    docstore_ids: set[str],
) -> dict[str, Any]:
    missing_sources = sorted(
        {
            str(record.get("source_parent_id"))
            for record in registry
            if record.get("source_parent_id") not in docstore_ids
        }
    )
    return {
        "schema_version": "two-table-categories-v1",
        "categories": {
            "regulation_table": {
                "path": str(STRUCTURED_TABLE_REGISTRY_PATH),
                "count": len(registry),
                "table_type_counts": _count_by(registry, "table_type"),
                "cohort_counts": _count_by(registry, "cohort"),
                "qdrant_indexed_from_json": False,
            },
            "directory_table": {
                "catalogs": {
                    name: {
                        "path": str(DIRECTORY_DIR / f"{name}.json"),
                        "count": len(records),
                        "cohort_counts": _count_by(records, "cohort"),
                    }
                    for name, records in directory_catalogs.items()
                },
                "qdrant_indexed_from_json": False,
            },
        },
        "separate_catalogs": {
            "form_template": "data/processed/forms/clean_form_templates.json",
            "formula": "data/processed/tables/formula_rules.json",
        },
        "storage_policy": {
            "qdrant": "regulation_text_only",
            "mongo": "full_parent_regulation_with_structured_tables",
            "structured_json": "local_source_of_truth",
        },
        "validation": {
            "missing_regulation_table_source_count": len(missing_sources),
            "missing_regulation_table_sources": missing_sources,
            "synthetic_citation_source_count": sum(
                1
                for record in registry
                if str(record.get("source_parent_id") or "").startswith("SYN_")
            ),
        },
    }


def build_structured_table_layer(
    docstore_path: Path = DOCSTORE_PATH,
    table_dir: Path = TABLE_DIR,
    directory_dir: Path = DIRECTORY_DIR,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    items = load_json(docstore_path, [])
    if not isinstance(items, list):
        raise ValueError(f"Expected JSON array in {docstore_path}")

    items, boundary_report = repair_boundary_leaks(items)
    attach_foreign_language_tables(items)
    attach_scholarship_tables(items, table_dir / SCORING_TABLES_PATH.name)
    pass_fail_attached_count = attach_pass_fail_ungraded_tables(items)
    registry = build_registry(items, table_dir / SCORING_TABLES_PATH.name)
    pass_fail_table_count = sum(
        record.get("table_subtype") == "pass_fail_ungraded" for record in registry
    )
    foreign_tables = [
        table
        for table in registry
        if table.get("table_type") == "foreign_language"
    ]
    source_records = []
    if directory_dir.resolve() == DIRECTORY_DIR.resolve():
        source_records = load_primary_office_records()
    services = build_student_service_directory(
        directory_dir,
        source_records=source_records,
    )
    if not services:
        existing_services = load_json(directory_dir / STUDENT_SERVICE_DIRECTORY_PATH.name, [])
        services = existing_services if isinstance(existing_services, list) else []
    services = normalize_directory_catalog(services, "student_service_directory")
    office_profiles = normalize_directory_catalog(
        build_student_office_profiles(services), "student_office_profiles"
    )
    faculty_profiles = normalize_directory_catalog(
        build_student_faculty_profiles(directory_dir), "student_faculty_profiles"
    )
    program_directory = normalize_directory_catalog(
        load_json(directory_dir / PROGRAM_DIRECTORY_PATH.name, []), "program_directory"
    )
    docstore_ids = {
        str(item.get("_id")) for item in items if isinstance(item, dict) and item.get("_id")
    }
    directory_catalogs = {
        "student_service_directory": services,
        "student_office_profiles": office_profiles,
        "student_faculty_profiles": faculty_profiles,
        "program_directory": program_directory,
    }
    manifest = build_structured_data_manifest(registry, directory_catalogs, docstore_ids)
    formula_cleanup = clean_formula_catalogs(table_dir)

    save_json(docstore_path, items)
    save_json(table_dir / STRUCTURED_TABLE_REGISTRY_PATH.name, registry)
    save_json(table_dir / FOREIGN_LANGUAGE_TABLE_PATH.name, foreign_tables)
    save_json(directory_dir / STUDENT_SERVICE_DIRECTORY_PATH.name, services)
    save_json(directory_dir / STUDENT_OFFICE_PROFILES_PATH.name, office_profiles)
    save_json(directory_dir / STUDENT_FACULTY_PROFILES_PATH.name, faculty_profiles)
    save_json(directory_dir / PROGRAM_DIRECTORY_PATH.name, program_directory)
    effective_manifest_path = manifest_path or (
        STRUCTURED_DATA_MANIFEST_PATH
        if docstore_path.resolve() == DOCSTORE_PATH.resolve()
        else table_dir.parent / "metadata" / STRUCTURED_DATA_MANIFEST_PATH.name
    )
    save_json(effective_manifest_path, manifest)

    return {
        "status": "ok",
        "docstore_path": str(docstore_path),
        "structured_table_registry_count": len(registry),
        "foreign_language_table_count": len(foreign_tables),
        "foreign_language_rows_per_table": len(FOREIGN_LANGUAGE_ROWS),
        "pass_fail_ungraded_table_count": pass_fail_table_count,
        "pass_fail_ungraded_attached_count": pass_fail_attached_count,
        "student_service_count": len(services),
        "student_office_profile_count": len(office_profiles),
        "student_faculty_profile_count": len(faculty_profiles),
        "program_directory_count": len(program_directory),
        "boundary_repair": boundary_report,
        "formula_cleanup": formula_cleanup,
        "validation": manifest["validation"],
        "manifest_path": str(effective_manifest_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build structured table layer artifacts.")
    parser.add_argument("--docstore-path", type=Path, default=DOCSTORE_PATH)
    parser.add_argument("--table-dir", type=Path, default=TABLE_DIR)
    parser.add_argument("--directory-dir", type=Path, default=DIRECTORY_DIR)
    parser.add_argument("--manifest-path", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_structured_table_layer(
        docstore_path=args.docstore_path,
        table_dir=args.table_dir,
        directory_dir=args.directory_dir,
        manifest_path=args.manifest_path,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
