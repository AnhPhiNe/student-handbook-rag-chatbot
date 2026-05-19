from typing import Any


def parse_source_pages(value: Any) -> list[int]:
    if value is None:
        return []

    if isinstance(value, list):
        return [int(v) for v in value]

    if isinstance(value, int):
        return [value]

    if isinstance(value, str):
        pages = []
        for item in value.split(","):
            item = item.strip()
            if item.isdigit():
                pages.append(int(item))
        return pages

    return []


def build_citations_from_vector_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations = []

    for item in results:
        metadata = item.get("metadata", {})
        citations.append(
            {
                "chunk_id": item.get("chunk_id"),
                "chunk_type": metadata.get("chunk_type"),
                "title": metadata.get("title") or metadata.get("form_name") or metadata.get("unit_name") or metadata.get("faculty_or_unit_name") or metadata.get("procedure_name"),
                "source_pages": parse_source_pages(metadata.get("source_pages")),
                "distance": item.get("distance"),
                "retrieval_purpose": item.get("retrieval_purpose"),
            }
        )

    return citations


def build_citation_from_lookup(lookup_result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_type": "structured_lookup",
            "title": lookup_result.get("table_name"),
            "source_pages": lookup_result.get("source_pages", []),
        }
    ]
