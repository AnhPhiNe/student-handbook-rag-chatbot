from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_DOCSTORE_PATH = Path("data/processed/chunks/all_docstore_items.json")
DEFAULT_V7_PATH = Path("data/processed/chunks/v7_child_parent_chunks.json")
DEFAULT_OUTPUT_PATH = Path("data/processed/metadata/table_quality_report.json")
DEFAULT_REGISTRY_PATH = Path("data/processed/tables/structured_tables_registry.json")
DEFAULT_DIRECTORY_DIR = Path("data/processed/directories")
DIRECTORY_CATALOG_NAMES = (
    "student_service_directory",
    "student_office_profiles",
    "student_faculty_profiles",
    "program_directory",
)
ALLOWED_REGULATION_TABLE_TYPES = {
    "scoring",
    "study_duration",
    "scholarship",
    "foreign_language",
    "conduct",
}

TABLE_SIGNAL_PATTERNS = [
    r"\bTT\b.*\bNgôn\s*ngữ\b",
    r"\bChứng\s*chỉ\b.*\bTương\s*đương\s*bậc\b",
    r"\bTOEFL\b|\bIELTS\b|\bTOEIC\b|\bHSK\b|\bJLPT\b|\bTOPIK\b",
    r"\bThang\s*điểm\s*10\b.*\bThang\s*điểm\s*chữ\b",
    r"\bThời\s*gian\s*học\s*tập\s*chuẩn\b.*\btối\s*đa\b",
    r"\bXếp\s*loại\b.*\bhọc\s*bổng\b",
    r"\bPhân\s*loại\b.*\brèn\s*luyện\b",
]
BOUNDARY_SIGNATURE_PATTERNS = (
    r"^Nơi nhận:\s*$",
    r"^TM\.\s*CHÍNH PHỦ\s*$",
    r"^HIỆU TRƯỞNG\s*$",
)
BOUNDARY_DOCUMENT_PATTERNS = (
    r"^BỘ GIÁO DỤC VÀ ĐÀO TẠO\s*$",
    r"^THÔNG BÁO\s*$",
)


def load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _metadata(item: dict[str, Any]) -> dict[str, Any]:
    value = item.get("metadata")
    return value if isinstance(value, dict) else {}


def _cohort(item: dict[str, Any]) -> str:
    return str(item.get("cohort") or _metadata(item).get("cohort") or "")


def _document_id(item: dict[str, Any]) -> str:
    return str(item.get("document_id") or _metadata(item).get("document_id") or "")


def _article(item: dict[str, Any]) -> str:
    return str(_metadata(item).get("article") or "")


def _valid_structured_tables(item: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        table
        for table in item.get("tables") or []
        if isinstance(table, dict)
        and table.get("columns")
        and table.get("rows")
        and all(isinstance(row, dict) for row in table.get("rows") or [])
    ]


def _regex_signals(patterns: list[str], text: str) -> list[str]:
    return [
        pattern
        for pattern in patterns
        if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)
    ]


