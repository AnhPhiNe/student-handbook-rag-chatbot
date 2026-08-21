"""Registry-backed adapters for validated structured requests.

Planner selects ``lookup_type`` from the versioned lookup registry.  This module
owns execution selection: central executor never guesses a tool nor performs a
structured-to-RAG fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal, Mapping, Protocol

from src.common.cohort import normalize_cohort

from .citation_builder import build_citation_from_lookup
from .formula_lookup import formula_lookup
from .foreign_language_lookup import foreign_language_lookup
from .office_lookup import office_lookup
from .program_lookup import program_lookup
from .request_execution import RequestExecutionContext
from .scholarship_lookup import scholarship_classification_lookup
from .source_contract import enrich_source_records_from_registry, source_records_from_result
from .structured_lookup import structured_lookup_from_slots
from .study_duration_lookup import study_duration_lookup


REQUESTED_FIELD_RESULT_KEYS = {
    "unit": "unit_name",
    "phone": "phones",
    "email": "emails",
    "office": "office",
    "website": "websites",
    "services": "responsibilities",
}


@dataclass(frozen=True)
class ToolResources:
    scoring_tables: list[dict[str, Any]]
    formula_rules: list[dict[str, Any]]
    office_directory: list[dict[str, Any]]
    student_service_directory: list[dict[str, Any]]
    student_faculty_profiles: list[dict[str, Any]] | None
    foreign_language_tables: list[dict[str, Any]]
    structured_tables_registry: list[dict[str, Any]]
    program_directory: list[dict[str, Any]]
    detected_entities: list[dict[str, Any]] | None = None
    model: Any | None = None


ToolExecutionStatus = Literal["ok", "no_match", "invalid", "unresolved", "error"]


@dataclass(frozen=True)
class AtomicToolRequest:
    tool_name: str
    intent: str
    query_span: str
    slots: Mapping[str, Any] = field(default_factory=dict)
    slot_spans: Mapping[str, Any] = field(default_factory=dict)
    cohort_refs: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, request: Mapping[str, Any]) -> "AtomicToolRequest":
        return cls(
            tool_name=str(request.get("tool_name") or request.get("lookup_type") or "").strip(),
            intent=str(request.get("intent") or "").strip(),
            query_span=str(request.get("query_span") or "").strip(),
            slots=dict(request.get("slots") or {}),
            slot_spans=dict(request.get("slot_spans") or {}),
            cohort_refs=tuple(str(value) for value in request.get("cohort_refs") or []),
        )


@dataclass(frozen=True)
class ToolExecutionInput:
    request: AtomicToolRequest
    decision: Mapping[str, Any]
    context: RequestExecutionContext | None
    query: str
    effective_cohort: str | None
    resources: ToolResources

    @property
    def slots(self) -> Mapping[str, Any]:
        return self.request.slots


@dataclass(frozen=True)
class ToolExecutionResult:
    status: ToolExecutionStatus
    result: dict[str, Any] | None
    strategy: str
    result_kind: str = "structured"
    target_chunk_types: list[str] = field(default_factory=list)
    source_records: list[dict[str, Any]] = field(default_factory=list)
    citations: list[dict[str, Any]] = field(default_factory=list)
    confidence: float | str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)


class ToolAdapter(Protocol):
    def execute(self, payload: ToolExecutionInput) -> ToolExecutionResult: ...


def _slot_text(request: AtomicToolRequest, *names: str) -> str:
    spans = request.slot_spans
    slots = request.slots
    for name in names:
        # Canonical typed values are validator-approved execution inputs.
        # Source spans are provenance and only serve as a fallback when the
        # typed slot is absent.
        for source in (slots, spans):
            value = source.get(name) if isinstance(source, Mapping) else None
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, list) and value:
                joined = " ".join(str(item).strip() for item in value if str(item).strip())
                if joined:
                    return joined
    return ""


def _bind_regulation_source(
    result: dict[str, Any] | None, registry: list[dict[str, Any]]
) -> dict[str, Any] | None:
    if result is None:
        return None
    source_records = source_records_from_result(result)
    if not source_records:
        return result
    bound = dict(result)
    bound["source_records"] = enrich_source_records_from_registry(source_records, registry)
    return bound


def _requested_field_present(result: dict[str, Any] | None, field: str) -> bool:
    if result is None or field in {"", "all"}:
        return result is not None
    record_field = REQUESTED_FIELD_RESULT_KEYS.get(field)
    records = result.get("result") if result else None
    return bool(record_field and records and all(record.get(record_field) for record in records))


def _result(
    payload: ToolExecutionInput, strategy: str, result: dict[str, Any] | None,
    *, result_kind: str = "structured", target_chunk_types: list[str] | None = None,
) -> ToolExecutionResult:
    status: ToolExecutionStatus = (
        "unresolved"
        if result_kind == "clarification"
        else "ok" if result is not None else "no_match"
    )
    records = source_records_from_result(result) if result else []
    return ToolExecutionResult(
        status=status, result=result, strategy=strategy, result_kind=result_kind,
        target_chunk_types=target_chunk_types or [str((result or {}).get("content_type") or "structured_lookup")],
        source_records=records,
        confidence=(result or {}).get("confidence")
        or (result or {}).get("match_confidence")
        or (result or {}).get("score"),
        provenance={"tool_name": payload.request.tool_name, "cohort": payload.effective_cohort},
    )


class ForeignLanguageAdapter:
    def execute(self, payload: ToolExecutionInput) -> ToolExecutionResult:
        result = foreign_language_lookup(payload.query, payload.resources.foreign_language_tables, cohort=payload.effective_cohort, slots=payload.slots)
        return _result(payload, "foreign_language_lookup", _bind_regulation_source(result, payload.resources.structured_tables_registry))


class StudyDurationAdapter:
    def execute(self, payload: ToolExecutionInput) -> ToolExecutionResult:
        result = study_duration_lookup(payload.query, payload.resources.structured_tables_registry, cohort=payload.effective_cohort, slots=payload.slots)
        return _result(payload, "study_duration_lookup", _bind_regulation_source(result, payload.resources.structured_tables_registry))


class ScholarshipAdapter:
    def execute(self, payload: ToolExecutionInput) -> ToolExecutionResult:
        result = scholarship_classification_lookup(payload.query, payload.resources.scoring_tables, cohort=payload.effective_cohort, slots=payload.slots)
        return _result(payload, "scholarship_classification_lookup", _bind_regulation_source(result, payload.resources.structured_tables_registry))


class ScoringAdapter:
    def execute(self, payload: ToolExecutionInput) -> ToolExecutionResult:
        result = structured_lookup_from_slots(dict(payload.slots), payload.resources.scoring_tables, cohort=payload.effective_cohort) if payload.slots else None
        return _result(payload, "structured_lookup", _bind_regulation_source(result, payload.resources.structured_tables_registry))


class DirectoryAdapter:
    def __init__(self, lookup_type: str) -> None:
        self.lookup_type = lookup_type

    def execute(self, payload: ToolExecutionInput) -> ToolExecutionResult:
        slot = {"student_service": "service", "office": "office", "faculty": "faculty"}[self.lookup_type]
        candidate_text = _slot_text(
            payload.request, slot, "faculty", "office", "program_or_faculty"
        ) or payload.query
        if self.lookup_type == "student_service":
            directory = (
                payload.resources.student_service_directory
                + payload.resources.office_directory
            )
        elif self.lookup_type == "faculty":
            directory = payload.resources.student_faculty_profiles or []
        else:
            directory = payload.resources.office_directory
        # Execute the selected adapter from validator-approved typed slots.
        # Raw query text is only the fallback used above when no slot exists;
        # it must not override a canonical entity after alias/provenance checks.
        result = office_lookup(
            candidate_text,
            directory,
            cohort=payload.effective_cohort,
            detected_entities=payload.resources.detected_entities,
            routing={
                "intent": "office_query",
                "content_type": "office_directory",
                "target_chunk_types": ["office_directory"],
            },
            candidate_text=candidate_text,
            require_confident_match=True,
            model=(
                payload.resources.model
                if self.lookup_type == "student_service"
                else None
            ),
        )
        if result is not None and result.get("resolution_status") == "ambiguous":
            options = result.get("clarification_options") or []
            result = {**result, "clarification_question": "Câu hỏi của bạn liên quan đến nhiều đơn vị. Bạn cần hỗ trợ cụ thể về mảng nào dưới đây?\n\n" + "\n".join(options)}
            return _result(payload, "office_lookup_clarification", result, result_kind="clarification", target_chunk_types=[])
        requested_field = str(payload.slots.get("requested_field") or "")
        if not _requested_field_present(result, requested_field):
            result = None
        elif result is not None:
            result = {**result, "requested_field": requested_field}
        strategy = {"student_service": "student_service_lookup", "office": "office_lookup", "faculty": "faculty_lookup"}[self.lookup_type]
        chunk_types = {"student_service": ["student_service_directory", "student_office_profile"], "office": ["student_office_profile", "student_faculty_profile"], "faculty": ["student_faculty_profile", "student_office_profile"]}[self.lookup_type]
        return _result(payload, strategy, result, target_chunk_types=chunk_types)


class ProgramAdapter:
    def execute(self, payload: ToolExecutionInput) -> ToolExecutionResult:
        intent = payload.request.intent
        field = str(payload.slots.get("requested_field") or "")
        action = "resolve_faculty" if intent == "direct_value" and field == "faculty" else "exists" if intent == "exists" or field == "exists" else "list" if intent == "list_items" and field in {"", "programs", "all"} else None
        if action is None:
            return _result(payload, "program_lookup", None)
        result = program_lookup(payload.query or _slot_text(payload.request, "program_or_faculty"), payload.resources.program_directory, cohort=payload.effective_cohort, detected_entities=payload.resources.detected_entities, routing={"content_type": "program_directory", "action": action, "scope": str(payload.slots.get("scope") or "school")})
        return _result(payload, "program_lookup", result)


class FormulaAdapter:
    def execute(self, payload: ToolExecutionInput) -> ToolExecutionResult:
        result = formula_lookup(payload.query, payload.resources.formula_rules, cohort=payload.effective_cohort, slots=payload.slots)
        return _result(payload, "formula_lookup", _bind_regulation_source(result, payload.resources.structured_tables_registry), result_kind="formula")


class ToolRegistry:
    def __init__(self, specs: Mapping[str, Mapping[str, Any]], adapters: Mapping[str, ToolAdapter]) -> None:
        self._specs = specs
        self._adapters = adapters

    def execute(self, tool_name: str, payload: ToolExecutionInput) -> ToolExecutionResult:
        spec = self._specs.get(tool_name)
        adapter_id = str((spec or {}).get("adapter_id") or tool_name)
        adapter = self._adapters.get(adapter_id)
        if spec is None or adapter is None:
            return ToolExecutionResult(status="invalid", result=None, strategy="reject_invalid_plan", provenance={"tool_name": tool_name, "reason": "unregistered_tool"})
        validation_errors = self._validate_request(spec, payload.request)
        if validation_errors:
            return ToolExecutionResult(
                status="invalid",
                result=None,
                strategy="reject_invalid_plan",
                provenance={"tool_name": tool_name, "validation_errors": validation_errors},
            )
        required_cohort = bool(spec.get("cohort_sensitive"))
        if required_cohort and not normalize_cohort(payload.effective_cohort):
            return ToolExecutionResult(status="unresolved", result=None, strategy="reject_invalid_plan", provenance={"tool_name": tool_name, "reason": "missing_cohort"})
        try:
            result = adapter.execute(payload)
        except Exception as exc:
            return ToolExecutionResult(
                status="error",
                result=None,
                strategy=str(spec.get("strategy") or adapter_id),
                provenance={"tool_name": tool_name, "reason": "adapter_exception", "exception_type": type(exc).__name__},
            )
        source_contract = str(spec.get("source_contract") or "").strip()
        records = result.source_records
        if result.result is not None and not records:
            records = source_records_from_result(result.result)
        provenance = {
            **result.provenance,
            "adapter_id": adapter_id,
            "source_contract": source_contract,
            "source_bound": bool(records),
        }
        if result.status == "ok" and source_contract and not records:
            return replace(
                result,
                status="invalid",
                result=None,
                source_records=[],
                provenance={**provenance, "reason": "source_contract_unbound"},
            )
        bound_result = result.result
        if bound_result is not None and records:
            bound_result = {**bound_result, "source_records": records}
        citations = result.citations
        if bound_result is not None and not citations:
            citations = build_citation_from_lookup(bound_result)
        return replace(
            result,
            result=bound_result,
            source_records=records,
            citations=citations,
            provenance=provenance,
        )

    @staticmethod
    def _validate_request(
        spec: Mapping[str, Any], request: AtomicToolRequest
    ) -> list[str]:
        errors: list[str] = []
        intents = {str(value) for value in spec.get("intents") or []}
        if request.intent not in intents:
            errors.append(f"unsupported_intent:{request.intent or 'missing'}")
            return errors
        required_by_intent = spec.get("required_slots") or {}
        for slot_name in required_by_intent.get(request.intent) or []:
            value = request.slots.get(slot_name)
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(f"missing_slot:{slot_name}")
        schemas = spec.get("slot_schema") or {}
        for slot_name, value in request.slots.items():
            schema = schemas.get(slot_name)
            if not isinstance(schema, Mapping):
                errors.append(f"unknown_slot:{slot_name}")
                continue
            allowed = schema.get("enum") or schema.get("canonical_values")
            if allowed and value not in allowed:
                errors.append(f"invalid_slot_value:{slot_name}")
            declared_types = schema.get("type")
            if declared_types and not ToolRegistry._matches_type(value, declared_types):
                errors.append(f"invalid_slot_type:{slot_name}")
        return errors

    @staticmethod
    def _matches_type(value: Any, declared_types: Any) -> bool:
        values = declared_types if isinstance(declared_types, list) else [declared_types]
        checks = {
            "string": lambda item: isinstance(item, str),
            "number": lambda item: isinstance(item, int | float) and not isinstance(item, bool),
            "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
            "boolean": lambda item: isinstance(item, bool),
        }
        return any(checks.get(str(name), lambda _item: False)(value) for name in values)


def build_tool_registry(specs: Mapping[str, Mapping[str, Any]]) -> ToolRegistry:
    adapters: dict[str, ToolAdapter] = {
        "foreign_language": ForeignLanguageAdapter(), "study_duration": StudyDurationAdapter(),
        "scholarship_classification": ScholarshipAdapter(), "scoring": ScoringAdapter(),
        "student_service": DirectoryAdapter("student_service"), "office": DirectoryAdapter("office"),
        "faculty": DirectoryAdapter("faculty"), "program": ProgramAdapter(), "formula": FormulaAdapter(),
    }
    return ToolRegistry(specs, adapters)
