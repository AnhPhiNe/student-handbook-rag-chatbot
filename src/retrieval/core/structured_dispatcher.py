from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from src.common.cohort import normalize_cohort

from .formula_lookup import formula_lookup
from .foreign_language_lookup import foreign_language_lookup
from .office_lookup import office_lookup
from .program_lookup import program_lookup
from .request_execution import RequestExecutionContext
from .structured_routing import load_lookup_registry
from .tool_registry import (
    ToolExecutionInput,
    ToolResources,
    build_tool_registry,
)
from .scholarship_lookup import scholarship_classification_lookup
from .study_duration_lookup import study_duration_lookup
from .structured_lookup import structured_lookup_from_slots
from .source_contract import (
    deduplicate_source_records,
    enrich_source_records_from_registry,
    source_records_from_result,
)


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
        for source in (spans, slots):
            value = source.get(name)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, list) and value:
                joined = " ".join(str(v).strip() for v in value if str(v).strip())
                if joined:
                    return joined
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
        "services": "responsibilities",
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
    del cohort, table_type, subtypes
    source_records = source_records_from_result(result)
    if not source_records:
        return result
    source_records = enrich_source_records_from_registry(source_records, registry)
    bound = dict(result)
    bound["source_records"] = source_records
    parent_ids = [
        str(record.get("parent_section_id"))
        for record in source_records
        if record.get("parent_section_id")
    ]
    if parent_ids:
        bound["source_parent_ids"] = list(dict.fromkeys(parent_ids))
        bound["source_parent_id"] = parent_ids[0]
        bound["source_section"] = parent_ids[0]
    document_ids = {
        record.get("document_id")
        for record in source_records
        if record.get("document_id")
    }
    if len(document_ids) == 1:
        bound["document_id"] = next(iter(document_ids))
    bound["source_pages"] = sorted(
        {
            page
            for record in source_records
            for page in record.get("source_pages") or []
        }
    )
    return bound


def _resolve_registry_lookup(
    lookup_type: str,
    *,
    decision: dict[str, Any],
    request: dict[str, Any],
    query: str,
    effective_cohort: str | None,
    resources: ToolResources,
    context: RequestExecutionContext | None,
) -> StructuredResolution | None:
    """Execute selected tool only; no tool inference or RAG fallback here."""
    result = build_tool_registry(load_lookup_registry().get("tools") or {}).execute(
        lookup_type,
        ToolExecutionInput(
            request=request,
            decision=decision,
            context=context,
            query=query,
            effective_cohort=effective_cohort,
            resources=resources,
        ),
    )
    if result.result is None:
        return None
    return StructuredResolution(
        lookup_type=lookup_type,
        strategy=result.strategy,
        result_kind=result.result_kind,
        result=result.result,
        target_chunk_types=result.target_chunk_types,
    )