def _has_boundary_leak(item: dict[str, Any], text: str) -> tuple[bool, list[str]]:
    if not _article(item) or len(text) < 5000:
        return False, []
    signature_hits = [
        match
        for pattern in BOUNDARY_SIGNATURE_PATTERNS
        for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match.start() > 300
    ]
    if not signature_hits:
        return False, []
    signature_start = min(match.start() for match in signature_hits)
    document_hits = [
        pattern
        for pattern in BOUNDARY_DOCUMENT_PATTERNS
        if any(
            match.start() > signature_start + 100
            for match in re.finditer(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        )
    ]
    return bool(document_hits), document_hits


def classify_item(item: dict[str, Any]) -> dict[str, Any] | None:
    text = str(item.get("content") or "")
    if not text:
        return None
    structured_tables = _valid_structured_tables(item)
    table_signals = _regex_signals(TABLE_SIGNAL_PATTERNS, text)
    if structured_tables:
        extraction_status = "structured"
        confidence = 1.0
        signals = [f"structured_tables:{len(structured_tables)}"]
        recommended_action = "keep_regulation_table"
    elif table_signals:
        extraction_status = "flattened"
        confidence = 0.85
        signals = table_signals
        recommended_action = "extract_structured_table"
    else:
        return None
    has_boundary, boundary_signals = _has_boundary_leak(item, text)
    meta = _metadata(item)
    return {
        "_id": item.get("_id"),
        "cohort": _cohort(item),
        "document_id": _document_id(item),
        "article": _article(item),
        "title": meta.get("title") or item.get("title"),
        "source_pages": meta.get("source_pages") or item.get("source_pages") or [],
        "category": "regulation_table",
        "extraction_status": extraction_status,
        "confidence": confidence,
        "signals": signals,
        "recommended_action": recommended_action,
        "content_chars": len(text),
        "boundary_error": has_boundary,
        "boundary_signals": boundary_signals,
        "snippet": " ".join(text.split())[:700],
    }


def build_report(
    docstore_path: Path = DEFAULT_DOCSTORE_PATH,
    v7_path: Path = DEFAULT_V7_PATH,
    registry_path: Path = DEFAULT_REGISTRY_PATH,
    directory_dir: Path = DEFAULT_DIRECTORY_DIR,
) -> dict[str, Any]:
    items = load_json(docstore_path, [])
    if not isinstance(items, list):
        raise ValueError(f"Expected JSON array in {docstore_path}")
    classified = [
        result
        for item in items
        if isinstance(item, dict)
        for result in [classify_item(item)]
        if result is not None
    ]
    category_counts = Counter(item["category"] for item in classified)
    cohort_counts = Counter(
        f"{item['cohort']}::{item['category']}" for item in classified
    )
    boundary_errors = [
        {
            "_id": item.get("_id"),
            "cohort": _cohort(item),
            "document_id": _document_id(item),
            "signals": signals,
        }
        for item in items
        if isinstance(item, dict)
        for has_error, signals in [
            _has_boundary_leak(item, str(item.get("content") or ""))
        ]
        if has_error
    ]

    v7_chunks = load_json(v7_path, [])
    table_like_chunks = [
        chunk
        for chunk in v7_chunks
        if isinstance(chunk, dict)
        and (
            chunk.get("chunk_type") == "table_like_row"
            or (chunk.get("metadata") or {}).get("block_type") == "table_like_row"
        )
    ]
    registry = load_json(registry_path, [])
    registry = registry if isinstance(registry, list) else []
    docstore_ids = {
        str(item.get("_id"))
        for item in items
        if isinstance(item, dict) and item.get("_id")
    }
    missing_source_ids = sorted(
        {
            str(table.get("source_parent_id") or table.get("source_section_id"))
            for table in registry
            if isinstance(table, dict)
            and str(table.get("source_parent_id") or table.get("source_section_id"))
            not in docstore_ids
        }
    )
    invalid_regulation_tables = [
        table.get("table_id")
        for table in registry
        if isinstance(table, dict)
        and (
            table.get("data_category") != "regulation_table"
            or table.get("quality_status") != "approved"
            or table.get("table_type") not in ALLOWED_REGULATION_TABLE_TYPES
        )
    ]
    directory_catalogs: dict[str, Any] = {}
    invalid_directory_records: list[str] = []
    for name in DIRECTORY_CATALOG_NAMES:
        records = load_json(directory_dir / f"{name}.json", [])
        records = records if isinstance(records, list) else []
        directory_catalogs[name] = {
            "count": len(records),
            "cohort_counts": dict(
                sorted(
                    Counter(str(record.get("cohort") or "") for record in records).items()
                )
            ),
        }
        invalid_directory_records.extend(
            f"{name}:{index}"
            for index, record in enumerate(records)
            if not isinstance(record, dict)
            or record.get("data_category") != "directory_table"
            or record.get("quality_status") != "approved"
        )

    return {
        "status": "ok",
        "docstore_path": str(docstore_path),
        "v7_path": str(v7_path),
        "summary": {
            "docstore_item_count": len(items),
            "classified_item_count": len(classified),
            "category_counts": dict(sorted(category_counts.items())),
            "cohort_category_counts": dict(sorted(cohort_counts.items())),
            "v7_table_like_chunk_count": len(table_like_chunks),
            "regulation_table_registry_count": len(registry),
            "directory_table_record_count": sum(
                value["count"] for value in directory_catalogs.values()
            ),
            "boundary_error_count": len(boundary_errors),
            "missing_source_id_count": len(missing_source_ids),
            "invalid_regulation_table_count": len(invalid_regulation_tables),
            "invalid_directory_record_count": len(invalid_directory_records),
        },
        "items": classified,
        "boundary_errors": boundary_errors,
        "directory_catalogs": directory_catalogs,
        "validation": {
            "allowed_categories": ["regulation_table", "directory_table"],
            "missing_source_ids": missing_source_ids,
            "invalid_regulation_tables": invalid_regulation_tables,
            "invalid_directory_records": invalid_directory_records,
            "production_boundary_leak_count": len(boundary_errors),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit the two table categories.")
    parser.add_argument("--docstore-path", type=Path, default=DEFAULT_DOCSTORE_PATH)
    parser.add_argument("--v7-path", type=Path, default=DEFAULT_V7_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--registry-path", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--directory-dir", type=Path, default=DEFAULT_DIRECTORY_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    report = build_report(
        args.docstore_path,
        args.v7_path,
        args.registry_path,
        args.directory_dir,
    )
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
