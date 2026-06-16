from typing import Any

from .chunk_schema import create_chunk
from .text_utils import format_source_pages, join_non_empty, normalize_text
from .token_utils import count_tokens_approx, split_text_by_paragraph


def build_directory_content(
    title: str,
    raw_text: str,
    source_pages: list[int],
) -> str:
    return join_non_empty(
        [
            title,
            "Thông tin liên quan:",
            normalize_text(raw_text),
            f"Nguồn: {format_source_pages(source_pages)}",
        ]
    )


def split_long_directory_content(
    content: str,
    max_tokens: int,
) -> list[str]:
    if count_tokens_approx(content) <= max_tokens:
        return [content]

    return split_text_by_paragraph(
        text=content,
        max_tokens=max_tokens,
        overlap_tokens=0,
    )


def build_office_chunks(
    office_records: list[dict[str, Any]],
    max_tokens: int = 350,
) -> list[dict[str, Any]]:
    chunks = []

    for record in office_records:
        source_pages = record.get("source_pages", [])
        unit_name = record.get("unit_name", "")

        content = build_directory_content(
            title=f"Đơn vị/phòng ban: {unit_name}",
            raw_text=record.get("raw_text", ""),
            source_pages=source_pages,
        )

        parts = split_long_directory_content(content, max_tokens=max_tokens)

        for idx, part in enumerate(parts, start=1):
            suffix = f"_part_{idx}" if len(parts) > 1 else ""

            chunks.append(
                create_chunk(
                    chunk_id=f"office_{record['record_id']}{suffix}",
                    chunk_type="office_directory",
                    index_mode="semantic",
                    content=part,
                    metadata={
                        "source_type": "office_directory",
                        "record_id": record.get("record_id"),
                        "unit_name": unit_name,
                        "source_pages": source_pages,
                        "needs_manual_review": record.get("needs_manual_review"),
                        "split_from_record": len(parts) > 1,
                        "part_index": idx,
                        "total_parts": len(parts),
                    },
                )
            )

    return chunks


def build_faculty_chunks(
    faculty_records: list[dict[str, Any]],
    max_tokens: int = 350,
) -> list[dict[str, Any]]:
    chunks = []

    for record in faculty_records:
        source_pages = record.get("source_pages", [])
        faculty_name = record.get("faculty_or_unit_name", "")

        content = build_directory_content(
            title=f"Khoa/Tổ: {faculty_name}",
            raw_text=record.get("raw_text", ""),
            source_pages=source_pages,
        )

        parts = split_long_directory_content(content, max_tokens=max_tokens)

        for idx, part in enumerate(parts, start=1):
            suffix = f"_part_{idx}" if len(parts) > 1 else ""

            chunks.append(
                create_chunk(
                    chunk_id=f"faculty_{record['record_id']}{suffix}",
                    chunk_type="faculty_program_directory",
                    index_mode="semantic",
                    content=part,
                    metadata={
                        "source_type": "faculty_program_directory",
                        "record_id": record.get("record_id"),
                        "faculty_or_unit_name": faculty_name,
                        "source_pages": source_pages,
                        "needs_manual_review": record.get("needs_manual_review"),
                        "split_from_record": len(parts) > 1,
                        "part_index": idx,
                        "total_parts": len(parts),
                    },
                )
            )

    return chunks


def build_reference_chunks(
    reference_records: list[dict[str, Any]],
    max_tokens: int = 350,
) -> list[dict[str, Any]]:
    chunks = []

    for record in reference_records:
        source_pages = record.get("source_pages", [])

        content = build_directory_content(
            title=f"Trang tham khảo: {record.get('name')}",
            raw_text=record.get("raw_text", ""),
            source_pages=source_pages,
        )

        parts = split_long_directory_content(content, max_tokens=max_tokens)

        for idx, part in enumerate(parts, start=1):
            suffix = f"_part_{idx}" if len(parts) > 1 else ""

            chunks.append(
                create_chunk(
                    chunk_id=f"reference_{record['record_id']}{suffix}",
                    chunk_type="reference_directory",
                    index_mode="semantic",
                    content=part,
                    metadata={
                        "source_type": "reference_directory",
                        "record_id": record.get("record_id"),
                        "name": record.get("name"),
                        "source_pages": source_pages,
                        "split_from_record": len(parts) > 1,
                        "part_index": idx,
                        "total_parts": len(parts),
                    },
                )
            )

    return chunks


def build_directory_chunks(
    office_records: list[dict[str, Any]],
    faculty_records: list[dict[str, Any]],
    reference_records: list[dict[str, Any]],
    directory_max_tokens: int = 350,
) -> list[dict[str, Any]]:
    return (
        build_office_chunks(office_records, max_tokens=directory_max_tokens)
        + build_faculty_chunks(faculty_records, max_tokens=directory_max_tokens)
        + build_reference_chunks(reference_records, max_tokens=directory_max_tokens)
    )