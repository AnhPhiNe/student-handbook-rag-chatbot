import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any


def normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("–", "-")
    text = text.replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
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

        # Exact phrase match duoc uu tien truoc, co boundary de alias ngan khong match nham trong tu dai.
        if _contains_phrase(q, canonical) or any(_contains_phrase(q, alias) for alias in aliases):
            detected.append(entity)
            continue

        # Fuzzy match chi dung cho alias dai, giup bat typo nhe nhung tranh false positive voi alias ngan.
        if _has_fuzzy_alias_match(q, [canonical, *aliases]):
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
        # Append canonical name de embedding co them tu khoa chuan, nhung van giu nguyen cau user.
        if canonical not in query:
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


def _has_fuzzy_alias_match(query: str, aliases: list[str]) -> bool:
    query_tokens = re.findall(r"\w+", query)
    if len(query_tokens) < 2:
        return False

    for alias in aliases:
        alias = normalize_text(alias)
        alias_tokens = re.findall(r"\w+", alias)
        # Alias qua ngan rat de match nham, nen khong fuzzy cho cac alias ngan.
        if len(alias_tokens) < 2 or len(alias) < 8:
            continue

        if _best_window_ratio(query_tokens, alias_tokens) >= _threshold_for_alias(alias):
            return True

    return False


def _contains_phrase(text: str, phrase: str) -> bool:
    phrase = phrase.strip()
    if not phrase:
        return False

    # Boundary giup "hoc vu" khong match vao "hoc vuot", va "CNTT" khong match trong token la.
    starts_word = phrase[0].isalnum() or phrase[0] == "_"
    ends_word = phrase[-1].isalnum() or phrase[-1] == "_"
    prefix = r"(?<!\w)" if starts_word else ""
    suffix = r"(?!\w)" if ends_word else ""
    return re.search(prefix + re.escape(phrase) + suffix, text) is not None


def _best_window_ratio(query_tokens: list[str], alias_tokens: list[str]) -> float:
    best = 0.0
    min_size = max(1, len(alias_tokens) - 1)
    max_size = min(len(query_tokens), len(alias_tokens) + 1)

    # So alias voi tung cua so token trong query de bat typo/thieu mot tu.
    for size in range(min_size, max_size + 1):
        for start in range(0, len(query_tokens) - size + 1):
            window = " ".join(query_tokens[start : start + size])
            alias = " ".join(alias_tokens)
            best = max(best, SequenceMatcher(None, window, alias).ratio())

    return best


def _threshold_for_alias(alias: str) -> float:
    if len(alias) <= 15:
        return 0.90
    if len(alias) <= 25:
        return 0.88
    return 0.85
