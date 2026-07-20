import re
import unicodedata
from typing import Any

from src.common.cohort import normalize_cohort, resolve_cohort_from_query


def normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d")
    return re.sub(r"[^a-z0-9+\s-]", " ", text)


def _filter_by_cohort(
    tables: list[dict[str, Any]],
    cohort: str | None,
) -> list[dict[str, Any]]:
    normalized_cohort = normalize_cohort(cohort)
    candidates = [table for table in tables if table.get("table_type") == "study_duration"]
    if not normalized_cohort:
        return candidates
    return [
        table
        for table in candidates
        if normalize_cohort(table.get("cohort")) == normalized_cohort
    ]


def _is_study_duration_query(query_norm: str) -> bool:
    negative_terms = [
        "co bi",
        "bi buoc",
        "buoc thoi hoc",
        "canh bao",
        "thu tuc",
        "can lam",
        "lam thu tuc",
        "gia han",
        "xin",
        "neu",
        "thi co",
    ]
    if any(term in query_norm for term in negative_terms):
        return False
    signals = [
        "thoi gian hoc tap",
        "thoi gian hoc",
        "thoi gian dao tao",
        "thoi gian toi da",
        "thoi gian chuan",
        "hoc toi da",
        "hoc trong bao lau",
        "bao nhieu nam hoc",
        "bao nhieu nam",
        "may nam hoc",
        "may nam",
        "chuong trinh dao tao",
    ]
    return any(signal in query_norm for signal in signals) and any(
        term in query_norm for term in ["toi da", "chuan", "nam hoc", "nam", "bao lau"]
    )


def _wanted_training_mode(query_norm: str) -> str | None:
    if any(term in query_norm for term in ["vua lam vua hoc", "vlvh"]):
        return "vua_lam_vua_hoc"
    if any(term in query_norm for term in ["chinh quy", "dai hoc chinh quy"]):
        return "chinh_quy"
    return None


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
    if any(term in query_norm for term in ("cao dang", "college bridge")) and "cao dang" in program:
        score += 4
    if any(term in query_norm for term in ("trung cap", "secondary bridge")) and "trung cap" in program:
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
    slots: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    has_relevant_slots = slots and (
        slots.get("training_mode") or slots.get("program_type")
    )
    if has_relevant_slots:
        query_norm = normalize_text(
            f"{slots.get('training_mode', '')} {slots.get('program_type', '')}"
        )
    else:
        query_norm = normalize_text(query)
        if not _is_study_duration_query(query_norm):
            return None

    effective_cohort = normalize_cohort(cohort) or resolve_cohort_from_query(query)
    candidates = _filter_by_cohort(tables, effective_cohort)
    if not candidates:
        return None

    wanted_mode = _wanted_training_mode(query_norm)
    if slots and slots.get("training_mode"):
        mode_value = normalize_text(slots["training_mode"])
        if "vua lam vua hoc" in mode_value or mode_value == "vlvh":
            wanted_mode = "vua_lam_vua_hoc"
        elif "chinh quy" in mode_value:
            wanted_mode = "chinh_quy"
    if wanted_mode:
        candidates = [table for table in candidates if _table_mode(table) == wanted_mode]
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
        {
            page
            for table in table_results
            for page in table.get("source_pages") or []
        }
    )
    document_ids = {
        table.get("document_id") for table in table_results if table.get("document_id")
    }
    source_sections = {
        table.get("source_section")
        for table in table_results
        if table.get("source_section")
    }

    return {
        "lookup_type": "study_duration",
        "input_value": query,
        "result": {
            "tables": table_results,
            "table_count": len(table_results),
        },
        "items": table_results,
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
