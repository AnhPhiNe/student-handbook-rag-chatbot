from __future__ import annotations

from dataclasses import dataclass

from src.retrieval.core.tool_registry import (
    AtomicToolRequest,
    ToolExecutionInput,
    ToolExecutionResult,
    ToolRegistry,
    ToolResources,
)
from src.retrieval.core.structured_dispatcher import resolve_structured_decision


@dataclass
class _Adapter:
    called: bool = False

    def execute(self, payload: ToolExecutionInput) -> ToolExecutionResult:
        self.called = True
        return ToolExecutionResult(status="ok", result={"result": ["bound"]}, strategy="adapter")


class _FailingAdapter:
    def execute(self, payload: ToolExecutionInput) -> ToolExecutionResult:
        raise RuntimeError("adapter failed")


def _payload(cohort: str | None = "K51") -> ToolExecutionInput:
    return ToolExecutionInput(
        request=AtomicToolRequest(
            tool_name="example", intent="direct_value", query_span="query"
        ),
        decision={}, context=None,
        query="query", effective_cohort=cohort,
        resources=ToolResources([], [], [], [], None, [], [], []),
    )


def test_registry_executes_selected_adapter_only() -> None:
    adapter = _Adapter()
    registry = ToolRegistry({"example": {"adapter_id": "registered", "cohort_sensitive": False, "intents": ["direct_value"]}}, {"registered": adapter})
    result = registry.execute("example", _payload())
    assert result.status == "ok"
    assert adapter.called


def test_registry_rejects_unknown_or_unbound_cohort_sensitive_tool() -> None:
    registry = ToolRegistry({"example": {"adapter_id": "registered", "cohort_sensitive": True, "intents": ["direct_value"]}}, {"registered": _Adapter()})
    assert registry.execute("unknown", _payload()).status == "invalid"
    assert registry.execute("example", _payload(None)).status == "unresolved"


def test_registry_validates_schema_and_normalizes_adapter_exception() -> None:
    spec = {
        "adapter_id": "registered",
        "cohort_sensitive": False,
        "intents": ["direct_value"],
        "required_slots": {"direct_value": ["score"]},
        "slot_schema": {"score": {"type": "number"}},
    }
    registry = ToolRegistry({"example": spec}, {"registered": _FailingAdapter()})
    assert registry.execute("example", _payload()).status == "invalid"
    payload = ToolExecutionInput(
        request=AtomicToolRequest(
            tool_name="example",
            intent="direct_value",
            query_span="score 3",
            slots={"score": 3},
        ),
        decision={},
        context=None,
        query="score 3",
        effective_cohort="K51",
        resources=ToolResources([], [], [], [], None, [], [], []),
    )
    result = registry.execute("example", payload)
    assert result.status == "error"
    assert result.provenance["exception_type"] == "RuntimeError"


def test_registry_enforces_declared_source_contract() -> None:
    spec = {
        "adapter_id": "registered",
        "cohort_sensitive": False,
        "intents": ["direct_value"],
        "source_contract": "structured_record",
    }
    registry = ToolRegistry({"example": spec}, {"registered": _Adapter()})
    result = registry.execute("example", _payload())
    assert result.status == "invalid"
    assert result.provenance["reason"] == "source_contract_unbound"


def test_dispatcher_preserves_invalid_adapter_status() -> None:
    resolution = resolve_structured_decision(
        {
            "cohort": "K51",
            "lookup_requests": [
                {
                    "request_kind": "structured",
                    "lookup_type": "unknown_tool",
                    "intent": "direct_value",
                    "query_span": "unknown",
                    "slots": {},
                    "cohort_refs": ["K51"],
                }
            ],
        },
        query="unknown",
        cohort="K51",
        scoring_tables=[],
        formula_rules=[],
        office_directory=[],
        student_service_directory=[],
        student_faculty_profiles=[],
        foreign_language_tables=[],
        structured_tables_registry=[],
        program_directory=[],
    )
    assert resolution is not None
    assert resolution.status == "invalid"
    assert resolution.provenance["reason"] == "unregistered_tool"
