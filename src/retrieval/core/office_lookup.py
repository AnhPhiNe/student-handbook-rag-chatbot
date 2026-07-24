import hashlib
import re
import threading
import unicodedata
from difflib import SequenceMatcher
from typing import Any

import numpy as np

from src.common.cohort import normalize_cohort


STOPWORDS = {
    "ai",
    "ban",
    "can",
    "cho",
    "co",
    "cua",
    "dang",
    "de",
    "den",
    "duoc",
    "gi",
    "hoi",
    "la",
    "lam",
    "lien",
    "minh",
    "nao",
    "neu",
    "o",
    "phong",
    "sinh",
    "thi",
    "toi",
    "truong",
    "vien",
    "ve",
}

_EMBEDDING_CACHE: dict[tuple[int, str], np.ndarray] = {}
_EMBEDDING_CACHE_LOCK = threading.Lock()


def normalize_text(text: Any) -> str:
    value = str(text or "").lower()
    value = value.replace("đ", "d").replace("Đ", "d")
    decomposed = unicodedata.normalize("NFD", value)
    value = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    value = re.sub(r"[^a-z0-9@._+-]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def tokenize(text: Any) -> set[str]:
    return {
        token
        for token in normalize_text(text).split()
        if len(token) >= 2 and token not in STOPWORDS
    }


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
    values = [
        _strip_order_prefix(record.get("unit_name") or record.get("unit")),
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


def _grounded_query_span(query: str, normalized_value: str) -> str | None:
    words = re.findall(r"[\w@._+-]+", query, flags=re.UNICODE)
    target_size = max(1, len(normalized_value.split()))
    for size in range(max(1, target_size - 1), target_size + 2):
        for start in range(0, len(words) - size + 1):
            span = " ".join(words[start : start + size])
            if normalize_text(span) == normalized_value:
                return span
    return None


def find_grounded_catalog_hint(
    query: str,
    office_directory: list[dict[str, Any]],
    student_service_directory: list[dict[str, Any]],
    student_faculty_profiles: list[dict[str, Any]] | None = None,
    *,
    cohort: str | None = None,
) -> dict[str, Any] | None:
    """Return an exact catalog span that can safely repair a premature clarify route."""
    query_norm = normalize_text(query)
    if not query_norm:
        return None
    normalized_cohort = normalize_cohort(cohort)
    matches: list[dict[str, Any]] = []
    catalogs = (
        ("office", office_directory),
        ("student_service", student_service_directory),
        ("faculty", student_faculty_profiles or []),
    )
    for lookup_type, records in catalogs:
        for record in records:
            record_cohort = normalize_cohort(record.get("cohort"))
            if normalized_cohort and record_cohort and record_cohort != normalized_cohort:
                continue
            for value in _candidate_values(record):
                value_norm = normalize_text(value)
                if len(value_norm) < 3:
                    continue
                if not re.search(
                    rf"(?<![a-z0-9]){re.escape(value_norm)}(?![a-z0-9])",
                    query_norm,
                ):
                    continue
                grounded_span = _grounded_query_span(query, value_norm)
                if not grounded_span:
                    continue
                matches.append(
                    {
                        "lookup_type": lookup_type,
                        "entity_text": grounded_span,
                        "unit_name": _strip_order_prefix(
                            record.get("unit_name") or record.get("unit")
                        ),
                        "entity_key": _entity_key(record),
                        "specificity": (len(value_norm.split()), len(value_norm)),
                        "match_type": "exact_catalog_span",
                    }
                )

    if not matches:
        return None
    matches.sort(key=lambda item: item["specificity"], reverse=True)
    top = matches[0]
    tied_entities = {
        item["entity_key"]
        for item in matches
        if item["specificity"] == top["specificity"]
    }
    if len(tied_entities) > 1:
        return None
    return {
        key: value
        for key, value in top.items()
        if key not in {"entity_key", "specificity"}
    }


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
    responsibilities = record.get("responsibilities") or _extract_responsibilities(raw_text)
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
        cohort_matches = [
            item
            for item in candidates
            if normalize_cohort(item.get("cohort")) == normalized_cohort
        ]
        if cohort_matches:
            candidates = cohort_matches

    ranked = _rank_candidates(candidate_text or query, candidates, model)
    match_score = ranked[0]["confidence"] if ranked else 0.0
    runner_up_score = ranked[1]["confidence"] if len(ranked) > 1 else 0.0
    score_margin = match_score - runner_up_score
    if require_confident_match:
        minimum_confidence = (
            0.62
            if any(
                record.get("content_type") == "student_service_directory"
                for record in candidates
            )
            else 0.72
        )
        if not ranked or match_score < minimum_confidence:
            return None
        if len(ranked) > 1 and score_margin < 0.08:
            options = [
                _strip_order_prefix(item["record"].get("unit_name") or item["record"].get("unit"))
                for item in ranked[:3]
            ]
            return {
                "lookup_type": "office_directory",
                "resolution_status": "ambiguous",
                "clarification_options": list(dict.fromkeys(options)),
                "candidate_text": candidate_text or query,
                "match_score": round(match_score, 4),
                "score_margin": round(score_margin, 4),
            }
        ranked = ranked[:1]
    matches = [
        _summarize_office(item["record"])
        | {
            "score": round(item["confidence"], 4),
            "lexical_score": round(item["lexical_score"], 4),
            "semantic_score": round(item["semantic_score"], 4),
            "selection_method": item["selection_method"],
        }
        for item in ranked[:top_k]
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
