import re
from typing import Any


def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("–", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def detect_entities(
    query: str,
    entity_registry: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    q = normalize_text(query)
    detected = []

    for entity in entity_registry:
        canonical = normalize_text(entity["canonical_name"])
        aliases = [normalize_text(a) for a in entity.get("aliases", [])]

        if canonical in q or any(alias in q for alias in aliases):
            detected.append(entity)

    return detected


def normalize_query_with_entities(
    query: str,
    detected_entities: list[dict[str, Any]],
) -> str:
    """
    Không replace query gốc, chỉ append canonical name để retrieval dễ bắt đúng entity.
    """
    additions = []

    for entity in detected_entities:
        canonical = entity["canonical_name"]
        if canonical.lower() not in query.lower():
            additions.append(canonical)

    if not additions:
        return query

    return query + " " + " ".join(additions)


def get_entity_target_chunk_types(
    detected_entities: list[dict[str, Any]],
) -> list[str]:
    chunk_types = []

    for entity in detected_entities:
        chunk_types.extend(entity.get("target_chunk_types", []))

    return list(dict.fromkeys(chunk_types))