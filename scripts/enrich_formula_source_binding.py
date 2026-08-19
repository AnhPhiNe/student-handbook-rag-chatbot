"""Backfill exact parent-section provenance for extracted formula records."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FORMULAS = ROOT / "data/processed/tables/formula_rules.json"
DOCSTORE = ROOT / "data/processed/chunks/all_docstore_items.json"


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").casefold()).replace("đ", "d")
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def main() -> None:
    formulas = _load(FORMULAS)
    parents = _load(DOCSTORE)
    index: dict[tuple[str, str, str], list[str]] = {}
    for parent in parents:
        metadata = parent.get("metadata") or {}
        key = (
            str(parent.get("document_id") or metadata.get("document_id") or ""),
            _normalize(metadata.get("article")),
            _normalize(metadata.get("title")),
        )
        index.setdefault(key, []).append(str(parent.get("_id") or ""))

    errors: list[str] = []
    for record in formulas:
        key = (
            str(record.get("document_id") or ""),
            _normalize(record.get("source_article")),
            _normalize(record.get("source_title")),
        )
        matches = [value for value in index.get(key, []) if value]
        if len(matches) != 1:
            errors.append(f"{record.get('record_id') or record.get('rule_id')}: {len(matches)} parent matches")
            continue
        record["source_parent_id"] = matches[0]
        record["source_section_id"] = matches[0]
        provenance = record.get("source_provenance") or {}
        record["source_provenance"] = {
            **provenance,
            "parent_section_id": matches[0],
            "document_id": record.get("document_id"),
            "source_pages": record.get("source_pages") or [],
        }
    if errors:
        raise SystemExit("\n".join(errors))
    FORMULAS.write_text(
        json.dumps(formulas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Bound {len(formulas)} formula records to exact parent sections")


if __name__ == "__main__":
    main()
