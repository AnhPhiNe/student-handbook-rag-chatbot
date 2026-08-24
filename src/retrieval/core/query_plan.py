from __future__ import annotations

from typing import Any

from src.common.cohort import (
    build_cohort_token_regex,
    extract_cohorts_from_query,
    normalize_cohort,
    valid_cohorts,
)

from .structured_routing import (
    load_lookup_registry,
    normalize_router_decision,
    validate_router_decision,
)


QUERY_PLAN_SCHEMA_VERSION = "v1"
MAX_QUERY_TASKS = 3
ALLOWED_TASK_MODES = {"structured", "rag", "clarify"}


def query_plan_json_schema() -> dict[str, Any]:
    tools = list(load_lookup_registry().get("tools", {}).keys())
    cohorts = list(valid_cohorts())
    return {
        "schema_version": QUERY_PLAN_SCHEMA_VERSION,
        "context_mode": "standalone|follow_up|ambiguous",
        "normalized_query": "orthographic correction only or original query",
        "standalone_query": "history-grounded query for follow_up or null",
        "referenced_turns": [],
        "out_of_domain": False,
        "tasks": [
            {
                "id": "t1",
                "question": "one self-contained student request",
                "mode": "structured|rag|clarify",
                "intent": "intent name",
                "lookup_type": "|".join(tools) + "|null",
                "slots": {},
                "slot_spans": {},
                "cohorts": cohorts,
                "clarification_question": None,
            }
        ],
    }


def query_plan_response_schema() -> dict[str, Any]:
    tools = list(load_lookup_registry().get("tools", {}).keys())
    cohorts = list(valid_cohorts())
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": {"type": "string"},
            "context_mode": {
                "type": "string",
                "enum": ["standalone", "follow_up", "ambiguous"],
            },
            "normalized_query": {"type": ["string", "null"]},
            "standalone_query": {"type": ["string", "null"]},
            "referenced_turns": {
                "type": "array",
                "items": {"type": "integer"},
            },
            "out_of_domain": {"type": ["boolean", "null"]},
            "tasks": {
                "type": "array",
                "minItems": 1,
                "maxItems": MAX_QUERY_TASKS,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "id": {"type": "string"},
                        "question": {"type": "string"},
                        "mode": {
                            "type": "string",
                            "enum": ["structured", "rag", "clarify"],
                        },
                        "intent": {"type": "string"},
                        "lookup_type": {
                            "anyOf": [
                                {"type": "string", "enum": tools},
                                {"type": "null"},
                            ]
                        },
                        "slots": {"type": "object", "additionalProperties": True},
                        "slot_spans": {
                            "type": "object",
                            "additionalProperties": {
                                "anyOf": [
                                    {"type": "string"},
                                    {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                ]
                            },
                        },
                        "cohorts": {
                            "type": "array",
                            "items": {
                                "type": "string",
                                "enum": cohorts,
                            },
                        },
                        "clarification_question": {"type": ["string", "null"]},
                    },
                    "required": [
                        "id",
                        "question",
                        "mode",
                        "intent",
                        "lookup_type",
                        "slots",
                        "slot_spans",
                        "cohorts",
                        "clarification_question",
                    ],
                },
            },
        },
        "required": [
            "schema_version",
            "context_mode",
            "normalized_query",
            "standalone_query",
            "referenced_turns",
            "out_of_domain",
            "tasks",
        ],
    }


def legacy_rag_plan(
    query: str,
    cohort: str | None = None,
    *,
    reason: str = "legacy_rag",
) -> dict[str, Any]:
    normalized_cohort = normalize_cohort(cohort)
    return {
        "schema_version": QUERY_PLAN_SCHEMA_VERSION,
        "context_mode": "standalone",
        "normalized_query": query,
        "standalone_query": None,
        "referenced_turns": [],
        "out_of_domain": False,
        "tasks": [
            {
                "id": "t1",
                "question": query,
                "mode": "rag",
                "intent": "open_question",
                "lookup_type": None,
                "slots": {},
                "slot_spans": {},
                "cohorts": [normalized_cohort] if normalized_cohort else [],
                "clarification_question": None,
                "validation_errors": [],
            }
        ],
        "planner_fallback": reason,
        "planner_validation_errors": [],
    }


