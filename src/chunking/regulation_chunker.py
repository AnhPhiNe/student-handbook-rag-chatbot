import re
from typing import Any

from .chunk_schema import create_chunk
from .regulation_highlight_extractor import (
    build_regulation_highlight_chunk_content,
    extract_regulation_highlights,
    highlight_metadata_payload,
)
from .regulation_table_extractor import (
    build_regulation_table_chunk_content,
    extract_regulation_tables,
    format_tables_for_parent,
    table_metadata_payload,
)
from .text_utils import join_non_empty, source_page_range
from .token_utils import count_tokens_approx, split_text_by_paragraph


CLAUSE_PATTERN = re.compile(r"^\d+\.\s+", re.MULTILINE)


def build_regulation_chunk_content(section: dict[str, Any], content: str) -> str:
    return join_non_empty(
        [
            f"Tài liệu: {section.get('document_title') or ''}",
            f"Phần: {section.get('part') or ''}",
            f"Chương: {section.get('chapter') or ''}",
            f"Điều: {section.get('article') or ''}",
            f"Tiêu đề: {section.get('title') or ''}",
            "Nội dung:",
            content,
        ]
    )


def build_parent_doc_content(
    section: dict[str, Any],
    content: str,
    tables: list[dict[str, Any]],
    highlights: list[dict[str, Any]] | None = None,
) -> str:
    """Tạo parent doc có thêm bảng đã chuẩn hóa để LLM không phải đọc bảng bị dính dòng."""

    normalized_tables = format_tables_for_parent(tables)
    highlight_text = format_highlights_for_parent(highlights or [])
    return join_non_empty(
        [
            build_regulation_chunk_content(section, content),
            normalized_tables,
            highlight_text,
        ]
    )


def format_highlights_for_parent(highlights: list[dict[str, Any]]) -> str:
    if not highlights:
        return ""
    lines = ["THÔNG TIN TRỌNG TÂM ĐÃ TÁCH TỪ NGUỒN:"]
    for highlight in highlights:
        lines.append(f"- {highlight['highlight_name']}: {highlight['text']}")
    return "\n".join(lines).strip()


def split_by_clause(content: str) -> list[str]:
    """
    Tách theo Khoản: 1. 2. 3.
    Nếu không tìm thấy khoản thì trả về content gốc.
    """
    matches = list(CLAUSE_PATTERN.finditer(content))

    if len(matches) <= 1:
        return [content]

    chunks = []

    intro = content[: matches[0].start()].strip()
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
        clause_text = content[start:end].strip()

        if intro:
            clause_text = intro + "\n" + clause_text

        chunks.append(clause_text)

    return chunks


def build_regulation_chunks(
    sections: list[dict[str, Any]],
    max_tokens: int = 200,
    overlap_tokens: int = 40,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    chunks = []
    docstore_items = []

    for section in sections:
        if section.get("content_type") != "regulation_text":
            continue

        content = section.get("content", "").strip()
        if not content:
            continue

        source_pages = source_page_range(section["page_start"], section["page_end"])
        extracted_tables = extract_regulation_tables(section)
        extracted_highlights = extract_regulation_highlights(section)
        base_metadata = {
            "source_type": "structured_section",
            "document_title": section.get("document_title"),
            "part": section.get("part"),
            "chapter": section.get("chapter"),
            "article": section.get("article"),
            "title": section.get("title"),
            "source_pages": source_pages,
            "content_type": section.get("content_type"),
            "has_table": section.get("has_table"),
            "has_formula": section.get("has_formula"),
            "has_scoring_rule": section.get("has_scoring_rule"),
            "has_thresholds": section.get("has_thresholds"),
        }

        full_content = build_parent_doc_content(
            section,
            content,
            extracted_tables,
            extracted_highlights,
        )
        docstore_items.append(
            {
                "_id": section["section_id"],
                "content": full_content,
                "normalized_content": full_content,
                "tables": [table_metadata_payload(table) for table in extracted_tables],
                "highlights": [
                    highlight_metadata_payload(highlight)
                    for highlight in extracted_highlights
                ],
                "metadata": base_metadata,
            }
        )

        for table in extracted_tables:
            table_metadata = dict(base_metadata)
            table_metadata.update(
                {
                    "source_type": "regulation_table",
                    "parent_section_id": section["section_id"],
                    "semantic_content_kind": "table",
                    "table_id": table["table_id"],
                    "table_name": table["table_name"],
                    "table_kind": table["table_kind"],
                    "applicability": table.get("applicability"),
                }
            )
            chunks.append(
                create_chunk(
                    chunk_id=f"reg_table_{table['table_id']}",
                    chunk_type="regulation_table",
                    index_mode="semantic",
                    content=build_regulation_table_chunk_content(section, table),
                    metadata=table_metadata,
                )
            )

        for highlight in extracted_highlights:
            highlight_metadata = dict(base_metadata)
            highlight_metadata.update(
                {
                    "source_type": "regulation_highlight",
                    "parent_section_id": section["section_id"],
                    "semantic_content_kind": "highlight",
                    "highlight_id": highlight["highlight_id"],
                    "highlight_name": highlight["highlight_name"],
                    "highlight_kind": highlight["highlight_kind"],
                }
            )
            chunks.append(
                create_chunk(
                    chunk_id=f"reg_highlight_{highlight['highlight_id']}",
                    chunk_type="regulation_highlight",
                    index_mode="semantic",
                    content=build_regulation_highlight_chunk_content(section, highlight),
                    metadata=highlight_metadata,
                )
            )

        if count_tokens_approx(full_content) <= max_tokens:
            chunks.append(
                create_chunk(
                    chunk_id=f"reg_{section['section_id']}",
                    chunk_type="regulation",
                    index_mode="semantic",
                    content=full_content,
                    metadata=base_metadata,
                )
            )
            continue

        clause_parts = split_by_clause(content)
        sub_index = 1

        for clause in clause_parts:
            clause_content = build_regulation_chunk_content(section, clause)

            if count_tokens_approx(clause_content) <= max_tokens:
                split_parts = [clause_content]
            else:
                split_parts = split_text_by_paragraph(
                    clause_content,
                    max_tokens=max_tokens,
                    overlap_tokens=overlap_tokens,
                )

            for part in split_parts:
                metadata = dict(base_metadata)
                metadata["parent_section_id"] = section["section_id"]
                metadata["split_strategy"] = "clause_or_paragraph"

                chunks.append(
                    create_chunk(
                        chunk_id=f"reg_{section['section_id']}_part_{sub_index}",
                        chunk_type="regulation",
                        index_mode="semantic",
                        content=part,
                        metadata=metadata,
                    )
                )
                sub_index += 1

    return chunks, docstore_items