def _resolve_single_lookup(
    lookup_type: str,
    *,
    decision: dict[str, Any],
    query: str,
    effective_cohort: str | None,
    scoring_tables: list[dict[str, Any]],
    formula_rules: list[dict[str, Any]],
    office_directory: list[dict[str, Any]],
    student_service_directory: list[dict[str, Any]],
    student_faculty_profiles: list[dict[str, Any]] | None,
    foreign_language_tables: list[dict[str, Any]],
    structured_tables_registry: list[dict[str, Any]],
    program_directory: list[dict[str, Any]],
    detected_entities: list[dict[str, Any]] | None = None,
    model: Any | None = None,
) -> StructuredResolution | None:
    slots = decision.get("slots") or {}

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
        ) if slots else None
        operation = str(slots.get("operation") or "")
        subtype_map = {
            "grade_10_to_letter": {
                "grade_scale",
                "grade_10_to_letter",
            },
            "pass_fail_ungraded": {
                "grade_scale",
                "grade_10_to_letter",
                "pass_fail_ungraded",
            },
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
        candidate_text = (
            query
            or _slot_text(decision, candidate_slot)
            or _slot_text(decision, "faculty")
            or _slot_text(decision, "office")
            or _slot_text(decision, "program_or_faculty")
            or query
        )
        if lookup_type == "student_service":
            directory = student_service_directory + office_directory
        else:
            directory = office_directory + (student_faculty_profiles or [])

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
            model=model if lookup_type == "student_service" else None,
        )
        if result is not None and result.get("resolution_status") == "ambiguous":
            options = result.get("clarification_options") or []
            result["clarification_question"] = (
                "Câu hỏi của bạn liên quan đến nhiều đơn vị. Bạn cần hỗ trợ cụ thể về mảng nào dưới đây?\n\n" + "\n".join(options)
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
            "student_service": ["student_service_directory", "student_office_profile"],
            "office": ["student_office_profile", "student_faculty_profile"],
            "faculty": ["student_faculty_profile", "student_office_profile"],
        }
        return _resolution(
            lookup_type,
            strategies[lookup_type],
            result,
            target_chunk_types=target_content_types.get(lookup_type, ["student_office_profile"]),
        )

    if lookup_type == "program":
        candidate_text = query or _slot_text(decision, "program_or_faculty")
        intent = decision.get("intent")
        scope = str(slots.get("scope") or "school")
        requested_field = str(slots.get("requested_field") or "")
        if intent == "direct_value" and requested_field == "faculty":
            action = "resolve_faculty"
        elif intent == "exists" or requested_field == "exists":
            action = "exists"
        elif intent == "list_items" and requested_field in {"", "programs", "all"}:
            action = "list"
        else:
            return _resolution(lookup_type, "program_lookup", None)
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



def _has_structured_result(
    resolution: StructuredResolution | None,
) -> bool:
    if not resolution or not resolution.result or resolution.result_kind == "clarification":
        return False
    res_data = resolution.result
    if isinstance(res_data, dict):
        if "result" in res_data:
            result = res_data["result"]
            if isinstance(result, (dict, list)):
                return bool(result)
            if result is not None:
                return True
        if "rows" in res_data and isinstance(res_data["rows"], list):
            return len(res_data["rows"]) > 0
        if "items" in res_data and isinstance(res_data["items"], list):
            return len(res_data["items"]) > 0
        if "table" in res_data and isinstance(res_data["table"], dict):
            return bool(res_data["table"])
        if res_data.get("exists") is True:
            return True
        if res_data.get("formula_text"):
            return True
    elif isinstance(res_data, list):
        return len(res_data) > 0
    return False


def _request_applies_to_cohort(
    request: dict[str, Any],
    cohort: str | None,
) -> bool:
    normalized_cohort = normalize_cohort(cohort)
    refs = [
        normalized
        for value in request.get("cohort_refs") or []
        if (normalized := normalize_cohort(value))
    ]
    return not refs or not normalized_cohort or normalized_cohort in refs


def _decision_for_request(
    decision: dict[str, Any],
    request: dict[str, Any],
) -> dict[str, Any]:
    return {
        **decision,
        "intent": request.get("intent"),
        "lookup_type": request.get("lookup_type"),
        "slots": dict(request.get("slots") or {}),
        "slot_spans": dict(request.get("slot_spans") or {}),
    }


def _with_request_metadata(
    resolution: StructuredResolution,
    *,
    request_index: int,
    query_span: str,
    cohort: str | None,
) -> StructuredResolution:
    result = {
        **resolution.result,
        "request_index": request_index,
        "query_span": query_span,
        "request_lookup_type": resolution.lookup_type,
        "request_cohort": normalize_cohort(cohort),
    }
    return StructuredResolution(
        lookup_type=resolution.lookup_type,
        strategy=resolution.strategy,
        result_kind=resolution.result_kind,
        result=result,
        target_chunk_types=resolution.target_chunk_types,
    )


