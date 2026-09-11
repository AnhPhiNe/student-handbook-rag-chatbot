import re
from functools import partial
from typing import Any

from src.common.cohort import (
    is_cohort_applicable,
    normalize_cohort,
)
from src.common.text import fold_text
from src.common.text import slot_values as _slot_values

normalize_text = partial(fold_text, keep="+.,-")


def _filter_by_cohort(
    tables: list[dict[str, Any]],
    cohort: str | None,
) -> list[dict[str, Any]]:
    normalized_cohort = normalize_cohort(cohort)
    if not normalized_cohort:
        return tables
    return [table for table in tables if is_cohort_applicable(table, normalized_cohort)]


def _extract_numbers(text: str) -> list[float]:
    values: list[float] = []
    for match in re.finditer(r"(?<!\d)(\d+(?:[,.]\d+)?)(?!\d)", text):
        value = match.group(1).replace(",", ".")
        try:
            values.append(float(value))
        except ValueError:
            continue
    return values


def _strip_cohort_numbers(text: str) -> str:
    text = re.sub(r"\bk\s*\d{2}\b", " ", text)
    text = re.sub(r"\bkhoa\s*\d{2}\b", " ", text)
    return text


def _parse_range(value: Any) -> tuple[float, float] | None:
    nums = _extract_numbers(normalize_text(value))
    if len(nums) >= 2:
        return min(nums[0], nums[1]), max(nums[0], nums[1])
    if len(nums) == 1:
        return nums[0], nums[0]
    return None


def _level_from_numeric(row: dict[str, Any], numbers: list[float]) -> str | None:
    if not numbers:
        return None

    row_norm = normalize_text(
        " ".join(
            [
                str(row.get("certificate") or ""),
                str(row.get("level_or_scale") or ""),
            ]
        )
    )
    value = numbers[-1]

    if "toeic" in row_norm:
        return None

    level_4_range = _parse_range(row.get("equivalent_level_4"))
    if level_4_range and level_4_range[0] <= value <= level_4_range[1]:
        return "bac_4"

    level_3_range = _parse_range(row.get("equivalent_level_3"))
    if level_3_range and level_3_range[0] <= value <= level_3_range[1]:
        return "bac_3"

    if "hsk" in row_norm and value in {3.0, 4.0}:
        return "bac_4" if value == 4.0 else "bac_3"

    if "topik" in row_norm:
        if value >= 150:
            return "bac_4"
        if value >= 120:
            return "bac_3"

    return None


def _level_from_text(row: dict[str, Any], query_norm: str) -> str | None:
    level_3_norm = normalize_text(row.get("equivalent_level_3"))
    level_4_norm = normalize_text(row.get("equivalent_level_4"))

    if "bac 4" in query_norm and ("bac 4" in level_4_norm or "4" in level_4_norm):
        return "bac_4"
    if "bac 3" in query_norm and ("bac 3" in level_3_norm or "3" in level_3_norm):
        return "bac_3"
    if "n3" in query_norm and "n3" in level_4_norm:
        return "bac_4"
    if "n4" in query_norm and "n4" in level_3_norm:
        return "bac_3"
    if "b2" in query_norm and "b2" in level_4_norm:
        return "bac_4"
    if "b1" in query_norm and "b1" in level_3_norm:
        return "bac_3"
    return None


def _build_result_row(
    row: dict[str, Any],
    matched_level: str | None,
    matched_value: float | None,
) -> dict[str, Any]:
    result = {
        "language": row.get("language"),
        "certificate": row.get("certificate"),
        "level_or_scale": row.get("level_or_scale"),
        "equivalent_level_3": row.get("equivalent_level_3"),
        "equivalent_level_4": row.get("equivalent_level_4"),
        "matched_level": matched_level,
    }
    if matched_value is not None:
        result["matched_value"] = matched_value
    return result


