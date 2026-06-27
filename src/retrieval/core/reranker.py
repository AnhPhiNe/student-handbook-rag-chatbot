import re
import unicodedata
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
    text = text.replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
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

        query_mentions_entity = bool(canonical and canonical in q) or any(
            alias and alias in q for alias in aliases
        )

        if not query_mentions_entity:
            continue

        item_matches_entity = bool(canonical and canonical in text) or any(
            alias and alias in text for alias in aliases
        )

        if not item_matches_entity:
            penalty += 0.45

    return min(penalty, 0.8)


def exact_phrase_boost(query: str, item: dict[str, Any]) -> float:
    """Boost chunks that contain exact multi-word phrases from the query.

    Ví dụ: Câu hỏi chứa 'tài khoản sinh viên' → chunk nào chứa đúng cụm này
    sẽ được cộng điểm lớn, thắng các chunk chỉ chứa 'sinh viên' riêng lẻ.
    """
    q = normalize_text(query)
    text = get_searchable_text(item)

    # Trích xuất các cụm từ liên tiếp (2-5 từ) từ câu hỏi
    words = q.split()
    score = 0.0
    matched_phrases: set[str] = set()

    for length in range(min(5, len(words)), 1, -1):  # Ưu tiên cụm dài hơn
        for i in range(len(words) - length + 1):
            phrase = " ".join(words[i : i + length])
            if len(phrase) < 6:  # Bỏ qua cụm quá ngắn
                continue
            # Kiểm tra cụm này không phải là sub-phrase của cụm đã match
            if any(phrase in m for m in matched_phrases):
                continue
            if phrase in text:
                matched_phrases.add(phrase)
                # Cụm càng dài → boost càng lớn
                boost = 0.15 + 0.1 * (length - 2)
                score += min(boost, 0.45)

    return min(score, 0.6)


def keyword_boost(query: str, item: dict[str, Any]) -> float:
    q = normalize_text(query)
    text = get_searchable_text(item)

    score = 0.0

    for keyword in CONTACT_KEYWORDS:
        keyword = normalize_text(keyword)
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
        query_keywords = [normalize_text(k) for k in rule["query_contains"]]
        bad_keywords = [normalize_text(k) for k in rule["bad_chunk_contains"]]
        if any(k in q for k in query_keywords):
            if any(k in text for k in bad_keywords):
                penalty += rule["penalty"]

    return penalty


def rerank_results(
    query: str,
    results: list[dict[str, Any]],
    target_chunk_types: list[str],
    detected_entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Bộ Xếp Hạng Siêu Tốc (Heuristic Reranker).

    Thay vì dùng mô hình Machine Learning (Cross-Encoder) nặng nề chậm chạp,
    hàm này chấm điểm lại (Rerank) các tài liệu lấy từ VectorDB dựa trên luật (Rules):
    - Cộng điểm (Boost) nếu tài liệu chứa đúng Thực thể (Tên phòng ban) người dùng hỏi.
    - Trừ điểm (Penalty) nếu tài liệu chứa tên phòng ban khác dễ gây nhầm lẫn.
    - Tốc độ chạy chỉ ~0.001 giây, không ngốn RAM.
    """
    detected_entities = detected_entities or []
    reranked = []

    for item in results:
        distance = float(item.get("distance", 1.0))
        semantic_score = 1.0 - distance

        e_boost = entity_boost(detected_entities, item)
        p_boost = exact_phrase_boost(query, item)
        k_boost = keyword_boost(query, item)
        t_boost = type_boost(target_chunk_types, item)
        penalty = negative_penalty(query, item)
        mismatch_penalty = exact_entity_mismatch_penalty(query, detected_entities, item)

        final_score = (
            semantic_score
            + e_boost
            + p_boost
            + k_boost
            + t_boost
            - penalty
            - mismatch_penalty
        )

        new_item = dict(item)
        new_item["rerank"] = {
            "semantic_score": round(semantic_score, 4),
            "entity_boost": round(e_boost, 4),
            "exact_phrase_boost": round(p_boost, 4),
            "keyword_boost": round(k_boost, 4),
            "type_boost": round(t_boost, 4),
            "negative_penalty": round(penalty, 4),
            "entity_mismatch_penalty": round(mismatch_penalty, 4),
            "final_score": round(final_score, 4),
        }

        reranked.append(new_item)

    return sorted(reranked, key=lambda x: x["rerank"]["final_score"], reverse=True)
