"""Build an isolated regulation corpus with registry-derived table evidence.

This command never updates the production artifacts or remote stores. Only a
complete, ordered table signature can authorize removal from the source text.
Partial row matches are diagnostics, not deletion instructions.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_child_parent_index import (  # noqa: E402
    INDEXABLE_CONTENT_TYPES,
    _base_metadata,
    build_child_parent_chunks,
    validate_child_parent_chunks,
)

POLICY = "registry-regulation-text-candidate-v1"


def dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def digest(value: Any) -> str:
    return hashlib.sha256(dump(value).encode("utf-8")).hexdigest()


def columns_for(table: dict) -> list[str]:
    # Preserve every field, including fields omitted from an explicit column list.
    return list(dict.fromkeys([
        *table.get("columns", []),
        *(key for row in table["rows"] for key in row),
    ]))


def cell_text(value: Any) -> str:
    return value if isinstance(value, str) else dump(value)


def literal_pattern(value: str) -> str:
    """Ignore only layout whitespace and case; never discard signs or numbers."""
    return r"\s+".join(re.escape(word) for word in value.split())


def table_spans(content: str, table: dict) -> list[tuple[int, int, str]]:
    columns = table.get("columns") or []
    rows = table["rows"]
    # No guessing of raw source layout for schema-less or heterogeneous records.
    if not columns or any(set(row) != set(columns) for row in rows):
        return []
    lines = [columns, *[[cell_text(row[c]) for c in columns] for row in rows]]
    if any(not str(cell).strip() for line in lines for cell in line):
        return []
    flat = r"\s+".join(literal_pattern(str(cell)) for line in lines for cell in line)
    markdown_lines = [r"\|\s*" + r"\s*\|\s*".join(
        literal_pattern(str(cell)) for cell in line
    ) + r"\s*\|" for line in lines]
    separator = r"\|\s*" + r"\s*\|\s*".join(
        r":?-{3,}:?" for _ in columns
    ) + r"\s*\|"
    markdown = r"\s*".join([markdown_lines[0], separator, *markdown_lines[1:]])
    result = []
    for kind, pattern in (("flat", flat), ("markdown", markdown)):
        # Word boundaries prevent e.g. a terminal value '3' matching '30'.
        for match in re.finditer(r"(?<!\w)" + pattern + r"(?!\w)", content, re.I):
            result.append((match.start(), match.end(), kind))
    return result


def render_table_chunks(parent: dict, table: dict, max_chars: int) -> list[dict]:
    parent_id = table["source_parent_id"]
    columns = columns_for(table)
    prefix = (
        f"Parent section: {parent['metadata'].get('title', '')}\n"
        f"Bảng: {table['table_name']}\n"
        f"Khóa nguồn: {table['cohort']}\n"
        f"Phạm vi: {table.get('applicability') or 'Theo điều khoản nguồn'}\n"
        f"Cột: {dump(columns)}\n"
    )
    groups: list[list[tuple[int, str]]] = []
    for index, row in enumerate(table["rows"]):
        line = f"Hàng {index + 1}: {dump(row)}"
        if len(prefix + line) > max_chars:
            raise ValueError(f"Row exceeds chunk budget without splitting cells: {table['table_id']}:{index}")
        if not groups or len(prefix + "\n".join(v for _, v in groups[-1]) + "\n" + line) > max_chars:
            groups.append([])
        groups[-1].append((index, line))
    chunks = []
    key = digest([parent_id, table["cohort"], table["table_id"]])[:20]
    for part, group in enumerate(groups):
        chunk_id = f"cp_{parent_id}_registry_{key}_{part:03d}"
        chunks.append({
            "_id": chunk_id, "chunk_id": chunk_id,
            "content": prefix + "\n".join(line for _, line in group),
            "metadata": {
                **_base_metadata(parent, parent_id),
                "chunk_id": chunk_id, "chunk_type": "regulation",
                "chunk_granularity": "child", "block_type": "registry_table",
                "table_id": table["table_id"], "table_sha256": digest(table),
                "table_row_indices": [index for index, _ in group],
                "table_applicability": table.get("applicability"),
                "source_pages": table.get("source_pages") or parent["metadata"].get("source_pages", []),
                "table_text_policy": POLICY,
            },
        })
    return chunks


def build_candidate(parents: list[dict], tables: list[dict], max_chars: int = 1600) -> tuple[list[dict], dict]:
    cleaned = copy.deepcopy(parents)
    parent_map = {p["metadata"].get("parent_section_id") or p["_id"]: p for p in cleaned}
    by_parent: dict[str, list[dict]] = defaultdict(list)
    identities: dict[tuple, dict] = {}
    excluded = []
    for table in tables:
        if (table.get("data_category") != "regulation_table"
                or table.get("quality_status") != "approved"
                or table.get("used_by_runtime") is False):
            excluded.append(table.get("table_id"))
            continue
        parent = parent_map.get(table.get("source_parent_id"))
        if not parent:
            raise ValueError(f"Missing parent: {table['table_id']}")
        meta = parent["metadata"]
        if meta.get("content_type") not in INDEXABLE_CONTENT_TYPES:
            raise ValueError(f"Non-regulation parent: {table['table_id']}")
        if any(table.get(field) != meta.get(field) for field in ("cohort", "document_id")):
            raise ValueError(f"Source identity mismatch: {table['table_id']}")
        if not table.get("rows") or any(not isinstance(row, dict) or not row for row in table["rows"]):
            raise ValueError(f"Invalid rows: {table['table_id']}")
        pages = set(table.get("source_pages") or [])
        if pages and not pages.issubset(meta.get("source_pages") or []):
            raise ValueError(f"Source page mismatch: {table['table_id']}")
        key = (table["source_parent_id"], table["cohort"], table["table_id"])
        if key in identities:
            if identities[key] != table:
                raise ValueError(f"Conflicting registry identity: {key}")
            continue
        identities[key] = table
        by_parent[key[0]].append(table)

    audit = []
    generated = []
    for parent_id, parent_tables in by_parent.items():
        parent = parent_map[parent_id]
        original = parent["content"]
        spans = []
        for table in parent_tables:
            for start, end, kind in table_spans(original, table):
                spans.append((start, end, kind, table["table_id"]))
        spans.sort()
        # Overlapping source matches cannot safely establish table ownership.
        overlapping = {
            i for i, a in enumerate(spans)
            if any(i != j and a[0] < b[1] and b[0] < a[1] for j, b in enumerate(spans))
        }
        safe = [span for i, span in enumerate(spans) if i not in overlapping]
        content = original
        for start, end, _, _ in reversed(safe):
            content = content[:start] + "\n" + content[end:]
        parent["content"] = content
        residual_rows = []
        for table in parent_tables:
            for row_index, row in enumerate(table["rows"]):
                values = [cell_text(row[c]) for c in columns_for(table) if c in row]
                if len(values) < 2 or any(not v.strip() for v in values):
                    continue
                pattern = r"\s+".join(literal_pattern(v) for v in values)
                if re.search(r"(?<!\w)" + pattern + r"(?!\w)", content, re.I):
                    residual_rows.append({"table_id": table["table_id"], "row_index": row_index})
            generated.extend(render_table_chunks(parent, table, max_chars))
        unproven = [
            table["table_id"] for table in parent_tables
            if not any(kind == "flat" and table_id == table["table_id"]
                       for _, _, kind, table_id in safe)
        ]
        audit.append({
            "parent_id": parent_id,
            "tables_without_proven_flat_span": unproven,
            "removed_spans": [
                {"start": start, "end": end, "kind": kind, "table_id": table_id,
                 "source_text": original[start:end]}
                for start, end, kind, table_id in safe
            ],
            "overlapping_spans": len(overlapping),
            "residual_exact_rows_for_review": residual_rows,
            "review_required": bool(overlapping or residual_rows or unproven),
        })
    chunks = build_child_parent_chunks(cleaned, structured_tables=tables)
    chunks.extend(generated)
    validate_child_parent_chunks(chunks, parents)
    return chunks, {
        "policy": POLICY, "publication_status": "candidate_not_deployed",
        "tables_rendered": len(identities),
        "rows_rendered": sum(len(t["rows"]) for t in identities.values()),
        "canonical_chunks": len(generated), "excluded_tables": excluded,
        "parents_requiring_review": sum(a["review_required"] for a in audit),
        "tables_without_proven_flat_span": sum(len(a["tables_without_proven_flat_span"]) for a in audit),
        "parents": audit,
        "limitation": "Exact full-table removal only; unmatched or reformatted source text is retained. This is not a visual PDF completeness audit.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    work = (ROOT / "work").resolve()
    if not output.is_relative_to(work) or output == work:
        parser.error("Candidate output must be a new subdirectory of work/.")
    if output.exists():
        parser.error("Output already exists; use a new directory to retain previous results.")
    paths = {
        "parents": ROOT / "data/processed/chunks/all_docstore_items.json",
        "registry": ROOT / "data/processed/tables/structured_tables_registry.json",
        "baseline": ROOT / "data/processed/chunks/child_parent_chunks.json",
    }
    inputs = {key: json.loads(path.read_text(encoding="utf-8")) for key, path in paths.items()}
    chunks, report = build_candidate(inputs["parents"], inputs["registry"])
    report["input_sha256"] = {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in paths.items()}
    baseline_content = Counter(c["content"] for c in inputs["baseline"])
    candidate_content = Counter(c["content"] for c in chunks)
    report["comparison"] = {
        "baseline_chunks": len(inputs["baseline"]), "candidate_chunks": len(chunks),
        "unchanged_chunk_contents": sum((baseline_content & candidate_content).values()),
        "removed_or_changed_chunk_contents": sum((baseline_content - candidate_content).values()),
        "added_or_changed_chunk_contents": sum((candidate_content - baseline_content).values()),
    }
    output.mkdir(parents=True)
    for name, value in (("child_parent_chunks.json", chunks), ("audit.json", report)):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(dump({key: value for key, value in report.items() if key != "parents"}))


if __name__ == "__main__":
    main()
