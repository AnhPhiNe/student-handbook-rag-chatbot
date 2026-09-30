"""Evaluation-only record of what the planner returned on each attempt.

The deterministic evaluation turns this on with `planner_diagnostics_scope(True)`
to see how a raw plan changed in normalization. Outside that scope every
`PlannerTrace` call does nothing, so production requests carry no diagnostics.
A snapshot keeps only structural fields (modes, lookups, cohorts, declared slot
names and values, error messages): never the question text, history, sources,
the answer or a key.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from typing import Any

from .query_plan import QUERY_PLAN_NORMALIZER_VERSION, QUERY_PLAN_SCHEMA_VERSION
from .structured_routing import load_lookup_registry

PLANNER_DIAGNOSTIC_SCHEMA_VERSION = "planner-decision-diagnostics-v2"

_planner_diagnostics_scope: ContextVar[bool] = ContextVar(
    "planner_diagnostics_scope", default=False
)


@contextmanager
def planner_diagnostics_scope(enabled: bool) -> Iterator[None]:
    """Enable planner capture only inside an explicit evaluation scope."""
    token = _planner_diagnostics_scope.set(bool(enabled))
    try:
        yield
    finally:
        _planner_diagnostics_scope.reset(token)


def planner_diagnostics_enabled() -> bool:
    return _planner_diagnostics_scope.get()


_PLANNER_DIAGNOSTIC_DECISION_FIELDS = (
    "route",
    "execution_mode",
    "mode",
    "intent",
    "lookup_type",
    "context_mode",
    "schema_version",
    "out_of_domain",
)
_PLANNER_DIAGNOSTIC_TASK_FIELDS = (
    "id",
    "task_id",
    "mode",
    "execution_mode",
    "intent",
    "lookup_type",
    "cohort",
    "cohorts",
    "slots",
    "slot_spans",
)
_DIAGNOSTIC_MISSING = object()


def _diagnostic_copy(value: Any) -> Any:
    """Copy JSON-compatible diagnostic values without retaining live aliases."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_diagnostic_copy(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _diagnostic_copy(item)
            for key, item in value.items()
            if isinstance(key, str)
        }
    return None


def _diagnostic_leaf(value: Any) -> Any:
    """Copy a slot/span leaf while rejecting arbitrary nested payloads."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        copied = []
        for item in value:
            leaf = _diagnostic_leaf(item)
            if leaf is _DIAGNOSTIC_MISSING:
                return _DIAGNOSTIC_MISSING
            copied.append(leaf)
        return copied
    return _DIAGNOSTIC_MISSING


def _diagnostic_slot_map(
    value: Any,
    *,
    allowed_keys: set[str],
) -> dict[str, Any]:
    """Copy only declared slot names and scalar/list leaves."""
    if not isinstance(value, dict):
        return {}
    copied: dict[str, Any] = {}
    for key, item in value.items():
        if not isinstance(key, str) or key not in allowed_keys:
            continue
        leaf = _diagnostic_leaf(item)
        if leaf is not _DIAGNOSTIC_MISSING:
            copied[key] = leaf
    return copied


def _diagnostic_allowed_slot_keys(
    lookup_type: Any,
    registry: dict[str, Any] | None,
) -> set[str]:
    """Return registry-declared slot keys for a planner task."""
    if not isinstance(lookup_type, str) or not isinstance(registry, dict):
        return set()
    tools = registry.get("tools")
    spec = tools.get(lookup_type) if isinstance(tools, dict) else None
    schema = spec.get("slot_schema") if isinstance(spec, dict) else None
    if not isinstance(schema, dict):
        return set()
    return {key for key in schema if isinstance(key, str)}


def _diagnostic_messages(value: Any) -> list[str]:
    values = value if isinstance(value, (list, tuple)) else [value]
    return [
        item[:500]
        for item in values
        if isinstance(item, str) and item.strip()
    ]


def planner_decision_snapshot(
    payload: Any,
    *,
    errors: Any = None,
    warnings: Any = None,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Keep only structural planner fields for an explicit eval diagnostic."""
    if registry is None:
        registry = load_lookup_registry()
    decision = payload if isinstance(payload, dict) else {}
    snapshot: dict[str, Any] = {}
    for field in _PLANNER_DIAGNOSTIC_DECISION_FIELDS:
        if field in decision:
            snapshot[field] = _diagnostic_copy(decision[field])

    raw_tasks = decision.get("tasks")
    if isinstance(raw_tasks, list):
        tasks: list[dict[str, Any]] = []
        for raw_task in raw_tasks:
            if not isinstance(raw_task, dict):
                continue
            task = {
                field: _diagnostic_copy(raw_task[field])
                for field in _PLANNER_DIAGNOSTIC_TASK_FIELDS
                if field in raw_task
            }
            allowed_slot_keys = _diagnostic_allowed_slot_keys(
                raw_task.get("lookup_type"), registry
            )
            for field in ("slots", "slot_spans"):
                if field in raw_task:
                    task[field] = _diagnostic_slot_map(
                        raw_task[field], allowed_keys=allowed_slot_keys
                    )
            task_errors = raw_task.get("errors")
            if task_errors is None:
                task_errors = raw_task.get("validation_errors")
            task_warnings = raw_task.get("warnings")
            if task_warnings is None:
                task_warnings = raw_task.get("normalization_warnings")
            if task_errors is not None:
                task["errors"] = _diagnostic_messages(task_errors)
            if task_warnings is not None:
                task["warnings"] = _diagnostic_messages(task_warnings)
            tasks.append(task)
        snapshot["tasks"] = tasks

    if errors is None:
        errors = decision.get("errors")
    if errors is None:
        errors = decision.get("planner_validation_errors")
    if errors is None:
        errors = decision.get("validation_errors")
    if warnings is None:
        warnings = decision.get("warnings")
    if warnings is None:
        warnings = decision.get("normalization_warnings")
    snapshot["errors"] = _diagnostic_messages(errors)
    snapshot["warnings"] = _diagnostic_messages(warnings)
    return snapshot


