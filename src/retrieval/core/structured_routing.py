from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from src.common.cohort import build_cohort_token_regex, normalize_cohort


ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY_PATH = ROOT / "configs" / "structured_lookup_registry.yaml"
ALLOWED_ROUTES = {"structured", "rag", "clarify", "out_of_domain"}
ALLOWED_EXECUTION_MODES = {"structured", "regulation", "mixed"}
ALLOWED_CONTEXT_MODES = {"standalone", "follow_up", "ambiguous"}
ALLOWED_CONFIDENCE_LEVELS = {"high", "medium", "low", "none"}
COHORT_SCOPED_LOOKUPS = {
    "foreign_language",
    "study_duration",
    "scholarship_classification",
    "scoring",
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
    return bool(build_cohort_token_regex().search(query))


def _literal_query_span(query: str, literal: Any) -> str | None:
    """Return the exact query span for one declared literal alias."""

    normalized_literal = _normalize_text(literal).replace("_", " ")
    if not normalized_literal:
        return None
    tokens = list(re.finditer(r"[\w+.,-]+", str(query or ""), flags=re.UNICODE))
    token_count = len(normalized_literal.split())
    if not tokens or token_count <= 0:
        return None
    for start in range(0, len(tokens) - token_count + 1):
        end = start + token_count - 1
        span = query[tokens[start].start() : tokens[end].end()]
        if _normalize_text(span).replace("_", " ") == normalized_literal:
            return span
    return None


def _ground_declared_literal_slots(
    query: str,
    *,
    intent: str | None,
    spec: dict[str, Any] | None,
    slots: dict[str, Any],
    spans: dict[str, Any],
) -> None:
    """Ground exact slot literals declared by the capability registry."""

    for slot_name, slot_spec in ((spec or {}).get("slot_schema") or {}).items():
        aliases_by_value = slot_spec.get("span_aliases") or {}
        if not isinstance(aliases_by_value, dict) or not aliases_by_value:
            continue
        allowed_intents = slot_spec.get("grounding_intents") or []
        if allowed_intents and intent not in allowed_intents:
            continue

        current_value = slots.get(slot_name)
        current_span = spans.get(slot_name)
        if (
            _is_present(current_value)
            and _is_present(current_span)
            and _span_matches_slot_value(current_value, current_span, slot_spec)
        ):
            continue

        matches: list[tuple[str, str]] = []
        for canonical_value, aliases in aliases_by_value.items():
            literal_aliases = [canonical_value, *(_as_values(aliases))]
            for alias in literal_aliases:
                literal_span = _literal_query_span(query, alias)
                if literal_span:
                    matches.append((str(canonical_value), literal_span))
                    break

        matched_values = {canonical_value for canonical_value, _ in matches}
        if len(matched_values) != 1:
            continue
        canonical_value = next(iter(matched_values))
        literal_span = max(
            (span for value, span in matches if value == canonical_value),
            key=len,
        )
        slots[slot_name] = canonical_value
        spans[slot_name] = literal_span


def _infer_explicit_structured_slots(
    query: str,
    *,
    lookup_type: str | None,
    intent: str | None,
    spec: dict[str, Any] | None,
    slots: dict[str, Any],
    spans: dict[str, Any],
) -> None:
    """Fill slots that are explicitly present in the query but missed by the router."""

    raw_query = str(query or "")
    _ground_declared_literal_slots(
        query,
        intent=intent,
        spec=spec,
        slots=slots,
        spans=spans,
    )

    if lookup_type == "student_service":
        # Preserve a compact service phrase only when the planner copied it
        # faithfully from the query. Otherwise use the complete query instead
        # of accepting an invented paraphrase as the retrieval identity.
        service = slots.get("service")
        service_span = spans.get("service")
        grounded_service = (
            isinstance(service, str)
            and isinstance(service_span, str)
            and bool(_normalize_text(service))
            and _normalize_text(service) == _normalize_text(service_span)
            and _normalize_text(service_span) in _normalize_text(raw_query)
        )
        if not grounded_service:
            slots["service"] = raw_query
            spans["service"] = raw_query


@lru_cache(maxsize=4)
def load_lookup_registry(path: str | Path = DEFAULT_REGISTRY_PATH) -> dict[str, Any]:
    """Load the structured lookup registry."""

    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    tools = data.get("tools")
    if not isinstance(tools, dict) or not tools:
        raise ValueError("Structured lookup registry must define at least one tool.")
    return data


def compact_registry_for_prompt(registry: dict[str, Any] | None = None) -> str:
    """Project lookup capabilities into a compact planner prompt."""

    registry = registry or load_lookup_registry()
    lines: list[str] = []
    for name, spec in registry["tools"].items():
        intents = ",".join(spec.get("intents") or [])
        required = spec.get("required_slots") or {}
        slot_contract: dict[str, Any] = {}
        for slot_name, slot_spec in (spec.get("slot_schema") or {}).items():
            compact_spec: dict[str, Any] = {}
            if slot_spec.get("type") is not None:
                compact_spec["type"] = slot_spec["type"]
            if slot_spec.get("description"):
                compact_spec["description"] = slot_spec["description"]
            allowed_values = (
                slot_spec.get("enum") or slot_spec.get("canonical_values") or []
            )
            if allowed_values:
                compact_spec["values"] = allowed_values
            slot_contract[slot_name] = compact_spec
        lines.append(
            "|".join(
                (
                    name,
                    f"use={spec.get('description') or ''}",
                    f"intents={intents}",
                    "required="
                    + json.dumps(required, ensure_ascii=False, separators=(",", ":")),
                    "slots="
                    + json.dumps(
                        slot_contract, ensure_ascii=False, separators=(",", ":")
                    ),
                )
            )
        )
    return "\n".join(lines)


def normalize_router_decision(
    payload: dict[str, Any],
    *,
    query: str,
    selected_cohort: str | None = None,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize a raw router decision to the stable contract."""

    raw_route = str(payload.get("route") or "rag").strip().lower()
    raw_execution_mode = str(payload.get("execution_mode") or "").strip().lower()
    if raw_route == "structured":
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

    slots = dict(payload.get("slots")) if isinstance(payload.get("slots"), dict) else {}
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

    registry = registry or load_lookup_registry()
    spec = registry["tools"].get(lookup_type) if lookup_type else None
    allowed_intents = list((spec or {}).get("intents") or [])
    if route == "structured" and intent not in allowed_intents:
        default_intent = (spec or {}).get("default_intent")
        if default_intent in allowed_intents:
            intent = str(default_intent)
        elif len(allowed_intents) == 1:
            intent = allowed_intents[0]
    target_types = payload.get("target_chunk_types")
    if not isinstance(target_types, list):
        target_types = (
            ["regulation"]
            if route == "rag" and execution_mode in {"regulation", "mixed"}
            else []
        )

    raw_cohorts = payload.get("cohorts")
    if isinstance(raw_cohorts, list):
        payload_cohorts = [
            normalize_cohort(c) for c in raw_cohorts if normalize_cohort(c)
        ]
    else:
        payload_cohorts = []
    payload_cohort = normalize_cohort(payload.get("cohort"))
    if payload_cohort and payload_cohort not in payload_cohorts:
        payload_cohorts.insert(0, payload_cohort)
    payload_cohorts = list(dict.fromkeys(payload_cohorts))

    is_multi_cohort = len(payload_cohorts) >= 2 or bool(
        payload.get("is_multi_cohort") and len(payload_cohorts) >= 2
    )
    selected = normalize_cohort(selected_cohort)
    if is_multi_cohort:
        cohorts = payload_cohorts
        cohort = payload_cohorts[0]
    else:
        cohort = selected or payload_cohort
        cohorts = [cohort] if cohort else []
        is_multi_cohort = False

    retrieval_query = str(payload.get("retrieval_query") or query).strip()
    if not retrieval_query or len(retrieval_query) > 600:
        retrieval_query = query.strip()

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
    referenced_turns = payload.get("referenced_turns")
    if not isinstance(referenced_turns, list):
        referenced_turns = []

    _infer_explicit_structured_slots(
        query,
        lookup_type=lookup_type,
        intent=intent,
        spec=spec,
        slots=slots,
        spans=spans,
    )

    return {
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
        "referenced_turns": [
            int(item)
            for item in referenced_turns
            if isinstance(item, int) and not isinstance(item, bool) and item >= 0
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
        "retrieval_query": retrieval_query,
        "target_chunk_types": [str(item) for item in target_types if item],
        "needs_clarification": route == "clarify"
        or bool(payload.get("needs_clarification")),
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
        return bool(span) and all(
            _span_is_grounded(value, source_text) for value in span.values()
        )
    if isinstance(span, list):
        return bool(span) and all(
            _span_is_grounded(value, source_text) for value in span
        )
    normalized = _normalize_text(span)
    return bool(normalized) and normalized in _normalize_text(source_text)


def _span_is_only_cohort(span: Any) -> bool:
    if isinstance(span, dict):
        return bool(span) and all(
            _span_is_only_cohort(value) for value in span.values()
        )
    if isinstance(span, list):
        return bool(span) and all(_span_is_only_cohort(value) for value in span)
    return bool(build_cohort_token_regex().fullmatch(str(span).strip()))


def _as_values(value: Any) -> list[Any]:
    return value if isinstance(value, list) else [value]


def _normalized_phrase_in_text(phrase: Any, text: Any) -> bool:
    normalized_phrase = _normalize_text(phrase).replace("_", " ")
    normalized_text = _normalize_text(text).replace("_", " ")
    if not normalized_phrase or not normalized_text:
        return False
    return f" {normalized_phrase} " in f" {normalized_text} "


def _numeric_value_matches_span(value: Any, span: Any) -> bool:
    """Treat Vietnamese decimal commas and decimal points as equivalent."""

    if isinstance(value, bool):
        return False
    raw_value = str(value).strip()
    if not re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?", raw_value):
        return False
    expected = float(raw_value.replace(",", "."))
    for token in re.findall(r"[-+]?\d+(?:[.,]\d+)?", str(span)):
        if float(token.replace(",", ".")) == expected:
            return True
    return False


def _span_matches_slot_value(value: Any, span: Any, schema: dict[str, Any]) -> bool:
    """Validate extracted values against their literal spans and aliases."""

    aliases_by_value = schema.get("span_aliases") or {}
    span_values = _as_values(span)
    for item in _as_values(value):
        aliases = [item]
        aliases.extend(aliases_by_value.get(str(item)) or [])
        if not any(
            _normalized_phrase_in_text(alias, literal_span)
            or _numeric_value_matches_span(item, literal_span)
            for alias in aliases
            for literal_span in span_values
        ):
            return False
    return True


def _matches_type(value: Any, expected: str) -> bool:
    if expected == "string":
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, list):
            return bool(value) and all(
                isinstance(v, str) and bool(v.strip()) for v in value
            )
        return False
    if expected == "number":
        if isinstance(value, int | float) and not isinstance(value, bool):
            return True
        if isinstance(value, list):
            return bool(value) and all(
                isinstance(v, int | float) and not isinstance(v, bool) for v in value
            )
        return False
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    return True


def _validate_slot_contract(slots: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    slot_schema = spec.get("slot_schema") or {}
    for slot_name in slots:
        if slot_name not in slot_schema:
            errors.append(f"unknown_slot:{slot_name}")

    for slot_name, schema in slot_schema.items():
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
        allowed = schema.get("enum") or schema.get("canonical_values") or []
        if allowed and any(item not in allowed for item in _as_values(value)):
            errors.append(f"invalid_slot_value:{slot_name}")

    return errors


def validate_fact_lock_inputs(
    decision: dict[str, Any],
    *,
    query: str,
    registry: dict[str, Any] | None = None,
) -> list[str]:
    """Return reasons why a table-first decision must not emit a fact lock."""

    registry = registry or load_lookup_registry()
    lookup_type = str(decision.get("lookup_type") or "")
    spec = registry.get("tools", {}).get(lookup_type)
    if not isinstance(spec, dict):
        return ["unknown_lookup_type"]

    slots = decision.get("slots") or {}
    spans = decision.get("slot_spans") or {}
    slot_schema = spec.get("slot_schema") or {}
    errors = _validate_slot_contract(slots, spec)
    grounded_value_slots = 0
    for slot_name, value in slots.items():
        if (
            slot_name in UNGROUNDED_SCHEMA_SLOTS
            or slot_name not in slot_schema
            or not _is_present(value)
        ):
            continue
        grounded_value_slots += 1
        span = spans.get(slot_name)
        if not _is_present(span):
            errors.append(f"missing_slot_span:{slot_name}")
        elif not _span_is_grounded(span, query):
            errors.append(f"ungrounded_slot:{slot_name}")
        elif _span_is_only_cohort(span):
            errors.append(f"misgrounded_slot:{slot_name}")
        elif not _span_matches_slot_value(value, span, slot_schema[slot_name]):
            errors.append(f"slot_span_mismatch:{slot_name}")
    if grounded_value_slots == 0:
        errors.append("missing_fact_lock_value")
    return list(dict.fromkeys(errors))


def validate_router_decision(
    decision: dict[str, Any],
    *,
    query: str,
    selected_cohort: str | None = None,
    grounding_context: str = "",
    registry: dict[str, Any] | None = None,
) -> list[str]:
    """Validate router intent, tasks, cohorts, and lookup targets."""

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
    slot_schema = spec.get("slot_schema") or {}
    declared_slots = set((spec.get("slot_schema") or {}).keys())
    for slot_name in spans:
        if slot_name not in declared_slots:
            errors.append(f"unknown_slot_span:{slot_name}")
    contract_intent = (
        intent if intent in allowed_intents else spec.get("default_intent")
    )
    required = list((spec.get("required_slots") or {}).get(contract_intent, []))
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
        elif _span_is_only_cohort(spans[slot_name]):
            errors.append(f"misgrounded_slot:{slot_name}")
        elif not _span_matches_slot_value(
            slots[slot_name], spans[slot_name], slot_schema[slot_name]
        ):
            errors.append(f"slot_span_mismatch:{slot_name}")

    for slot_name, value in slots.items():
        if (
            slot_name in required
            or slot_name in UNGROUNDED_SCHEMA_SLOTS
            or slot_name not in declared_slots
            or not _is_present(value)
        ):
            continue
        span = spans.get(slot_name)
        if not _is_present(span):
            errors.append(f"missing_slot_span:{slot_name}")
        elif not _span_is_grounded(span, source_text):
            errors.append(f"ungrounded_slot:{slot_name}")
        elif _span_is_only_cohort(span):
            errors.append(f"misgrounded_slot:{slot_name}")
        elif not _span_matches_slot_value(value, span, slot_schema[slot_name]):
            errors.append(f"slot_span_mismatch:{slot_name}")

    errors.extend(_validate_slot_contract(slots, spec))

    return errors


def registry_digest(registry: dict[str, Any] | None = None) -> str:
    """Return a stable digest for structured-routing configuration."""

    registry = registry or load_lookup_registry()
    return json.dumps(
        registry, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
