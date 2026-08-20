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
ENTITY_REGISTRY_PATH = ROOT / "data" / "processed" / "entities" / "entity_registry.json"
OFFICE_ALIASES_PATH = ROOT / "configs" / "office_aliases.yaml"
ALLOWED_ROUTES = {"structured", "rag", "clarify", "out_of_domain"}
ALLOWED_EXECUTION_MODES = {"structured", "regulation", "mixed"}
ALLOWED_CONTEXT_MODES = {"standalone", "follow_up", "ambiguous"}
ALLOWED_CONFIDENCE_LEVELS = {"high", "medium", "low", "none"}
ALLOWED_REQUEST_KINDS = {"structured", "rag"}
MAX_LOOKUP_REQUESTS = 6
PLANNER_CONTRACT_VERSION = "single-cohort-v2"
LEGACY_STRUCTURED_ROUTES = {"deterministic"}
LEGACY_STRUCTURED_MODES = {"direct_lookup", "structured_reasoning"}
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


def _normalized_with_offsets(value: Any) -> tuple[str, list[int], list[int]]:
    text = str(value or "")
    normalized_chars: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    pending_space = False
    pending_space_start = 0
    for index, char in enumerate(text):
        folded = char.lower().replace("đ", "d")
        folded = unicodedata.normalize("NFD", folded)
        folded = "".join(
            item for item in folded if unicodedata.category(item) != "Mn"
        )
        if folded and all(item.isalnum() or item in "+.," for item in folded):
            if pending_space and normalized_chars:
                normalized_chars.append(" ")
                starts.append(pending_space_start)
                ends.append(index)
            pending_space = False
            for item in folded:
                normalized_chars.append(item)
                starts.append(index)
                ends.append(index + 1)
        elif normalized_chars:
            pending_space = True
            pending_space_start = index
    return "".join(normalized_chars), starts, ends


def _recover_grounded_span(span: Any, source_text: str) -> str | None:
    requested = _normalize_text(span)
    if not requested:
        return None
    normalized, starts, ends = _normalized_with_offsets(source_text)
    position = normalized.find(requested)
    if position < 0:
        return None
    end_position = position + len(requested) - 1
    if end_position >= len(starts):
        return None
    return source_text[starts[position] : ends[end_position]].strip()


def _query_mentions_cohort(query: str) -> bool:
    normalized = _normalize_text(query)
    return bool(re.search(r"\bk\s*(?:48|49|50|51)\b", normalized))


def _explicit_cohorts(query: str) -> list[str]:
    """Extract cohort references from user-grounded text in appearance order."""
    normalized = _normalize_text(query)
    values: list[str] = []
    for match in re.finditer(r"\bk\s*(48|49|50|51)\b", normalized):
        value = "K48-K49" if match.group(1) in {"48", "49"} else f"K{match.group(1)}"
        if value not in values:
            values.append(value)
    return values


def _cohort_is_grounded(cohort: str, source_text: str) -> bool:
    normalized_cohort = _normalize_text(cohort)
    normalized_source = _normalize_text(source_text)
    return bool(normalized_cohort and normalized_cohort in normalized_source)


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
        default_intent = spec.get("default_intent") or ""
        required = spec.get("required_slots") or {}
        slot_contract: dict[str, Any] = {}
        for slot_name, slot_spec in (spec.get("slot_schema") or {}).items():
            compact_spec: dict[str, Any] = {}
            allowed_values = (
                slot_spec.get("enum") or slot_spec.get("canonical_values") or []
            )
            if allowed_values:
                compact_spec["values"] = allowed_values
            slot_contract[slot_name] = compact_spec
        fields = [
            name,
            f"use={spec.get('description') or ''}",
            f"intents={intents}",
        ]
        if default_intent:
            fields.append(f"default={default_intent}")
        fields.extend(
            [
                "required="
                + json.dumps(required, ensure_ascii=True, separators=(",", ":")),
                "slots="
                + json.dumps(
                    slot_contract, ensure_ascii=True, separators=(",", ":")
                ),
            ]
        )
        lines.append("|".join(fields))
    rag_intents = ",".join(sorted((registry.get("rag_intents") or {}).keys()))
    lines.append(f"RAG_INTENTS|{rag_intents}")
    return "\n".join(lines)


def _normalize_request_cohorts(
    value: Any,
    *,
    default_cohorts: list[str],
) -> list[str]:
    raw_values = value if isinstance(value, list) else []
    cohorts: list[str] = []
    for item in raw_values:
        normalized = normalize_cohort(item)
        raw_value = str(item or "").strip()
        if normalized:
            cohorts.append(normalized)
        elif raw_value:
            cohorts.append(raw_value)
    return list(dict.fromkeys(cohorts or default_cohorts))


