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


def _row_score(row: dict[str, Any], query_norm: str) -> int:
    program = normalize_text(row.get("Chương trình đào tạo"))
    score = 0
    if any(
        term in query_norm
        for term in ("cap bang thu nhat", "bang thu nhat", "first degree", "cu nhan")
    ):
        if "cap bang thu nhat" in program:
            score += 4
    if (
        any(term in query_norm for term in ("cao dang", "college bridge"))
        and "cao dang" in program
    ):
        score += 4
    if (
        any(term in query_norm for term in ("trung cap", "secondary bridge"))
        and "trung cap" in program
    ):
        score += 4
    if any(
        term in query_norm
        for term in (
            "van bang",
            "bang dai hoc thu hai",
            "mot bang dai hoc",
            "second degree",
        )
    ):
        if "mot bang dai hoc" in program:
            score += 4
    return score


def _select_rows(table: dict[str, Any], query_norm: str) -> list[dict[str, Any]]:
    rows = list(table.get("rows") or [])
    scored = [(row, _row_score(row, query_norm)) for row in rows]
    max_score = max((score for _, score in scored), default=0)
    if max_score <= 0:
        return rows
    return [row for row, score in scored if score == max_score]


def study_duration_lookup(
    query: str,
    tables: list[dict[str, Any]],
    cohort: str | None = None,
    *,
    slots: dict[str, Any],
) -> dict[str, Any] | None:
    """Resolve program duration rules from validated structured slots."""

    program_values = _slot_values(slots.get("program_type"))
    query_norm = normalize_text(" ".join(str(value) for value in program_values))
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
        rows = _select_rows(table, query_norm)
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
