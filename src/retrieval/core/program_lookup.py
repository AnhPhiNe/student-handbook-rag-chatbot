"""Program-directory lookups: list, existence and the faculty that runs a program.

Which programs a text refers to (by name, shortened name, faculty or field) is
decided by the directory selector; this module applies the requested action to
the chosen records of one cohort.
"""
import re
from collections import defaultdict
from functools import partial
from typing import Any

from src.common.cohort import is_cohort_applicable, normalize_cohort
from src.common.text import fold_text, slot_values

from .directory_selector import AMBIGUOUS, UNAVAILABLE, DirectorySelector, select_records

normalize_text = partial(fold_text, keep="")


def _normalize_faculty_name(value: Any) -> str:
    text = normalize_text(value)
    text = re.sub(r"^\d+\s+", "", text)
    return text


def _program_summary(record: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "record_id": record.get("record_id"),
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


def _group_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for record in records:
        faculty = str(record.get("faculty_name") or "Chua xac dinh")
        counts[faculty] += 1
    return dict(counts)


def program_lookup(
    program_directory: list[dict[str, Any]],
    *,
    candidate_text: str | list[str],
    cohort: str | None = None,
    action: str,
    scope: str,
    selector: DirectorySelector | None = None,
) -> dict[str, Any] | None:
    """Execute a validated program-directory action within one cohort."""

    action = str(action or "").strip()
    scope = str(scope or "").strip()
    if action not in {"list", "resolve_faculty", "exists"}:
        return None
    if action == "list" and scope not in {"school", "faculty"}:
        return None

    normalized_cohort = normalize_cohort(cohort)
    catalog = _sort_programs(_dedupe_programs(_filter_by_cohort(program_directory, cohort)))
    if not catalog:
        return None
    if action == "list" and scope == "school":
        return _program_result(candidate_text, catalog, cohort=normalized_cohort, lookup_scope="school")
    if action == "exists" and not normalized_cohort:
        return None

    chosen: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    for name in (str(value).strip() for value in slot_values(candidate_text)):
        if not name:
            continue
        selection = select_records(selector, "program", name, catalog)
        traces.append({"text": name, **selection.trace()})
        if selection.status in {AMBIGUOUS, UNAVAILABLE}:
            # Undecided is not "no such program": ask rather than deny it.
            return _program_clarification(name, selection.records, cohort=normalized_cohort, selection=traces)
        chosen.extend(record for record in selection.records if record not in chosen)
    chosen = _sort_programs(chosen)

    if action == "exists":
        result = _program_result(candidate_text, chosen, cohort=normalized_cohort,
                                 lookup_scope="program_exists", selection=traces)
        result.update(searched_program=candidate_text, exists=bool(chosen),
                      source_pages=_source_pages(catalog))
        if not chosen:
            result["not_found_note"] = "Không có trong danh sách ngành đào tạo của khóa trong sổ tay sinh viên."
        return result
    if not chosen:
        return None
    lookup_scope = "faculty" if action == "list" else "program"
    return _program_result(candidate_text, chosen, cohort=normalized_cohort,
                           lookup_scope=lookup_scope, selection=traces)


def _program_clarification(
    candidate_text: str,
    records: list[dict[str, Any]],
    *,
    cohort: str | None,
    selection: list[dict[str, Any]],
) -> dict[str, Any]:
    """Ask which program was meant, listing the selector's candidates when it has them."""
    options = [f"- **{record.get('program_name')}** ({record.get('faculty_name')})" for record in records[:3]]
    if options:
        question = "Bạn muốn hỏi ngành nào dưới đây?\n\n" + "\n".join(options)
    else:
        question = f"Mình chưa xác định được ngành ứng với \"{candidate_text}\". Bạn ghi rõ tên ngành giúp mình nhé."
    return {
        "lookup_type": "program_directory",
        "needs_clarification": True,
        "clarification_question": question,
        "candidate_text": candidate_text,
        "candidate_programs": [record.get("program_name") for record in records[:3]],
        "content_type": "structured_lookup_clarification",
        "cohort": cohort,
        "selection": selection,
    }


def _program_result(
    candidate_text: str | list[str],
    records: list[dict[str, Any]],
    *,
    cohort: str | None,
    lookup_scope: str,
    selection: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    result = [_program_summary(record) for record in records]
    document_ids = {str(item.get("document_id")) for item in result if item.get("document_id")}
    return {
        "lookup_type": "program_directory",
        "lookup_scope": lookup_scope,
        "input_value": candidate_text,
        "result": result,
        "program_count": len(result),
        "faculty_counts": _group_counts(records),
        "source_pages": _source_pages(records),
        "table_name": "Danh sach nganh dao tao",
        "source_label": "Danh muc nganh dao tao trong So tay sinh vien HCMUE",
        "cohort": cohort,
        "document_id": next(iter(document_ids)) if len(document_ids) == 1 else None,
        "source_section": "program_directory",
        "content_type": "program_directory",
        "selection": selection or [],
    }
