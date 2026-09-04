import re
import unicodedata
from collections import defaultdict
from typing import Any

from src.common.cohort import is_cohort_applicable, normalize_cohort


def normalize_text(text: Any) -> str:
    """Fold text into a stable accent-insensitive comparison form."""
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


def _normalize_faculty_name(value: Any) -> str:
    text = normalize_text(value)
    text = re.sub(r"^\d+\s+", "", text)
    return text


def _program_summary(record: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "program_name": record.get("program_name"),
        "faculty_name": record.get("faculty_name"),
        "source_pages": record.get("source_pages") or [],
        "source_section": record.get("source_section"),
        "cohort": record.get("cohort"),
        "document_id": record.get("document_id"),
        "summary": record.get("summary"),
        "raw_text": record.get("raw_text"),
    }
    if record.get("faculty_name_source"):
        summary["faculty_name_source"] = record["faculty_name_source"]
    if record.get("quality_status"):
        summary["quality_status"] = record["quality_status"]
    return summary


def _sort_programs(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda item: (
            _normalize_faculty_name(item.get("faculty_name")),
            normalize_text(item.get("program_name")),
        ),
    )


def _dedupe_programs(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        key = (
            normalize_text(record.get("program_name")),
            _normalize_faculty_name(record.get("faculty_name")),
        )
        if key not in deduped:
            deduped[key] = dict(record)
            continue

        pages = {
            int(page)
            for page in (deduped[key].get("source_pages") or [])
            + (record.get("source_pages") or [])
            if str(page).isdigit()
        }
        deduped[key]["source_pages"] = sorted(pages)
    return list(deduped.values())


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
        record for record in records if is_cohort_applicable(record, normalized_cohort)
    ]


def _infer_faculty_names_from_query(
    records: list[dict[str, Any]], query: str
) -> set[str]:
    query_text = normalize_text(query)
    matched_spans: list[tuple[str, int, int, int]] = []
    for record in records:
        faculty_name = _normalize_faculty_name(record.get("faculty_name"))
        if not faculty_name:
            continue
        core_name = re.sub(r"^khoa\s+", "", faculty_name).strip()
        words = [word for word in core_name.split() if word]
        acronym = "".join(word[0] for word in words)
        name_forms = {core_name}
        for alias in record.get("faculty_aliases") or []:
            normalized_alias = _normalize_faculty_name(alias)
            normalized_alias = re.sub(r"^khoa\s+", "", normalized_alias).strip()
            if normalized_alias:
                name_forms.add(normalized_alias)
        if words and words[-1] == "hoc":
            name_forms.add(" ".join(words[:-1]))
        for name_form in name_forms:
            if not name_form:
                continue
            token_count = len(name_form.split())
            pattern = rf"(?<![a-z0-9]){re.escape(name_form)}(?![a-z0-9])"
            matched_spans.extend(
                (faculty_name, match.start(), match.end(), token_count)
                for match in re.finditer(pattern, query_text)
            )
        if len(acronym) >= 2:
            matched_spans.extend(
                (faculty_name, match.start(), match.end(), 1)
                for match in re.finditer(
                    rf"(?<!\w){re.escape(acronym)}(?!\w)", query_text
                )
            )

        # A short alias helps when it is the only signal, but must not override
        # a query containing a longer, more specific program name.
    # Keep non-overlapping matches and let the longest phrase claim its span.
    matched: set[str] = set()
    accepted_spans: list[tuple[int, int, int]] = []
    for faculty_name, start, end, token_count in sorted(
        matched_spans,
        key=lambda item: (-item[3], item[1], item[2] - item[1]),
    ):
        contained = any(
            start >= accepted_start
            and end <= accepted_end
            and token_count < accepted_tokens
            for accepted_start, accepted_end, accepted_tokens in accepted_spans
        )
        if contained:
            continue
        accepted_spans.append((start, end, token_count))
        matched.add(faculty_name)
    return matched


def _filter_by_faculty_names(
    records: list[dict[str, Any]], faculty_names: set[str]
) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if _normalize_faculty_name(record.get("faculty_name")) in faculty_names
    ]


