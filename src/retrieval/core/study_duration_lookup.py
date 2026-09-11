from functools import partial
from typing import Any

from src.common.cohort import (
    is_cohort_applicable,
    normalize_cohort,
)
from src.common.text import fold_text
from src.common.text import slot_values as _slot_values

normalize_text = partial(fold_text, keep="+-")


def _filter_by_cohort(
    tables: list[dict[str, Any]],
    cohort: str | None,
) -> list[dict[str, Any]]:
    normalized_cohort = normalize_cohort(cohort)
    candidates = [
        table for table in tables if table.get("table_type") == "study_duration"
    ]
    if not normalized_cohort:
        return candidates
    return [
        table for table in candidates if is_cohort_applicable(table, normalized_cohort)
    ]


def _wanted_training_modes(value: Any) -> set[str]:
    modes: set[str] = set()
    for item in _slot_values(value):
        normalized = normalize_text(item)
        if "vua lam vua hoc" in normalized or normalized == "vlvh":
            modes.add("vua_lam_vua_hoc")
        elif "chinh quy" in normalized:
            modes.add("chinh_quy")
    return modes


def _table_mode(table: dict[str, Any]) -> str | None:
    table_id = normalize_text(table.get("table_id"))
    if "vua lam vua hoc" in table_id:
        return "vua_lam_vua_hoc"
    if "chinh quy" in table_id:
        return "chinh_quy"
    return None


# Folded "Chương trình đào tạo" label fragment that identifies each program_type row.
_PROGRAM_ROW_MARKERS = {
    "first_degree": "cap bang thu nhat",
    "college_bridge": "cao dang",
    "secondary_bridge": "trung cap",
    "second_degree": "mot bang dai hoc",
}


def _select_rows(table: dict[str, Any], program_types: list[Any]) -> list[dict[str, Any]]:
    rows = list(table.get("rows") or [])
    markers = [
        _PROGRAM_ROW_MARKERS[code]
        for code in (str(value).strip().lower() for value in program_types)
        if code in _PROGRAM_ROW_MARKERS
    ]
    matched = [
        row
        for row in rows
        if any(marker in normalize_text(row.get("Chương trình đào tạo")) for marker in markers)
    ]
    return matched or rows


def study_duration_lookup(
    query: str,
    tables: list[dict[str, Any]],
    cohort: str | None = None,
    *,
    slots: dict[str, Any],
) -> dict[str, Any] | None:
    """Resolve program duration rules from validated structured slots."""

    program_types = _slot_values(slots.get("program_type"))
    wanted_modes = _wanted_training_modes(slots.get("training_mode"))
    effective_cohort = normalize_cohort(cohort)

    candidates = _filter_by_cohort(tables, effective_cohort)
    if not candidates:
        return None

    if wanted_modes:
        candidates = [
            table for table in candidates if _table_mode(table) in wanted_modes
        ]
    if not candidates:
        return None

    table_results = []
    for table in candidates:
        rows = _select_rows(table, program_types)
        if rows:
            table_results.append(
                {
                    "table_id": table.get("table_id"),
                    "table_name": table.get("table_name"),
                    "training_mode": _table_mode(table),
                    "rows": rows,
                    "source_pages": table.get("source_pages") or [],
                    "cohort": table.get("cohort"),
                    "document_id": table.get("document_id"),
                    "source_section": table.get("source_section_id"),
                }
            )

    if not table_results:
        return None

    source_pages = sorted(
        {page for table in table_results for page in table.get("source_pages") or []}
    )
    document_ids = {
        table.get("document_id") for table in table_results if table.get("document_id")
    }
    source_sections = {
        table.get("source_section")
        for table in table_results
        if table.get("source_section")
    }
    display_rows = [
        {
            "training_mode": _table_mode(table),
            **row,
        }
        for table in candidates
        for row in table.get("rows") or []
        if isinstance(row, dict)
    ]

    return {
        "lookup_type": "study_duration",
        "input_value": query,
        "result": {
            "tables": table_results,
            "table_count": len(table_results),
        },
        "items": table_results,
        "display_rows": display_rows,
        "source_pages": source_pages,
        "table_name": "Thời gian học tập chuẩn và tối đa",
        "source_label": "Bảng thời gian học tập trong Sổ tay sinh viên HCMUE",
        "cohort": table_results[0].get("cohort"),
        "document_id": next(iter(document_ids)) if len(document_ids) == 1 else None,
        "source_section": next(iter(source_sections))
        if len(source_sections) == 1
        else "study_duration",
        "content_type": "structured_lookup",
    }