def _normalize_lookup_request(
    value: Any,
    *,
    query: str,
    default_cohorts: list[str],
    registry: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {
            "request_kind": "",
            "lookup_type": None,
            "intent": "",
            "query_span": "",
            "slots": {},
            "slot_spans": {},
            "cohort_refs": [],
            "invalid_request_payload": True,
        }

    lookup_type = str(value.get("lookup_type") or "").strip().lower() or None
    request_kind = str(value.get("request_kind") or "").strip().lower()
    if not request_kind:
        request_kind = "structured" if lookup_type else "rag"
    intent = str(value.get("intent") or "").strip().lower()
    spec = registry.get("tools", {}).get(lookup_type) if lookup_type else None
    allowed_intents = list((spec or {}).get("intents") or [])
    if request_kind == "structured" and not intent:
        default_intent = (spec or {}).get("default_intent")
        if default_intent in allowed_intents:
            intent = str(default_intent)
        elif len(allowed_intents) == 1:
            intent = str(allowed_intents[0])
    elif request_kind == "rag" and not intent:
        intent = "open_question"

    raw_span = str(value.get("query_span") or "").strip()
    query_span = _recover_grounded_span(raw_span, query) or raw_span
    slots = dict(value.get("slots")) if isinstance(value.get("slots"), dict) else {}
    slots = _canonicalize_slots(slots, spec or {})
    spans = (
        dict(value.get("slot_spans"))
        if isinstance(value.get("slot_spans"), dict)
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

    normalized_request = {
        "request_kind": request_kind,
        "lookup_type": lookup_type,
        "intent": intent,
        "query_span": query_span,
        "slots": slots,
        "slot_spans": spans,
        "cohort_refs": _normalize_request_cohorts(
            value.get("cohort_refs"),
            default_cohorts=default_cohorts,
        ),
    }
    if "cohort_refs" in value and not isinstance(value.get("cohort_refs"), list):
        normalized_request["invalid_cohort_refs_payload"] = True
    return normalized_request


def _legacy_lookup_requests(
    *,
    route: str,
    execution_mode: str,
    intent: str,
    lookup_type: str | None,
    query: str,
    slots: dict[str, Any],
    spans: dict[str, Any],
    cohorts: list[str],
    registry: dict[str, Any],
) -> list[dict[str, Any]]:
    if route not in {"structured", "rag"}:
        return []
    request_kind = "structured" if lookup_type else "rag"
    request_intent = intent
    if request_kind == "rag" and request_intent not in registry.get("rag_intents", {}):
        request_intent = "open_question"
    return [
        {
            "request_kind": request_kind,
            "lookup_type": lookup_type,
            "intent": request_intent,
            "query_span": query.strip(),
            "slots": slots if request_kind == "structured" else {},
            "slot_spans": spans if request_kind == "structured" else {},
            "cohort_refs": cohorts,
            "legacy_execution_mode": execution_mode,
        }
    ]


def router_json_schema() -> dict[str, Any]:
    registry = load_lookup_registry()
    tools = list(registry.get("tools", {}).keys())
    lookup_type_enum = "|".join(tools) + "|null" if tools else "tool name or null"
    return {
        "context_mode": "standalone|follow_up|ambiguous",
        "context_confidence": "high|medium|low|none",
        "normalized_query": "orthographic correction only or original query",
        "normalization_confidence": "high|medium|low|none",
        "corrections": [
            {
                "original_span": "exact span from QUERY",
                "normalized_span": "corrected spelling",
            }
        ],
        "standalone_query": "history-grounded query for follow_up or null",
        "referenced_turn_ids": [],
        "referenced_evidence": [
            {"turn_id": 0, "evidence_span": "exact span from referenced turn"}
        ],
        "outcome": "execute|clarify|out_of_domain",
        "cohort": "K48-K49|K50|K51|null",
        "cohorts": ["K48-K49", "K50", "K51"],
        "is_multi_cohort": False,
        "lookup_requests": [
            {
                "request_kind": "structured|rag",
                "lookup_type": lookup_type_enum,
                "intent": "tool intent or rag intent",
                "query_span": "smallest contiguous verbatim topic span from QUERY",
                "slots": {},
                "slot_spans": {},
                "cohort_refs": [],
            }
        ],
        "clarification_question": None,
    }


def router_response_schema() -> dict[str, Any]:
    """JSON Schema used by providers that support structured output."""

    tools = list(load_lookup_registry().get("tools", {}).keys())
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "context_mode": {
                "type": "string",
                "enum": ["standalone", "follow_up", "ambiguous"],
            },
            "context_confidence": {
                "type": "string",
                "enum": ["high", "medium", "low", "none"],
            },
            "normalized_query": {"type": ["string", "null"]},
            "normalization_confidence": {
                "type": "string",
                "enum": ["high", "medium", "low", "none"],
            },
            "corrections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "original_span": {"type": "string"},
                        "normalized_span": {"type": "string"},
                    },
                    "required": ["original_span", "normalized_span"],
                },
            },
            "standalone_query": {"type": ["string", "null"]},
            "referenced_turn_ids": {
                "type": "array",
                "items": {"type": "integer"},
            },
            "referenced_evidence": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "turn_id": {"type": "integer"},
                        "evidence_span": {"type": "string"},
                    },
                    "required": ["turn_id", "evidence_span"],
                },
            },
            "outcome": {
                "type": "string",
                "enum": ["execute", "clarify", "out_of_domain"],
            },
            "route": {"type": ["string", "null"]},
            "cohort": {
                "anyOf": [
                    {"type": "string", "enum": ["K48-K49", "K50", "K51"]},
                    {"type": "null"},
                ]
            },
            "cohorts": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": ["K48-K49", "K50", "K51"],
                },
            },
            "is_multi_cohort": {"type": ["boolean", "null"]},
            "lookup_requests": {
                "type": "array",
                "maxItems": MAX_LOOKUP_REQUESTS,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "request_kind": {
                            "type": "string",
                            "enum": sorted(ALLOWED_REQUEST_KINDS),
                        },
                        "lookup_type": {
                            "anyOf": [
                                {"type": "string", "enum": tools},
                                {"type": "null"},
                            ]
                        },
                        "intent": {"type": "string"},
                        "query_span": {"type": "string"},
                        "slots": {
                            "type": "object",
                            "additionalProperties": True,
                        },
                        "slot_spans": {
                            "type": "object",
                            "additionalProperties": True,
                        },
                        "cohort_refs": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": ["K48-K49", "K50", "K51"],
                            },
                        },
                    },
                    "required": [
                        "request_kind",
                        "lookup_type",
                        "intent",
                        "query_span",
                        "slots",
                        "slot_spans",
                        "cohort_refs",
                    ],
                },
            },
            "clarification_question": {"type": ["string", "null"]},
        },
        "required": [
            "context_mode",
            "context_confidence",
            "normalized_query",
            "normalization_confidence",
            "corrections",
            "standalone_query",
            "referenced_turn_ids",
            "referenced_evidence",
            "outcome",
            "cohort",
            "cohorts",
            "is_multi_cohort",
            "lookup_requests",
            "clarification_question",
        ],
    }


