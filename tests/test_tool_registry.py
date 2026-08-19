from __future__ import annotations

from dataclasses import dataclass

from src.retrieval.core.tool_registry import (
    ToolExecutionInput,
    ToolExecutionResult,
    ToolRegistry,
    ToolResources,
)


@dataclass
class _Adapter:
    called: bool = False

    def execute(self, payload: ToolExecutionInput) -> ToolExecutionResult:
        self.called = True
        return ToolExecutionResult(status="ok", result={"result": ["bound"]}, strategy="adapter")


def _payload(cohort: str | None = "K51") -> ToolExecutionInput:
    return ToolExecutionInput(
        request={"lookup_type": "example"}, decision={}, context=None,
        query="query", effective_cohort=cohort,
        resources=ToolResources([], [], [], [], None, [], [], []),
    )


def test_registry_executes_selected_adapter_only() -> None:
    adapter = _Adapter()
    registry = ToolRegistry({"example": {"adapter_id": "registered", "cohort_sensitive": False}}, {"registered": adapter})
    result = registry.execute("example", _payload())
    assert result.status == "ok"
    assert adapter.called


def test_registry_rejects_unknown_or_unbound_cohort_sensitive_tool() -> None:
    registry = ToolRegistry({"example": {"adapter_id": "registered", "cohort_sensitive": True}}, {"registered": _Adapter()})
    assert registry.execute("unknown", _payload()).status == "invalid"
    assert registry.execute("example", _payload(None)).status == "unresolved"
