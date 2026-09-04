from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


ALLOWED_COHORTS = {"K48-K49", "K50", "K51"}
GRANULARITIES = {"section_heading", "child"}
REGULATION_CONTENT_TYPES = {"regulation_text", "regulation_sections", "regulation"}
INDEXABLE_CONTENT_TYPES = REGULATION_CONTENT_TYPES
CHUNK_TYPE_BY_CONTENT_TYPE = {}
DEFAULT_STRUCTURED_TABLE_REGISTRY = Path(
    "data/processed/tables/structured_tables_registry.json"
)
DEFAULT_TABLE_EMBEDDING_AUDIT = Path(
    "data/processed/metadata/structured_table_embedding_audit.json"
)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build child-parent regulation chunks for Qdrant."
    )
    parser.add_argument(
        "--docstore",
        default="data/processed/chunks/all_docstore_items.json",
        help="Parent docstore JSON. MongoDB should contain the same parent ids.",
    )
    parser.add_argument(
        "--output",
        default="data/processed/chunks/child_parent_chunks.json",
        help="Output child/table/heading chunks.",
    )
    parser.add_argument(
        "--max-child-chars",
        type=int,
        default=1600,
        help="Hard cap for child/table text length. Parent articles are never indexed.",
    )
    parser.add_argument(
        "--structured-table-registry",
        type=Path,
        default=DEFAULT_STRUCTURED_TABLE_REGISTRY,
        help="Authoritative structured tables used to suppress covered table rows.",
    )
    parser.add_argument(
        "--table-embedding-audit",
        type=Path,
        default=DEFAULT_TABLE_EMBEDDING_AUDIT,
        help="Audit report for excluded and retained table-like rows.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    parents = json.loads(Path(args.docstore).read_text(encoding="utf-8"))
    structured_tables = json.loads(
        args.structured_table_registry.read_text(encoding="utf-8")
    )
    audit_rows: list[dict[str, Any]] = []
    chunks = build_child_parent_chunks(
        parents,
        max_child_chars=args.max_child_chars,
        structured_tables=structured_tables,
        table_embedding_audit=audit_rows,
    )
    validate_child_parent_chunks(chunks, parents)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")

    audit_report = build_table_embedding_audit_report(
        audit_rows,
        docstore_path=Path(args.docstore),
        registry_path=args.structured_table_registry,
        child_output_path=output,
        child_count=len(chunks),
    )
    args.table_embedding_audit.parent.mkdir(parents=True, exist_ok=True)
    args.table_embedding_audit.write_text(
        json.dumps(audit_report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    by_granularity = Counter(chunk["metadata"]["chunk_granularity"] for chunk in chunks)
    by_cohort = Counter(chunk["metadata"]["cohort"] for chunk in chunks)
    print(f"Built {len(chunks)} child-parent chunks -> {output}")
    print("By granularity:", dict(sorted(by_granularity.items())))
    print("By cohort:", dict(sorted(by_cohort.items())))
    print(
        "Table-like rows:",
        {
            "total": audit_report["total_table_like_rows"],
            "excluded_as_structured": audit_report["excluded_as_structured"],
            "retained_unmatched": audit_report["retained_unmatched"],
            "ignored_non_content": audit_report["ignored_non_content"],
        },
    )
    print(f"Table embedding audit -> {args.table_embedding_audit}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _normalize_table_cell(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.replace("–", "-").replace("—", "-")
    text = re.sub(r"\s+", " ", text).strip().casefold()
    return text.strip(" |")


def _parse_table_like_cells(text: str) -> tuple[str, ...]:
    if "|" not in text:
        return ()
    first_pipe = text.find("|")
    cells = [
        _normalize_table_cell(cell)
        for cell in text[first_pipe:].split("|")[1:]
    ]
    return tuple(cell for cell in cells if cell)


def _ordered_registry_row(
    row: dict[str, Any], columns: list[Any]
) -> tuple[str, ...]:
    if columns and all(str(column) in row for column in columns):
        values = [row.get(str(column)) for column in columns]
    else:
        values = list(row.values())
    return tuple(_normalize_table_cell(value) for value in values if value is not None)


def _table_cells_match(actual: tuple[str, ...], expected: tuple[str, ...]) -> bool:
    if not expected or len(actual) < len(expected):
        return False
    if actual[: len(expected)] == expected:
        return True
    if len(expected) == 1 or actual[: len(expected) - 1] != expected[:-1]:
        return False
    # PDF extraction can append a following caption after the final table delimiter.
    # Matching remains deterministic because all preceding cells, cohort and parent
    # must already agree, and the final cell must preserve the complete registry value.
    return actual[len(expected) - 1].startswith(expected[-1] + " ")


def _is_markdown_separator_row(cells: tuple[str, ...]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def match_structured_table_block(
    block: dict[str, Any],
    structured_tables: list[dict[str, Any]],
) -> dict[str, Any]:
    cohort = str(block.get("cohort") or "")
    parent_id = str(block.get("parent_section_id") or "")
    source_pages = {int(page) for page in block.get("source_pages") or []}
    cells = _parse_table_like_cells(str(block.get("text") or ""))

    parent_tables = [
        table
        for table in structured_tables
        if str(table.get("source_parent_id") or "") == parent_id
    ]
    cohort_tables = [
        table
        for table in parent_tables
        if str(table.get("cohort") or "") == cohort
        and str(table.get("quality_status") or "").casefold() == "approved"
        and table.get("used_by_runtime") is not False
    ]
    page_tables = [
        table
        for table in cohort_tables
        if not source_pages
        or not table.get("source_pages")
        or source_pages.intersection(int(page) for page in table.get("source_pages") or [])
    ]

    matches: list[dict[str, str]] = []
    for table in page_tables:
        columns = list(table.get("columns") or [])
        header = tuple(_normalize_table_cell(column) for column in columns)
        if _table_cells_match(cells, header):
            matches.append(
                {"table_id": str(table.get("table_id") or ""), "match_type": "header"}
            )
        for row in table.get("rows") or []:
            if not isinstance(row, dict):
                continue
            signature = _ordered_registry_row(row, columns)
            if _table_cells_match(cells, signature):
                matches.append(
                    {"table_id": str(table.get("table_id") or ""), "match_type": "row"}
                )

    unique_matches = sorted(
        {(item["table_id"], item["match_type"]) for item in matches}
    )
    if _is_markdown_separator_row(cells):
        status = "ignored_non_content"
        reason = "markdown_table_separator"
    elif unique_matches:
        status = "excluded_as_structured"
        reason = "exact_registry_row_or_header_match"
    elif not parent_tables:
        status = "retained_unmatched"
        reason = "no_registry_table_for_parent"
    elif not cohort_tables:
        status = "retained_unmatched"
        reason = "cohort_or_quality_mismatch"
    elif not page_tables:
        status = "retained_unmatched"
        reason = "source_page_mismatch"
    elif not cells:
        status = "retained_unmatched"
        reason = "unparseable_table_row"
    else:
        status = "retained_unmatched"
        reason = "row_not_present_in_registry"

    return {
        "status": status,
        "reason": reason,
        "cohort": cohort,
        "parent_section_id": parent_id,
        "block_index": int(block.get("block_index") or 0),
        "source_pages": sorted(source_pages),
        "normalized_cells": list(cells),
        "matched_tables": [
            {"table_id": table_id, "match_type": match_type}
            for table_id, match_type in unique_matches
        ],
    }


def build_table_embedding_audit_report(
    rows: list[dict[str, Any]],
    *,
    docstore_path: Path,
    registry_path: Path,
    child_output_path: Path,
    child_count: int,
) -> dict[str, Any]:
    excluded = sum(row.get("status") == "excluded_as_structured" for row in rows)
    retained = sum(row.get("status") == "retained_unmatched" for row in rows)
    ignored = sum(row.get("status") == "ignored_non_content" for row in rows)
    return {
        "schema_version": "structured-table-embedding-audit-v1",
        "docstore_path": str(docstore_path),
        "docstore_sha256": _sha256_file(docstore_path),
        "structured_registry_path": str(registry_path),
        "structured_registry_sha256": _sha256_file(registry_path),
        "child_output_path": str(child_output_path),
        "child_count": child_count,
        "total_table_like_rows": len(rows),
        "excluded_as_structured": excluded,
        "retained_unmatched": retained,
        "ignored_non_content": ignored,
        "rows": rows,
    }


def _extract_blocks_from_docstore_item(item: dict[str, Any]) -> list[dict[str, Any]]:
    metadata = item.get("metadata") or {}
    base = {
        "document_id": str(item.get("document_id") or metadata.get("document_id") or ""),
        "cohort": str(item.get("cohort") or metadata.get("cohort") or ""),
        "parent_section_id": str(metadata.get("parent_section_id") or item.get("_id") or ""),
        "source_section": str(metadata.get("title") or metadata.get("source_section") or ""),
        "source_pages": metadata.get("source_pages") or [],
        "section_title": str(metadata.get("title") or metadata.get("article") or ""),
    }

    blocks: list[dict[str, Any]] = []
    block_index = 0

        # Do not create vector chunks from item["tables"]. Table rows still present
        # in content are audited against the structured registry before indexing.
    content = _strip_docstore_preamble(str(item.get("content") or ""))
    for raw_block in _split_text_blocks(content):
        text = raw_block.strip()
        if not text:
            continue
        block_type, list_marker, parent_marker = _classify_text_block(text)
        blocks.append(
            _make_block(
                base,
                block_index,
                block_type,
                text,
                list_marker=list_marker,
                parent_marker=parent_marker,
            )
        )
        block_index += 1

    return blocks


def _make_block(
    base: dict[str, Any],
    block_index: int,
    block_type: str,
    text: str,
    *,
    list_marker: str | None,
    parent_marker: str | None,
) -> dict[str, Any]:
    text = _clean_block_text(text)
    return {
        **base,
        "block_type": block_type,
        "block_index": block_index,
        "list_marker": list_marker,
        "parent_marker": parent_marker,
        "text": text,
        "signals": {
            "has_numeric_signal": bool(re.search(r"\d", text)),
            "has_table_signal": _looks_table_like(text),
            "char_count": len(text),
        },
    }

def _strip_docstore_preamble(content: str) -> str:
    match = re.search(r"^(?:Nội dung|Noi dung):\s*$", content, flags=re.MULTILINE)
    if match:
        content = content[match.end() :].strip()
    return _strip_generated_focus_sections(content.strip())


def _strip_generated_focus_sections(content: str) -> str:
    markers = (
        "THONG TIN TRONG TAM",
        "THÔNG TIN TRỌNG TÂM",
        "DA TACH TU NGUON",
        "ĐÃ TÁCH TỪ NGUỒN",
        "NORMALIZED TABLE/LIST:",
        "RELATED SECTION:",
        "RELATED SNIPPET:",
        "SOURCE TEXT:",
    )
    upper_content = content.upper()
    for marker in markers:
        marker_index = upper_content.find(marker)
        if marker_index > 0:
            return content[:marker_index].strip()
    return content


def _split_text_blocks(content: str) -> list[str]:
    lines = [_clean_block_text(line) for line in content.splitlines()]
    lines = [line for line in lines if line]
    blocks: list[str] = []
    current: list[str] = []

    def flush() -> None:
        nonlocal current
        if current:
            blocks.append(" ".join(current).strip())
            current = []

    for line in lines:
        if _starts_new_block(line):
            flush()
            current = [line]
        else:
            current.append(line)
    flush()

    expanded: list[str] = []
    marker_pattern = re.compile(r"(?=(?:^|\s)(?:\d+\.|[a-z]\)|[-*]\s))", re.IGNORECASE)
    for block in blocks:
        if len(block) < 650:
            expanded.append(block)
            continue
        pieces = [piece.strip() for piece in marker_pattern.split(block) if piece.strip()]
        if len(pieces) <= 1:
            expanded.extend(_split_long_text(block, 900))
        else:
            for piece in pieces:
                expanded.extend(_split_long_text(piece, 900))
    return expanded


def _starts_new_block(line: str) -> bool:
    return bool(
        re.match(r"^\d+\.", line)
        or re.match(r"^[a-z]\)", line, flags=re.IGNORECASE)
        or re.match(r"^[-*]\s+", line)
        or _looks_table_like(line)
    )


def _classify_text_block(text: str) -> tuple[str, str | None, str | None]:
    stripped = text.strip()
    numbered = re.match(r"^(\d+)\.", stripped)
    if numbered:
        return (
            "numbered_condition" if re.search(r"\d", stripped) else "clause",
            numbered.group(1),
            "numbered",
        )
    item = re.match(r"^([a-z])\)", stripped, flags=re.IGNORECASE)
    if item:
        return "item", item.group(1), "lettered"
    if re.match(r"^[-*]\s+", stripped):
        return "bullet", None, "bullet"
    if _looks_table_like(stripped):
        return "table_like_row", None, "table"
    return "clause", None, None


def build_child_parent_chunks(
    parents: list[dict[str, Any]],
    *,
    max_child_chars: int = 1600,
    structured_tables: list[dict[str, Any]] | None = None,
    table_embedding_audit: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []

    for parent in parents:
        metadata = parent.get("metadata") or {}
        content_type = metadata.get("content_type") or metadata.get("chunk_type")
        parent_id = str(metadata.get("parent_section_id") or parent.get("_id") or "")
        if not parent_id:
            continue

        if content_type not in INDEXABLE_CONTENT_TYPES:
            continue

        base_metadata = _base_metadata(parent, parent_id)
        chunks.append(_make_heading_chunk(parent, base_metadata))

        seen_texts: set[str] = set()
        for block in _extract_blocks_from_docstore_item(parent):
            if block.get("block_type") == "table_like_row" and structured_tables is not None:
                audit_row = match_structured_table_block(block, structured_tables)
                if table_embedding_audit is not None:
                    table_embedding_audit.append(audit_row)
                if audit_row["status"] in {
                    "excluded_as_structured",
                    "ignored_non_content",
                }:
                    continue
            text = _clean_block_text(str(block.get("text") or ""))
            if not text:
                continue
            if _looks_like_section_heading(text, base_metadata):
                continue

            granularity = "child"

            for part_index, part in enumerate(_split_long_text(text, max_child_chars)):
                part = _clean_block_text(part)
                if len(part) < 24:
                    continue
                fingerprint = _fingerprint(part)
                if fingerprint in seen_texts:
                    continue
                seen_texts.add(fingerprint)

                block_index = int(block.get("block_index") or 0)
                chunk_id = (
                    f"cp_{parent_id}_{granularity}_{block_index:04d}_{part_index:02d}"
                )
                chunks.append(
                    {
                        "_id": chunk_id,
                        "chunk_id": chunk_id,
                        "content": _format_child_content(
                            part,
                            base_metadata=base_metadata,
                            block=block,
                            granularity=granularity,
                        ),
                        "metadata": {
                            **base_metadata,
                            "chunk_id": chunk_id,
                            "chunk_type": _chunk_type_for_content_type(
                                str(base_metadata.get("content_type") or content_type)
                            ),
                            "content_type": base_metadata.get("content_type") or content_type,
                            "chunk_granularity": granularity,
                            "block_type": block.get("block_type"),
                            "block_index": block_index,
                            "clause_marker": block.get("list_marker"),
                            "parent_marker": block.get("parent_marker"),
                            "signals": block.get("signals") or {},
                        },
                    }
                )

    return chunks


def validate_child_parent_chunks(
    chunks: list[dict[str, Any]], parents: list[dict[str, Any]]
) -> None:
    parent_by_id: dict[str, dict[str, Any]] = {}
    for parent in parents:
        metadata = parent.get("metadata") or {}
        parent_id = str(metadata.get("parent_section_id") or parent.get("_id") or "")
        if parent_id:
            parent_by_id[parent_id] = parent

    errors: list[str] = []
    ids: set[str] = set()
    by_parent: dict[str, Counter[str]] = defaultdict(Counter)

    for chunk in chunks:
        chunk_id = str(chunk.get("_id") or chunk.get("chunk_id") or "")
        metadata = chunk.get("metadata") or {}
        if not chunk_id:
            errors.append("Missing chunk id")
        if chunk_id in ids:
            errors.append(f"Duplicate chunk id: {chunk_id}")
        ids.add(chunk_id)

        parent_id = str(metadata.get("parent_section_id") or "")
        parent = parent_by_id.get(parent_id)
        if not parent:
            errors.append(f"{chunk_id}: missing/unknown parent_section_id {parent_id!r}")
            continue

        parent_meta = parent.get("metadata") or {}
        for field in ("cohort", "document_id"):
            if metadata.get(field) != parent_meta.get(field):
                errors.append(
                    f"{chunk_id}: {field} mismatch {metadata.get(field)!r} != {parent_meta.get(field)!r}"
                )

        if metadata.get("cohort") not in ALLOWED_COHORTS:
            errors.append(f"{chunk_id}: invalid cohort {metadata.get('cohort')!r}")
        if metadata.get("cohort") == "K50-K51":
            errors.append(f"{chunk_id}: legacy cohort leaked")
        parent_content_type = parent_meta.get("content_type") or parent_meta.get("chunk_type")
        if metadata.get("content_type") not in INDEXABLE_CONTENT_TYPES:
            errors.append(f"{chunk_id}: invalid content_type {metadata.get('content_type')!r}")
        if metadata.get("content_type") != parent_content_type:
            errors.append(
                f"{chunk_id}: content_type mismatch {metadata.get('content_type')!r} != {parent_content_type!r}"
            )
        if metadata.get("chunk_granularity") not in GRANULARITIES:
            errors.append(
                f"{chunk_id}: invalid granularity {metadata.get('chunk_granularity')!r}"
            )

        parent_text = str(parent.get("content") or "")
        content = str(chunk.get("content") or "")
        if metadata.get("chunk_granularity") != "section_heading" and len(content) > 2200:
            errors.append(f"{chunk_id}: child/table content too long ({len(content)} chars)")
        if (
            metadata.get("chunk_granularity") != "section_heading"
            and len(parent_text) > 2600
            and _fingerprint(content) == _fingerprint(parent_text)
        ):
            errors.append(f"{chunk_id}: appears to contain full parent text")

        by_parent[parent_id][str(metadata.get("chunk_granularity"))] += 1

    for parent_id, counts in by_parent.items():
        if counts.get("section_heading", 0) != 1:
            errors.append(f"{parent_id}: expected exactly one section_heading")

    if errors:
        preview = "\n".join(errors[:30])
        raise SystemExit(
            f"Child-parent validation failed with {len(errors)} errors:\n{preview}"
        )


def _base_metadata(parent: dict[str, Any], parent_id: str) -> dict[str, Any]:
    metadata = parent.get("metadata") or {}
    title = str(metadata.get("title") or metadata.get("article") or parent_id)
    chapter = str(metadata.get("chapter") or "")
    base = {
        "parent_section_id": parent_id,
        "parent_chunk_id": parent_id,
        "cohort": metadata.get("cohort"),
        "document_id": metadata.get("document_id"),
        "document_title": metadata.get("document_title"),
        "chapter_title": chapter,
        "chapter": chapter,
        "source_section": metadata.get("source_section") or title,
        "title": title,
        "article": metadata.get("article"),
        "source_pages": metadata.get("source_pages") or [],
        "source_type": metadata.get("source_type") or "structured_section",
        "content_type": metadata.get("content_type") or metadata.get("chunk_type") or "regulation_text",
    }
    for field in (
        "source_cohort",
        "applicable_cohorts",
        "applicability",
        "applicability_basis_parent_id",
        "applicability_validated",
    ):
        value = metadata.get(field)
        if value not in (None, "", []):
            base[field] = value
    return base


def _make_heading_chunk(parent: dict[str, Any], base_metadata: dict[str, Any]) -> dict[str, Any]:
    metadata = parent.get("metadata") or {}
    title = str(base_metadata.get("title") or "")
    chapter = str(base_metadata.get("chapter_title") or "")
    document_title = str(metadata.get("document_title") or "")
    first_lines = _first_content_lines(str(parent.get("content") or ""), max_lines=2)
    content = "\n".join(
        part
        for part in [
            f"Section heading: {title}",
            f"Chapter: {chapter}" if chapter else "",
            f"Document: {document_title}" if document_title else "",
            f"Summary anchor: {first_lines}" if first_lines else "",
        ]
        if part
    )
    chunk_id = f"cp_{base_metadata['parent_section_id']}_section_heading"
    return {
        "_id": chunk_id,
        "chunk_id": chunk_id,
        "content": content[:900],
        "metadata": {
            **base_metadata,
            "chunk_id": chunk_id,
            "chunk_type": _chunk_type_for_content_type(str(base_metadata.get("content_type") or "")),
            "content_type": base_metadata.get("content_type") or "regulation_text",
            "chunk_granularity": "section_heading",
            "clause_marker": None,
        },
    }


def _chunk_type_for_content_type(content_type: str) -> str:
    if content_type in REGULATION_CONTENT_TYPES:
        return "regulation"
    return CHUNK_TYPE_BY_CONTENT_TYPE.get(content_type, content_type or "unknown")


def _format_child_content(
    text: str,
    *,
    base_metadata: dict[str, Any],
    block: dict[str, Any],
    granularity: str,
) -> str:
    marker = block.get("list_marker")
    title = base_metadata.get("title")
    lines = [
        f"Parent section: {title}",
        f"Granularity: {granularity}",
    ]
    if marker:
        lines.append(f"Clause marker: {marker}")
    lines.append(f"Content: {text}")
    return "\n".join(lines)


def _first_content_lines(content: str, *, max_lines: int) -> str:
    marker = "Nội dung:"
    if marker in content:
        content = content.split(marker, 1)[1]
    lines = [_clean_block_text(line) for line in content.splitlines()]
    lines = [
        line
        for line in lines
        if line
        and not line.startswith("[ID ")
        and not line.startswith("Tài liệu:")
        and not line.startswith("Phần:")
        and not line.startswith("Chương:")
        and not line.startswith("Điều:")
        and not line.startswith("Tiêu đề:")
    ]
    return " ".join(lines[:max_lines])[:420]


def _split_long_text(text: str, max_chars: int) -> list[str]:
    text = _clean_block_text(text)

    if not text:
        return []

    if len(text) <= max_chars:
        return [text]

    parts: list[str] = []
    remaining = text

    while len(remaining) > max_chars:
        window = remaining[: max_chars + 1]

        split_at = max(
            window.rfind(". "),
            window.rfind("; "),
            window.rfind(": "),
            window.rfind(" "),
        )

    # Fall back to a hard boundary when no safe split point exists.
        if split_at < max_chars // 2:
            split_at = max_chars
        else:
            split_at += 1

        part = remaining[:split_at].strip()
        if part:
            parts.append(part)

        remaining = remaining[split_at:].strip()

    if remaining:
        parts.append(remaining)

    return parts


def _clean_block_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text).strip()
    if re.fullmatch(
        r"(?:\d+\s+)?SỔ TAY SINH VIÊN KHÓA\s+\d+(?:\s+\d+)?",
        text,
        flags=re.IGNORECASE,
    ):
        return ""
    if re.fullmatch(
        r"(?:MÃ\s+QR|QR|\(đã ký\)|TM\.\s*CHÍNH PHỦ|HIỆU TRƯỞNG)",
        text,
        flags=re.IGNORECASE,
    ):
        return ""
    return text


def _looks_like_section_heading(text: str, metadata: dict[str, Any]) -> bool:
    title = _clean_block_text(str(metadata.get("title") or ""))
    article = _clean_block_text(str(metadata.get("article") or ""))
    if text == title:
        return True
    heading_variants = {
        _clean_block_text(value)
        for value in (
            article,
            f"{article} {title}".strip(),
            f"{article.rstrip('.')} {title}".strip(),
        )
        if value
    }
    return text in heading_variants


def _looks_table_like(text: str) -> bool:
    if "|" in text:
        return True
    label_count = len(re.findall(r"\b[\w\s]{2,24}:\s*[^|;]+", text))
    return label_count >= 3

def _fingerprint(text: str) -> str:
    value = re.sub(r"\s+", " ", text).strip().lower()
    return value


if __name__ == "__main__":
    main()