def _combine_structured_resolutions(
    resolutions: list[StructuredResolution],
    *,
    cohort: str | None,
) -> StructuredResolution:
    sub_results = [
        {
            "request_index": item.result.get("request_index"),
            "query_span": item.result.get("query_span"),
            "lookup_type": item.lookup_type,
            "cohort": normalize_cohort(cohort),
            "resolution_status": "resolved",
            "result": item.result,
            "source_records": item.result.get("source_records") or [],
        }
        for item in resolutions
    ]
    combined_result = {
        "lookup_type": "multi_request",
        "cohort": normalize_cohort(cohort),
        "lookup_count": len(resolutions),
        "sub_results": sub_results,
        "sub_lookups": [item.result for item in resolutions],
        "result": sub_results,
        "source_records": deduplicate_source_records(
            [
                source_record
                for item in resolutions
                for source_record in item.result.get("source_records") or []
            ]
        ),
        "table_name": "Các nguồn structured theo từng ý hỏi",
        "source_label": "Dữ liệu tra cứu theo semantic request",
        "content_type": "multi_structured_lookup",
    }
    return StructuredResolution(
        lookup_type="multi_request",
        strategy="semantic_request_lookup",
        result_kind="multi_structured",
        result=combined_result,
        target_chunk_types=list(
            dict.fromkeys(
                chunk_type
                for item in resolutions
                for chunk_type in item.target_chunk_types
            )
        ),
    )


def resolve_structured_decision(
    decision: dict[str, Any],
    *,
    query: str,
    cohort: str | None,
    scoring_tables: list[dict[str, Any]],
    formula_rules: list[dict[str, Any]],
    office_directory: list[dict[str, Any]],
    student_service_directory: list[dict[str, Any]],
    student_faculty_profiles: list[dict[str, Any]] | None,
    foreign_language_tables: list[dict[str, Any]],
    structured_tables_registry: list[dict[str, Any]],
    program_directory: list[dict[str, Any]],
    detected_entities: list[dict[str, Any]] | None = None,
    model: Any | None = None,
    request_contexts: Mapping[int, RequestExecutionContext] | None = None,
) -> StructuredResolution | None:
    effective_cohort = normalize_cohort(cohort or decision.get("cohort"))

    resources = ToolResources(
        scoring_tables=scoring_tables,
        formula_rules=formula_rules,
        office_directory=office_directory,
        student_service_directory=student_service_directory,
        student_faculty_profiles=student_faculty_profiles,
        foreign_language_tables=foreign_language_tables,
        structured_tables_registry=structured_tables_registry,
        program_directory=program_directory,
        detected_entities=detected_entities,
        model=model,
    )

    raw_requests = decision.get("lookup_requests")
    if isinstance(raw_requests, list):
        request_entries = [
            (index, request)
            for index, request in enumerate(raw_requests)
            if isinstance(request, dict)
            and request.get("request_kind") == "structured"
            and request.get("lookup_type")
            and _request_applies_to_cohort(request, effective_cohort)
        ]
    else:
        lookup_type = str(decision.get("lookup_type") or "").strip()
        request_entries = [
            (
                0,
                {
                    "lookup_type": lookup_type,
                    "intent": decision.get("intent"),
                    "query_span": query,
                    "slots": decision.get("slots") or {},
                    "slot_spans": decision.get("slot_spans") or {},
                },
            )
        ] if lookup_type else []

    collected: list[StructuredResolution] = []
    for request_index, request in request_entries:
        execution_context = (request_contexts or {}).get(request_index)
        request_query = (
            execution_context.query_span
            if execution_context
            else str(request.get("query_span") or query).strip()
        )
        lookup_query = (
            execution_context.retrieval_query
            if execution_context
            else request_query
        )
        request_decision = _decision_for_request(decision, request)
        resolution = _resolve_registry_lookup(
            str(request.get("lookup_type") or "").strip(),
            decision=request_decision,
            request=request,
            query=lookup_query,
            effective_cohort=effective_cohort,
            resources=resources,
            context=execution_context,
        )
        if resolution and resolution.result_kind == "clarification":
            return _with_request_metadata(
                resolution,
                request_index=request_index,
                query_span=request_query,
                cohort=effective_cohort,
            )
        if _has_structured_result(resolution) and resolution:
            collected.append(
                _with_request_metadata(
                    resolution,
                    request_index=request_index,
                    query_span=request_query,
                    cohort=effective_cohort,
                )
            )

    if len(collected) == 1:
        return collected[0]
    if collected:
        return _combine_structured_resolutions(collected, cohort=effective_cohort)
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