def normalize_query_plan(
    payload: dict[str, Any],
    *,
    query: str,
    selected_cohort: str | None = None,
    grounding_context: str = "",
    registry: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    registry = registry or load_lookup_registry()
    query_cohorts = extract_cohorts_from_query(query)
    default_cohort = query_cohorts[0] if len(query_cohorts) == 1 else selected_cohort
    raw_tasks = payload.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        return legacy_rag_plan(query, default_cohort, reason="invalid_plan_to_legacy_rag"), [
            "missing_tasks"
        ]

    if len(raw_tasks) > 12:
        return _too_many_tasks_plan(query, default_cohort), []

    context_mode = str(payload.get("context_mode") or "standalone").strip().lower()
    if context_mode not in {"standalone", "follow_up", "ambiguous"}:
        context_mode = "ambiguous"
    normalized_query = str(payload.get("normalized_query") or query).strip() or query
    standalone_query = str(payload.get("standalone_query") or "").strip() or None
    referenced_turns = [
        value
        for value in (payload.get("referenced_turns") or [])
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
    ]

    errors: list[str] = []
    tasks: list[dict[str, Any]] = []
    for index, raw_task in enumerate(raw_tasks, start=1):
        if not isinstance(raw_task, dict):
            errors.append(f"task_{index}:invalid_object")
            continue
        task, task_errors = _normalize_task(
            raw_task,
            task_id=f"t{index}",
            original_query=query,
            selected_cohort=default_cohort,
            grounding_context=grounding_context,
            registry=registry,
        )
        tasks.append(task)
        errors.extend(f"{task['id']}:{error}" for error in task_errors)

    tasks = _merge_compatible_structured_tasks(tasks, original_query=query)
    tasks = _merge_cohort_variant_tasks(tasks)
    if len(tasks) > MAX_QUERY_TASKS:
        return _too_many_tasks_plan(query, default_cohort), []
    for index, task in enumerate(tasks, start=1):
        task["id"] = f"t{index}"

    if not tasks:
        return legacy_rag_plan(query, default_cohort, reason="invalid_plan_to_legacy_rag"), (
            errors or ["missing_valid_tasks"]
        )

    plan = {
        "schema_version": QUERY_PLAN_SCHEMA_VERSION,
        "context_mode": context_mode,
        "normalized_query": normalized_query,
        "standalone_query": standalone_query,
        "referenced_turns": referenced_turns,
        "out_of_domain": bool(payload.get("out_of_domain")),
        "tasks": tasks,
        "planner_fallback": payload.get("planner_fallback"),
        "planner_validation_errors": errors,
    }
    if context_mode == "ambiguous" and not any(
        task["mode"] == "clarify" for task in tasks
    ):
        plan["tasks"] = [_clarify_task("t1", query)]
    return plan, errors


def _normalize_task(
    raw_task: dict[str, Any],
    *,
    task_id: str,
    original_query: str,
    selected_cohort: str | None,
    grounding_context: str,
    registry: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    mode = str(raw_task.get("mode") or "").strip().lower()
    question = str(raw_task.get("question") or original_query).strip() or original_query
    errors: list[str] = []
    if mode not in ALLOWED_TASK_MODES:
        mode = "rag"
        errors.append("invalid_mode")

    raw_cohorts = raw_task.get("cohorts")
    cohorts = []
    if isinstance(raw_cohorts, list):
        cohorts = [normalize_cohort(value) for value in raw_cohorts]
        cohorts = [value for value in cohorts if value]
    cohorts = list(dict.fromkeys(cohorts))
    fallback_cohort = normalize_cohort(selected_cohort)
    if not cohorts and fallback_cohort:
        cohorts = [fallback_cohort]

    lookup_type = raw_task.get("lookup_type")
    lookup_type = str(lookup_type).strip().lower() if lookup_type else None
    intent = str(raw_task.get("intent") or "open_question").strip().lower()
    clarification = str(raw_task.get("clarification_question") or "").strip() or None
    slots = dict(raw_task.get("slots")) if isinstance(raw_task.get("slots"), dict) else {}
    raw_spans = (
        dict(raw_task.get("slot_spans"))
        if isinstance(raw_task.get("slot_spans"), dict)
        else {}
    )
    spans = {
        key: value
        for key, raw_value in raw_spans.items()
        if (value := _normalize_span_value(raw_value, original_query)) not in (None, "", [])
    }

    if mode == "clarify":
        return {
            "id": task_id,
            "question": question,
            "mode": "clarify",
            "intent": intent,
            "lookup_type": None,
            "slots": {},
            "slot_spans": {},
            "cohorts": cohorts,
            "clarification_question": clarification
            or "Bạn có thể nói rõ hơn phần thông tin cần tra cứu không?",
            "validation_errors": [],
        }, errors

    if mode == "rag":
        if lookup_type:
            errors.append("rag_must_not_select_lookup")
        return {
            "id": task_id,
            "question": question,
            "mode": "rag",
            "intent": "open_question",
            "lookup_type": None,
            "slots": {},
            "slot_spans": {},
            "cohorts": cohorts,
            "clarification_question": None,
            "validation_errors": errors.copy(),
        }, errors

    if lookup_type not in registry.get("tools", {}):
        errors.append("unknown_lookup_type")
        return _clarify_task(
            task_id,
            question,
            cohorts=cohorts,
            clarification="Mình chưa xác định được loại thông tin cần tra. Bạn có thể nói rõ hơn không?",
            validation_errors=errors,
        ), errors

    decision = normalize_router_decision(
        {
            "route": "structured",
            "execution_mode": "structured",
            "intent": intent,
            "lookup_type": lookup_type,
            "cohort": cohorts[0] if cohorts else None,
            "cohorts": cohorts,
            "is_multi_cohort": len(cohorts) > 1,
            "slots": slots,
            "slot_spans": spans,
            "retrieval_query": question,
        },
        query=original_query,
        selected_cohort=cohorts[0] if cohorts else selected_cohort,
    )
    validation_errors = validate_router_decision(
        decision,
        query=original_query,
        selected_cohort=cohorts[0] if cohorts else selected_cohort,
        grounding_context=grounding_context,
        registry=registry,
    )
    if validation_errors:
        errors.extend(validation_errors)
        if all(
            error.startswith(
                (
                    "missing_slot",
                    "missing_cohort",
                    "unsupported_intent",
                    "ungrounded_slot",
                )
            )
            for error in validation_errors
        ):
            return _clarify_task(
                task_id,
                question,
                cohorts=cohorts,
                clarification=clarification
                or "Bạn có thể bổ sung thông tin còn thiếu để mình tra đúng bảng không?",
                validation_errors=errors,
            ), errors

    return {
        "id": task_id,
        "question": question,
        "mode": "structured",
        "intent": decision.get("intent"),
        "lookup_type": decision.get("lookup_type"),
        "slots": decision.get("slots") or {},
        "slot_spans": decision.get("slot_spans") or {},
        "cohorts": decision.get("cohorts") or cohorts,
        "clarification_question": clarification,
        "validation_errors": errors.copy(),
    }, errors


def _clarify_task(
    task_id: str,
    question: str,
    *,
    cohorts: list[str] | None = None,
    clarification: str | None = None,
    validation_errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": task_id,
        "question": question,
        "mode": "clarify",
        "intent": "clarify",
        "lookup_type": None,
        "slots": {},
        "slot_spans": {},
        "cohorts": cohorts or [],
        "clarification_question": clarification
        or "Bạn có thể nói rõ hơn phần thông tin cần tra cứu không?",
        "validation_errors": validation_errors or [],
    }


def _normalize_span_value(value: Any, source_text: str) -> Any:
    """Accept literal spans and defensively convert common offset objects."""
    if isinstance(value, dict):
        literal = str(value.get("text") or "").strip()
        if literal:
            return literal
        start = value.get("start")
        end = value.get("end")
        if (
            isinstance(start, int)
            and not isinstance(start, bool)
            and isinstance(end, int)
            and not isinstance(end, bool)
            and 0 <= start < end <= len(source_text)
        ):
            return source_text[start:end].strip()
        return None
    if isinstance(value, list):
        normalized = [
            item
            for raw_item in value
            if (item := _normalize_span_value(raw_item, source_text)) not in (None, "", [])
        ]
        return normalized
    return str(value).strip() if value is not None else None


def _merge_compatible_structured_tasks(
    tasks: list[dict[str, Any]],
    *,
    original_query: str,
) -> list[dict[str, Any]]:
    """Keep multiple entities in one logical task without adding recursive planning."""
    merged: list[dict[str, Any]] = []
    index_by_key: dict[tuple[Any, ...], int] = {}
    for task in tasks:
        if task.get("mode") != "structured":
            merged.append(task)
            continue
        key = (
            task.get("lookup_type"),
            task.get("intent"),
            tuple(task.get("cohorts") or []),
        )
        existing_index = index_by_key.get(key)
        if existing_index is None:
            index_by_key[key] = len(merged)
            merged.append(task)
            continue
        existing = merged[existing_index]
        existing["question"] = original_query
        existing["cohorts"] = list(
            dict.fromkeys((existing.get("cohorts") or []) + (task.get("cohorts") or []))
        )
        # Multi-entity structured lookups select the matching table/rows from
        # the whole task question. Scalar slots would otherwise discard peers.
        existing["slots"] = {}
        existing["slot_spans"] = {}
        existing["validation_errors"] = list(
            dict.fromkeys(
                (existing.get("validation_errors") or [])
                + (task.get("validation_errors") or [])
            )
        )
    return merged


def _merge_cohort_variant_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse planner-created per-cohort copies into one logical RAG task."""
    merged: list[dict[str, Any]] = []
    index_by_key: dict[tuple[str, str, str], int] = {}
    cohort_token_re = build_cohort_token_regex()
    for task in tasks:
        if task.get("mode") != "rag":
            merged.append(task)
            continue
        generic_question = " ".join(
            cohort_token_re.sub("", str(task.get("question") or "")).split()
        ).strip(" ,;:-")
        key = (
            "rag",
            str(task.get("intent") or "open_question"),
            generic_question.casefold(),
        )
        existing_index = index_by_key.get(key)
        if existing_index is None:
            index_by_key[key] = len(merged)
            copied = dict(task)
            merged.append(copied)
            continue
        existing = merged[existing_index]
        existing["question"] = generic_question or existing.get("question")
        existing["cohorts"] = list(
            dict.fromkeys((existing.get("cohorts") or []) + (task.get("cohorts") or []))
        )
    return merged


def _too_many_tasks_plan(query: str, cohort: str | None) -> dict[str, Any]:
    normalized_cohort = normalize_cohort(cohort)
    return {
        "schema_version": QUERY_PLAN_SCHEMA_VERSION,
        "context_mode": "ambiguous",
        "normalized_query": query,
        "standalone_query": None,
        "referenced_turns": [],
        "out_of_domain": False,
        "tasks": [
            _clarify_task(
                "t1",
                query,
                cohorts=[normalized_cohort] if normalized_cohort else [],
                clarification=(
                    "Câu hỏi đang có nhiều hơn ba yêu cầu độc lập. "
                    "Bạn có thể chọn tối đa ba nội dung cần tra trước không?"
                ),
                validation_errors=["too_many_tasks"],
            )
        ],
        "planner_fallback": None,
        "planner_validation_errors": ["too_many_tasks"],
    }
