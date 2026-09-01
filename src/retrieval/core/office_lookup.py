import hashlib
import re
import threading
import unicodedata
from difflib import SequenceMatcher
from typing import Any

import numpy as np

from src.common.cohort import is_validated_source_applicable, normalize_cohort


_EMBEDDING_CACHE: dict[tuple[int, str], np.ndarray] = {}
_EMBEDDING_CACHE_LOCK = threading.Lock()
DEFAULT_MIN_CONFIDENCE = 0.72
DEFAULT_AMBIGUITY_MARGIN = 0.08
_IGNORED_ENTITY_SPAN_WORDS = {
    "dia",
    "chi",
    "so",
    "thong",
    "tin",
    "ban",
    "khoa",
    "phong",
    "dien",
    "thoai",
    "email",
}


def normalize_text(text: Any) -> str:
    value = str(text or "").lower()
    value = value.replace("đ", "d").replace("Đ", "d")
    decomposed = unicodedata.normalize("NFD", value)
    value = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    value = re.sub(r"[^a-z0-9@._+-]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _strip_order_prefix(value: Any) -> str:
    return re.sub(r"^\s*\d+\.\s*", "", str(value or "")).strip()


def _office_search_text(record: dict[str, Any]) -> str:
    return " ".join(
        str(value)
        for value in [
            record.get("unit_name"),
            record.get("unit"),
            record.get("service"),
            " ".join(record.get("aliases") or []),
            record.get("summary"),
            record.get("raw_text"),
            record.get("email"),
            record.get("phone"),
            record.get("office"),
            record.get("source_section"),
        ]
        if value
    )


def _candidate_values(record: dict[str, Any]) -> list[str]:
    base_unit = _strip_order_prefix(record.get("unit_name") or record.get("unit"))
    values = [
        base_unit,
        str(record.get("service") or "").strip(),
        *(str(alias).strip() for alias in record.get("aliases") or []),
    ]
    return list(dict.fromkeys(value for value in values if value))


def _fuzzy_similarity(left: str, right: str) -> float:
    left_norm = normalize_text(left)
    right_norm = normalize_text(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0

    left_tokens = set(left_norm.split())
    right_tokens = set(right_norm.split())
    overlap = len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)
    sequence = SequenceMatcher(None, left_norm, right_norm).ratio()
    containment = 0.0
    if min(len(left_norm), len(right_norm)) >= 3:
        short_str, long_str = (
            (left_norm, right_norm)
            if len(left_norm) < len(right_norm)
            else (right_norm, left_norm)
        )
        if re.search(rf"(?<![a-z0-9]){re.escape(short_str)}(?![a-z0-9])", long_str):
            containment = 0.84 + 0.12 * (len(short_str) / len(long_str))
    return min(1.0, max(sequence, overlap, containment))


def _lexical_candidate_score(candidate_text: str, record: dict[str, Any]) -> float:
    return max(
        (_fuzzy_similarity(candidate_text, value) for value in _candidate_values(record)),
        default=0.0,
    )


def _catalog_fingerprint(records: list[dict[str, Any]]) -> str:
    payload = "\n".join(
        f"{record.get('record_id') or record.get('service_id') or ''}|"
        f"{'|'.join(_candidate_values(record))}"
        for record in records
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _encode(model: Any, texts: list[str]) -> np.ndarray:
    try:
        encoded = model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
    except TypeError:
        encoded = model.encode(texts)
    array = np.asarray(encoded, dtype=np.float32)
    if array.ndim == 1:
        array = array.reshape(1, -1)
    norms = np.linalg.norm(array, axis=1, keepdims=True)
    return array / np.maximum(norms, 1e-12)


def _semantic_candidate_scores(
    candidate_text: str,
    records: list[dict[str, Any]],
    model: Any | None,
) -> list[float]:
    if model is None or not records:
        return [0.0] * len(records)
    search_texts = [" | ".join(_candidate_values(record)) for record in records]
    cache_key = (id(model), _catalog_fingerprint(records))
    try:
        with _EMBEDDING_CACHE_LOCK:
            catalog_embeddings = _EMBEDDING_CACHE.get(cache_key)
        if catalog_embeddings is None:
            catalog_embeddings = _encode(model, search_texts)
            with _EMBEDDING_CACHE_LOCK:
                _EMBEDDING_CACHE[cache_key] = catalog_embeddings
        query_embedding = _encode(model, [candidate_text])[0]
        scores = catalog_embeddings @ query_embedding
        return [float(max(0.0, min(1.0, score))) for score in scores]
    except Exception:
        return [0.0] * len(records)


def _entity_key(record: dict[str, Any]) -> str:
    return normalize_text(
        _strip_order_prefix(record.get("unit_name") or record.get("unit"))
    ) or normalize_text(record.get("record_id") or record.get("service_id"))


def _rank_candidates(
    candidate_text: str,
    records: list[dict[str, Any]],
    model: Any | None,
) -> list[dict[str, Any]]:
    semantic_scores = _semantic_candidate_scores(candidate_text, records, model)
    best_by_entity: dict[str, dict[str, Any]] = {}
    for record, semantic_score in zip(records, semantic_scores, strict=True):
        lexical_score = _lexical_candidate_score(candidate_text, record)
        if lexical_score >= 0.98:
            confidence = 1.0
            method = "catalog_exact"
        else:
            confidence = max(
                lexical_score,
                0.65 * lexical_score + 0.35 * semantic_score,
                0.85 * semantic_score,
            )
            method = "catalog_fuzzy_semantic" if semantic_score else "catalog_fuzzy"
        ranked = {
            "record": record,
            "confidence": confidence,
            "lexical_score": lexical_score,
            "semantic_score": semantic_score,
            "selection_method": method,
        }
        key = _entity_key(record)
        previous = best_by_entity.get(key)
        if previous is None or confidence > previous["confidence"]:
            best_by_entity[key] = ranked
    return sorted(
        best_by_entity.values(),
        key=lambda item: item["confidence"],
        reverse=True,
    )


def _extract_emails(raw_text: str) -> list[str]:
    return sorted(set(re.findall(r"[A-Za-z0-9._%+-]+@hcmue\.edu\.vn", raw_text)))


def _extract_websites(raw_text: str) -> list[str]:
    matches = re.findall(r"(?:https?://)?[A-Za-z0-9.-]+\.hcmue\.edu\.vn", raw_text)
    return sorted(set(match.rstrip(".,;") for match in matches))


def _extract_phones(raw_text: str) -> list[str]:
    phones = re.findall(r"\(?0\d{2,3}\)?[ .-]?\d{3,4}[ .-]?\d{3,4}", raw_text)
    return sorted(set(phone.strip() for phone in phones))


def _extract_internal_numbers(raw_text: str) -> list[str]:
    numbers: set[str] = set()
    for line in raw_text.splitlines():
        if "nội bộ" not in line.lower() and "noi bo" not in normalize_text(line):
            continue
        for number in re.findall(r"\b\d{2,4}\b", line):
            numbers.add(number)
    return sorted(numbers)


def _extract_responsibilities(raw_text: str, limit: int = 4) -> list[str]:
    responsibilities: list[str] = []
    for line in raw_text.splitlines():
        line = re.sub(r"^[•\-–+\s]+", "", line.strip())
        if not line or len(line) < 18:
            continue
        norm = normalize_text(line)
        if any(
            marker in norm
            for marker in (
                "phu trach",
                "thuc hien",
                "quan ly",
                "tham muu",
                "cap",
                "giai quyet",
                "to chuc",
                "ho tro",
            )
        ):
            responsibilities.append(line)
        if len(responsibilities) >= limit:
            break
    return responsibilities


def _summarize_office(record: dict[str, Any]) -> dict[str, Any]:
    raw_text = str(record.get("raw_text") or "")
    emails = record.get("emails") or _extract_emails(raw_text)
    phones = record.get("phones") or _extract_phones(raw_text)
    websites = record.get("websites") or _extract_websites(raw_text)
    internal_numbers = record.get("internal_numbers") or _extract_internal_numbers(raw_text)
    responsibilities = record.get("responsibilities") or record.get("services") or _extract_responsibilities(raw_text)
    if record.get("service"):
        responsibilities = [str(record["service"])] + [
            item for item in responsibilities if item != record.get("service")
        ]
    return {
        "record_id": record.get("record_id")
        or record.get("service_id")
        or record.get("faculty_profile_id"),
        "service_id": record.get("service_id"),
        "service": record.get("service"),
        "aliases": record.get("aliases") or [],
        "unit_name": _strip_order_prefix(record.get("unit_name") or record.get("unit")),
        "content_type": record.get("content_type") or "office_directory",
        "source_pages": record.get("source_pages") or [],
        "source_section": record.get("source_section"),
        "cohort": record.get("cohort"),
        "document_id": record.get("document_id"),
        "emails": emails,
        "phones": phones,
        "internal_numbers": internal_numbers,
        "websites": websites,
        "office": record.get("office"),
        "responsibilities": responsibilities,
        "summary": (record.get("summary") or raw_text[:500]).strip(),
    }


def _explicit_ranked_entities(
    search_text: str,
    ranked: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    """Return distinct catalog entities explicitly named in the search text."""

    span_matches: list[tuple[int, int, int, str, dict[str, Any]]] = []
    for ranked_item in ranked:
        for candidate_value in _candidate_values(ranked_item["record"]):
            normalized_value = normalize_text(candidate_value)
            if (
                len(normalized_value) < 3
                or normalized_value in _IGNORED_ENTITY_SPAN_WORDS
            ):
                continue
            for match in re.finditer(
                rf"(?<![a-z0-9]){re.escape(normalized_value)}(?![a-z0-9])",
                search_text,
            ):
                span_matches.append(
                    (
                        len(normalized_value),
                        match.start(),
                        match.end(),
                        normalized_value,
                        ranked_item,
                    )
                )

    span_matches.sort(key=lambda item: (item[0], len(item[3].split())), reverse=True)
    accepted_spans: list[tuple[int, int]] = []
    distinct_items: list[dict[str, Any]] = []
    seen_entity_keys: set[str] = set()
    for _, start, end, _, ranked_item in span_matches:
        if any(
            accepted_start <= start and end <= accepted_end
            for accepted_start, accepted_end in accepted_spans
        ):
            continue
        accepted_spans.append((start, end))
        entity_key = _entity_key(ranked_item["record"])
        if entity_key not in seen_entity_keys:
            seen_entity_keys.add(entity_key)
            distinct_items.append(ranked_item)

    if not span_matches:
        return distinct_items, 0
    top_span = span_matches[0]
    tied_span_count = sum(
        match[1] == top_span[1] and match[2] == top_span[2]
        for match in span_matches
    )
    return distinct_items, tied_span_count


def _clarification_response(
    ranked: list[dict[str, Any]],
    *,
    candidate_text: str,
    match_score: float,
    score_margin: float,
) -> dict[str, Any]:
    options: list[str] = []
    seen_units: set[str] = set()
    for item in ranked[:3]:
        record = item["record"]
        unit = _strip_order_prefix(record.get("unit_name") or record.get("unit"))
        if unit in seen_units:
            continue
        seen_units.add(unit)

        service = record.get("service")
        if not service:
            responsibilities = record.get("responsibilities")
            if responsibilities and isinstance(responsibilities, list):
                service = responsibilities[0] if responsibilities else None

        if service:
            service_text = str(service).strip()
            if len(service_text) > 250:
                service_text = service_text[:247] + "..."
            options.append(f"- **{unit}**: {service_text}")
        else:
            options.append(f"- **{unit}**")

    return {
        "lookup_type": "office_directory",
        "resolution_status": "ambiguous",
        "clarification_options": options,
        "candidate_text": candidate_text,
        "match_score": round(match_score, 4),
        "score_margin": round(score_margin, 4),
    }


def _select_confident_candidates(
    *,
    query: str,
    candidate_text: str,
    ranked: list[dict[str, Any]],
    require_confident_match: bool,
    min_confidence: float,
    ambiguity_margin: float,
) -> tuple[list[dict[str, Any]] | None, dict[str, Any] | None, int]:
    """Apply confidence, explicit-entity and ambiguity rules to ranked records."""

    if not require_confident_match:
        return ranked, None, 0

    match_score = ranked[0]["confidence"] if ranked else 0.0
    runner_up_score = ranked[1]["confidence"] if len(ranked) > 1 else 0.0
    score_margin = match_score - runner_up_score
    if not ranked or match_score < min_confidence:
        return None, None, 0

    normalized_candidate = normalize_text(candidate_text)
    normalized_query = normalize_text(query)
    search_text = (
        normalized_query
        if len(normalized_query) > len(normalized_candidate)
        else normalized_candidate
    )
    explicit_entities, tied_span_count = _explicit_ranked_entities(search_text, ranked)
    if len(explicit_entities) > 1:
        return explicit_entities, None, len(explicit_entities)
    if len(explicit_entities) == 1 and tied_span_count <= 1:
        return explicit_entities, None, 1

    if len(ranked) > 1 and score_margin < ambiguity_margin:
        return (
            None,
            _clarification_response(
                ranked,
                candidate_text=candidate_text,
                match_score=match_score,
                score_margin=score_margin,
            ),
            0,
        )
    return ranked, None, 0


def office_lookup(
    query: str,
    office_directory: list[dict[str, Any]],
    cohort: str | None = None,
    detected_entities: list[dict[str, Any]] | None = None,
    routing: dict[str, Any] | None = None,
    top_k: int = 3,
    candidate_text: str | None = None,
    require_confident_match: bool = False,
    model: Any | None = None,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    ambiguity_margin: float = DEFAULT_AMBIGUITY_MARGIN,
) -> dict[str, Any] | None:
    """Resolve an office or student service from the production catalog."""
    routing = routing or {}
    target_types = set(routing.get("target_chunk_types") or [])
    routed_to_office = (
        routing.get("intent") == "office_query"
        or routing.get("content_type") == "office_directory"
        or "office_directory" in target_types
    )
    typed_candidate = bool(candidate_text and candidate_text.strip())
    entity_targets = {
        target
        for entity in (detected_entities or [])
        for target in (entity.get("target_chunk_types") or [])
    }
    routed_to_office = routed_to_office or "office_directory" in entity_targets

    if not typed_candidate and not routed_to_office:
        return None

    normalized_cohort = normalize_cohort(cohort)
    candidates = office_directory
    if normalized_cohort:
        candidates = [
            item
            for item in candidates
            if is_validated_source_applicable(item, normalized_cohort)
        ]

    ranked = _rank_candidates(candidate_text or query, candidates, model)
    match_score = ranked[0]["confidence"] if ranked else 0.0
    runner_up_score = ranked[1]["confidence"] if len(ranked) > 1 else 0.0
    score_margin = match_score - runner_up_score
    ranked, ambiguity, explicit_entity_count = _select_confident_candidates(
        query=query,
        candidate_text=candidate_text or query,
        ranked=ranked,
        require_confident_match=require_confident_match,
        min_confidence=min_confidence,
        ambiguity_margin=ambiguity_margin,
    )
    if ambiguity is not None:
        return ambiguity
    if ranked is None:
        return None

    effective_top_k = max(top_k, explicit_entity_count)
    matches = [
        _summarize_office(item["record"])
        | {
            "score": round(item["confidence"], 4),
            "lexical_score": round(item["lexical_score"], 4),
            "semantic_score": round(item["semantic_score"], 4),
            "selection_method": item["selection_method"],
        }
        for item in ranked[:effective_top_k]
    ]

    if not matches:
        return None

    source_pages = sorted(
        {
            int(page)
            for match in matches
            for page in match.get("source_pages", [])
            if str(page).isdigit()
        }
    )
    document_ids = {
        str(match.get("document_id")) for match in matches if match.get("document_id")
    }

    selected_content_types = {
        str(match.get("content_type") or "") for match in matches
    }
    is_service = "student_service_directory" in selected_content_types
    is_faculty = "student_faculty_profile" in selected_content_types
    if is_service:
        lookup_scope = "student_service"
        table_name = "Danh sach dich vu sinh vien"
        source_label = "Danh muc dich vu sinh vien trong So tay sinh vien HCMUE"
        source_section = "student_service_directory"
        content_type = "student_service_directory"
    elif is_faculty:
        lookup_scope = "faculty"
        table_name = "Danh sach Khoa lien he"
        source_label = "Danh muc Khoa/lien he trong So tay sinh vien HCMUE"
        source_section = "student_faculty_profiles"
        content_type = "student_faculty_profile"
    else:
        lookup_scope = "office"
        table_name = "Danh sach phong ban lien he"
        source_label = "Danh muc phong ban/lien he trong So tay sinh vien HCMUE"
        source_section = "student_office_profiles"
        content_type = "student_office_profile"

    return {
        "lookup_type": "office_directory",
        "lookup_scope": lookup_scope,
        "input_value": query,
        "result": matches,
        "items": matches,
        "office_count": len(matches),
        "source_pages": source_pages,
        "table_name": table_name,
        "source_label": source_label,
        "cohort": normalized_cohort,
        "document_id": next(iter(document_ids)) if len(document_ids) == 1 else None,
        "source_section": source_section,
        "content_type": content_type,
        "match_score": round(match_score, 4),
        "score_margin": round(score_margin, 4),
        "selection_method": matches[0]["selection_method"],
    }
