import re
import unicodedata
from typing import Any

from src.common.cohort import normalize_cohort


STOPWORDS = {
    "a",
    "ai",
    "ban",
    "bieu",
    "bieu mau",
    "can",
    "cho",
    "co",
    "cua",
    "don",
    "duoc",
    "gi",
    "hoi",
    "khong",
    "lam",
    "lay",
    "mau",
    "minh",
    "nao",
    "o",
    "sinh",
    "sv",
    "thi",
    "vien",
    "xin",
}


def normalize_text(text: str) -> str:
    """Chuẩn hóa văn bản để so khớp có dấu và không dấu ổn định hơn."""
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    text = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in normalize_text(text).split()
        if len(token) >= 2 and token not in STOPWORDS
    }


def _form_search_text(form: dict[str, Any]) -> str:
    fields = " ".join(form.get("required_fields_detected") or [])
    return " ".join(
        str(value)
        for value in [
            form.get("form_name"),
            form.get("summary"),
            form.get("purpose"),
            fields,
            (form.get("raw_text") or "")[:1200],
        ]
        if value
    )


def _score_form(query: str, form: dict[str, Any]) -> float:
    query_norm = normalize_text(query)
    form_name = str(form.get("form_name") or "")
    name_norm = normalize_text(form_name)
    search_norm = normalize_text(_form_search_text(form))

    query_tokens = tokenize(query)
    name_tokens = tokenize(form_name)
    search_tokens = tokenize(search_norm)

    if not query_tokens:
        return 0.0

    score = 0.0
    score += len(query_tokens & name_tokens) * 4
    score += len(query_tokens & search_tokens) * 1.5

    if name_norm and (name_norm in query_norm or query_norm in name_norm):
        score += 12

    important_phrases = [
        "tam nghi",
        "tro lai hoc",
        "thoi hoc",
        "chuyen truong",
        "ky tuc xa",
        "mien giam hoc phi",
        "tro cap",
        "ren luyen",
        "phuc khao",
        "xac nhan",
    ]
    for phrase in important_phrases:
        if phrase in query_norm and phrase in search_norm:
            score += 6

    return score


def _score_form_from_data(candidate_text: str, form: dict[str, Any]) -> float:
    candidate_norm = normalize_text(candidate_text)
    candidate_tokens = tokenize(candidate_text)
    if not candidate_norm or not candidate_tokens:
        return 0.0
    name_norm = normalize_text(form.get("form_name") or "")
    search_norm = normalize_text(_form_search_text(form))
    score = len(candidate_tokens & tokenize(search_norm)) * 2.0
    if candidate_norm == name_norm:
        score += 20
    elif candidate_norm in search_norm or name_norm in candidate_norm:
        score += 10
    return score


def _summarize_form(form: dict[str, Any]) -> dict[str, Any]:
    raw_text = str(form.get("raw_text") or "")
    return {
        "form_id": form.get("form_id"),
        "form_name": form.get("form_name"),
        "content_type": form.get("content_type") or "form_template",
        "source_pages": form.get("source_pages") or [],
        "source_section": form.get("source_section"),
        "required_fields_detected": form.get("required_fields_detected") or [],
        "review_status": form.get("review_status"),
        "cohort": form.get("cohort"),
        "document_id": form.get("document_id"),
        "summary": form.get("summary") or raw_text[:500],
    }


def form_lookup(
    query: str,
    form_templates: list[dict[str, Any]],
    cohort: str | None = None,
    top_k: int = 3,
    candidate_text: str | None = None,
    require_confident_match: bool = False,
) -> dict[str, Any] | None:
    """Tra cứu biểu mẫu bằng metadata, không cần embed toàn văn mẫu đơn."""
    normalized_cohort = normalize_cohort(cohort)
    candidates = form_templates
    if normalized_cohort:
        cohort_matches = [
            form
            for form in candidates
            if normalize_cohort(form.get("cohort")) == normalized_cohort
        ]
        if cohort_matches:
            candidates = cohort_matches

    if candidate_text and candidate_text.strip():
        scored = [
            (score, form)
            for form in candidates
            if (score := _score_form_from_data(candidate_text, form)) > 0
        ]
    else:
        scored = [
            (score, form)
            for form in candidates
            if (score := _score_form(query, form)) > 0
        ]
    scored.sort(key=lambda item: item[0], reverse=True)

    match_score = scored[0][0] if scored else 0.0
    runner_up_score = scored[1][0] if len(scored) > 1 else 0.0
    score_margin = match_score - runner_up_score
    if require_confident_match:
        required_margin = max(1.0, match_score * 0.15)
        if not scored or score_margin < required_margin:
            return None
        scored = scored[:1]

    matches = [
        _summarize_form(form) | {"score": round(score, 2)}
        for score, form in scored[:top_k]
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
        str(match.get("document_id"))
        for match in matches
        if match.get("document_id")
    }

    return {
        "lookup_type": "form_template",
        "input_value": query,
        "result": matches,
        "source_pages": source_pages,
        "table_name": "Biểu mẫu phù hợp",
        "source_label": "Danh mục biểu mẫu trong Sổ tay sinh viên",
        "cohort": normalized_cohort,
        "document_id": next(iter(document_ids)) if len(document_ids) == 1 else None,
        "source_section": "form_templates",
        "content_type": "form_template",
        "match_score": round(match_score, 2),
        "score_margin": round(score_margin, 2),
        "selection_method": (
            "typed_candidate_confident" if require_confident_match else "lexical_rank"
        ),
    }
