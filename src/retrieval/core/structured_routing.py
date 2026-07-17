from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from src.common.cohort import normalize_cohort


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY_PATH = ROOT / "configs" / "structured_lookup_registry.yaml"
ALLOWED_ROUTES = {"structured", "rag", "clarify", "out_of_domain"}
ALLOWED_EXECUTION_MODES = {"structured", "regulation", "mixed"}
LEGACY_STRUCTURED_ROUTES = {"deterministic"}
LEGACY_STRUCTURED_MODES = {"direct_lookup", "structured_reasoning"}
REGULATION_TABLE_LOOKUPS = {
    "foreign_language",
    "study_duration",
    "scholarship_classification",
    "scoring",
}
COHORT_SCOPED_LOOKUPS = {
    "foreign_language",
    "study_duration",
    "scholarship_classification",
    "scoring",
    "student_service",
    "office",
    "faculty",
    "program",
    "form",
    "formula",
}
UNGROUNDED_SCHEMA_SLOTS = {
    "action",
    "formula_type",
    "operation",
    "requested_field",
    "scope",
    "source_scale",
    "target_scale",
}


def _normalize_text(value: Any) -> str:
    text = str(value or "").lower().replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = re.sub(r"[^a-z0-9+.,]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _query_mentions_cohort(query: str) -> bool:
    normalized = _normalize_text(query)
    return bool(re.search(r"\bk\s*(?:48|49|50|51)\b", normalized))


@lru_cache(maxsize=4)
def load_lookup_registry(path: str | Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    tools = data.get("tools")
    if not isinstance(tools, dict) or not tools:
        raise ValueError("Structured lookup registry must define at least one tool.")
    return data


def compact_registry_for_prompt(registry: dict[str, Any] | None = None) -> str:
    registry = registry or load_lookup_registry()
    lines: list[str] = []
    for name, spec in registry["tools"].items():
        intents = ",".join(spec.get("intents") or [])
        required = spec.get("required_slots") or {}
        contract = {
            "required_slots": required,
            "slot_schema": spec.get("slot_schema") or {},
            "operand_requirements": spec.get("operand_requirements") or {},
        }
        lines.append(
            "|".join(
                (
                    name,
                    intents,
                    json.dumps(contract, ensure_ascii=True, separators=(",", ":")),
                    str(spec.get("description") or ""),
                )
            )
        )
    return "\n".join(lines)


def router_json_schema() -> dict[str, Any]:
    return {
        "route": "structured|rag|clarify|out_of_domain",
        "execution_mode": "structured|regulation|mixed",
        "intent": "intent name",
        "lookup_type": "tool name or null",
        "cohort": "K48-K49|K50|K51|null",
        "slots": {},
        "slot_spans": {},
        "retrieval_query": "standalone Vietnamese search query",
        "target_chunk_types": [],
        "needs_clarification": False,
        "clarification_question": None,
    }


def normalize_router_decision(
    payload: dict[str, Any],
    *,
    query: str,
    selected_cohort: str | None = None,
) -> dict[str, Any]:
    raw_route = str(payload.get("route") or "rag").strip().lower()
    raw_execution_mode = str(payload.get("execution_mode") or "").strip().lower()
    if raw_route in LEGACY_STRUCTURED_ROUTES or raw_execution_mode in LEGACY_STRUCTURED_MODES:
        route = "structured"
        execution_mode = "structured"
    elif raw_route == "structured":
        route = "structured"
        execution_mode = "structured"
    elif raw_route in ALLOWED_ROUTES:
        route = raw_route
        if raw_execution_mode in ALLOWED_EXECUTION_MODES:
            execution_mode = raw_execution_mode
        elif route == "rag" and payload.get("lookup_type"):
            execution_mode = "mixed"
        else:
            execution_mode = "regulation"
    else:
        route = raw_route
        execution_mode = raw_execution_mode or "regulation"

    if route == "rag" and execution_mode == "structured":
        route = "structured"
    elif route == "structured":
        execution_mode = "structured"
    elif raw_execution_mode in ALLOWED_EXECUTION_MODES:
        execution_mode = raw_execution_mode
    elif route == "rag" and payload.get("lookup_type"):
        execution_mode = "mixed"
    else:
        execution_mode = "regulation"
    intent = str(payload.get("intent") or "open_question").strip().lower()
    lookup_type = payload.get("lookup_type")
    if lookup_type is not None:
        lookup_type = str(lookup_type).strip().lower() or None

    slots = payload.get("slots") if isinstance(payload.get("slots"), dict) else {}
    spans = (
        payload.get("slot_spans")
        if isinstance(payload.get("slot_spans"), dict)
        else {}
    )
    for slot_name, slot_value in slots.items():
        if not isinstance(slot_value, dict) or isinstance(spans.get(slot_name), dict):
            continue
        nested_spans = {
            key: spans[key]
            for key in slot_value
            if key in spans and _is_present(spans[key])
        }
        if nested_spans:
            spans[slot_name] = nested_spans

    spec = load_lookup_registry()["tools"].get(lookup_type) if lookup_type else None
    allowed_intents = list((spec or {}).get("intents") or [])
    if route == "structured" and intent not in allowed_intents:
        default_intent = (spec or {}).get("default_intent")
        if default_intent in allowed_intents:
            intent = str(default_intent)
        elif len(allowed_intents) == 1:
            intent = allowed_intents[0]
    target_types = payload.get("target_chunk_types")
    if not isinstance(target_types, list):
        target_types = []

    payload_cohort = normalize_cohort(payload.get("cohort"))
    selected = normalize_cohort(selected_cohort)
    cohort = selected or payload_cohort

    retrieval_query = str(payload.get("retrieval_query") or query).strip()
    if not retrieval_query or len(retrieval_query) > 600:
        retrieval_query = query.strip()

    return {
        "route": route,
        "execution_mode": execution_mode,
        "intent": intent,
        "lookup_type": lookup_type,
        "cohort": cohort,
        "router_cohort": payload_cohort,
        "slots": slots,
        "slot_spans": spans,
        "retrieval_query": retrieval_query,
        "target_chunk_types": [str(item) for item in target_types if item],
        "needs_clarification": bool(payload.get("needs_clarification")),
        "clarification_question": payload.get("clarification_question"),
    }


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict | list | tuple | set):
        return bool(value)
    return True


def _span_is_grounded(span: Any, source_text: str) -> bool:
    if isinstance(span, dict):
        return bool(span) and all(_span_is_grounded(value, source_text) for value in span.values())
    if isinstance(span, list):
        return bool(span) and all(_span_is_grounded(value, source_text) for value in span)
    normalized = _normalize_text(span)
    return bool(normalized) and normalized in _normalize_text(source_text)


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str) and bool(value.strip())
    if expected == "number":
        return isinstance(value, int | float) and not isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    return True