def _get_program_name_forms(raw_name: Any) -> set[str]:
    """Derive general parenthetical, suffix, prefix, and acronym name forms."""
    forms = set()
    norm_full = normalize_text(raw_name)
    if norm_full:
        forms.add(norm_full)

    base = re.sub(r"\(.*?\)", "", str(raw_name or "")).strip()
    norm_base = normalize_text(base)
    if not norm_base:
        return forms
    forms.add(norm_base)

    words = norm_base.split()

    # Derive acronyms from initial letters for names with at least three words.
    if len(words) >= 3:
        forms.add("".join(w[0] for w in words))
    elif len(words) == 2 and "thong tin" in norm_base:
        forms.add("".join(w[0] for w in words))

    # Derive aliases by removing the common academic suffix.
    if (
        len(words) > 1
        and words[-1] == "hoc"
        and words[-2] not in {"tieu", "trung", "dai", "cao"}
    ):
        base_no_hoc = " ".join(words[:-1])
        forms.add(base_no_hoc)
        if len(words[:-1]) >= 3:
            forms.add("".join(w[0] for w in words[:-1]))

    # Derive aliases by removing the country/language qualifier.
    if len(words) > 1 and words[-1] == "quoc":
        base_no_quoc = " ".join(words[:-1])
        forms.add(base_no_quoc)
        if len(words[:-1]) >= 3:
            forms.add("".join(w[0] for w in words[:-1]))

    # Normalize the teacher-training prefix to its canonical abbreviation.
    if norm_base.startswith("su pham "):
        rem = norm_base[8:]
        forms.add("sp " + rem)
        rem_words = rem.split()
        if (
            len(rem_words) > 1
            and rem_words[-1] == "hoc"
            and rem_words[-2] not in {"tieu", "trung", "dai", "cao"}
        ):
            forms.add("sp " + " ".join(rem_words[:-1]))
        if len(rem_words) > 1 and rem_words[-1] == "quoc":
            forms.add("sp " + " ".join(rem_words[:-1]))
        if len(rem_words) >= 2:
            forms.add("sp" + "".join(w[0] for w in rem_words))

    return forms


