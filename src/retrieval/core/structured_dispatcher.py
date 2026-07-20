from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.common.cohort import normalize_cohort

from .form_lookup import form_lookup
from .formula_lookup import formula_lookup
from .foreign_language_lookup import foreign_language_lookup
from .office_lookup import office_lookup
from .program_lookup import program_lookup
from .scholarship_lookup import scholarship_classification_lookup
from .study_duration_lookup import study_duration_lookup
from .structured_lookup import structured_lookup_from_slots


@dataclass(frozen=True)
class StructuredResolution:
    lookup_type: str
    strategy: str
    result_kind: str
    result: dict[str, Any]
    target_chunk_types: list[str]


def _slot_text(decision: dict[str, Any], *names: str) -> str:
    spans = decision.get("slot_spans") or {}
    slots = decision.get("slots") or {}
    for name in names:
        value = spans.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
        value = slots.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _result_supports_requested_field(
    result: dict[str, Any] | None,
    requested_field: str,
) -> bool:
    if result is None or requested_field in {"", "all"}:
        return result is not None
    field_map = {
        "unit": "unit_name",
        "phone": "phones",
        "email": "emails",
        "office": "office",
        "website": "websites",
    }
    record_field = field_map.get(requested_field)
    if record_field is None:
        return False
    records = result.get("result") or []
    return bool(records) and all(record.get(record_field) for record in records)


def _bind_regulation_source(
    result: dict[str, Any] | None,
    registry: list[dict[str, Any]],
    *,
    cohort: str | None,
    table_type: str,
    subtypes: set[str] | None = None,
) -> dict[str, Any] | None:
    if result is None:
        return None
    candidates = [
        table
        for table in registry
        if table.get("data_category") == "regulation_table"
        and table.get("table_type") == table_type
        and (not cohort or normalize_cohort(table.get("cohort")) == cohort)
        and (
            not subtypes
            or str(table.get("table_subtype") or "") in subtypes
        )
    ]
    source_parent_ids = list(
        dict.fromkeys(
            str(table.get("source_parent_id") or table.get("source_section_id"))
            for table in candidates
            if table.get("source_parent_id") or table.get("source_section_id")
        )
    )
    if not source_parent_ids:
        return result
    bound = dict(result)
    bound["source_parent_ids"] = source_parent_ids
    bound["source_parent_id"] = source_parent_ids[0]
    bound["source_section"] = source_parent_ids[0]
    if len({str(table.get("document_id") or "") for table in candidates}) == 1:
        bound["document_id"] = candidates[0].get("document_id")
    bound["source_pages"] = sorted(
        {
            page
            for table in candidates
            for page in table.get("source_pages") or []
        }
    )
    return bound


