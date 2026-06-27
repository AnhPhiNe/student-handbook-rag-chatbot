from typing import Any


def flatten_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    flat = {}

    for key, value in metadata.items():
        if value is None:
            flat[key] = ""
        elif isinstance(value, list):
            flat[key] = ",".join(str(item) for item in value)
        elif isinstance(value, dict):
            flat[key] = str(value)
        elif isinstance(value, (str, int, float, bool)):
            flat[key] = value
        else:
            flat[key] = str(value)

    source_pages = metadata.get("source_pages", [])

    if isinstance(source_pages, list) and source_pages:
        flat["page_start"] = min(source_pages)
        flat["page_end"] = max(source_pages)
        flat["source_pages"] = ",".join(str(p) for p in source_pages)

    return flat


def prepare_chroma_payload(
    chunks: list[dict[str, Any]],
) -> tuple[list[str], list[str], list[dict]]:
    ids = []
    documents = []
    metadatas = []

    for chunk in chunks:
        ids.append(chunk["chunk_id"])
        documents.append(chunk["content"])

        metadata = dict(chunk.get("metadata", {}))
        metadata["chunk_id"] = chunk["chunk_id"]
        metadata["chunk_type"] = chunk["chunk_type"]
        metadata["index_mode"] = chunk["index_mode"]
        metadata["token_count_approx"] = chunk.get("token_count_approx", 0)

        metadatas.append(flatten_metadata(metadata))

    return ids, documents, metadatas