def normalize_router_decision(
    payload: dict[str, Any],
    *,
    query: str,
    selected_cohort: str | None = None,
) -> dict[str, Any]:
    raw_outcome = str(payload.get("outcome") or "").strip().lower()
    raw_route = str(payload.get("route") or "rag").strip().lower()
    if raw_outcome == "execute":
        raw_route = raw_route if raw_route in {"structured", "rag"} else "rag"
    elif raw_outcome in {"clarify", "out_of_domain"}:
        raw_route = raw_outcome
    raw_execution_mode = str(payload.get("execution_mode") or "").strip().lower()
    legacy_structured = (
        raw_route in LEGACY_STRUCTURED_ROUTES
        or raw_execution_mode in LEGACY_STRUCTURED_MODES
    )
    intent = str(payload.get("intent") or "open_question").strip().lower()
    lookup_type = payload.get("lookup_type")
    if lookup_type is not None:
        lookup_type = str(lookup_type).strip().lower() or None

    slots = (
        dict(payload.get("slots"))
        if isinstance(payload.get("slots"), dict)
        else {}
    )
    spans = (
        dict(payload.get("slot_spans"))
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

    raw_cohorts = payload.get("cohorts")
    if isinstance(raw_cohorts, list):
        payload_cohorts = [normalize_cohort(c) for c in raw_cohorts if normalize_cohort(c)]
    else:
        payload_cohorts = []
    payload_cohort = normalize_cohort(payload.get("cohort"))
    if payload_cohort and payload_cohort not in payload_cohorts:
        payload_cohorts.insert(0, payload_cohort)
    payload_cohorts = list(dict.fromkeys(payload_cohorts))

    explicit_cohorts = _explicit_cohorts(query)
    selected = normalize_cohort(selected_cohort)
    if len(explicit_cohorts) >= 2:
        cohorts = explicit_cohorts
        cohort = explicit_cohorts[0]
        is_multi_cohort = True
    elif explicit_cohorts:
        cohorts = explicit_cohorts
        cohort = explicit_cohorts[0]
        is_multi_cohort = False
    else:
        cohort = selected
        cohorts = [cohort] if cohort else []
        is_multi_cohort = False

    registry = load_lookup_registry()
    explicit_requests = "lookup_requests" in payload
    if explicit_requests:
        raw_requests = payload.get("lookup_requests")
        values = raw_requests if isinstance(raw_requests, list) else []
        lookup_requests = [
            _normalize_lookup_request(
                value,
                query=query,
                default_cohorts=cohorts,
                registry=registry,
            )
            for value in values
        ]
    else:
        if legacy_structured:
            raw_route = "structured"
        if raw_route == "structured":
            raw_execution_mode = "structured"
        elif raw_route == "rag" and lookup_type:
            raw_execution_mode = "mixed"
        elif raw_route == "rag":
            raw_execution_mode = "regulation"
        lookup_requests = [
            _normalize_lookup_request(
                value,
                query=query,
                default_cohorts=cohorts,
                registry=registry,
            )
            for value in _legacy_lookup_requests(
                route=raw_route,
                execution_mode=raw_execution_mode,
                intent=intent,
                lookup_type=lookup_type,
                query=query,
                slots=slots,
                spans=spans,
                cohorts=cohorts,
                registry=registry,
            )
        ]

    if len(lookup_requests) >= 2:
        grounded_requests = [
            req
            for req in lookup_requests
            if req.get("request_kind") != "structured"
            or _is_grounded_structured_request(req, registry)
        ]
        if grounded_requests:
            lookup_requests = grounded_requests

    structured_requests = [
        request
        for request in lookup_requests
        if request.get("request_kind") == "structured"
    ]
    rag_requests = [
        request for request in lookup_requests if request.get("request_kind") == "rag"
    ]
    if raw_route in {"clarify", "out_of_domain"} and not lookup_requests:
        route = raw_route
        execution_mode = "regulation"
    elif len(lookup_requests) == 1 and structured_requests:
        route = "structured"
        execution_mode = "structured"
    elif len(lookup_requests) == 1 and rag_requests:
        route = "rag"
        execution_mode = "regulation"
    elif lookup_requests:
        route = "rag"
        execution_mode = "mixed"
    else:
        route = raw_route if raw_route in ALLOWED_ROUTES else "rag"
        execution_mode = "regulation"

    primary_request = structured_requests[0] if structured_requests else (
        lookup_requests[0] if lookup_requests else None
    )
    if len(lookup_requests) > 1:
        intent = "multi_request"
    elif primary_request:
        intent = str(primary_request.get("intent") or intent)
    if primary_request and primary_request.get("request_kind") == "structured":
        lookup_type = primary_request.get("lookup_type")
        slots = dict(primary_request.get("slots") or {})
        spans = dict(primary_request.get("slot_spans") or {})
    elif not primary_request:
        lookup_type = None
        slots = {}
        spans = {}

    target_types = sorted(
        {
            target
            for request in lookup_requests
            for target in (
                registry.get("tools", {})
                .get(request.get("lookup_type"), {})
                .get("target_chunk_types", [])
                if request.get("request_kind") == "structured"
                else ["regulation"]
            )
        }
    )

    raw_context_mode = str(payload.get("context_mode") or "standalone").strip().lower()
    context_mode = (
        raw_context_mode if raw_context_mode in ALLOWED_CONTEXT_MODES else "ambiguous"
    )
    raw_context_confidence = (
        str(payload.get("context_confidence") or "none").strip().lower()
    )
    context_confidence = (
        raw_context_confidence
        if raw_context_confidence in ALLOWED_CONFIDENCE_LEVELS
        else "none"
    )
    raw_normalization_confidence = (
        str(payload.get("normalization_confidence") or "none").strip().lower()
    )
    normalization_confidence = (
        raw_normalization_confidence
        if raw_normalization_confidence in ALLOWED_CONFIDENCE_LEVELS
        else "none"
    )
    normalized_query = str(payload.get("normalized_query") or query).strip()
    if not normalized_query or len(normalized_query) > 600:
        normalized_query = query.strip()
    standalone_query = str(payload.get("standalone_query") or "").strip() or None
    if standalone_query and len(standalone_query) > 600:
        standalone_query = None
    corrections = payload.get("corrections")
    if not isinstance(corrections, list):
        corrections = []
    referenced_turns = payload.get("referenced_turn_ids")
    if not isinstance(referenced_turns, list):
        referenced_turns = payload.get("referenced_turns")
    if not isinstance(referenced_turns, list):
        referenced_turns = []
    referenced_evidence = payload.get("referenced_evidence")
    if not isinstance(referenced_evidence, list):
        referenced_evidence = []

    return {
        "plan_version": PLANNER_CONTRACT_VERSION,
        "outcome": (
            "execute" if route in {"structured", "rag"} else route
        ),
        "context_mode": context_mode,
        "context_confidence": context_confidence,
        "normalized_query": normalized_query,
        "normalization_confidence": normalization_confidence,
        "corrections": [
            {
                "original_span": str(item.get("original_span") or "").strip(),
                "normalized_span": str(item.get("normalized_span") or "").strip(),
            }
            for item in corrections
            if isinstance(item, dict)
            and str(item.get("original_span") or "").strip()
            and str(item.get("normalized_span") or "").strip()
        ],
        "standalone_query": standalone_query,
        "referenced_turn_ids": [
            int(item)
            for item in referenced_turns
            if isinstance(item, int) and not isinstance(item, bool) and item >= 0
        ],
        "referenced_turns": [
            int(item)
            for item in referenced_turns
            if isinstance(item, int) and not isinstance(item, bool) and item >= 0
        ],
        "referenced_evidence": [
            {
                "turn_id": int(item.get("turn_id")),
                "evidence_span": str(item.get("evidence_span") or "").strip(),
            }
            for item in referenced_evidence
            if isinstance(item, dict)
            and isinstance(item.get("turn_id"), int)
            and not isinstance(item.get("turn_id"), bool)
            and int(item.get("turn_id")) >= 0
            and str(item.get("evidence_span") or "").strip()
        ],
        "route": route,
        "execution_mode": execution_mode,
        "intent": intent,
        "lookup_type": lookup_type,
        "cohort": cohort,
        "cohorts": cohorts,
        "is_multi_cohort": is_multi_cohort,
        "router_cohort": payload_cohort,
        "slots": slots,
        "slot_spans": spans,
        "target_chunk_types": [str(item) for item in target_types if item],
        "lookup_requests": lookup_requests,
        "request_plan_provided": explicit_requests,
        "needs_clarification": route == "clarify"
        or bool(payload.get("needs_clarification")),
        "clarification_question": payload.get("clarification_question"),
    }


def bind_effective_cohort(
    decision: dict[str, Any],
    *,
    raw_query: str,
    effective_query: str,
    selected_cohort: str | None,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind one cohort from grounded sources using the declared priority order."""
    registry = registry or load_lookup_registry()
    raw_cohorts = _explicit_cohorts(raw_query)
    selected = normalize_cohort(selected_cohort)
    history_cohorts = _explicit_cohorts(effective_query)

    if raw_cohorts:
        grounded_cohorts = raw_cohorts
        source = "raw_query"
    elif selected:
        grounded_cohorts = [selected]
        source = "selected_cohort"
    else:
        grounded_cohorts = history_cohorts
        source = "grounded_history" if history_cohorts else "unresolved"

    is_multi = len(grounded_cohorts) > 1
    effective_cohort = grounded_cohorts[0] if len(grounded_cohorts) == 1 else None
    bound_requests: list[Any] = []
    for request in decision.get("lookup_requests") or []:
        if not isinstance(request, dict):
            bound_requests.append(request)
            continue
        bound_request = dict(request)
        refs = list(bound_request.get("cohort_refs") or [])
        lookup_type = bound_request.get("lookup_type")
        spec = registry.get("tools", {}).get(lookup_type) if lookup_type else None
        requires_cohort = (
            bool(registry.get("rag_cohort_sensitive", True))
            if bound_request.get("request_kind") == "rag"
            else bool((spec or {}).get("cohort_sensitive"))
        )
        if requires_cohort and not refs and effective_cohort:
            bound_request["cohort_refs"] = [effective_cohort]
        bound_requests.append(bound_request)

    bound_decision = {
        **decision,
        "cohort": effective_cohort,
        "cohorts": grounded_cohorts,
        "is_multi_cohort": is_multi,
        "effective_cohort_source": source,
    }
    if "lookup_requests" in decision:
        bound_decision["lookup_requests"] = bound_requests
    return bound_decision


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict | list | tuple | set):
        return bool(value)
    return True


def _span_is_grounded(span: Any, source_text: str) -> bool:
    if isinstance(span, dict) and set(span) == {"start", "end"}:
        start = span.get("start")
        end = span.get("end")
        return bool(
            isinstance(start, int)
            and not isinstance(start, bool)
            and isinstance(end, int)
            and not isinstance(end, bool)
            and 0 <= start < end <= len(source_text)
            and source_text[start:end].strip()
        )
    if isinstance(span, dict):
        return bool(span) and all(
            _span_is_grounded(value, source_text) for value in span.values()
        )
    if isinstance(span, list):
        return bool(span) and all(
            _span_is_grounded(value, source_text) for value in span
        )
    normalized = _normalize_text(span)
    return bool(normalized) and normalized in _normalize_text(source_text)


def _normalized_leaf_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [
            normalized
            for item in value.values()
            for normalized in _normalized_leaf_values(item)
        ]
    if isinstance(value, list | tuple | set):
        return [
            normalized
            for item in value
            for normalized in _normalized_leaf_values(item)
        ]
    normalized = _normalize_text(value)
    return [normalized] if normalized else []


def _resolved_span_value(span: Any, source_text: str) -> Any:
    if isinstance(span, dict) and set(span) == {"start", "end"}:
        if not _span_is_grounded(span, source_text):
            return None
        return source_text[int(span["start"]) : int(span["end"])]
    if isinstance(span, dict):
        return {
            key: _resolved_span_value(item, source_text)
            for key, item in span.items()
        }
    if isinstance(span, list):
        return [_resolved_span_value(item, source_text) for item in span]
    return span


def _slot_value_matches_span(
    value: Any,
    span: Any,
    source_text: str,
    schema: dict[str, Any],
    corrections: list[dict[str, Any]] | None = None,
) -> bool:
    values = _normalized_leaf_values(value)
    resolved_span = _resolved_span_value(span, source_text)
    spans = _normalized_leaf_values(resolved_span)
    canonical_spans = _normalized_leaf_values(
        _canonicalize_scalar(resolved_span, schema)
    )
    span_values = set(spans)
    corrected_values = [
        correction.get("normalized_span")
        for correction in corrections or []
        if _normalize_text(correction.get("original_span")) in span_values
        and _is_present(correction.get("normalized_span"))
    ]
    canonical_corrections = [
        normalized
        for corrected in corrected_values
        for normalized in _normalized_leaf_values(
            _canonicalize_scalar(corrected, schema)
        )
    ]
    return bool(values and spans) and all(
        any(
            item == source or item in source or source in item
            for source in [*spans, *canonical_spans, *canonical_corrections]
        )
        for item in values
    )


@lru_cache(maxsize=1)
def _slot_alias_index() -> dict[str, dict[str, frozenset[str]]]:
    index: dict[str, dict[str, set[str]]] = {}

    def add(entity_type: str, canonical: Any, aliases: list[Any]) -> None:
        canonical_text = str(canonical or "").strip()
        if not canonical_text:
            return
        namespace = index.setdefault(entity_type, {})
        for alias in [canonical_text, *aliases]:
            normalized = _normalize_text(alias)
            if normalized:
                namespace.setdefault(normalized, set()).add(canonical_text)

    if ENTITY_REGISTRY_PATH.is_file():
        entities = json.loads(ENTITY_REGISTRY_PATH.read_text(encoding="utf-8"))
        for entity in entities if isinstance(entities, list) else []:
            add(
                str(entity.get("entity_type") or ""),
                entity.get("canonical_name"),
                list(entity.get("aliases") or []),
            )
    if OFFICE_ALIASES_PATH.is_file():
        aliases = yaml.safe_load(OFFICE_ALIASES_PATH.read_text(encoding="utf-8")) or {}
        for canonical, values in (aliases.get("unit_aliases") or {}).items():
            entity_type = "faculty" if _normalize_text(canonical).startswith("khoa ") else "office"
            add(entity_type, canonical, list(values or []))
        for service in aliases.get("service_aliases") or []:
            if isinstance(service, dict):
                add("service", service.get("match"), list(service.get("aliases") or []))
        for services in (aliases.get("unit_service_aliases") or {}).values():
            for service in services or []:
                if isinstance(service, dict):
                    add("service", service.get("service"), list(service.get("aliases") or []))
    return {
        entity_type: {
            alias: frozenset(canonical_values)
            for alias, canonical_values in aliases.items()
        }
        for entity_type, aliases in index.items()
    }


def _canonical_alias(value: str, schema: dict[str, Any]) -> str | None:
    normalized = _normalize_text(value)
    candidates: set[str] = set()
    for canonical, aliases in (schema.get("aliases") or {}).items():
        if normalized in {_normalize_text(canonical), *map(_normalize_text, aliases or [])}:
            candidates.add(str(canonical))
    index = _slot_alias_index()
    for entity_type in schema.get("alias_entity_types") or []:
        candidates.update(index.get(str(entity_type), {}).get(normalized, ()))
    return next(iter(candidates)) if len(candidates) == 1 else None


def _canonicalize_scalar(value: Any, schema: dict[str, Any]) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    canonical_values = schema.get("canonical_values") or []
    normalized_value = _normalize_text(stripped)
    for candidate in canonical_values:
        if normalized_value == _normalize_text(candidate):
            return candidate
    alias = _canonical_alias(stripped, schema)
    if alias is not None:
        return alias
    if schema.get("canonical_type") == "number" and re.fullmatch(
        r"[+-]?\d+(?:[.,]\d+)?",
        stripped,
    ):
        number = float(stripped.replace(",", "."))
        return int(number) if number.is_integer() else number
    return value


def _canonicalize_slots(
    slots: dict[str, Any], spec: dict[str, Any]
) -> dict[str, Any]:
    schema = spec.get("slot_schema") or {}
    return {
        name: _canonicalize_scalar(value, schema.get(name) or {})
        for name, value in slots.items()
    }


def _is_grounded_structured_request(
    request: dict[str, Any],
    registry: dict[str, Any],
) -> bool:
    """Check if a structured request's extracted slots map to grounded entities in the registry."""
    if request.get("request_kind") != "structured":
        return True
    lookup_type = request.get("lookup_type")
    spec = registry.get("tools", {}).get(lookup_type)
    if not spec:
        return False
    slots = request.get("slots") or {}
    slot_schema = spec.get("slot_schema") or {}
    alias_idx = _slot_alias_index()
    for slot_name, val in slots.items():
        if not _is_present(val) or slot_name in UNGROUNDED_SCHEMA_SLOTS:
            continue
        schema = slot_schema.get(slot_name) or {}
        canonical_values = [
            _normalize_text(c)
            for c in (schema.get("canonical_values") or schema.get("enum") or [])
        ]
        canonical = _canonicalize_scalar(val, schema)
        val_norm = _normalize_text(val)
        can_norm = _normalize_text(canonical)
        if canonical_values:
            if val_norm in canonical_values or can_norm in canonical_values:
                continue
            return False

        alias_types = schema.get("alias_entity_types") or []
        if alias_types:
            matched = False
            for entity_type in alias_types:
                type_aliases = alias_idx.get(str(entity_type), {})
                if val_norm in type_aliases or (can_norm and can_norm in type_aliases):
                    matched = True
                    break
                if any(
                    (len(k) >= 4 and (k in val_norm or val_norm in k))
                    for k in type_aliases
                ):
                    matched = True
                    break
            if not matched:
                return False
    return True


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "string":
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, list):
            return bool(value) and all(isinstance(v, str) and bool(v.strip()) for v in value)
        return False
    if expected == "number":
        if isinstance(value, int | float) and not isinstance(value, bool):
            return True
        if isinstance(value, list):
            return bool(value) and all(isinstance(v, int | float) and not isinstance(v, bool) for v in value)
        return False
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    return True


def _validate_slot_contract(slots: dict[str, Any], spec: dict[str, Any]) -> list[str]:
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


def _validate_lookup_request(
    request: dict[str, Any],
    *,
    index: int,
    source_text: str,
    selected_cohort: str | None,
    registry: dict[str, Any],
    corrections: list[dict[str, Any]] | None = None,
) -> list[str]:
    prefix = f"request:{index}:"
    errors: list[str] = []
    if request.get("invalid_request_payload"):
        return [f"{prefix}invalid_payload"]

    request_kind = request.get("request_kind")
    if request_kind not in ALLOWED_REQUEST_KINDS:
        return [f"{prefix}invalid_request_kind"]

    query_span = str(request.get("query_span") or "").strip()
    if not query_span:
        errors.append(f"{prefix}missing_query_span")
    elif len(query_span) > 600:
        errors.append(f"{prefix}query_span_too_long")
    elif not _span_is_grounded(query_span, source_text):
        errors.append(f"{prefix}ungrounded_query_span")

    cohort_refs = request.get("cohort_refs") or []
    if request.get("invalid_cohort_refs_payload"):
        errors.append(f"{prefix}invalid_cohort_refs")
    if not isinstance(cohort_refs, list):
        errors.append(f"{prefix}invalid_cohort_refs")
        cohort_refs = []
    normalized_selected = normalize_cohort(selected_cohort)
    for cohort in cohort_refs:
        normalized_cohort = normalize_cohort(cohort)
        if not normalized_cohort:
            errors.append(f"{prefix}invalid_cohort")
        elif normalized_cohort != normalized_selected and not _cohort_is_grounded(
            normalized_cohort,
            source_text,
        ):
            errors.append(f"{prefix}ungrounded_cohort:{normalized_cohort}")

    lookup_type = request.get("lookup_type")
    intent = request.get("intent")
    slots = request.get("slots") or {}
    spans = request.get("slot_spans") or {}
    if not isinstance(slots, dict) or not isinstance(spans, dict):
        errors.append(f"{prefix}invalid_slots")
        return errors

    if request_kind == "rag":
        if lookup_type:
            errors.append(f"{prefix}rag_request_has_lookup_type")
        if intent not in registry.get("rag_intents", {}):
            errors.append(f"{prefix}unsupported_rag_intent")
        if slots or spans:
            errors.append(f"{prefix}rag_request_has_slots")
        if bool(registry.get("rag_cohort_sensitive", True)) and (
            not normalized_selected or not cohort_refs
        ):
            errors.append(f"{prefix}missing_cohort")
        return errors

    spec = registry.get("tools", {}).get(lookup_type)
    if not spec:
        errors.append(f"{prefix}unknown_lookup_type")
        return errors
    if bool(spec.get("cohort_sensitive")) and not cohort_refs:
        errors.append(f"{prefix}missing_cohort")

    allowed_intents = set(spec.get("intents") or [])
    if intent not in allowed_intents:
        errors.append(f"{prefix}unsupported_intent")
    contract_intent = intent if intent in allowed_intents else spec.get("default_intent")
    required = list((spec.get("required_slots") or {}).get(contract_intent, []))
    slot_schema = spec.get("slot_schema") or {}
    for slot_name in slots:
        if slot_name not in slot_schema:
            errors.append(f"{prefix}unknown_slot:{slot_name}")
    for slot_name in spans:
        if slot_name not in slot_schema:
            errors.append(f"{prefix}unknown_slot_span:{slot_name}")

    request_source = query_span
    for slot_name in required:
        if not _is_present(slots.get(slot_name)):
            errors.append(f"{prefix}missing_slot:{slot_name}")

    for slot_name, value in slots.items():
        if not _is_present(value) or slot_name in UNGROUNDED_SCHEMA_SLOTS:
            continue
        span = spans.get(slot_name)
        schema = slot_schema.get(slot_name) or {}
        if not _is_present(span):
            errors.append(f"{prefix}missing_slot_span:{slot_name}")
        elif not _span_is_grounded(span, request_source):
            errors.append(f"{prefix}ungrounded_slot:{slot_name}")
        elif not schema.get("enum") and not (
            _slot_value_matches_span(
                value,
                span,
                request_source,
                schema,
                corrections,
            )
        ):
            errors.append(f"{prefix}slot_value_mismatch:{slot_name}")

    for slot_name, span in spans.items():
        if slot_name in UNGROUNDED_SCHEMA_SLOTS:
            continue
        if _is_present(span) and not _span_is_grounded(span, request_source):
            errors.append(f"{prefix}ungrounded_slot:{slot_name}")

    errors.extend(
        f"{prefix}{error}" for error in _validate_slot_contract(slots, spec)
    )
    return errors


def validate_router_decision(
    decision: dict[str, Any],
    *,
    query: str,
    selected_cohort: str | None = None,
    grounding_context: str = "",
    registry: dict[str, Any] | None = None,
    validated_corrections: list[dict[str, str]] | None = None,
) -> list[str]:
    registry = registry or load_lookup_registry()
    errors: list[str] = []
    route = decision.get("route")
    if route not in ALLOWED_ROUTES:
        errors.append("invalid_route")
        return errors

    selected = normalize_cohort(decision.get("cohort") or selected_cohort)
    router_cohort = normalize_cohort(decision.get("router_cohort"))
    if selected and router_cohort and selected != router_cohort:
        errors.append("cohort_conflict")
    if decision.get("is_multi_cohort") or len(decision.get("cohorts") or []) > 1:
        errors.append("multi_cohort_not_supported")

    execution_mode = decision.get("execution_mode")
    if execution_mode not in ALLOWED_EXECUTION_MODES:
        errors.append("invalid_execution_mode")
        return errors
    if route == "structured" and execution_mode != "structured":
        errors.append("structured_requires_structured_mode")
    if route == "rag" and execution_mode == "structured":
        errors.append("rag_cannot_use_structured_mode")

    lookup_requests = decision.get("lookup_requests")
    if route not in {"structured", "rag"}:
        if route == "clarify" and not decision.get("clarification_question"):
            errors.append("missing_clarification_question")
        if lookup_requests:
            errors.append("non_answer_route_has_requests")
        return errors

    if not isinstance(lookup_requests, list) or not lookup_requests:
        errors.append("missing_lookup_requests")
        return errors
    if len(lookup_requests) > MAX_LOOKUP_REQUESTS:
        errors.append("too_many_lookup_requests")

    request_cohorts = {
        normalized
        for request in lookup_requests
        if isinstance(request, dict)
        for value in request.get("cohort_refs") or []
        if (normalized := normalize_cohort(value))
    }
    if len(request_cohorts) > 1:
        errors.append("multi_cohort_not_supported")
    if selected and any(value != selected for value in request_cohorts):
        errors.append("request_cohort_conflict")

    source_text = " ".join(
        part.strip() for part in (query, grounding_context) if part and part.strip()
    )
    for index, request in enumerate(lookup_requests):
        if not isinstance(request, dict):
            errors.append(f"request:{index}:invalid_payload")
            continue
        errors.extend(
            _validate_lookup_request(
                request,
                index=index,
                source_text=source_text,
                selected_cohort=selected,
                registry=registry,
                corrections=validated_corrections or [],
            )
        )
    return errors


def reject_invalid_plan(
    decision: dict[str, Any],
    errors: list[str],
    *,
    query: str | None = None,
) -> dict[str, Any]:
    rejected_decision = {
        "route": decision.get("route"),
        "execution_mode": decision.get("execution_mode"),
        "intent": decision.get("intent"),
        "lookup_type": decision.get("lookup_type"),
        "slots": decision.get("slots") or {},
        "slot_spans": decision.get("slot_spans") or {},
        "lookup_requests": decision.get("lookup_requests") or [],
    }
    del query
    return {
        **decision,
        "outcome": "clarify",
        "route": "clarify",
        "execution_mode": "regulation",
        "intent": "invalid_plan",
        "lookup_type": None,
        "slots": {},
        "slot_spans": {},
        "lookup_requests": [],
        "target_chunk_types": [],
        "content_types": [],
        "retrieval_query": None,
        "retrieval_executed": False,
        "needs_clarification": True,
        "clarification_question": (
            "Mình chưa xác định được chính xác phần cần tra cứu. "
            "Bạn có thể viết rõ hơn tên nội dung hoặc chương trình cần hỏi không?"
        ),
        "router_validation_errors": list(errors),
        "router_rejected_decision": rejected_decision,
        "router_fallback": "invalid_plan_to_clarify",
    }


def registry_digest(registry: dict[str, Any] | None = None) -> str:
    registry = registry or load_lookup_registry()
    return json.dumps(
        registry, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