def _filter_by_program_name(
    records: list[dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    text = normalize_text(query)
    found_matches: list[tuple[int, int, dict[str, Any]]] = []
    for record in records:
        raw_name = record.get("program_name")
        forms = _get_program_name_forms(raw_name)
        for form in forms:
            if not form:
                continue
            if len(form) <= 4:
                for m in re.finditer(
                    rf"(?<![a-z0-9]){re.escape(form)}(?![a-z0-9])", text
                ):
                    found_matches.append((m.start(), m.end(), record))
            else:
                start = 0
                while True:
                    idx = text.find(form, start)
                    if idx == -1:
                        break
                    end = idx + len(form)
                    found_matches.append((idx, end, record))
                    start = idx + 1

    if not found_matches:
        return []

    found_matches.sort(key=lambda item: item[1] - item[0], reverse=True)

    kept_records: list[dict[str, Any]] = []
    accepted_spans: list[tuple[int, int]] = []

    for start, end, record in found_matches:
        is_subsumed = any(
            acc_start <= start and end <= acc_end
            for acc_start, acc_end in accepted_spans
        )
        if not is_subsumed:
            accepted_spans.append((start, end))
            if record not in kept_records:
                kept_records.append(record)

    return kept_records


def _filter_by_program_topic(
    records: list[dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    text = normalize_text(query)
    grammar_stopwords = {
        "cac",
        "cho",
        "cua",
        "danh",
        "do",
        "em",
        "gi",
        "khoa",
        "la",
        "nao",
        "nganh",
        "nhung",
        "sach",
        "tra",
        "ve",
        "hoi",
        "hoc",
        "truong",
        "co",
        "trong",
        "tai",
        "theo",
        "voi",
        "nhu",
        "the",
    }
    query_tokens = [
        token
        for token in text.split()
        if token not in grammar_stopwords and len(token) >= 2
    ]
    if not query_tokens:
        return []

    query_token_set = set(query_tokens)
    scored_candidates: list[tuple[float, dict[str, Any]]] = []

    for record in records:
        prog_tokens = set(normalize_text(record.get("program_name")).split())
        prog_tokens_clean = {
            t for t in prog_tokens if t not in grammar_stopwords and len(t) >= 2
        }
        if not prog_tokens_clean:
            continue
        overlap = len(query_token_set & prog_tokens_clean)
        if overlap >= 1:
            score = overlap / len(prog_tokens_clean)
            if (
                overlap >= 2
                or score >= 0.5
                or query_token_set.issubset(prog_tokens_clean)
            ):
                scored_candidates.append((score, record))

    if not scored_candidates:
        return []

    scored_candidates.sort(key=lambda item: item[0], reverse=True)
    best_score = scored_candidates[0][0]
    return [record for score, record in scored_candidates if score >= best_score * 0.8]


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
    routing: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Tra cuu nganh tu structured data theo quyet dinh cua router."""
    routing = routing or {}
    action = str(routing.get("action") or "").strip()
    routed_to_program = routing.get(
        "content_type"
    ) == "program_directory" and action in {
        "list",
        "resolve_faculty",
        "exists",
    }
    routed_to_program_list = routed_to_program and action == "list"
    routed_to_program_faculty = routed_to_program and action == "resolve_faculty"
    routed_to_program_exists = routed_to_program and action == "exists"
    if (
        not routed_to_program_list
        and not routed_to_program_faculty
        and not routed_to_program_exists
        and not _is_fallback_program_list_query(query)
    ):
        return None

    scope = str(routing.get("scope") or "").strip()
    asks_school_programs = scope == "school" or (
        not routed_to_program_list and _asks_school_programs(query)
    )
    asks_faculty_programs = scope == "faculty"

    if (
        not asks_school_programs
        and not asks_faculty_programs
        and not routed_to_program_faculty
        and not routed_to_program_exists
    ):
        return None

    candidates = _filter_by_cohort(program_directory, cohort)
    normalized_cohort = normalize_cohort(cohort)
    topic_filtered_for_faculty = False
    if routed_to_program_exists:
        if not normalized_cohort or not candidates:
            return None
        cohort_catalog = _sort_programs(_dedupe_programs(candidates))
        matched = _sort_programs(
            _dedupe_programs(_filter_by_program_name(cohort_catalog, query))
        )
        result = [_program_summary(record) for record in matched]
        document_ids = {
            str(record.get("document_id"))
            for record in cohort_catalog
            if record.get("document_id")
        }
        return {
            "lookup_type": "program_directory",
            "lookup_scope": "program_exists",
            "input_value": query,
            "searched_program": query,
            "exists": bool(result),
            "result": result,
            "program_count": len(result),
            "faculty_counts": _group_counts(result),
            "source_pages": _source_pages(cohort_catalog),
            "table_name": "Danh sach nganh dao tao",
            "source_label": "Danh muc nganh dao tao trong So tay sinh vien HCMUE",
            "cohort": normalized_cohort,
            "document_id": next(iter(document_ids)) if len(document_ids) == 1 else None,
            "source_section": "program_directory",
            "content_type": "program_directory",
        }

    inferred_faculty_names: set[str] = set()
    if scope == "faculty":
        inferred_faculty_names = _infer_faculty_names_from_query(candidates, query)
        if not inferred_faculty_names:
            topic_matches = _filter_by_program_topic(candidates, query)
            if not topic_matches:
                return None
            candidates = topic_matches
            topic_filtered_for_faculty = True
    lookup_scope = "school"
    if routed_to_program_faculty:
        candidates = _filter_by_program_name(
            candidates, query
        ) or _filter_by_program_topic(candidates, query)
        lookup_scope = "program"
        if not candidates:
            return None

    if (
        asks_faculty_programs
        and not asks_school_programs
        and not routed_to_program_faculty
        and not topic_filtered_for_faculty
    ):
        candidates = _filter_by_faculty_names(candidates, inferred_faculty_names)
        lookup_scope = "faculty"
    elif topic_filtered_for_faculty:
        lookup_scope = "program_topic_faculty"

    candidates = _sort_programs(_dedupe_programs(candidates))
    if not candidates:
        return None

    result = [_program_summary(record) for record in candidates]
    document_ids = {
        str(item.get("document_id")) for item in result if item.get("document_id")
    }

    return {
        "lookup_type": "program_directory",
        "lookup_scope": lookup_scope,
        "source_lookup_type": (
            "faculty" if lookup_scope == "program_topic_faculty" else None
        ),
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
