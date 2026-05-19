from typing import Any

from .chunk_schema import create_chunk
from .text_utils import format_source_pages, join_non_empty, normalize_text
from .token_utils import count_tokens_approx, split_text_by_paragraph


def steps_to_text(steps: list[str]) -> str:
    if not steps:
        return "Không phát hiện bước rõ ràng."

    return "\n".join(f"- {step}" for step in steps)


def build_procedure_content(procedure: dict[str, Any]) -> str:
    source_pages = procedure.get("source_pages", [])

    return join_non_empty(
        [
            f"Quy trình: {procedure.get('procedure_name')}",
            "Các bước phát hiện:",
            steps_to_text(procedure.get("steps_detected", [])),
            "Nội dung đầy đủ:",
            normalize_text(procedure.get("raw_text", "")),
            f"Nguồn: {format_source_pages(source_pages)}",
        ]
    )


def split_long_procedure_content(
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


def build_procedure_chunks(
    procedures: list[dict[str, Any]],
    max_tokens: int = 500,
) -> list[dict[str, Any]]:
    chunks = []

    for procedure in procedures:
        source_pages = procedure.get("source_pages", [])
        content = build_procedure_content(procedure)

        parts = split_long_procedure_content(
            content=content,
            max_tokens=max_tokens,
        )

        for idx, part in enumerate(parts, start=1):
            suffix = f"_part_{idx}" if len(parts) > 1 else ""

            chunks.append(
                create_chunk(
                    chunk_id=f"procedure_{procedure['procedure_id']}{suffix}",
                    chunk_type="procedure",
                    index_mode="semantic",
                    content=part,
                    metadata={
                        "source_type": "procedure",
                        "procedure_id": procedure.get("procedure_id"),
                        "procedure_name": procedure.get("procedure_name"),
                        "source_pages": source_pages,
                        "review_status": procedure.get("review_status"),
                        "split_from_record": len(parts) > 1,
                        "part_index": idx,
                        "total_parts": len(parts),
                    },
                )
            )

    return chunks