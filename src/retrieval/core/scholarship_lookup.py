import re
from functools import partial
from typing import Any

from src.common.cohort import (
    is_cohort_applicable,
    normalize_cohort,
)
from src.common.score import parse_score
from src.common.text import fold_text
from src.common.text import slot_values as _slot_values
from src.retrieval.core.ordinal_labels import annotate_minimum_levels
from src.retrieval.core.structured_lookup import in_range

LABEL_ALIASES = {
    "Khá": ["kha"],
    "Giỏi": ["gioi"],
    "Xuất sắc": ["xuat sac", "xuatsac"],
}


normalize_text = partial(fold_text, keep="+.,-")


def _filter_tables(
    tables: list[dict[str, Any]],
    cohort: str | None,
    *,
    table_id: str = "scholarship_classification",
) -> list[dict[str, Any]]:
    normalized_cohort = normalize_cohort(cohort)
    candidates = [table for table in tables if table.get("table_id") == table_id]
    if not normalized_cohort:
        return candidates
    return [
        table for table in candidates if is_cohort_applicable(table, normalized_cohort)
    ]


def _requested_labels(query_norm: str) -> list[str]:
    labels = []
    for label, aliases in LABEL_ALIASES.items():
        # A label must be a whole word or phrase: "khác" must not select "Khá".
        if any(re.search(rf"\b{re.escape(alias)}\b", query_norm) for alias in aliases):
            labels.append(label)
    return labels


def _rows_for_slots(
    value: Any,
    table: dict[str, Any],
) -> tuple[list[dict[str, Any]], float | None]:
    """Select the union of every explicitly supplied score/label choice."""

    rows = list(table.get("rows") or [])
    values = _slot_values(value)
    if not values:
        return rows, None

    matched_rows: list[dict[str, Any]] = []
    numeric_values: list[float] = []
    for item in values:
        item_norm = normalize_text(item)
        labels = _requested_labels(item_norm)
        score = parse_score(item)
        item_score = None
        if labels:
            norm_labels = {normalize_text(label) for label in labels}
            item_rows = [row for row in rows
                         if normalize_text(row.get("label") or row.get("scholarship_level")) in norm_labels]
        elif score is not None and score.scale is None and score.value >= 0:
            # Match the scalar input, not numbers extracted from a label or fraction.
            item_score = float(score.value)
            item_rows = [row for row in rows
                         if in_range(item_score, str(row.get("scholarship_score_range") or ""))]
        else:
            continue
        if item_score is not None:
            numeric_values.append(item_score)
        for row in item_rows:
            if row not in matched_rows:
                matched_rows.append(row)

    matched_score = numeric_values[0] if len(numeric_values) == 1 else None
    return matched_rows, matched_score


def scholarship_table_lookup(
    query: str,
    tables: list[dict[str, Any]],
    cohort: str | None = None,
    *,
    slots: dict[str, Any],
    table_id: str = "scholarship_classification",
) -> dict[str, Any] | None:
    """Resolve scholarship thresholds from validated structured slots."""

    score_or_label = slots.get("score_or_label")
    effective_cohort = normalize_cohort(cohort)

    candidates = _filter_tables(tables, effective_cohort, table_id=table_id)
    if not candidates:
        return None

    table = {**candidates[0], "rows": annotate_minimum_levels(list(candidates[0].get("rows") or []))}
    rows, score = _rows_for_slots(score_or_label, table)
    if not rows:
        return None

    result: dict[str, Any] = {
        "rows": rows,
        "matched_score": score,
        "result_count": len(rows),
    }
    if len(rows) == 1:
        result = dict(rows[0])
        if score is not None:
            result["matched_score"] = score

    return {
        "lookup_type": "scholarship_classification",
        "input_value": query,
        "result": result,
        "items": rows,
        "display_rows": list(table.get("rows") or []),
        "source_pages": table.get("source_pages") or [],
        "table_name": table.get("table_name")
        or (
            "Mức học bổng khuyến khích học tập"
            if table_id == "scholarship_amount"
            else "Xếp loại học bổng khuyến khích học tập"
        ),
        "source_label": "Bảng học bổng khuyến khích học tập trong Sổ tay sinh viên HCMUE",
        "cohort": table.get("cohort"),
        "document_id": table.get("document_id"),
        "source_section": table.get("source_section") or "scoring_table",
        "content_type": "structured_lookup",
    }
