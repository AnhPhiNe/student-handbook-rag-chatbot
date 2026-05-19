import re
from typing import Any


CONTACT_KEYWORDS = [
    "email",
    "số điện thoại",
    "điện thoại",
    "website",
    "ở đâu",
    "địa chỉ",
    "văn phòng",
    "tầng",
    "liên hệ",
]


NEGATIVE_PATTERNS = [
    {
        "query_contains": ["bảo lưu"],
        "bad_chunk_contains": ["lưu trữ"],
        "penalty": 0.25,
    }
]


def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("–", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def get_searchable_text(item: dict[str, Any]) -> str:
    metadata = item.get("metadata", {})
    parts = [
        item.get("content", ""),
        metadata.get("title", ""),
        metadata.get("form_name", ""),
        metadata.get("unit_name", ""),
        metadata.get("faculty_or_unit_name", ""),
        metadata.get("procedure_name", ""),
    ]
    return normalize_text(" ".join(str(p) for p in parts if p))


def entity_boost(
    detected_entities: list[dict[str, Any]],
    item: dict[str, Any],
) -> float:
    if not detected_entities:
        return 0.0

    text = get_searchable_text(item)
    score = 0.0

    for entity in detected_entities:
        canonical = normalize_text(entity.get("canonical_name", ""))
        aliases = [normalize_text(a) for a in entity.get("aliases", [])]

        if canonical and canonical in text:
            score += 0.7
            continue

        if any(alias and alias in text for alias in aliases):
            score += 0.25

    return min(score, 0.9)


def exact_entity_mismatch_penalty(
    query: str,
    detected_entities: list[dict[str, Any]],
    item: dict[str, Any],
) -> float:
    """
    Penalize results that are semantically close but not the exact entity requested.

    Example:
    Query: "email Phòng Đào tạo"
    Bad result: "Phòng Thanh tra Đào tạo"

    The bad result contains "Đào tạo" but does not match the canonical entity
    "Phòng Đào tạo", so it should be pushed down.
    """
    if not detected_entities:
        return 0.0

    q = normalize_text(query)
    text = get_searchable_text(item)
    penalty = 0.0

    for entity in detected_entities:
        canonical = normalize_text(entity.get("canonical_name", ""))
        aliases = [normalize_text(a) for a in entity.get("aliases", [])]

        query_mentions_entity = (
            bool(canonical and canonical in q)
            or any(alias and alias in q for alias in aliases)
        )

        if not query_mentions_entity:
            continue

        item_matches_entity = (
            bool(canonical and canonical in text)
            or any(alias and alias in text for alias in aliases)
        )

        if not item_matches_entity:
            penalty += 0.45

    return min(penalty, 0.8)


def keyword_boost(query: str, item: dict[str, Any]) -> float:
    q = normalize_text(query)
    text = get_searchable_text(item)

    score = 0.0

    for keyword in CONTACT_KEYWORDS:
        if keyword in q and keyword in text:
            score += 0.08

    return min(score, 0.25)


def type_boost(target_chunk_types: list[str], item: dict[str, Any]) -> float:
    if not target_chunk_types:
        return 0.0

    chunk_type = item.get("metadata", {}).get("chunk_type")
    return 0.15 if chunk_type in target_chunk_types else 0.0


def negative_penalty(query: str, item: dict[str, Any]) -> float:
    q = normalize_text(query)
    text = get_searchable_text(item)

    penalty = 0.0

    for rule in NEGATIVE_PATTERNS:
        if any(k in q for k in rule["query_contains"]):
            if any(k in text for k in rule["bad_chunk_contains"]):
                penalty += rule["penalty"]

    return penalty


def rerank_results(
    query: str,
    results: list[dict[str, Any]],
    target_chunk_types: list[str],
    detected_entities: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    detected_entities = detected_entities or []
    reranked = []

    for item in results:
        distance = float(item.get("distance", 1.0))
        semantic_score = 1.0 - distance

        e_boost = entity_boost(detected_entities, item)
        k_boost = keyword_boost(query, item)
        t_boost = type_boost(target_chunk_types, item)
        penalty = negative_penalty(query, item)
        mismatch_penalty = exact_entity_mismatch_penalty(query, detected_entities, item)

        final_score = (
            semantic_score
            + e_boost
            + k_boost
            + t_boost
            - penalty
            - mismatch_penalty
        )

        new_item = dict(item)
        new_item["rerank"] = {
            "semantic_score": round(semantic_score, 4),
            "entity_boost": round(e_boost, 4),
            "keyword_boost": round(k_boost, 4),
            "type_boost": round(t_boost, 4),
            "negative_penalty": round(penalty, 4),
            "entity_mismatch_penalty": round(mismatch_penalty, 4),
            "final_score": round(final_score, 4),
        }

        reranked.append(new_item)

    return sorted(reranked, key=lambda x: x["rerank"]["final_score"], reverse=True)