def build_planner_diagnostics(
    attempts: list[dict[str, Any]],
    final_plan: Any,
    *,
    prompt_version: str,
    final_errors: Any = None,
    cache_hit: bool = False,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an evaluation-only raw/normalized planner decision envelope."""
    return {
        "schema_version": PLANNER_DIAGNOSTIC_SCHEMA_VERSION,
        "versions": {
            "router_prompt_version": prompt_version,
            "query_plan_schema_version": QUERY_PLAN_SCHEMA_VERSION,
            "query_plan_normalizer_version": QUERY_PLAN_NORMALIZER_VERSION,
        },
        "cache_hit": bool(cache_hit),
        "attempts": deepcopy(attempts),
        "final": planner_decision_snapshot(
            final_plan,
            errors=final_errors,
            registry=registry,
        ),
    }


class PlannerTrace:
    """Collect one planner call's attempts when diagnostics are on.

    `AIRouter.plan` calls it at each step; while diagnostics are off (the
    default, and always for a message with chat history) every call returns
    at once, so the planner code reads the same either way.
    """

    def __init__(
        self,
        *,
        enabled: bool,
        registry: dict[str, Any] | None,
        prompt_version: str,
        describe_response: Callable[[Any], dict[str, Any]],
        describe_error: Callable[[Exception], dict[str, Any]],
    ) -> None:
        self.enabled = enabled
        self.registry = registry
        self.prompt_version = prompt_version
        self._describe_response = describe_response
        self._describe_error = describe_error
        self.attempts: list[dict[str, Any]] = []

    def snapshot_raw(self, parsed: dict[str, Any]) -> dict[str, Any] | None:
        """Snapshot the planner's JSON before normalization can change it."""
        if not self.enabled:
            return None
        return planner_decision_snapshot(parsed, registry=self.registry)

    def record_plan(
        self,
        label: str,
        response: Any,
        raw_snapshot: dict[str, Any] | None,
        plan: dict[str, Any],
        errors: list[str],
    ) -> None:
        if not self.enabled:
            return
        self.attempts.append({
            "label": label,
            "response": self._describe_response(response),
            "raw": raw_snapshot,
            "normalized": planner_decision_snapshot(plan, errors=errors, registry=self.registry),
        })

    def record_failure(self, stage: str, exc: Exception, response: Any = None) -> None:
        """Record a failed attempt; the reply's size and finish reason, never its text."""
        if not self.enabled:
            return
        failure: dict[str, Any] = {
            "label": "failure",
            "stage": stage,
            "error": self._describe_error(exc),
        }
        if response is not None:
            failure["response"] = self._describe_response(response)
        self.attempts.append(failure)

    def attach(
        self,
        result: dict[str, Any],
        *,
        final_plan: Any,
        final_errors: Any = None,
        cache_hit: bool = False,
    ) -> dict[str, Any]:
        if self.enabled:
            result["planner_diagnostics"] = build_planner_diagnostics(
                self.attempts,
                final_plan,
                prompt_version=self.prompt_version,
                final_errors=final_errors,
                cache_hit=cache_hit,
                registry=self.registry,
            )
        return result
