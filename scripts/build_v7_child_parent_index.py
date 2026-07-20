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


ALLOWED_COHORTS = {"K48-K49", "K50", "K51"}
GRANULARITIES = {"section_heading", "child"}
REGULATION_CONTENT_TYPES = {"regulation_text", "regulation_sections", "regulation"}
INDEXABLE_CONTENT_TYPES = REGULATION_CONTENT_TYPES
CHUNK_TYPE_BY_CONTENT_TYPE = {}

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

    # Không sinh vector chunk từ từng row trong item["tables"]. Phần bảng xuất hiện
    # tự nhiên trong content vẫn được giữ như regulation text để RAG có đường fallback.
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


def build_v7_chunks(
    parents: list[dict[str, Any]],
    *,
    max_child_chars: int = 1600,
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
        "content_type": metadata.get("content_type") or metadata.get("chunk_type") or "regulation_text",
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

        # Không tìm được điểm ngắt hợp lý thì cắt cứng.
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
    if text == title:
        return True
    return bool(re.match(r"^(Điều|Chương|Mục)\s+\w+", text, flags=re.IGNORECASE)) and len(text) < 180


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
