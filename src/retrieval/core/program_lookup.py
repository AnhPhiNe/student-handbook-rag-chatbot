import re
import unicodedata
from collections import defaultdict
from typing import Any

from src.common.cohort import normalize_cohort


def normalize_text(text: Any) -> str:
    """Chuan hoa chuoi de so khop co dau/khong dau on dinh."""
    value = str(text or "").lower()
    value = value.replace("đ", "d").replace("Đ", "D")
    value = unicodedata.normalize("NFD", value)
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _is_fallback_program_list_query(query: str) -> bool:
    text = normalize_text(query)
    if "nganh" not in text:
        return False

    list_cues = (
        "danh sach nganh",
        "liet ke nganh",
        "cac nganh nao",
        "nganh nao",
    )
    return any(cue in text for cue in list_cues)


def _asks_school_programs(query: str) -> bool:
    text = normalize_text(query)
    school_cues = (
        "truong",
        "hcmue",
        "dai hoc su pham",
        "dai hoc su pham tp hcm",
        "dai hoc su pham thanh pho ho chi minh",
        "hien truong",
    )
    return _is_fallback_program_list_query(query) and any(
        cue in text for cue in school_cues
    )


def _faculty_entities(detected_entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        entity
        for entity in detected_entities
        if entity.get("entity_type") == "faculty"
        or "faculty_directory" in (entity.get("target_chunk_types") or [])
    ]


def _normalize_faculty_name(value: Any) -> str:
    text = normalize_text(value)
    text = re.sub(r"^\d+\s+", "", text)
    return text


def _program_summary(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "program_name": record.get("program_name"),
        "faculty_name": record.get("faculty_name"),
        "source_pages": record.get("source_pages") or [],
        "source_section": record.get("source_section"),
        "cohort": record.get("cohort"),
        "document_id": record.get("document_id"),
        "summary": record.get("summary"),
    }


def _sort_programs(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda item: (
            _normalize_faculty_name(item.get("faculty_name")),
            normalize_text(item.get("program_name")),
        ),
    )


def _source_pages(records: list[dict[str, Any]]) -> list[int]:
    pages = {
        int(page)
        for record in records
        for page in (record.get("source_pages") or [])
        if str(page).isdigit()
    }
    return sorted(pages)


def _filter_by_cohort(
    records: list[dict[str, Any]],
    cohort: str | None,
) -> list[dict[str, Any]]:
    normalized_cohort = normalize_cohort(cohort)
    if not normalized_cohort:
        return records
    return [
        record
        for record in records
        if normalize_cohort(record.get("cohort")) == normalized_cohort
    ]


def _filter_by_faculty(
    records: list[dict[str, Any]],
    faculty_entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not faculty_entities:
        return records

    faculty_names = {
        _normalize_faculty_name(entity.get("canonical_name"))
        for entity in faculty_entities
        if entity.get("canonical_name")
    }
    if not faculty_names:
        return records

    return [
        record
        for record in records
        if _normalize_faculty_name(record.get("faculty_name")) in faculty_names
    ]


def _filter_by_program_name(
    records: list[dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    text = normalize_text(query)
    matches = [
        record
        for record in records
        if normalize_text(record.get("program_name")) in text
    ]
    return matches


def _group_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for record in records:
        faculty = str(record.get("faculty_name") or "Chua xac dinh")
        counts[faculty] += 1
    return dict(counts)


def program_lookup(
    query: str,
    program_directory: list[dict[str, Any]],
    cohort: str | None = None,
    detected_entities: list[dict[str, Any]] | None = None,
    routing: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Tra cuu nganh tu structured data theo quyet dinh cua router."""
    routing = routing or {}
    action = str(routing.get("action") or "").strip()
    routed_to_program = routing.get("content_type") == "program_directory" and action in {
        "list",
        "resolve_faculty",
    }
    routed_to_program_list = routed_to_program and action == "list"
    routed_to_program_faculty = routed_to_program and action == "resolve_faculty"
    if (
        not routed_to_program_list
        and not routed_to_program_faculty
        and not _is_fallback_program_list_query(query)
    ):
        return None

    detected_entities = detected_entities or []
    faculty_entities = _faculty_entities(detected_entities)
    scope = str(routing.get("scope") or "").strip()
    asks_school_programs = scope == "school" or (
        not routed_to_program_list and _asks_school_programs(query)
    )
    asks_faculty_programs = scope == "faculty" or bool(faculty_entities)

    if scope == "faculty" and not faculty_entities:
        return None

    if not asks_school_programs and not asks_faculty_programs and not routed_to_program_faculty:
        return None

    candidates = _filter_by_cohort(program_directory, cohort)
    lookup_scope = "school"
    if routed_to_program_faculty:
        candidates = _filter_by_program_name(candidates, query)
        lookup_scope = "program"
        if not candidates:
            return None

    if asks_faculty_programs and not asks_school_programs:
        candidates = _filter_by_faculty(candidates, faculty_entities)
        lookup_scope = "faculty"

    candidates = _sort_programs(candidates)
    if not candidates:
        return None

    normalized_cohort = normalize_cohort(cohort)
    result = [_program_summary(record) for record in candidates]
    document_ids = {
        str(item.get("document_id"))
        for item in result
        if item.get("document_id")
    }

    return {
        "lookup_type": "program_directory",
        "lookup_scope": lookup_scope,
        "input_value": query,
        "result": result,
        "program_count": len(result),
        "faculty_counts": _group_counts(result),
        "source_pages": _source_pages(result),
        "table_name": "Danh sach nganh dao tao",
        "source_label": "Danh muc nganh dao tao trong So tay sinh vien HCMUE",
        "cohort": normalized_cohort,
        "document_id": next(iter(document_ids)) if len(document_ids) == 1 else None,
        "source_section": "program_directory",
        "content_type": "program_directory",
    }