def resolve_structured_decision(
    decision: dict[str, Any],
    *,
    query: str,
    cohort: str | None,
    scoring_tables: list[dict[str, Any]],
    formula_rules: list[dict[str, Any]],
    form_templates: list[dict[str, Any]],
    office_directory: list[dict[str, Any]],
    student_service_directory: list[dict[str, Any]],
    student_faculty_profiles: list[dict[str, Any]] | None,
    foreign_language_tables: list[dict[str, Any]],
    structured_tables_registry: list[dict[str, Any]],
    program_directory: list[dict[str, Any]],
    detected_entities: list[dict[str, Any]] | None = None,
    model: Any | None = None,
) -> StructuredResolution | None:
    """Resolve exactly the lookup selected by the validated Qwen decision."""
    lookup_type = str(decision.get("lookup_type") or "")
    slots = decision.get("slots") or {}
    effective_cohort = normalize_cohort(cohort) or normalize_cohort(decision.get("cohort"))

    if lookup_type == "foreign_language":
        result = foreign_language_lookup(
            query,
            foreign_language_tables,
            cohort=effective_cohort,
            slots=slots,
        )
        result = _bind_regulation_source(
            result,
            structured_tables_registry,
            cohort=effective_cohort,
            table_type="foreign_language",
        )
        return _resolution(lookup_type, "foreign_language_lookup", result)

    if lookup_type == "study_duration":
        result = study_duration_lookup(
            query,
            structured_tables_registry,
            cohort=effective_cohort,
            slots=slots,
        )
        result = _bind_regulation_source(
            result,
            structured_tables_registry,
            cohort=effective_cohort,
            table_type="study_duration",
        )
        return _resolution(lookup_type, "study_duration_lookup", result)

    if lookup_type == "scholarship_classification":
        result = scholarship_classification_lookup(
            query,
            scoring_tables,
            cohort=effective_cohort,
            slots=slots,
        )
        result = _bind_regulation_source(
            result,
            structured_tables_registry,
            cohort=effective_cohort,
            table_type="scholarship",
        )
        return _resolution(
            lookup_type,
            "scholarship_classification_lookup",
            result,
        )

    if lookup_type == "scoring":
        result = structured_lookup_from_slots(
            slots,
            scoring_tables,
            cohort=effective_cohort,
        )
        operation = str(slots.get("operation") or "")
        subtype_map = {
            "grade_10_to_letter": {
                "grade_scale",
                "grade_10_to_letter",
            },
            "pass_fail_ungraded": {"pass_fail_ungraded"},
            "pass_threshold": {
                "grade_scale",
                "grade_10_to_letter",
                "pass_fail_ungraded",
            },
            "letter_to_grade_4": {"letter_to_grade4", "letter_to_grade_4"},
            "academic_classification": {"academic_classification"},
            "conduct_classification": {"conduct_classification", "conduct"},
        }
        canonical_type = (
            "conduct" if operation == "conduct_classification" else "scoring"
        )
        result = _bind_regulation_source(
            result,
            structured_tables_registry,
            cohort=effective_cohort,
            table_type=canonical_type,
            subtypes=subtype_map.get(operation),
        )
        return _resolution(lookup_type, "structured_lookup", result)

    if lookup_type in {"student_service", "office", "faculty"}:
        candidate_slot = {
            "student_service": "service",
            "office": "office",
            "faculty": "faculty",
        }[lookup_type]
        candidate_text = _slot_text(decision, candidate_slot)
        directories = {
            "student_service": student_service_directory,
            "office": office_directory,
            "faculty": student_faculty_profiles or [],
        }
        directory = directories[lookup_type]
        routing = {
            "intent": "office_query",
            "content_type": "office_directory",
            "target_chunk_types": ["office_directory"],
        }
        result = office_lookup(
            query,
            directory,
            cohort=effective_cohort,
            detected_entities=detected_entities,
            routing=routing,
            candidate_text=candidate_text,
            require_confident_match=True,
            model=model,
        )
        if result is not None and result.get("resolution_status") == "ambiguous":
            options = result.get("clarification_options") or []
            result["clarification_question"] = (
                "Bạn đang muốn hỏi đơn vị nào: " + ", ".join(options) + "?"
            )
            return _resolution(
                lookup_type,
                "office_lookup_clarification",
                result,
                result_kind="clarification",
                target_chunk_types=[],
            )
        requested_field = str(slots.get("requested_field") or "")
        if not _result_supports_requested_field(result, requested_field):
            result = None
        elif result is not None:
            result["requested_field"] = requested_field
        strategies = {
            "student_service": "student_service_lookup",
            "office": "office_lookup",
            "faculty": "faculty_lookup",
        }
        target_content_types = {
            "student_service": "student_service_directory",
            "office": "student_office_profile",
            "faculty": "student_faculty_profile",
        }
        return _resolution(
            lookup_type,
            strategies[lookup_type],
            result,
            target_chunk_types=[target_content_types[lookup_type]],
        )

    if lookup_type == "form":
        candidate_text = _slot_text(decision, "purpose")
        result = form_lookup(
            query,
            form_templates,
            cohort=effective_cohort,
            candidate_text=candidate_text,
            require_confident_match=decision.get("intent") != "list_items",
        )
        return _resolution(lookup_type, "form_lookup", result)

    if lookup_type == "program":
        candidate_text = _slot_text(decision, "program_or_faculty") or query
        intent = decision.get("intent")
        scope = str(slots.get("scope") or "school")
        requested_field = str(slots.get("requested_field") or "")
        action = "list" if intent == "list_items" else "resolve_faculty"
        if intent == "exists" or requested_field == "exists":
            action = "exists"
        if requested_field in {"list", "programs", "nganh"}:
            action = "list"
        result = program_lookup(
            candidate_text,
            program_directory,
            cohort=effective_cohort,
            detected_entities=detected_entities,
            routing={
                "content_type": "program_directory",
                "action": action,
                "scope": scope,
            },
        )
        return _resolution(lookup_type, "program_lookup", result)

    if lookup_type == "formula":
        result = formula_lookup(
            query,
            formula_rules,
            cohort=effective_cohort,
            slots=slots,
        )
        formula_type = str(slots.get("formula_type") or "")
        if formula_type == "scholarship_score":
            result = _bind_regulation_source(
                result,
                structured_tables_registry,
                cohort=effective_cohort,
                table_type="scholarship",
            )
        else:
            result = _bind_regulation_source(
                result,
                structured_tables_registry,
                cohort=effective_cohort,
                table_type="scoring",
                subtypes={"academic_classification"},
            )
        return _resolution(
            lookup_type,
            "formula_lookup",
            result,
            result_kind="formula",
        )

    return None


def _resolution(
    lookup_type: str,
    strategy: str,
    result: dict[str, Any] | None,
    *,
    result_kind: str = "structured",
    target_chunk_types: list[str] | None = None,
) -> StructuredResolution | None:
    if result is None:
        return None
    return StructuredResolution(
        lookup_type=lookup_type,
        strategy=strategy,
        result_kind=result_kind,
        result=result,
        target_chunk_types=target_chunk_types or [
            str(result.get("content_type") or "structured_lookup")
        ],
    )
