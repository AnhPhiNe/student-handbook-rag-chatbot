from __future__ import annotations

import re
import unicodedata
from typing import Any

from src.common.cohort import normalize_cohort


CANONICAL_TYPES_BY_LOOKUP = {
    "foreign_language": {"foreign_language", "foreign_language_equivalency"},
    "study_duration": {"study_duration"},
    "scholarship_classification": {"scholarship", "scholarship_classification"},
    "scoring": {
        "scoring",
        "grade_scale",
        "grade_10_to_letter",
        "pass_fail_ungraded",
        "letter_to_grade4",
        "academic_classification",
        "conduct",
        "conduct_classification",
    },
}

SUBTYPES_BY_OPERATION = {
    "grade_10_to_letter": {
        "grade_scale",
        "grade_10_to_letter",
        "pass_fail_ungraded",
    },
    "pass_fail_ungraded": {"pass_fail_ungraded"},
    "letter_to_grade_4": {"letter_to_grade4", "letter_to_grade_4"},
    "academic_classification": {"academic_classification"},
    "conduct_classification": {"conduct", "conduct_classification"},
}


def _normalize(value: Any) -> str:
    text = str(value or "").lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = re.sub(r"[^a-z0-9+.,-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _mentioned_cohorts(query: str, selected_cohort: str | None) -> set[str]:
    selected = normalize_cohort(selected_cohort)
    if selected:
        return {selected}
    normalized = _normalize(query)
    cohorts: set[str] = set()
    if re.search(r"\bk\s*48\s*[-/]?\s*k?\s*49\b|\bk\s*48\b|\bk\s*49\b", normalized):
        cohorts.add("K48-K49")
    if re.search(r"\bk\s*50\b", normalized):
        cohorts.add("K50")
    if re.search(r"\bk\s*51\b", normalized):
        cohorts.add("K51")
    return cohorts


def _select_rows(table: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    rows = [row for row in table.get("rows") or [] if isinstance(row, dict)]
    return rows, "full_table"


def _table_text(table: dict[str, Any]) -> str:
    return " ".join(
        str(table.get(key) or "")
        for key in (
            "table_id",
            "table_name",
            "table_type",
            "table_subtype",
            "applicability",
        )
    )


def _matches_study_duration_slots(table: dict[str, Any], slots: dict[str, Any]) -> bool:
    training_mode = str(slots.get("training_mode") or "")
    if not training_mode:
        return True
    table_norm = _normalize(_table_text(table))
    mode_norm = _normalize(training_mode)
    if mode_norm == "chinh quy":
        return "chinh quy" in table_norm
    if mode_norm == "vua lam vua hoc":
        return "vua lam vua hoc" in table_norm
    return mode_norm in table_norm


def build_structured_context(
    decision: dict[str, Any],
    tables: list[dict[str, Any]],
    *,
    query: str,
    cohort: str | None,
) -> dict[str, Any] | None:
    """Select authoritative table data for reasoning without vector indexing."""
    lookup_type = str(decision.get("lookup_type") or "")
    allowed_types = CANONICAL_TYPES_BY_LOOKUP.get(lookup_type)
    if not allowed_types:
        return None

    slots = decision.get("slots") if isinstance(decision.get("slots"), dict) else {}
    operation = str(slots.get("operation") or "")
    allowed_subtypes = SUBTYPES_BY_OPERATION.get(operation)
    wanted_cohorts = _mentioned_cohorts(query, cohort or decision.get("cohort"))

    eligible_tables: list[dict[str, Any]] = []
    for table in tables:
        if not isinstance(table, dict) or not table.get("used_by_runtime", True):
            continue
        table_type = str(table.get("table_type") or "")
        table_subtype = str(table.get("table_subtype") or table_type)
        if table_type not in allowed_types and table_subtype not in allowed_types:
            continue
        if allowed_subtypes and table_subtype not in allowed_subtypes:
            continue
        if lookup_type == "study_duration" and not _matches_study_duration_slots(
            table, slots
        ):
            continue
        eligible_tables.append(table)

    available_cohorts = {
        normalized
        for table in eligible_tables
        if (normalized := normalize_cohort(table.get("cohort")))
    }
    if not wanted_cohorts:
        if len(available_cohorts) != 1:
            return None
        wanted_cohorts = set(available_cohorts)

    selected_tables: list[dict[str, Any]] = []
    for table in eligible_tables:
        table_type = str(table.get("table_type") or "")
        table_subtype = str(table.get("table_subtype") or table_type)
        table_cohort = normalize_cohort(table.get("cohort"))
        if wanted_cohorts and table_cohort not in wanted_cohorts:
            continue
        rows, selection_method = _select_rows(table)
        if not rows:
            continue
        selected_tables.append(
            {
                "table_id": table.get("table_id"),
                "table_type": table_type,
                "table_subtype": table_subtype,
                "table_name": table.get("table_name"),
                "applicability": table.get("applicability"),
                "cohort": table_cohort,
                "document_id": table.get("document_id"),
                "source_parent_id": table.get("source_parent_id")
                or table.get("source_section_id"),
                "source_pages": table.get("source_pages") or [],
                "columns": table.get("columns") or [],
                "rows": rows,
                "total_row_count": len(table.get("rows") or []),
                "selection_method": selection_method,
                "derived_from": table.get("derived_from"),
            }
        )

    if not selected_tables:
        return None
    selected_tables.sort(
        key=lambda item: (str(item.get("cohort") or ""), str(item.get("table_id") or ""))
    )
    return {
        "lookup_type": "structured_context",
        "source_lookup_type": lookup_type,
        "execution_mode": decision.get("execution_mode"),
        "cohort": (
            next(iter(wanted_cohorts)) if len(wanted_cohorts) == 1 else None
        ),
        "items": selected_tables,
        "source_parent_ids": list(
            dict.fromkeys(
                str(item["source_parent_id"])
                for item in selected_tables
                if item.get("source_parent_id")
            )
        ),
    }