def _validate_slot_contract(
    slots: dict[str, Any], spec: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    for slot_name, schema in (spec.get("slot_schema") or {}).items():
        if slot_name not in slots:
            continue
        value = slots[slot_name]
        if not _is_present(value):
            continue
        expected_types = schema.get("type") or []
        if isinstance(expected_types, str):
            expected_types = [expected_types]
        if expected_types and not any(
            _matches_type(value, expected) for expected in expected_types
        ):
            errors.append(f"invalid_slot_type:{slot_name}")
            continue
        allowed = schema.get("enum") or []
        if allowed and value not in allowed:
            errors.append(f"invalid_slot_value:{slot_name}")

    return errors


def validate_router_decision(
    decision: dict[str, Any],
    *,
    query: str,
    selected_cohort: str | None = None,
    grounding_context: str = "",
    registry: dict[str, Any] | None = None,
) -> list[str]:
    registry = registry or load_lookup_registry()
    errors: list[str] = []
    route = decision.get("route")
    if route not in ALLOWED_ROUTES:
        errors.append("invalid_route")
        return errors

    selected = normalize_cohort(selected_cohort)
    router_cohort = normalize_cohort(decision.get("router_cohort"))
    if selected and router_cohort and selected != router_cohort:
        errors.append("cohort_conflict")

    execution_mode = decision.get("execution_mode")
    if execution_mode not in ALLOWED_EXECUTION_MODES:
        errors.append("invalid_execution_mode")
        return errors
    if route == "structured" and execution_mode != "structured":
        errors.append("structured_requires_structured_mode")
    if route == "rag" and execution_mode == "structured":
        errors.append("rag_cannot_use_structured_mode")

    if route not in {"structured", "rag"}:
        if route == "clarify" and not decision.get("clarification_question"):
            errors.append("missing_clarification_question")
        return errors

    if execution_mode == "regulation":
        if decision.get("lookup_type"):
            errors.append("regulation_must_not_select_lookup")
        return errors

    if route == "structured" and execution_mode != "structured":
        return errors
    if route == "rag" and execution_mode != "mixed":
        errors.append("rag_lookup_requires_mixed_mode")

    lookup_type = decision.get("lookup_type")
    spec = registry["tools"].get(lookup_type)
    if not spec:
        errors.append("unknown_lookup_type")
        return errors
    if (
        execution_mode == "structured"
        and lookup_type in COHORT_SCOPED_LOOKUPS
        and not normalize_cohort(decision.get("cohort"))
        and not _query_mentions_cohort(query)
    ):
        errors.append("missing_cohort")

    intent = decision.get("intent")
    allowed_intents = set(spec.get("intents") or [])
    if route == "structured" and intent not in allowed_intents:
        errors.append("unsupported_intent")

    slots = decision.get("slots") or {}
    spans = decision.get("slot_spans") or {}
    contract_intent = (
        intent if intent in allowed_intents else spec.get("default_intent")
    )
    required = (
        []
        if lookup_type in REGULATION_TABLE_LOOKUPS
        else (spec.get("required_slots") or {}).get(contract_intent, [])
    )
    source_text = f"{query}\n{grounding_context}".strip()
    for slot_name in required:
        if not _is_present(slots.get(slot_name)):
            errors.append(f"missing_slot:{slot_name}")
            continue
        if slot_name in UNGROUNDED_SCHEMA_SLOTS:
            continue
        if not _is_present(spans.get(slot_name)):
            errors.append(f"missing_slot_span:{slot_name}")
        elif not _span_is_grounded(spans[slot_name], source_text):
            errors.append(f"ungrounded_slot:{slot_name}")

    for slot_name, span in spans.items():
        if slot_name in required or slot_name in UNGROUNDED_SCHEMA_SLOTS:
            continue
        if _is_present(span) and not _span_is_grounded(span, source_text):
            errors.append(f"ungrounded_slot:{slot_name}")

    errors.extend(_validate_slot_contract(slots, spec))

    return errors


def fallback_to_rag(
    decision: dict[str, Any], errors: list[str], *, query: str
) -> dict[str, Any]:
    lookup_type = decision.get("lookup_type")
    office_scope = lookup_type in {"office", "student_service"}
    faculty_scope = lookup_type == "faculty"
    rejected_decision = {
        "route": decision.get("route"),
        "execution_mode": decision.get("execution_mode"),
        "intent": decision.get("intent"),
        "lookup_type": decision.get("lookup_type"),
        "slots": decision.get("slots") or {},
        "slot_spans": decision.get("slot_spans") or {},
    }
    return {
        **decision,
        "route": "rag",
        "execution_mode": "regulation",
        "intent": "open_question",
        "lookup_type": None,
        "slots": {},
        "slot_spans": {},
        "retrieval_query": decision.get("retrieval_query") or query,
        "target_chunk_types": (
            ["office_directory"]
            if office_scope
            else ["faculty_program_directory"]
            if faculty_scope
            else ["regulation"]
        ),
        "content_types": (
            ["student_service_directory", "student_office_profile"]
            if office_scope
            else ["student_faculty_profile", "faculty_program_directory"]
            if faculty_scope
            else []
        ),
        "router_validation_errors": list(errors),
        "router_rejected_decision": rejected_decision,
        "router_fallback": "invalid_structured_decision_to_rag",
    }


def decision_to_legacy_routing(
    decision: dict[str, Any], registry: dict[str, Any] | None = None
) -> dict[str, Any]:
    registry = registry or load_lookup_registry()
    route = decision["route"]
    if route == "clarify":
        return {
            "intent": "needs_clarification",
            "strategy": "none",
            "target_chunk_types": [],
            "needs_clarification": True,
            "clarification_question": decision.get("clarification_question"),
        }
    if route == "out_of_domain":
        return {
            "intent": "out_of_domain",
            "strategy": "none",
            "target_chunk_types": [],
        }
    if route == "structured":
        spec = registry["tools"][decision["lookup_type"]]
        return {
            "intent": str(
                spec.get("response_intent") or f"{decision['lookup_type']}_query"
            ),
            "strategy": "structured_json",
            "target_chunk_types": [],
            "lookup_type": decision["lookup_type"],
            "slots": decision.get("slots") or {},
            "execution_mode": "structured",
        }

    execution_mode = decision.get("execution_mode") or "regulation"
    intent = decision.get("intent") or "open_question"
    configured_types = (registry.get("rag_intents") or {}).get(intent)
    target_types = decision.get("target_chunk_types") or configured_types or ["regulation"]
    legacy_intent = "regulation_query"
    strategy = "semantic_filtered"
    if len(target_types) > 1:
        legacy_intent = "mixed_query"
        strategy = "semantic_multi_filter"
    return {
        "intent": legacy_intent,
        "strategy": strategy,
        "target_chunk_types": list(target_types),
        "content_types": list(decision.get("content_types") or []),
        "execution_mode": execution_mode,
        "lookup_type": decision.get("lookup_type"),
        "slots": decision.get("slots") or {},
    }


def registry_digest(registry: dict[str, Any] | None = None) -> str:
    registry = registry or load_lookup_registry()
    return json.dumps(registry, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
