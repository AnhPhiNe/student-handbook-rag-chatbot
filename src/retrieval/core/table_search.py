"""Deterministic table search handles. Handles locate sources, never supply facts."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.common.cohort import is_validated_source_applicable, normalize_cohort, valid_cohorts

ROLE = "table_search_handle"
VERSION = "table-description-v1"


def table_key(table: dict[str, Any]) -> str:
    cohort = normalize_cohort(table.get("source_cohort") or table.get("cohort"))
    if cohort not in valid_cohorts():
        raise ValueError("Unsupported table source cohort")
    parts = [cohort,
             table.get("source_parent_id") or table.get("source_section_id"), table.get("table_id")]
    if not all(parts):
        raise ValueError("Table search requires source cohort, parent and table identity")
    return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))


def table_digest(table: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(table, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def build_table_descriptions(tables: list[dict[str, Any]], parents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One handle per approved table; no cell thresholds, paraphrased policy or LLM."""
    by_parent = {parent["_id"]: parent for parent in parents}
    result, seen = [], set()
    for table in tables:
        if table.get("quality_status") != "approved":
            continue
        key = table_key(table)
        if key in seen:
            raise ValueError("Duplicate composite table identity")
        seen.add(key)
        parent_id = table.get("source_parent_id") or table.get("source_section_id")
        parent = by_parent.get(parent_id)
        if parent is None or normalize_cohort(parent.get("cohort")) != normalize_cohort(table.get("source_cohort") or table.get("cohort")):
            raise ValueError("Missing or wrong-cohort table parent")
        if parent.get("document_id") != table.get("document_id"):
            raise ValueError("Table document differs from parent")
        rows = table.get("rows")
        if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) and row for row in rows):
            raise ValueError("Approved table has invalid rows")
        columns = table.get("columns") or list(dict.fromkeys(field for row in rows for field in row))
        # Names are searchable; numbers remain exclusively in the raw table.
        labels = list(dict.fromkeys(str(row[field]) for row in rows
                                    for field in ("language", "certificate", "level_or_scale", "scholarship_level", "label")
                                    if row.get(field)))
        content = "\n".join([
            f"Bảng tham chiếu: {table.get('table_name') or table.get('title') or table['table_id']}",
            f"Nguồn: {(parent.get('metadata') or {}).get('document_title') or table['document_id']}",
            f"Loại bảng: {table.get('table_subtype') or table.get('table_type')}",
            f"Các trường có thể tra: {', '.join(columns)}", f"Đối tượng/nhãn: {'; '.join(labels)}",
        ])
        chunk_id = "td_" + hashlib.sha256(key.encode()).hexdigest()[:24]
        metadata = {**(parent.get("metadata") or {}), "cohort": table.get("source_cohort") or table["cohort"],
                    "document_id": table["document_id"], "source_pages": table.get("source_pages") or [],
                    "parent_section_id": parent_id, "parent_chunk_id": parent_id,
                    "chunk_id": chunk_id, "content_type": "regulation_text", "chunk_type": "regulation",
                    "chunk_granularity": "table_description", "corpus_role": ROLE,
                    "table_search_key": key, "table_sha256": table_digest(table), "description_version": VERSION}
        for field in ("applicable_cohorts", "applicability_validated", "applicability_basis_parent_id", "applicability"):
            # A shared parent does not authorize every table attached to it.
            metadata[field] = table.get(field)
        result.append({"_id": chunk_id, "chunk_id": chunk_id, "content": content, "metadata": metadata})
    return sorted(result, key=lambda chunk: chunk["_id"])


def load_table_search(config: dict[str, Any], collection_name: str) -> dict[str, dict[str, Any]]:
    """Opt-in candidate index only; pin registry bytes and forbid the baseline target."""
    if not config:
        return {}
    if collection_name != config["collection_name"] or collection_name == config["baseline_collection"]:
        raise ValueError("Table search must use its separate candidate collection")
    raw = Path(config["registry_path"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != config["registry_sha256"]:
        raise ValueError("Table-search registry hash changed")
    tables = json.loads(raw)
    result = {table_key(table): table for table in tables if table.get("quality_status") == "approved"}
    if len(result) != sum(table.get("quality_status") == "approved" for table in tables):
        raise ValueError("Duplicate table-search identities")
    return result


def raw_table_for_handle(chunk: dict[str, Any], tables: dict[str, dict[str, Any]],
                         cohort: str | None = None) -> dict[str, Any] | None:
    metadata = chunk.get("metadata") or {}
    table = tables.get(metadata.get("table_search_key"))
    if table is None or metadata.get("table_sha256") != table_digest(table):
        return None
    if normalize_cohort(table.get("source_cohort") or table.get("cohort")) not in valid_cohorts():
        return None
    if not is_validated_source_applicable(table, cohort):
        return None
    if metadata.get("parent_section_id") != (table.get("source_parent_id") or table.get("source_section_id")):
        return None
    if normalize_cohort(metadata.get("cohort")) != normalize_cohort(table.get("source_cohort") or table.get("cohort")):
        return None
    if metadata.get("document_id") != table.get("document_id"):
        return None
    return table


def raw_table_context(chunks: list[tuple[float, dict[str, Any]]], tables: dict[str, dict[str, Any]],
                      parent: dict[str, Any], cohort: str | None = None) -> str:
    """Materialize only matched, trusted tables belonging to this full parent."""
    found = {}
    for _, chunk in chunks:
        if (chunk.get("metadata") or {}).get("corpus_role") != ROLE:
            continue
        table = raw_table_for_handle(chunk, tables, cohort)
        if (table and parent.get("_id") == (table.get("source_parent_id") or table.get("source_section_id"))
                and parent.get("document_id") == table.get("document_id")
                and normalize_cohort(parent.get("cohort")) == normalize_cohort(table.get("source_cohort") or table.get("cohort"))
                and is_validated_source_applicable(parent, cohort)):
            found[table_key(table)] = {field: table.get(field) for field in
                                      ("table_id", "table_name", "cohort", "applicability", "columns", "rows")}
    return json.dumps({"tables": list(found.values())}, ensure_ascii=False, indent=2) if found else ""
