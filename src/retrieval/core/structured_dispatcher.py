"""Generic structured-request executor backed by the versioned ToolRegistry."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from src.common.cohort import normalize_cohort

from .request_execution import RequestExecutionContext
from .source_contract import deduplicate_source_records
from .structured_routing import load_lookup_registry
from .tool_registry import (
    AtomicToolRequest,
    ToolExecutionInput,
    ToolExecutionStatus,
    ToolResources,
    ToolRegistry,
    build_tool_registry,
)


@dataclass(frozen=True)
class StructuredResolution:
    lookup_type: str
    strategy: str
    result_kind: str
    result: dict[str, Any] | None
    target_chunk_types: list[str]
    status: ToolExecutionStatus = "ok"
    source_records: list[dict[str, Any]] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    confidence: float | str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)


def _has_structured_result(resolution: StructuredResolution | None) -> bool:
    if (
        not resolution
        or resolution.status != "ok"
        or not resolution.result
        or resolution.result_kind == "clarification"
    ):
        return False
    value = resolution.result
    for key in ("result", "rows", "items", "table"):
        if key in value and value[key] is not None:
            candidate = value[key]
            return bool(candidate) if isinstance(candidate, dict | list) else True
    return bool(value.get("exists") is True or value.get("formula_text"))


def _request_applies_to_cohort(
    request: Mapping[str, Any], cohort: str | None
) -> bool:
    normalized_cohort = normalize_cohort(cohort)
    refs = {
        normalized
        for value in request.get("cohort_refs") or []
        if (normalized := normalize_cohort(value))
    }
    return not refs or not normalized_cohort or normalized_cohort in refs


def _decision_for_request(
    decision: Mapping[str, Any], request: AtomicToolRequest
) -> dict[str, Any]:
    return {
        **decision,
        "intent": request.intent,
        "lookup_type": request.tool_name,
        "slots": dict(request.slots),
        "slot_spans": dict(request.slot_spans),
    }


def _with_request_metadata(
    resolution: StructuredResolution,
    *,
    request_index: int,
    query_span: str,
    cohort: str | None,
) -> StructuredResolution:
    if resolution.result is None:
        return resolution
    result = {
        **resolution.result,
        "request_index": request_index,
        "query_span": query_span,
        "request_lookup_type": resolution.lookup_type,
        "request_cohort": normalize_cohort(cohort),
    }
    return StructuredResolution(
        **{**resolution.__dict__, "result": result},
    )


def _combine_structured_resolutions(
    resolutions: list[StructuredResolution], *, cohort: str | None
) -> StructuredResolution:
    sub_results = [
        {
            "request_index": item.result.get("request_index"),
            "query_span": item.result.get("query_span"),
            "lookup_type": item.lookup_type,
            "cohort": normalize_cohort(cohort),
            "resolution_status": item.status,
            "result": item.result,
            "source_records": item.source_records,
        }
        for item in resolutions
        if item.result is not None
    ]
    source_records = deduplicate_source_records(
        [record for item in resolutions for record in item.source_records]
    )
    combined_result = {
        "lookup_type": "multi_request",
        "cohort": normalize_cohort(cohort),
        "lookup_count": len(resolutions),
        "sub_results": sub_results,
        "sub_lookups": [item.result for item in resolutions],
        "result": sub_results,
        "source_records": source_records,
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
        status="ok",
        source_records=source_records,
        citations=[citation for item in resolutions for citation in item.citations],
        provenance={"request_count": len(resolutions)},
    )


def _execute_request(
    request: AtomicToolRequest,
    *,
    decision: Mapping[str, Any],
    query: str,
    effective_cohort: str | None,
    resources: ToolResources,
    registry: ToolRegistry,
    context: RequestExecutionContext | None,
) -> StructuredResolution:
    execution = registry.execute(
        request.tool_name,
        ToolExecutionInput(
            request=request,
            decision=_decision_for_request(decision, request),
            context=context,
            query=query,
            effective_cohort=effective_cohort,
            resources=resources,
        ),
    )
    return StructuredResolution(
        lookup_type=request.tool_name,
        strategy=execution.strategy,
        result_kind=execution.result_kind,
        result=execution.result,
        target_chunk_types=execution.target_chunk_types,
        status=execution.status,
        source_records=execution.source_records,
        citations=execution.citations,
        confidence=execution.confidence,
        provenance=execution.provenance,
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
    registry = build_tool_registry(load_lookup_registry().get("tools") or {})
    raw_requests = decision.get("lookup_requests")
    if isinstance(raw_requests, list):
        entries = [
            (index, item)
            for index, item in enumerate(raw_requests)
            if isinstance(item, Mapping)
            and item.get("request_kind") == "structured"
            and (item.get("tool_name") or item.get("lookup_type"))
            and _request_applies_to_cohort(item, effective_cohort)
        ]
    else:
        tool_name = str(decision.get("tool_name") or decision.get("lookup_type") or "").strip()
        entries = [
            (
                0,
                {
                    "tool_name": tool_name,
                    "intent": decision.get("intent"),
                    "query_span": query,
                    "slots": decision.get("slots") or {},
                    "slot_spans": decision.get("slot_spans") or {},
                },
            )
        ] if tool_name else []

    successes: list[StructuredResolution] = []
    failures: list[StructuredResolution] = []
    for request_index, raw_request in entries:
        request = AtomicToolRequest.from_mapping(raw_request)
        context = (request_contexts or {}).get(request_index)
        query_span = context.query_span if context else request.query_span or query
        retrieval_query = context.retrieval_query if context else query_span
        resolution = _execute_request(
            request,
            decision=decision,
            query=retrieval_query,
            effective_cohort=effective_cohort,
            resources=resources,
            registry=registry,
            context=context,
        )
        if resolution.result_kind == "clarification":
            return _with_request_metadata(
                resolution,
                request_index=request_index,
                query_span=query_span,
                cohort=effective_cohort,
            )
        if _has_structured_result(resolution):
            successes.append(
                _with_request_metadata(
                    resolution,
                    request_index=request_index,
                    query_span=query_span,
                    cohort=effective_cohort,
                )
            )
        else:
            failures.append(resolution)

    if len(successes) == 1:
        return successes[0]
    if successes:
        return _combine_structured_resolutions(successes, cohort=effective_cohort)
    return failures[0] if failures else None
