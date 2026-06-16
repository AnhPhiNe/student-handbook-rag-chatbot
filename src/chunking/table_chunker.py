from typing import Any

from .chunk_schema import create_chunk
from .text_utils import format_source_pages, join_non_empty


def table_rows_to_text(rows: list[dict[str, Any]]) -> str:
    lines = []

    for row in rows:
        row_text = "; ".join(f"{key}: {value}" for key, value in row.items())
        lines.append(f"- {row_text}")

    return "\n".join(lines)


def build_table_chunks(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks = []

    for table in tables:
        source_pages = table.get("source_pages", [])

        content = join_non_empty(
            [
                f"Bảng: {table.get('table_name')}",
                f"Nguồn: {format_source_pages(source_pages)}",
                "Nội dung bảng:",
                table_rows_to_text(table.get("rows", [])),
                "Ghi chú: Bảng này ưu tiên dùng structured lookup thay vì để LLM tự suy đoán.",
            ]
        )

        chunks.append(
            create_chunk(
                chunk_id=f"table_{table['table_id']}",
                chunk_type="table",
                index_mode="structured",
                content=content,
                metadata={
                    "source_type": "scoring_table",
                    "table_id": table.get("table_id"),
                    "table_name": table.get("table_name"),
                    "source_pages": source_pages,
                    "review_status": table.get("review_status"),
                    "lookup_preferred": True,
                },
            )
        )

    return chunks