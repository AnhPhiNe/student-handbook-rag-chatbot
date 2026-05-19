from typing import Any
from collections import Counter


def validate_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues = []
    chunk_ids = [chunk.get("chunk_id") for chunk in chunks]
    id_counts = Counter(chunk_ids)

    for chunk in chunks:
        chunk_id = chunk.get("chunk_id")

        if not chunk_id:
            issues.append({"issue": "missing_chunk_id", "severity": "high", "chunk": chunk})

        if id_counts[chunk_id] > 1:
            issues.append({"issue": "duplicate_chunk_id", "severity": "high", "chunk_id": chunk_id})

        if not chunk.get("content"):
            issues.append({"issue": "empty_content", "severity": "high", "chunk_id": chunk_id})

        if not chunk.get("chunk_type"):
            issues.append({"issue": "missing_chunk_type", "severity": "high", "chunk_id": chunk_id})

        if chunk.get("index_mode") not in {"semantic", "structured", "tool"}:
            issues.append({"issue": "invalid_index_mode", "severity": "high", "chunk_id": chunk_id})

        metadata = chunk.get("metadata", {})
        if not metadata.get("source_pages"):
            issues.append({"issue": "missing_source_pages", "severity": "medium", "chunk_id": chunk_id})

    return issues