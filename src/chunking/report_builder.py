from typing import Any
from collections import Counter


def get_max_token_limits() -> dict[str, int]:
    return {
        "regulation": 850,
        "form": 250,
        "table": 250,
        "formula": 180,
        "office_directory": 350,
        "faculty_program_directory": 350,
        "reference_directory": 350,
        "procedure": 500,
    }


def detect_overlong_chunks(
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    limits = get_max_token_limits()
    overlong = []

    for chunk in chunks:
        chunk_type = chunk.get("chunk_type")
        token_count = chunk.get("token_count_approx", 0)
        limit = limits.get(chunk_type)

        if limit is None:
            continue

        if token_count > limit:
            overlong.append(
                {
                    "chunk_id": chunk.get("chunk_id"),
                    "chunk_type": chunk_type,
                    "token_count_approx": token_count,
                    "limit": limit,
                    "excess": token_count - limit,
                    "source_pages": chunk.get("metadata", {}).get("source_pages"),
                }
            )

    return overlong


def build_chunk_report(
    regulation_chunks: list[dict[str, Any]],
    table_chunks: list[dict[str, Any]],
    formula_chunks: list[dict[str, Any]],
    form_chunks: list[dict[str, Any]],
    directory_chunks: list[dict[str, Any]],
    procedure_chunks: list[dict[str, Any]],
    all_chunks: list[dict[str, Any]],
    validation_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    overlong_chunks = detect_overlong_chunks(all_chunks)

    return {
        "total_chunks": len(all_chunks),
        "regulation_chunks": len(regulation_chunks),
        "table_chunks": len(table_chunks),
        "formula_chunks": len(formula_chunks),
        "form_chunks": len(form_chunks),
        "directory_chunks": len(directory_chunks),
        "procedure_chunks": len(procedure_chunks),
        "chunk_type_count": dict(Counter(chunk["chunk_type"] for chunk in all_chunks)),
        "index_mode_count": dict(Counter(chunk["index_mode"] for chunk in all_chunks)),
        "avg_token_count_approx": round(
            sum(chunk["token_count_approx"] for chunk in all_chunks) / max(len(all_chunks), 1),
            2,
        ),
        "max_token_count_approx": max(
            [chunk["token_count_approx"] for chunk in all_chunks],
            default=0,
        ),
        "overlong_chunks_count": len(overlong_chunks),
        "overlong_chunks": overlong_chunks,
        "validation_issues": validation_issues,
    }