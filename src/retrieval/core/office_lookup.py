"""Directory lookups (student services, offices, faculties) for one cohort.

Which records a student names is decided by the directory selector (an exact
name, else an LLM choosing from the closed list); this module filters the
catalog by cohort and formats the chosen records as contact evidence.
"""
import re
from functools import partial
from typing import Any

from src.common.cohort import is_validated_source_applicable, normalize_cohort
from src.common.text import fold_text, slot_values

from .directory_selector import AMBIGUOUS, UNAVAILABLE, DirectorySelector, select_records

normalize_text = partial(fold_text, keep="@._+-")


def _strip_order_prefix(value: Any) -> str:
    return re.sub(r"^\s*\d+\.\s*", "", str(value or "")).strip()


def _extract_emails(raw_text: str) -> list[str]:
    return sorted(set(re.findall(r"[A-Za-z0-9._%+-]+@hcmue\.edu\.vn", raw_text)))


def _extract_websites(raw_text: str) -> list[str]:
    matches = re.findall(r"(?:https?://)?[A-Za-z0-9.-]+\.hcmue\.edu\.vn", raw_text)
    return sorted(set(match.rstrip(".,;") for match in matches))


def _extract_phones(raw_text: str) -> list[str]:
    phones = re.findall(r"\(?0\d{2,3}\)?[ .-]?\d{3,4}[ .-]?\d{3,4}", raw_text)
    return sorted(set(phone.strip() for phone in phones))


def _extract_internal_numbers(raw_text: str) -> list[str]:
    numbers: set[str] = set()
    for line in raw_text.splitlines():
        if "nội bộ" not in line.lower() and "noi bo" not in normalize_text(line):
            continue
        for number in re.findall(r"\b\d{2,4}\b", line):
            numbers.add(number)
    return sorted(numbers)


def _extract_responsibilities(raw_text: str, limit: int = 4) -> list[str]:
    responsibilities: list[str] = []
    for line in raw_text.splitlines():
        line = re.sub(r"^[•\-–+\s]+", "", line.strip())
        if not line or len(line) < 18:
            continue
        norm = normalize_text(line)
        if any(
            marker in norm
            for marker in (
                "phu trach",
                "thuc hien",
                "quan ly",
                "tham muu",
                "cap",
                "giai quyet",
                "to chuc",
                "ho tro",
            )
        ):
            responsibilities.append(line)
        if len(responsibilities) >= limit:
            break
    return responsibilities


def _summarize_office(record: dict[str, Any]) -> dict[str, Any]:
    raw_text = str(record.get("raw_text") or "")
    emails = record.get("emails") or _extract_emails(raw_text)
    phones = record.get("phones") or _extract_phones(raw_text)
    websites = record.get("websites") or _extract_websites(raw_text)
    internal_numbers = record.get("internal_numbers") or _extract_internal_numbers(
        raw_text
    )
    # A faculty's handbook entry lists contacts only; the lines after it describe
    # the careers of its programs, which the keyword guess below would present
    # as the faculty's duties (31 of the 34 faculty entries it matched).
    derived = [] if record.get("faculty_profile_id") else _extract_responsibilities(raw_text)
    responsibilities = (
        record.get("responsibilities")
        or record.get("services")
        or derived
    )
    if record.get("service"):
        responsibilities = [str(record["service"])] + [
            item for item in responsibilities if item != record.get("service")
        ]
    return {
        "record_id": record.get("record_id")
        or record.get("service_id")
        or record.get("faculty_profile_id"),
        "service_id": record.get("service_id"),
        "service": record.get("service"),
        "aliases": record.get("aliases") or [],
        "unit_name": _strip_order_prefix(record.get("unit_name") or record.get("unit")),
        "content_type": record.get("content_type") or "office_directory",
        "source_pages": record.get("source_pages") or [],
        "source_section": record.get("source_section"),
        "cohort": record.get("cohort"),
        "document_id": record.get("document_id"),
        "emails": emails,
        "phones": phones,
        "internal_numbers": internal_numbers,
        "websites": websites,
        "office": record.get("office"),
        "responsibilities": responsibilities,
        "summary": (record.get("summary") or raw_text[:500]).strip(),
    }


