import re
import unicodedata
from typing import Any

from src.common.cohort import normalize_cohort, resolve_cohort_from_query
from src.retrieval.core.structured_lookup import in_range


LABEL_ALIASES = {
    "Khá": ["kha"],
    "Giỏi": ["gioi"],
    "Xuất sắc": ["xuat sac", "xuatsac"],
}


def normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d")
    return re.sub(r"[^a-z0-9+\s.,-]", " ", text)


def _extract_numbers(query_norm: str) -> list[float]:
    values: list[float] = []
    for match in re.finditer(r"(?<!\d)(\d+(?:[,.]\d+)?)(?!\d)", query_norm):
        try:
            values.append(float(match.group(1).replace(",", ".")))
        except ValueError:
            continue
    return values


def _strip_cohort_numbers(query_norm: str) -> str:
    query_norm = re.sub(r"\bk\s*\d{2}\b", " ", query_norm)
    query_norm = re.sub(r"\bkhoa\s*\d{2}\b", " ", query_norm)
    return query_norm


def _is_scholarship_lookup_query(query_norm: str) -> bool:
    if "hoc bong" not in query_norm:
        return False
    if "tinh" in query_norm and any(term in query_norm for term in ["gpa", "ren luyen"]):
        return False
    policy_terms = [
        "dieu kien",
        "thu tuc",
        "ho so",
        "quy trinh",
        "nop",
        "bao gio",
        "khi nao",
        "tin chi",
        "ky luat",
        "no hoc phi",
        "co duoc",
        "duoc nhan",
        "nhan khong",
        "nhung",
        "truong hop",
    ]
    if any(term in query_norm for term in policy_terms):
        return False
    lookup_terms = [
        "xep loai",
        "loai",
        "kha",
        "gioi",
        "xuat sac",
        "bao nhieu diem",
        "may diem",
        "diem hoc bong",
        "thang diem",
    ]
    return any(term in query_norm for term in lookup_terms)


def _filter_tables(
    tables: list[dict[str, Any]],
    cohort: str | None,
) -> list[dict[str, Any]]:
    normalized_cohort = normalize_cohort(cohort)
    candidates = [
        table
        for table in tables
        if table.get("table_id") == "scholarship_classification"
    ]
    if not normalized_cohort:
        return candidates
    return [
        table
        for table in candidates
        if normalize_cohort(table.get("cohort")) == normalized_cohort
    ]


def _requested_label(query_norm: str) -> str | None:
    for label, aliases in LABEL_ALIASES.items():
        if any(alias in query_norm for alias in aliases):
            return label
    return None


def _rows_for_query(
    query_norm: str,
    table: dict[str, Any],
) -> tuple[list[dict[str, Any]], float | None]:
    rows = list(table.get("rows") or [])
    label = _requested_label(query_norm)
    if label:
        return [
            row for row in rows if normalize_text(row.get("label")) == normalize_text(label)
        ], None

    numbers = _extract_numbers(_strip_cohort_numbers(query_norm))
    score = numbers[-1] if numbers else None
    if score is None:
        return rows, None

    matched = [
        row
        for row in rows
        if in_range(score, str(row.get("scholarship_score_range") or ""))
    ]
    return matched, score


def scholarship_classification_lookup(
    query: str,
    tables: list[dict[str, Any]],
    cohort: str | None = None,
    slots: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if slots is not None:
        query_norm = normalize_text(slots.get("score_or_label"))
    else:
        query_norm = normalize_text(query)
        if not _is_scholarship_lookup_query(query_norm):
            return None

    effective_cohort = normalize_cohort(cohort) or resolve_cohort_from_query(query)
    candidates = _filter_tables(tables, effective_cohort)
    if not candidates:
        return None

    table = candidates[0]
    rows, score = _rows_for_query(query_norm, table)
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
        "source_pages": table.get("source_pages") or [],
        "table_name": table.get("table_name")
        or "Xếp loại học bổng khuyến khích học tập",
        "source_label": "Bảng xếp loại học bổng khuyến khích học tập trong Sổ tay sinh viên HCMUE",
        "cohort": table.get("cohort"),
        "document_id": table.get("document_id"),
        "source_section": table.get("source_section") or "scoring_table",
        "content_type": "structured_lookup",
    }