def _build_lookup_result(
    query: str,
    table: dict[str, Any],
    rows: list[dict[str, Any]],
    matched_level: str | None = None,
    matched_value: float | None = None,
    effective_cohort: str | None = None,
) -> dict[str, Any]:
    result_rows = [
        _build_result_row(row, matched_level if len(rows) == 1 else None, matched_value)
        for row in rows
    ]
    result: dict[str, Any]
    if len(result_rows) == 1:
        result = result_rows[0]
    else:
        result = {
            "rows": result_rows,
            "matched_level": matched_level,
            "matched_value": matched_value,
        }

    return {
        "lookup_type": "foreign_language_equivalency",
        "input_value": query,
        "result": result,
        "items": result_rows,
        "display_rows": [
            _build_result_row(row, matched_level=None, matched_value=None)
            for row in table.get("rows") or []
        ],
        "result_count": len(result_rows),
        "source_pages": table.get("source_pages") or [],
        "table_name": table.get("table_name") or "Bang quy doi chuan dau ra ngoai ngu",
        "source_label": "Bang quy doi chuan dau ra ngoai ngu trong So tay sinh vien HCMUE",
        "cohort": effective_cohort or table.get("cohort"),
        "source_cohort": table.get("source_cohort") or table.get("cohort"),
        "applicable_cohorts": table.get("applicable_cohorts"),
        "applicability": table.get("applicability"),
        "document_id": table.get("document_id"),
        "source_section": table.get("source_section_id") or table.get("source_section"),
        "content_type": "structured_lookup",
    }


def foreign_language_lookup(
    query: str,
    tables: list[dict[str, Any]],
    cohort: str | None = None,
    *,
    slots: dict[str, Any],
) -> dict[str, Any] | None:
    """Resolve foreign-language equivalency from validated structured slots."""

    certificate_values = _slot_values(slots.get("certificate_or_language"))
    level_values = _slot_values(slots.get("score_or_level"))
    query_norm = normalize_text(
        " ".join(str(value) for value in [*certificate_values, *level_values])
    )
    effective_cohort = normalize_cohort(cohort)

    candidates = _filter_by_cohort(tables, effective_cohort)
    if not candidates:
        return None

    table = candidates[0]
    rows = list(table.get("rows") or [])
    if not rows:
        return None

    if certificate_values:
        wanted_values = [
            normalize_text(value)
            for value in certificate_values
        ]
        matched_rows = []
        for wanted in wanted_values:
            scored_rows = []
            wanted_tokens = set(wanted.split())
            for row in rows:
                searchable = normalize_text(
                    " ".join(
                        str(row.get(key) or "")
                        for key in ("certificate", "level_or_scale", "language")
                    )
                )
                score = len(wanted_tokens & set(searchable.split()))
                if wanted and (wanted in searchable or searchable in wanted):
                    score += 8
                if score > 0:
                    scored_rows.append((score, row))
            max_score = max((score for score, _ in scored_rows), default=0)
            # Select the best row(s) for each explicit entity independently;
            # one global maximum would drop a lower-scoring requested entity.
            for score, row in scored_rows:
                if score == max_score and row not in matched_rows:
                    matched_rows.append(row)
    else:
        matched_rows = rows

    if not matched_rows:
        return None

    # Certificate names such as HSK4 can contain digits; only explicit
    # level/score slots are operands for numeric equivalency matching.
    level_text = " ".join(str(value) for value in level_values)
    numbers = _extract_numbers(_strip_cohort_numbers(normalize_text(level_text)))
    matched_level = None
    matched_value = None

    if len(matched_rows) == 1:
        row = matched_rows[0]
        multiple_levels = len(level_values) > 1
        text_level = None if multiple_levels else _level_from_text(row, query_norm)
        numeric_level = (
            _level_from_numeric(row, numbers) if len(numbers) == 1 else None
        )
        matched_level = text_level or numeric_level
        if numeric_level and not text_level and len(numbers) == 1:
            matched_value = numbers[-1] if numbers else None

    return _build_lookup_result(
        query=query,
        table=table,
        rows=matched_rows,
        matched_level=matched_level,
        matched_value=matched_value,
        effective_cohort=effective_cohort,
    )
