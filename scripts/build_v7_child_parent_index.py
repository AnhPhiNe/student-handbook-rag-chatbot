from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.generation.evidence_selection import _extract_blocks_from_docstore_item


ALLOWED_COHORTS = {"K48-K49", "K50", "K51"}
GRANULARITIES = {"section_heading", "child", "table_like"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build V7 child-parent regulation chunks for Qdrant."
    )
    parser.add_argument(
        "--docstore",
        default="data/processed/chunks/all_docstore_items.json",
        help="Parent docstore JSON. MongoDB should contain the same parent ids.",
    )
    parser.add_argument(
        "--output",
        default="data/processed/chunks/v7_child_parent_chunks.json",
        help="Output V7 child/table/heading chunks.",
    )
    parser.add_argument(
        "--max-child-chars",
        type=int,
        default=1600,
        help="Hard cap for child/table text length. Parent articles are never indexed.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    parents = json.loads(Path(args.docstore).read_text(encoding="utf-8"))
    chunks = build_v7_chunks(parents, max_child_chars=args.max_child_chars)
    validate_v7_chunks(chunks, parents)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")

    by_granularity = Counter(chunk["metadata"]["chunk_granularity"] for chunk in chunks)
    by_cohort = Counter(chunk["metadata"]["cohort"] for chunk in chunks)
    print(f"Built {len(chunks)} V7 chunks -> {output}")
    print("By granularity:", dict(sorted(by_granularity.items())))
    print("By cohort:", dict(sorted(by_cohort.items())))


def build_v7_chunks(
    parents: list[dict[str, Any]],
    *,
    max_child_chars: int = 1600,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []

    for parent in parents:
        metadata = parent.get("metadata") or {}
        content_type = metadata.get("content_type") or metadata.get("chunk_type")
        if content_type not in {"regulation_text", "regulation_sections", "regulation"}:
            continue

        parent_id = str(metadata.get("parent_section_id") or parent.get("_id") or "")
        if not parent_id:
            continue

        base_metadata = _base_metadata(parent, parent_id)
        chunks.append(_make_heading_chunk(parent, base_metadata))

        seen_texts: set[str] = set()
        for block in _extract_blocks_from_docstore_item(parent):
            text = _clean_block_text(str(block.get("text") or ""))
            if not text:
                continue
            if _looks_like_section_heading(text, base_metadata):
                continue

            granularity = _granularity_from_block(block, text)
            if granularity not in {"child", "table_like"}:
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
                    f"v7_{parent_id}_{granularity}_{block_index:04d}_{part_index:02d}"
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
                            "chunk_type": "regulation",
                            "content_type": "regulation_text",
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


def validate_v7_chunks(chunks: list[dict[str, Any]], parents: list[dict[str, Any]]) -> None:
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
        if metadata.get("content_type") != "regulation_text":
            errors.append(f"{chunk_id}: invalid content_type {metadata.get('content_type')!r}")
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
        raise SystemExit(f"V7 validation failed with {len(errors)} errors:\n{preview}")


def _base_metadata(parent: dict[str, Any], parent_id: str) -> dict[str, Any]:
    metadata = parent.get("metadata") or {}
    title = str(metadata.get("title") or metadata.get("article") or parent_id)
    chapter = str(metadata.get("chapter") or "")
    return {
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
    }


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
    chunk_id = f"v7_{base_metadata['parent_section_id']}_section_heading"
    return {
        "_id": chunk_id,
        "chunk_id": chunk_id,
        "content": content[:900],
        "metadata": {
            **base_metadata,
            "chunk_id": chunk_id,
            "chunk_type": "regulation",
            "content_type": "regulation_text",
            "chunk_granularity": "section_heading",
            "clause_marker": None,
        },
    }


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


def _granularity_from_block(block: dict[str, Any], text: str) -> str:
    block_type = str(block.get("block_type") or "")
    if block_type == "table_like_row" or _looks_table_like(text):
        return "table_like"
    if _has_dense_numeric_or_list_signal(text):
        return "table_like"
    return "child"


def _split_long_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    sentences = re.split(r"(?<=[.!?;:])\s+", text)
    parts: list[str] = []
    current = ""
    for sentence in sentences:
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip()
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            parts.append(current)
        current = sentence[:max_chars]
    if current:
        parts.append(current)
    return parts


def _clean_block_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _looks_like_section_heading(text: str, metadata: dict[str, Any]) -> bool:
    title = _clean_block_text(str(metadata.get("title") or ""))
    if text == title:
        return True
    return bool(re.match(r"^(Điều|Chương|Mục)\s+\w+", text, flags=re.IGNORECASE)) and len(text) < 180


def _looks_table_like(text: str) -> bool:
    if "|" in text:
        return True
    label_count = len(re.findall(r"\b[\w\s]{2,24}:\s*[^|;]+", text))
    return label_count >= 3


def _has_dense_numeric_or_list_signal(text: str) -> bool:
    numbers = re.findall(r"\d+(?:[,.]\d+)?", text)
    time_or_unit = re.findall(
        r"(?:tháng\s+\d+|\d+\s*(?:năm|tháng|tín chỉ|đợt|%))",
        text,
        flags=re.IGNORECASE,
    )
    separators = text.count(";") + text.count("•") + text.count(" - ")
    return len(numbers) >= 3 or len(time_or_unit) >= 2 or separators >= 4


def _fingerprint(text: str) -> str:
    value = re.sub(r"\s+", " ", text).strip().lower()
    return value


if __name__ == "__main__":
    main()
