from __future__ import annotations

import json
import re
from functools import lru_cache, partial
from pathlib import Path
from typing import Any

import yaml

from src.common.cohort import build_cohort_token_regex, normalize_cohort
from src.common.text import fold_text

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY_PATH = ROOT / "configs" / "structured_lookup_registry.yaml"
COHORT_SCOPED_LOOKUPS = {
    "foreign_language",
    "study_duration",
    "scholarship_classification",
    "scoring",
    "formula",
}
SLOT_VERIFICATION_ROLES = frozenset(
    {"reading_intent", "result_input", "directory_entity"}
)
DEFAULT_SLOT_VERIFICATION_ROLE = "result_input"


def _slot_verification_role(slot_spec: dict[str, Any] | None) -> str:
    """Return a registry-declared slot role, defaulting to strict grounding."""

    role = str((slot_spec or {}).get("verification_role") or "").strip().lower()
    return role if role in SLOT_VERIFICATION_ROLES else DEFAULT_SLOT_VERIFICATION_ROLE


def _is_semantic_result_input_slot(slot_spec: dict[str, Any] | None) -> bool:
    """Identify canonical string selectors whose meaning belongs to the planner."""

    slot_spec = slot_spec or {}
    expected_types = slot_spec.get("type") or []
    if isinstance(expected_types, str):
        string_only = expected_types == "string"
    elif isinstance(expected_types, (list, tuple, set)):
        string_only = set(expected_types) == {"string"}
    else:
        string_only = False
    return (
        _slot_verification_role(slot_spec) == "result_input"
        and string_only
        and bool(slot_spec.get("enum") or slot_spec.get("canonical_values"))
    )


_normalize_text = partial(fold_text, keep="+.,")


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

        # The planner owns the meaning of a present slot.  Registry aliases
        # may repair evidence for that same value, but must never reinterpret
        # it as another canonical value.  Invalid values are deliberately
        # left untouched so the central contract validator can report them.
        if _is_present(current_value):
            if not _slot_value_matches_contract(current_value, slot_spec):
                continue

            same_value_matches: list[str] = []
            for item in _as_values(current_value):
                literal_aliases = [item, *(_as_values(aliases_by_value.get(str(item))))]
                item_matches = [
                    literal_span
                    for alias in literal_aliases
                    if (literal_span := _literal_query_span(query, alias))
                ]
                if not item_matches:
                    same_value_matches = []
                    break
                same_value_matches.extend(item_matches)
            if same_value_matches and not _is_present(current_span):
                spans[slot_name] = max(same_value_matches, key=len)
            continue

        # Missing values are not inferred from query aliases. The planner owns
        # the meaning of every slot; directory identity matching belongs to the
        # selected resolver rather than this normalizer.


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
                aliases = slot_spec.get("span_aliases") or {}
                # Codes such as "secondary_bridge" are opaque to the planner, so
                # map each to its first alias; self-describing codes map to
                # themselves.
                meanings = {
                    value: aliases[value][0]
                    for value in allowed_values
                    if aliases.get(value) and value not in aliases[value]
                }
                compact_spec["values"] = (
                    {value: meanings.get(value, value) for value in allowed_values}
                    if meanings
                    else allowed_values
                )
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


