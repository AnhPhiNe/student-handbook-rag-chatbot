from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOCSTORE_PATH = ROOT / "data" / "processed" / "chunks" / "all_docstore_items.json"
REPORT_PATH = ROOT / "data" / "processed" / "metadata" / "synthetic_retrieval_docs_report.json"

TABLE_DIR = ROOT / "data" / "processed" / "tables"
DIRECTORY_DIR = ROOT / "data" / "processed" / "directories"

COHORT_DOCUMENT_IDS = {
    "K48-K49": "so_tay_sinh_vien_khoa_48_49",
    "K50": "so_tay_sinh_vien_khoa_50",
    "K51": "so_tay_sinh_vien_khoa_51",
}
COHORTS = tuple(COHORT_DOCUMENT_IDS.keys())


def load_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def clean_text(value: Any) -> str:
    text = str(value or "").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def stable_token(value: Any, fallback: str) -> str:
    text = str(value or fallback).strip()
    text = re.sub(r"[^\w.-]+", "_", text, flags=re.UNICODE)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or fallback


def unique_values(values: list[Any]) -> list[Any]:
    output: list[Any] = []
    seen: set[str] = set()
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        output.append(value)
    return output


def normalize_cohorts(values: Any, fallback: str | None = None) -> list[str]:
    raw_values = values if isinstance(values, list) else [values]
    cohorts: list[str] = []
    for value in raw_values:
        text = str(value or "").strip().upper()
        if text in {"K48", "K49", "K48-K49", "K48_49"}:
            cohorts.append("K48-K49")
        elif text in {"K50", "K51"}:
            cohorts.append(text)
    if not cohorts and fallback in COHORT_DOCUMENT_IDS:
        cohorts.append(str(fallback))
    return [cohort for cohort in COHORTS if cohort in set(cohorts)]


def first_non_empty(record: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, "", []):
            return value
    return ""


def list_text(label: str, values: Any) -> str:
    if not values:
        return ""
    if isinstance(values, list):
        rendered = ", ".join(clean_text(value) for value in values if clean_text(value))
    else:
        rendered = clean_text(values)
    return f"{label}: {rendered}" if rendered else ""


def row_lines(rows: list[Any], columns: list[Any] | None = None) -> list[str]:
    output: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            text = clean_text(row)
            if text:
                output.append(text)
            continue
        ordered = [str(column) for column in (columns or []) if str(column) in row]
        if not ordered:
            ordered = list(row.keys())
        parts = []
        for column in ordered:
            value = clean_text(row.get(column))
            if value:
                parts.append(f"{column}: {value}")
        if parts:
            output.append(" | ".join(parts))
    return output


