import re
from typing import Any

from .chunk_schema import create_chunk
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


def split_by_clause(content: str) -> list[str]:
    """
    Tách theo Khoản: 1. 2. 3.
    Nếu không tìm thấy khoản thì trả về content gốc.
    """
    matches = list(CLAUSE_PATTERN.finditer(content))

    if len(matches) <= 1:
        return [content]

    chunks = []

    intro = content[:matches[0].start()].strip()
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
    max_tokens: int = 850,
    overlap_tokens: int = 80,
) -> list[dict[str, Any]]:
    chunks = []

    for section in sections:
        if section.get("content_type") != "regulation_text":
            continue

        content = section.get("content", "").strip()
        if not content:
            continue

        source_pages = source_page_range(section["page_start"], section["page_end"])
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

        full_content = build_regulation_chunk_content(section, content)

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

    return chunks