def _clarification_response(
    records: list[dict[str, Any]],
    *,
    candidate_text: str,
    selection: list[dict[str, Any]],
) -> dict[str, Any]:
    """Ask which unit was meant; options are the selector's candidates (at most three units)."""
    options: list[str] = []
    seen_units: set[str] = set()
    for record in records:
        unit = _strip_order_prefix(record.get("unit_name") or record.get("unit"))
        if unit in seen_units or len(seen_units) >= 3:
            continue
        seen_units.add(unit)
        service = str(record.get("service") or "").strip()
        if len(service) > 250:
            service = service[:247] + "..."
        options.append(f"- **{unit}**: {service}" if service else f"- **{unit}**")
    return {
        "lookup_type": "office_directory",
        "resolution_status": "ambiguous",
        "clarification_options": options,
        "candidate_units": sorted(seen_units),
        "candidate_text": candidate_text,
        "selection": selection,
    }


def directory_result(
    query: str,
    records: list[dict[str, Any]],
    *,
    cohort: str | None,
    selection: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Format chosen directory records as one structured lookup result."""
    matches = [_summarize_office(record) for record in records]
    source_pages = sorted(
        {
            int(page)
            for match in matches
            for page in match.get("source_pages", [])
            if str(page).isdigit()
        }
    )
    document_ids = {
        str(match.get("document_id")) for match in matches if match.get("document_id")
    }

    selected_content_types = {str(match.get("content_type") or "") for match in matches}
    if "student_service_directory" in selected_content_types:
        lookup_scope = "student_service"
        table_name = "Danh sách dịch vụ sinh viên"
        source_label = "Danh mục dịch vụ sinh viên trong Sổ tay sinh viên HCMUE"
        source_section = "student_service_directory"
        content_type = "student_service_directory"
    elif "student_faculty_profile" in selected_content_types:
        lookup_scope = "faculty"
        table_name = "Danh sách khoa liên hệ"
        source_label = "Danh mục khoa/liên hệ trong Sổ tay sinh viên HCMUE"
        source_section = "student_faculty_profiles"
        content_type = "student_faculty_profile"
    else:
        lookup_scope = "office"
        table_name = "Danh sách phòng ban liên hệ"
        source_label = "Danh mục phòng ban/liên hệ trong Sổ tay sinh viên HCMUE"
        source_section = "student_office_profiles"
        content_type = "student_office_profile"

    return {
        "lookup_type": "office_directory",
        "lookup_scope": lookup_scope,
        "input_value": query,
        "result": matches,
        "items": matches,
        "office_count": len(matches),
        "source_pages": source_pages,
        "table_name": table_name,
        "source_label": source_label,
        "cohort": normalize_cohort(cohort),
        "document_id": next(iter(document_ids)) if len(document_ids) == 1 else None,
        "source_section": source_section,
        "content_type": content_type,
        "selection_method": (selection or [{}])[0].get("method", "catalog_identity"),
        "selection": selection or [],
    }


def office_lookup(
    query: str,
    office_directory: list[dict[str, Any]],
    *,
    candidate_text: str | list[str],
    lookup_type: str = "office",
    cohort: str | None = None,
    selector: DirectorySelector | None = None,
    requested_field: str | list[str] | None = None,
) -> dict[str, Any] | None:
    """Find the directory records the student names within one cohort.

    Each name in `candidate_text` is selected on its own. A name that fits
    several units, or that the selector could not decide, stops the lookup
    with a clarification; a name with no unit is skipped. For services, the
    LLM also receives the whole task query and requested field, never just the
    extracted name. Exact name/alias matching remains an identity fast path.
    """
    names = [str(value).strip() for value in slot_values(candidate_text) if str(value).strip()]
    if not names:
        return None

    normalized_cohort = normalize_cohort(cohort)
    candidates = office_directory
    if normalized_cohort:
        candidates = [
            item
            for item in candidates
            if is_validated_source_applicable(item, normalized_cohort)
        ]

    chosen: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    for name in names:
        selection = select_records(
            selector, lookup_type, name, candidates,
            question=query if lookup_type == "student_service" else None,
            requested_field=requested_field,
        )
        traces.append({"text": name, **selection.trace()})
        if selection.status == AMBIGUOUS:
            return _clarification_response(selection.records, candidate_text=name, selection=traces)
        if selection.status == UNAVAILABLE:
            return {
                "lookup_type": "office_directory",
                "resolution_status": "unresolved",
                "clarification_options": [],
                "candidate_text": name,
                "selection": traces,
            }
        chosen.extend(record for record in selection.records if record not in chosen)
    if not chosen:
        return None
    return directory_result(query, chosen, cohort=normalized_cohort, selection=traces)
