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
BOUNDARY_STOP_MARKERS = (
    "THÔNG TIN TRỌNG TÂM",
    "THONG TIN TRONG TAM",
    "ĐÃ TÁCH TỪ NGUỒN",
    "DA TACH TU NGUON",
    "Nơi nhận:",
    "CÁC HƯỚNG DẪN LIÊN QUAN",
    "CAC HUONG DAN LIEN QUAN",
    "Phần 3\nCÁC QUY TRÌNH",
    "PHẦN 3\nCÁC QUY TRÌNH",
    "CÁC QUY TRÌNH, BIỂU MẪU",
    "QUY TRÌNH XÉT SINH VIÊN VÀO Ở KÝ TÚC XÁ",
    "THÔNG BÁO\nV/v thực hiện",
    "THÔNG BÁO\nVề việc thực hiện",
    "Sinh viên có thể quét mã QR",
    "Sinh viên tải mẫu đơn tại",
)
LOW_VALUE_LINK_PATTERNS = (
    r"\([^)]*(?:mã\s*qr|qr|https?://|đường\s+dẫn|link)[^)]*\)",
    r"https?://\S+",
    r"\b\S*bit\.ly/\S+",
    r"\b\S*forms\.gle/\S+",
    r"\b\S*google\.com/forms\S*",
    r"\s*(?:hoặc\s+)?quét\s+mã\s*qr\b.*$",
    r"\s*(?:hoặc\s+)?truy\s+cập\s+(?:vào\s+)?(?:đường\s+dẫn|link)\b.*$",
    r"\s*xem\s+trong\s+(?:đường\s+dẫn|link)\b.*$",
    r"\s*(?:thông\s+qua|qua|trong)?\s*(?:đường\s+)?dẫn\s+hoặc\s+mã\s*qr\b.*$",
)
LOW_VALUE_LINK_TERMS = (
    "mã qr",
    " qr",
    "http://",
    "https://",
    "bit.ly",
    "forms.gle",
    "google.com/forms",
    "đường dẫn",
)


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


def clean_regulation_source_content(content: str) -> str:
    """Remove generated notes, layout lines, and leaked appendix documents."""

    cleaned = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    upper_cleaned = cleaned.upper()
    stop_positions = [
        upper_cleaned.find(marker.upper())
        for marker in BOUNDARY_STOP_MARKERS
        if upper_cleaned.find(marker.upper()) > 0
    ]
    if stop_positions:
        cleaned = cleaned[: min(stop_positions)].strip()

    lines = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if re.fullmatch(
            r"\d*\s*SỔ TAY SINH VIÊN KHÓA\s+\d+(?:\s+\d+)?",
            stripped,
            flags=re.IGNORECASE,
        ):
            continue
        stripped = _strip_low_value_link_text(stripped)
        if stripped:
            lines.append(stripped)
    return "\n".join(lines).strip()


def _strip_low_value_link_text(text: str) -> str:
    stripped = text.strip()
    for pattern in LOW_VALUE_LINK_PATTERNS:
        stripped = re.sub(pattern, "", stripped, flags=re.IGNORECASE).strip()
    stripped = re.sub(r"\s+([,.;:])", r"\1", stripped)
    stripped = re.sub(r"\s{2,}", " ", stripped).strip()
    stripped = re.sub(r"\(\s*\)", "", stripped).strip()
    if any(term in stripped.lower() for term in LOW_VALUE_LINK_TERMS):
        return ""
    return stripped


def build_parent_doc_content(
    section: dict[str, Any],
    content: str,
    tables: list[dict[str, Any]],
    highlights: list[dict[str, Any]] | None = None,
) -> str:
    """Tạo parent doc có thêm bảng đã chuẩn hóa để LLM không phải đọc bảng bị dính dòng."""

    normalized_tables = format_tables_for_parent(tables)
    normalized_highlights = format_highlights_for_parent(highlights or [])
    return join_non_empty(
        [
            build_regulation_chunk_content(section, content),
            normalized_tables,
            normalized_highlights,
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

        content = clean_regulation_source_content(section.get("content", ""))
        if not content:
            continue

        cleaned_section = {**section, "content": content}
        source_pages = source_page_range(section["page_start"], section["page_end"])
        extracted_tables = extract_regulation_tables(cleaned_section)
        extracted_highlights = extract_regulation_highlights(cleaned_section)
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
            cleaned_section,
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
                    content=build_regulation_table_chunk_content(cleaned_section, table),
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
                    content=build_regulation_highlight_chunk_content(cleaned_section, highlight),
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
            clause_content = build_regulation_chunk_content(cleaned_section, clause)

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