def prepare_structured_task(
    question: str,
    *,
    lookup_type: str | None,
    intent: str | None,
    slots: dict[str, Any],
    slot_spans: dict[str, Any],
    cohort: str | None = None,
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare one structured task's slots before validation.

    Falls back to the lookup's default intent when the planner's intent is not
    supported, collects the spans of nested slots, and grounds spans only for
    values the planner supplied. ``question`` is the task-local text; missing
    values stay missing for the resolver to handle.
    """

    registry = registry or load_lookup_registry()
    spec = registry["tools"].get(lookup_type) if lookup_type else None
    intent = str(intent or "open_question").strip().lower()
    slots = dict(slots)
    spans = dict(slot_spans)
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

    allowed_intents = list((spec or {}).get("intents") or [])
    if intent not in allowed_intents:
        default_intent = (spec or {}).get("default_intent")
        if default_intent in allowed_intents:
            intent = str(default_intent)
        elif len(allowed_intents) == 1:
            intent = allowed_intents[0]

    _ground_declared_literal_slots(
        question, intent=intent, spec=spec, slots=slots, spans=spans
    )
    return {
        "lookup_type": lookup_type,
        "intent": intent,
        "cohort": normalize_cohort(cohort),
        "slots": slots,
        "slot_spans": spans,
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


def _span_satisfies_source_contract(
    value: Any,
    span: Any,
    schema: dict[str, Any],
) -> bool:
    """Validate a slot span without making the normalizer own semantic meaning."""

    if _span_matches_slot_value(value, span, schema):
        return True
    return _is_semantic_result_input_slot(schema)


def _slot_span_error(
    value: Any,
    span: Any,
    schema: dict[str, Any],
    source_text: str,
) -> str | None:
    """Return the first source-grounding error for a supplied slot value."""

    if not _is_present(span):
        return "missing_slot_span"
    if not _span_is_grounded(span, source_text):
        return "ungrounded_slot"
    if _span_is_only_cohort(span):
        return "misgrounded_slot"
    if not _span_satisfies_source_contract(value, span, schema):
        return "slot_span_mismatch"
    return None


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


def _slot_value_matches_contract(value: Any, schema: dict[str, Any]) -> bool:
    """Check type and enum validity without requiring a source span."""

    expected_types = schema.get("type") or []
    if isinstance(expected_types, str):
        expected_types = [expected_types]
    if expected_types and not any(
        _matches_type(value, expected) for expected in expected_types
    ):
        return False
    allowed = schema.get("enum") or schema.get("canonical_values") or []
    return not allowed or all(item in allowed for item in _as_values(value))


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
            _slot_verification_role(slot_schema.get(slot_name)) == "reading_intent"
            or slot_name not in slot_schema
            or not _is_present(value)
        ):
            continue
        grounded_value_slots += 1
        span = spans.get(slot_name)
        span_error = _slot_span_error(
            value,
            span,
            slot_schema[slot_name],
            query,
        )
        if span_error:
            errors.append(f"{span_error}:{slot_name}")
    if grounded_value_slots == 0:
        errors.append("missing_fact_lock_value")
    return list(dict.fromkeys(errors))


def validate_structured_task(
    task: dict[str, Any],
    *,
    query: str,
    grounding_context: str = "",
    registry: dict[str, Any] | None = None,
) -> list[str]:
    """Validate a prepared structured task against its lookup contract.

    Values must be grounded in ``query`` (the complete user question) or in
    ``grounding_context`` (recent history), never only in a task paraphrase.
    """

    registry = registry or load_lookup_registry()
    errors: list[str] = []
    lookup_type = task.get("lookup_type")
    spec = registry["tools"].get(lookup_type)
    if not spec:
        return ["unknown_lookup_type"]
    if (
        lookup_type in COHORT_SCOPED_LOOKUPS
        and not normalize_cohort(task.get("cohort"))
        and not _query_mentions_cohort(query)
    ):
        errors.append("missing_cohort")

    intent = task.get("intent")
    allowed_intents = set(spec.get("intents") or [])
    if intent not in allowed_intents:
        errors.append("unsupported_intent")

    slots = task.get("slots") or {}
    spans = task.get("slot_spans") or {}
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
        if _slot_verification_role(slot_schema.get(slot_name)) == "reading_intent":
            continue
        span_error = _slot_span_error(
            slots[slot_name],
            spans.get(slot_name),
            slot_schema[slot_name],
            source_text,
        )
        if span_error:
            errors.append(f"{span_error}:{slot_name}")

    for slot_name, value in slots.items():
        if (
            slot_name in required
            or _slot_verification_role(slot_schema.get(slot_name)) == "reading_intent"
            or slot_name not in declared_slots
            or not _is_present(value)
        ):
            continue
        span = spans.get(slot_name)
        span_error = _slot_span_error(
            value,
            span,
            slot_schema[slot_name],
            source_text,
        )
        if span_error:
            errors.append(f"{span_error}:{slot_name}")

    errors.extend(_validate_slot_contract(slots, spec))

    return errors


def registry_digest(registry: dict[str, Any] | None = None) -> str:
    """Return a stable digest for structured-routing configuration."""

    registry = registry or load_lookup_registry()
    return json.dumps(
        registry, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
