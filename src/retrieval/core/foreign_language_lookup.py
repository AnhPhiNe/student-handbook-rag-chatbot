import re
import unicodedata
from typing import Any

from src.common.cohort import normalize_cohort, resolve_cohort_from_query


CERTIFICATE_ALIASES = {
    "ielts": ["ielts"],
    "toefl_ibt": ["toefl ibt", "ibt"],
    "toefl_itp": ["toefl itp", "itp"],
    "toefl": ["toefl"],
    "toeic": ["toeic"],
    "cambridge": ["cambridge", "linguaskill", "b1 preliminary", "b2 first"],
    "tcf_delf": ["tcf", "delf"],
    "hsk": ["hsk", "han yu", "hanyu"],
    "jlpt": ["jlpt", "n3", "n4"],
    "topik": ["topik"],
    "trki": ["trki", "tpk", "tprk", "tieng nga"],
}

CERTIFICATE_ROW_HINTS = {
    "ielts": ["ielts"],
    "toefl_ibt": ["toefl ibt"],
    "toefl_itp": ["toefl itp"],
    "toefl": ["toefl"],
    "toeic": ["toeic"],
    "cambridge": ["cambridge", "linguaskill"],
    "tcf_delf": ["tcf", "delf"],
    "hsk": ["hsk"],
    "jlpt": ["jlpt", "japanese language proficiency"],
    "topik": ["topik"],
    "trki": ["trki", "tieng nga"],
}


def normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"[^a-z0-9+.,\s-]", " ", text)


def compact_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _filter_by_cohort(
    tables: list[dict[str, Any]],
    cohort: str | None,
) -> list[dict[str, Any]]:
    normalized_cohort = normalize_cohort(cohort)
    if not normalized_cohort:
        return tables
    return [
        table
        for table in tables
        if normalize_cohort(table.get("cohort")) == normalized_cohort
    ]


def _detect_certificate_keys(query_norm: str) -> list[str]:
    matched: list[str] = []
    for key, aliases in CERTIFICATE_ALIASES.items():
        if any(alias in query_norm for alias in aliases):
            matched.append(key)
    if "toefl_ibt" in matched or "toefl_itp" in matched:
        matched = [key for key in matched if key != "toefl"]
    return matched


def _has_foreign_language_signal(query_norm: str, certificate_keys: list[str]) -> bool:
    if certificate_keys:
        return True
    foreign_terms = [
        "ngoai ngu",
        "chuan dau ra",
        "chung chi",
        "bac 3",
        "bac 4",
        "quy doi",
        "tuong duong",
    ]
    return "ngoai ngu" in query_norm and any(term in query_norm for term in foreign_terms)


def _is_policy_query_without_specific_value(
    query_norm: str,
    certificate_keys: list[str],
) -> bool:
    policy_terms = [
        "quy trinh",
        "thu tuc",
        "ho so",
        "nop",
        "cong nhan",
        "mien",
        "dieu kien",
        "xet tot nghiep",
    ]
    strong_policy_terms = [
        "khong co",
        "chua co",
        "het han",
        "xin no",
        "gia han",
        "co duoc",
        "nhu the nao",
    ]
    if any(term in query_norm for term in strong_policy_terms):
        return True
    if not any(term in query_norm for term in policy_terms):
        return False
    has_specific_value = bool(certificate_keys) or bool(
        _extract_numbers(_strip_cohort_numbers(query_norm))
    )
    return not has_specific_value


def _has_direct_equivalency_signal(query_norm: str) -> bool:
    if _extract_numbers(_strip_cohort_numbers(query_norm)):
        return True
    direct_terms = [
        "bac may",
        "muc may",
        "bac 3",
        "bac 4",
        "tuong duong",
        "quy doi",
        "dat muc",
        "dat chuan",
        "du chuan",
        "n3",
        "n4",
        "b1",
        "b2",
    ]
    return any(term in query_norm for term in direct_terms)


def _row_matches_certificate(row: dict[str, Any], key: str) -> bool:
    row_norm = normalize_text(
        " ".join(
            [
                str(row.get("certificate") or ""),
                str(row.get("level_or_scale") or ""),
                str(row.get("language") or ""),
            ]
        )
    )
    hints = CERTIFICATE_ROW_HINTS.get(key, [])
    return any(hint in row_norm for hint in hints)


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
        "result_count": len(result_rows),
        "source_pages": table.get("source_pages") or [],
        "table_name": table.get("table_name")
        or "Bang quy doi chuan dau ra ngoai ngu",
        "source_label": "Bang quy doi chuan dau ra ngoai ngu trong So tay sinh vien HCMUE",
        "cohort": table.get("cohort"),
        "document_id": table.get("document_id"),
        "source_section": table.get("source_section_id") or table.get("source_section"),
        "content_type": "structured_lookup",
    }


def foreign_language_lookup(
    query: str,
    tables: list[dict[str, Any]],
    cohort: str | None = None,
    slots: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Deterministically answer clear foreign-language equivalency queries."""

    if slots is not None:
        certificate_value = str(slots.get("certificate_or_language") or "")
        level_value = slots.get("score_or_level")
        query_norm = normalize_text(f"{certificate_value} {level_value}")
        certificate_keys: list[str] = []
    else:
        query_norm = normalize_text(query)
        certificate_keys = _detect_certificate_keys(query_norm)
        if not _has_foreign_language_signal(query_norm, certificate_keys):
            return None
        if _is_policy_query_without_specific_value(query_norm, certificate_keys):
            return None
        if certificate_keys and not _has_direct_equivalency_signal(query_norm):
            return None

    effective_cohort = normalize_cohort(cohort) or resolve_cohort_from_query(query)
    candidates = _filter_by_cohort(tables, effective_cohort)
    if not candidates:
        return None

    table = candidates[0]
    rows = list(table.get("rows") or [])
    if not rows:
        return None

    if slots is not None:
        wanted = normalize_text(slots.get("certificate_or_language"))
        wanted_tokens = set(wanted.split())
        scored_rows = []
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
        matched_rows = [row for score, row in scored_rows if score == max_score]
    elif certificate_keys:
        matched_rows = [
            row
            for row in rows
            if any(_row_matches_certificate(row, key) for key in certificate_keys)
        ]
    else:
        matched_rows = rows

    if not matched_rows:
        return None

    numbers = _extract_numbers(_strip_cohort_numbers(query_norm))
    matched_level = None
    matched_value = None

    if len(matched_rows) == 1:
        row = matched_rows[0]
        text_level = _level_from_text(row, query_norm)
        numeric_level = _level_from_numeric(row, numbers)
        matched_level = text_level or numeric_level
        if numeric_level and not text_level:
            matched_value = numbers[-1] if numbers else None

    return _build_lookup_result(
        query=query,
        table=table,
        rows=matched_rows,
        matched_level=matched_level,
        matched_value=matched_value,
    )