def make_parent(
    *,
    parent_id: str,
    cohort: str,
    content_type: str,
    title: str,
    content: str,
    source_pages: list[Any] | None = None,
    source_section: str | None = None,
    document_id: str | None = None,
    source_record_id: str | None = None,
    tables: list[dict[str, Any]] | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    document_id = document_id or COHORT_DOCUMENT_IDS.get(cohort, "synthetic_sidecar")
    metadata = {
        "parent_section_id": parent_id,
        "cohort": cohort,
        "document_id": document_id,
        "document_title": f"Synthetic retrieval source - {cohort}",
        "content_type": content_type,
        "source_type": "synthetic_sidecar",
        "source_section": source_section or content_type,
        "title": title,
        "article": None,
        "source_pages": source_pages or [],
        "source_record_id": source_record_id,
        "synthetic_source": True,
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    normalized_content = clean_text(content)
    return {
        "_id": parent_id,
        "document_id": document_id,
        "cohort": cohort,
        "content": normalized_content,
        "normalized_content": normalized_content,
        "tables": tables or [],
        "metadata": metadata,
    }


def build_table_parent(
    record: dict[str, Any],
    *,
    content_type: str,
    source_section: str,
    id_prefix: str,
) -> dict[str, Any] | None:
    cohort = str(record.get("cohort") or "")
    if cohort not in COHORT_DOCUMENT_IDS:
        return None
    table_id = stable_token(first_non_empty(record, ["table_id", "rule_id", "record_id"]), "table")
    title = clean_text(first_non_empty(record, ["table_name", "rule_name", "source_title", "title"]))
    if not title:
        title = table_id
    columns = [str(column) for column in record.get("columns") or []]
    rows = record.get("rows") or []
    lines = [
        f"Source type: {content_type}",
        f"Cohort: {cohort}",
        f"Title: {title}",
        list_text("Applicability", record.get("applicability")),
        list_text("Source article", record.get("source_article")),
        list_text("Source title", record.get("source_title")),
        list_text("Columns", columns),
    ]
    lines.extend(f"Row: {line}" for line in row_lines(rows, columns))
    content = "\n".join(line for line in lines if line)
    if not content.strip():
        return None
    parent_id = f"SYN_{cohort}_{id_prefix}_{table_id}"
    table_payload = {
        "table_id": table_id,
        "table_type": record.get("table_type") or record.get("lookup_group") or content_type,
        "table_name": title,
        "columns": columns or sorted({key for row in rows if isinstance(row, dict) for key in row}),
        "rows": rows,
    }
    return make_parent(
        parent_id=parent_id,
        cohort=cohort,
        content_type=content_type,
        title=title,
        content=content,
        source_pages=record.get("source_pages") or [],
        source_section=source_section,
        document_id=record.get("document_id"),
        source_record_id=record.get("record_id") or record.get("table_id") or record.get("rule_id"),
        tables=[table_payload] if rows else [],
        extra_metadata={
            "table_id": record.get("table_id"),
            "table_type": record.get("table_type") or record.get("lookup_group"),
            "source_section_id": record.get("source_section_id"),
            "quality_status": record.get("quality_status"),
            "review_status": record.get("review_status"),
        },
    )


def build_formula_parent(record: dict[str, Any]) -> dict[str, Any] | None:
    cohort = str(record.get("cohort") or "")
    if cohort not in COHORT_DOCUMENT_IDS:
        return None
    rule_id = stable_token(record.get("rule_id") or record.get("record_id"), "formula")
    title = clean_text(record.get("rule_name") or record.get("source_title") or rule_id)
    variables = record.get("variables") or {}
    variable_lines = [
        f"{key}: {clean_text(value)}" for key, value in variables.items() if clean_text(value)
    ]
    lines = [
        "Source type: formula_rule",
        f"Cohort: {cohort}",
        f"Formula: {title}",
        list_text("Formula text", record.get("formula_text")),
        list_text("Calculation type", record.get("calculation_type")),
        list_text("Variables", variable_lines),
        list_text("Source article", record.get("source_article")),
        list_text("Source title", record.get("source_title")),
        list_text("Raw excerpt", record.get("raw_excerpt")),
    ]
    return make_parent(
        parent_id=f"SYN_{cohort}_formula_rule_{rule_id}",
        cohort=cohort,
        content_type="formula_rule",
        title=title,
        content="\n".join(line for line in lines if line),
        source_pages=record.get("source_pages") or [],
        source_section="formula_rule",
        document_id=record.get("document_id"),
        source_record_id=record.get("record_id") or record.get("rule_id"),
        extra_metadata={
            "rule_id": record.get("rule_id"),
            "calculation_type": record.get("calculation_type"),
            "review_status": record.get("review_status"),
        },
    )


def build_threshold_parent(record: dict[str, Any]) -> dict[str, Any] | None:
    cohort = str(record.get("cohort") or "")
    if cohort not in COHORT_DOCUMENT_IDS:
        return None
    rule_id = stable_token(record.get("rule_id") or record.get("record_id"), "threshold")
    title = clean_text(record.get("source_title") or rule_id)
    lines = [
        "Source type: threshold_rule",
        f"Cohort: {cohort}",
        f"Title: {title}",
        list_text("Source article", record.get("source_article")),
    ]
    lines.extend(f"Threshold: {line}" for line in record.get("threshold_lines") or [])
    return make_parent(
        parent_id=f"SYN_{cohort}_threshold_rule_{rule_id}",
        cohort=cohort,
        content_type="threshold_rule",
        title=title,
        content="\n".join(line for line in lines if line),
        source_pages=record.get("source_pages") or [],
        source_section="threshold_rule",
        document_id=record.get("document_id"),
        source_record_id=record.get("record_id") or record.get("rule_id"),
        extra_metadata={"rule_id": record.get("rule_id"), "priority": record.get("priority")},
    )


def build_service_parent(record: dict[str, Any]) -> dict[str, Any] | None:
    cohort = str(record.get("cohort") or "")
    if cohort not in COHORT_DOCUMENT_IDS:
        return None
    service_id = stable_token(record.get("service_id") or record.get("record_id"), "service")
    title = clean_text(record.get("service") or record.get("summary") or service_id)
    lines = [
        "Source type: student_service_directory",
        f"Cohort: {cohort}",
        f"Service: {title}",
        list_text("Aliases", record.get("aliases")),
        list_text("Responsible unit", record.get("unit") or record.get("unit_name")),
        list_text("Email", record.get("emails") or record.get("email")),
        list_text("Phone", record.get("phones") or record.get("phone")),
        list_text("Internal numbers", record.get("internal_numbers")),
        list_text("Website", record.get("websites") or record.get("website")),
        list_text("Office", record.get("office")),
        list_text("Raw text", record.get("raw_text")),
    ]
    return make_parent(
        parent_id=f"SYN_{cohort}_student_service_{service_id}",
        cohort=cohort,
        content_type="student_service_directory",
        title=title,
        content="\n".join(line for line in lines if line),
        source_pages=record.get("source_pages") or [],
        source_section="student_service_directory",
        document_id=record.get("document_id"),
        source_record_id=record.get("service_id") or record.get("record_id"),
        extra_metadata={"service_id": record.get("service_id"), "unit": record.get("unit")},
    )


def build_office_profile_parent(record: dict[str, Any]) -> dict[str, Any] | None:
    cohort = str(record.get("cohort") or "")
    if cohort not in COHORT_DOCUMENT_IDS:
        return None
    profile_id = stable_token(record.get("office_profile_id") or record.get("unit"), "office")
    title = clean_text(record.get("unit") or record.get("unit_name") or profile_id)
    lines = [
        "Source type: student_office_profile",
        f"Cohort: {cohort}",
        f"Unit: {title}",
        list_text("Aliases", record.get("aliases")),
        list_text("Services", record.get("services")),
        list_text("Email", record.get("emails") or record.get("email")),
        list_text("Phone", record.get("phones") or record.get("phone")),
        list_text("Internal numbers", record.get("internal_numbers")),
        list_text("Website", record.get("websites") or record.get("website")),
        list_text("Office", record.get("offices") or record.get("office")),
        list_text("Raw text", record.get("raw_text")),
    ]
    return make_parent(
        parent_id=f"SYN_{cohort}_student_office_profile_{profile_id}",
        cohort=cohort,
        content_type="student_office_profile",
        title=title,
        content="\n".join(line for line in lines if line),
        source_pages=record.get("source_pages") or [],
        source_section="student_office_profiles",
        document_id=(record.get("document_ids") or [None])[0] if isinstance(record.get("document_ids"), list) else None,
        source_record_id=record.get("office_profile_id"),
        extra_metadata={"office_profile_id": record.get("office_profile_id"), "unit": record.get("unit")},
    )


def build_faculty_profile_parent(record: dict[str, Any]) -> dict[str, Any] | None:
    cohort = str(record.get("cohort") or "")
    if cohort not in COHORT_DOCUMENT_IDS:
        return None
    profile_id = stable_token(record.get("faculty_profile_id") or record.get("unit"), "faculty")
    title = clean_text(record.get("unit") or record.get("unit_name") or profile_id)
    lines = [
        "Source type: student_faculty_profile",
        f"Cohort: {cohort}",
        f"Faculty: {title}",
        list_text("Campus", record.get("campus")),
        list_text("Aliases", record.get("aliases")),
        list_text("Email", record.get("emails") or record.get("email")),
        list_text("Phone", record.get("phones") or record.get("phone")),
        list_text("Internal numbers", record.get("internal_numbers")),
        list_text("Website", record.get("websites") or record.get("website")),
        list_text("Office", record.get("office")),
        list_text("Raw text", record.get("raw_text")),
    ]
    return make_parent(
        parent_id=f"SYN_{cohort}_student_faculty_profile_{profile_id}",
        cohort=cohort,
        content_type="student_faculty_profile",
        title=title,
        content="\n".join(line for line in lines if line),
        source_pages=record.get("source_pages") or [],
        source_section="student_faculty_profiles",
        document_id=record.get("document_id"),
        source_record_id=record.get("faculty_profile_id"),
        extra_metadata={
            "faculty_profile_id": record.get("faculty_profile_id"),
            "unit": record.get("unit"),
            "campus": record.get("campus"),
        },
    )


def build_directory_parent(record: dict[str, Any], *, content_type: str, id_prefix: str) -> dict[str, Any] | None:
    cohort = str(record.get("cohort") or "")
    if cohort not in COHORT_DOCUMENT_IDS:
        return None
    record_id = stable_token(record.get("record_id") or record.get("source_record_id"), id_prefix)
    title = clean_text(
        first_non_empty(
            record,
            ["program_name", "faculty_name", "faculty_or_unit_name", "summary", "raw_text"],
        )
    )[:180]
    lines = [
        f"Source type: {content_type}",
        f"Cohort: {cohort}",
        list_text("Program", record.get("program_name")),
        list_text("Faculty", record.get("faculty_name") or record.get("faculty_or_unit_name")),
        list_text("Summary", record.get("summary")),
        list_text("Raw text", record.get("raw_text")),
    ]
    return make_parent(
        parent_id=f"SYN_{cohort}_{id_prefix}_{record_id}",
        cohort=cohort,
        content_type=content_type,
        title=title or record_id,
        content="\n".join(line for line in lines if line),
        source_pages=record.get("source_pages") or [],
        source_section=content_type,
        document_id=record.get("document_id"),
        source_record_id=record.get("record_id") or record.get("source_record_id"),
        extra_metadata={"derived_from_cohort": record.get("derived_from_cohort")},
    )


def build_synthetic_parents() -> list[dict[str, Any]]:
    parents: list[dict[str, Any]] = []

    for record in load_json(TABLE_DIR / "structured_tables_registry.json", []):
        parent = build_table_parent(
            record,
            content_type="structured_lookup",
            source_section="structured_tables_registry",
            id_prefix="structured_table",
        )
        if parent:
            parents.append(parent)

    for record in load_json(TABLE_DIR / "scoring_tables.json", []):
        parent = build_table_parent(
            record,
            content_type="structured_lookup",
            source_section="scoring_tables",
            id_prefix="scoring_table",
        )
        if parent:
            parents.append(parent)

    for record in load_json(TABLE_DIR / "foreign_language_equivalency_table.json", []):
        parent = build_table_parent(
            record,
            content_type="foreign_language_equivalency",
            source_section="foreign_language_equivalency_table",
            id_prefix="foreign_language_table",
        )
        if parent:
            parents.append(parent)

    for record in load_json(TABLE_DIR / "formula_rules.json", []):
        parent = build_formula_parent(record)
        if parent:
            parents.append(parent)

    for record in load_json(TABLE_DIR / "threshold_rules.json", []):
        parent = build_threshold_parent(record)
        if parent:
            parents.append(parent)

    for record in load_json(DIRECTORY_DIR / "student_service_directory.json", []):
        parent = build_service_parent(record)
        if parent:
            parents.append(parent)

    for record in load_json(DIRECTORY_DIR / "student_office_profiles.json", []):
        parent = build_office_profile_parent(record)
        if parent:
            parents.append(parent)

    for record in load_json(DIRECTORY_DIR / "student_faculty_profiles.json", []):
        parent = build_faculty_profile_parent(record)
        if parent:
            parents.append(parent)

    for record in load_json(DIRECTORY_DIR / "program_directory.json", []):
        parent = build_directory_parent(
            record, content_type="program_directory", id_prefix="program_directory"
        )
        if parent:
            parents.append(parent)

    for record in load_json(DIRECTORY_DIR / "faculty_directory.json", []):
        parent = build_directory_parent(
            record, content_type="faculty_program_directory", id_prefix="faculty_directory"
        )
        if parent:
            parents.append(parent)

    by_id: dict[str, dict[str, Any]] = {}
    duplicates = 0
    for parent in parents:
        parent_id = str(parent.get("_id"))
        if parent_id in by_id:
            duplicates += 1
            continue
        by_id[parent_id] = parent
    return list(by_id.values())


def main() -> None:
    existing_items = load_json(DOCSTORE_PATH, [])
    base_items = [
        item
        for item in existing_items
        if not ((item.get("metadata") or {}).get("source_type") == "synthetic_sidecar")
        and not str(item.get("_id") or "").startswith("SYN_")
    ]
    synthetic_items = build_synthetic_parents()
    output_items = base_items + synthetic_items
    save_json(DOCSTORE_PATH, output_items)

    report = {
        "docstore_path": str(DOCSTORE_PATH.relative_to(ROOT)),
        "base_item_count": len(base_items),
        "removed_existing_synthetic_count": len(existing_items) - len(base_items),
        "synthetic_item_count": len(synthetic_items),
        "final_item_count": len(output_items),
        "synthetic_by_content_type": dict(
            sorted(Counter((item.get("metadata") or {}).get("content_type") for item in synthetic_items).items())
        ),
        "final_by_content_type": dict(
            sorted(Counter((item.get("metadata") or {}).get("content_type") for item in output_items).items())
        ),
    }
    save_json(REPORT_PATH, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
