from __future__ import annotations

from copy import deepcopy
import re
from functools import partial
from typing import Any

from src.common.cohort import (
    admission_years_for_cohort,
    build_cohort_token_regex,
    extract_cohorts_from_query,
    normalize_cohort,
    valid_cohorts,
)
from src.common.score import grounded_score, parse_score
from src.common.text import fold_text, slot_values

from .structured_routing import (
    load_lookup_registry,
    prepare_structured_task,
    validate_structured_task,
)

QUERY_PLAN_SCHEMA_VERSION = "v1"
QUERY_PLAN_NORMALIZER_VERSION = "v34-ask-for-what-is-missing"
QUERY_PLAN_STRICT_SCHEMA_VERSION = "v2-field-descriptions"
MAX_QUERY_TASKS = 3
MAX_RAW_QUERY_TASKS = 12
ALLOWED_TASK_MODES = {"structured", "rag", "clarify"}

_BARE_ARTICLE_QUESTION_WORDS = {
    "co",
    "dinh",
    "dung",
    "ghi",
    "gi",
    "la",
    "nao",
    "noi",
    "nhu",
    "quy",
    "the",
    "vay",
    "ve",
}

_ADMISSION_YEAR_PATTERNS = (
    re.compile(r"\bnam tuyen sinh\s*(?:la\s*)?(20\d{2})\b"),
    re.compile(r"\btuyen sinh nam\s*(?:la\s*)?(20\d{2})\b"),
)
_COMPARISON_PHRASES = (
    "so sanh",
    "so voi",
    "doi chieu",
    "khac nhau",
    "khac gi",
    "giua cac",
    "giua hai",
)


_fold_query = partial(fold_text, keep="")


def _cohort_admission_year_conflict(
    query: str, selected_cohort: str | None = None
) -> tuple[str, int] | None:
    """Return one explicit cohort/year mismatch for the same described student.

    Only years explicitly introduced as an admission year participate. Queries
    that explicitly compare groups are left to the planner instead of being
    mistaken for contradictory profile metadata.
    """

    query_cohorts = extract_cohorts_from_query(query)
    if len(query_cohorts) > 1:
        return None
    selected = normalize_cohort(selected_cohort)
    cohorts = query_cohorts or ([selected] if selected in valid_cohorts() else [])
    if len(cohorts) != 1:
        return None
    folded = _fold_query(query)
    if any(phrase in folded for phrase in _COMPARISON_PHRASES):
        return None
    years = {
        int(match.group(1))
        for pattern in _ADMISSION_YEAR_PATTERNS
        for match in pattern.finditer(folded)
    }
    if len(years) != 1:
        return None
    cohort = cohorts[0]
    year = next(iter(years))
    admitted = set(admission_years_for_cohort(cohort))
    return (cohort, year) if admitted and year not in admitted else None


def _bare_article_reference(query: str) -> str | None:
    """Return an article number only when its document and topic are omitted."""

    folded = _fold_query(query)
    folded = re.sub(r"\bk(?:48|49|50|51)\b", " ", folded)
    folded = re.sub(r"\s+", " ", folded).strip()
    match = re.fullmatch(r"dieu\s+(\d+[a-z]?)\s*(.*)", folded)
    if not match:
        return None
    remainder = match.group(2).split()
    if remainder and any(
        word not in _BARE_ARTICLE_QUESTION_WORDS for word in remainder
    ):
        return None
    return match.group(1)


def query_plan_response_schema() -> dict[str, Any]:
    """Return the shared, permissive QueryPlan JSON Schema."""

    tools = list(load_lookup_registry().get("tools", {}).keys())
    cohorts = list(valid_cohorts())
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": {
                "type": "string",
                "enum": [QUERY_PLAN_SCHEMA_VERSION],
            },
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
                "minItems": 0,
                "maxItems": MAX_RAW_QUERY_TASKS,
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


def query_plan_strict_response_schema(
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Close each task's slots using the registry for strict structured output.

    A structured branch belongs to exactly one lookup. Registry values remain
    scalar or homogeneous lists, as accepted by the runtime validator. Every
    declared slot/span key is required by the provider; null means omitted.
    Slot descriptions travel with their enums, where the model picks a value,
    and the task list is capped at the plan limit rather than the raw one.
    Required business inputs and grounding still belong to runtime validation.
    """
    registry = registry if registry is not None else load_lookup_registry()

    def closed_object(properties: dict[str, Any]) -> dict[str, Any]:
        return {"type": "object", "properties": properties,
                "required": list(properties), "additionalProperties": False}

    def nullable_value(slot_spec: dict[str, Any]) -> dict[str, Any]:
        types = slot_spec.get("type")
        types = [types] if isinstance(types, str) else types
        if not types or any(kind not in {"string", "number"} for kind in types):
            raise ValueError("Strict planner schema supports scalar string/number registry slots")
        allowed = slot_spec.get("enum") or slot_spec.get("canonical_values") or []
        variants: list[dict[str, Any]] = []
        for kind in types:
            scalar: dict[str, Any] = {"type": kind}
            if allowed:
                scalar["enum"] = list(allowed)
            variants.extend([scalar, {"type": "array", "minItems": 1,
                                      "items": deepcopy(scalar)}])
        variants.append({"type": "null"})
        value = {"anyOf": variants}
        if slot_spec.get("description"):
            value["description"] = slot_spec["description"]
        return value

    schema = query_plan_response_schema()
    common = schema["properties"]["tasks"]["items"]["properties"]
    branches = []
    span = {"anyOf": [{"type": "string"}, {"type": "array", "minItems": 1,
                      "items": {"type": "string"}}, {"type": "null"}]}
    for name, spec in registry["tools"].items():
        properties = deepcopy(common)
        properties.update(
            mode={"type": "string", "enum": ["structured"]},
            lookup_type={"type": "string", "enum": [name]},
            intent={"type": "string", "enum": list(spec["intents"])},
            slots=closed_object({key: nullable_value(value)
                                 for key, value in spec["slot_schema"].items()}),
            slot_spans=closed_object({key: deepcopy(span) for key in spec["slot_schema"]}),
            clarification_question={"type": "null"},
        )
        branches.append(closed_object(properties))
    for mode, intent in (("rag", "open_question"), ("clarify", "clarify")):
        properties = deepcopy(common)
        properties.update(
            mode={"type": "string", "enum": [mode]},
            intent={"type": "string", "enum": [intent]},
            lookup_type={"type": "null"},
            slots=closed_object({}), slot_spans=closed_object({}),
            clarification_question={"type": "string" if mode == "clarify" else "null"},
        )
        branches.append(closed_object(properties))
    schema["properties"]["tasks"]["items"] = {"anyOf": branches}
    schema["properties"]["tasks"]["maxItems"] = MAX_QUERY_TASKS
    return schema


def safe_rag_fallback_plan(
    query: str,
    cohort: str | None = None,
    *,
    reason: str = "safe_rag",
) -> dict[str, Any]:
    """Return one bounded RAG task when planning cannot be trusted."""
    explicit_cohorts = extract_cohorts_from_query(query)
    normalized_cohort = normalize_cohort(cohort)
    fallback_cohorts = explicit_cohorts or (
        [normalized_cohort] if normalized_cohort else []
    )
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
                "cohorts": fallback_cohorts,
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
    visible_history: dict[int, str] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Validate a raw plan; the router supplies exactly the displayed history.

    The checks run in this order, and the first that fails decides the plan:

    1. `out_of_domain` that is not a boolean: safe RAG fallback.
    2. A follow-up whose standalone text or turns are not in the visible
       history: ask the student to restate the question.
    3. A cohort that contradicts the admission year in the question, or a bare
       "Điều N" with no document or topic: ask which one is meant.
    4. Out of domain: no tasks.
    5. Each task is normalized on its own (`_normalize_task`), so one bad task
       does not invalidate its siblings. Identical lookups and per-cohort
       copies are merged; more than MAX_QUERY_TASKS asks the student to choose.

    ``grounding_context`` remains available to trusted offline callers. Runtime
    callers pass ``visible_history`` so references and grounding share one view.
    Standalone/ambiguous plans never use either history source for grounding.
    """

    registry = registry or load_lookup_registry()
    query_cohorts = extract_cohorts_from_query(query)
    default_cohort = query_cohorts[0] if len(query_cohorts) == 1 else selected_cohort
    supported_cohorts = set(valid_cohorts())
    fallback_cohorts = [
        normalized
        for value in (query_cohorts or [selected_cohort])
        if (normalized := normalize_cohort(value)) in supported_cohorts
    ]
    raw_ood = payload.get("out_of_domain")
    if raw_ood is not None and not isinstance(raw_ood, bool):
        errors = ["invalid_out_of_domain_type"]
        plan = safe_rag_fallback_plan(
            query, default_cohort, reason="invalid_plan_control"
        )
        plan["planner_validation_errors"] = errors
        return plan, errors
    out_of_domain = raw_ood is True
    context_mode = str(payload.get("context_mode") or "standalone").strip().lower()
    if context_mode not in {"standalone", "follow_up", "ambiguous"}:
        context_mode = "ambiguous"
    normalized_query = str(payload.get("normalized_query") or query).strip() or query

    history = _history_references(payload, context_mode, visible_history, grounding_context)
    if history is None:
        errors = ["invalid_history_reference"]
        return _clarification_plan(
            query,
            "Bạn có thể nêu lại nội dung hoặc đối tượng đang muốn hỏi không?",
            fallback="invalid_history_reference",
            errors=errors,
        ), errors
    standalone_query, referenced_turns, grounding_context = history

    if conflict := _cohort_admission_year_conflict(query, selected_cohort):
        cohort, year = conflict
        expected_years = ", ".join(
            str(value) for value in admission_years_for_cohort(cohort)
        )
        return _clarification_plan(
            query,
            f"Bạn đang nêu {cohort} nhưng năm tuyển sinh {year}; "
            f"theo dữ liệu khóa hiện có, {cohort} tương ứng năm "
            f"{expected_years}. Bạn muốn tra theo khóa hay theo năm "
            "tuyển sinh?",
            cohorts=[cohort],
            fallback="cohort_admission_year_conflict",
        ), []
    if article_number := _bare_article_reference(query):
        cohorts = [normalize_cohort(default_cohort)] if default_cohort else []
        return _clarification_plan(
            query,
            f"Bạn muốn hỏi Điều {article_number} của văn bản/quy chế nào, "
            "hoặc về chủ đề cụ thể nào?",
            cohorts=[value for value in cohorts if value],
            fallback="bare_article_requires_document_or_topic",
        ), []
    if out_of_domain:
        return {
            "schema_version": QUERY_PLAN_SCHEMA_VERSION,
            "context_mode": context_mode,
            "normalized_query": normalized_query,
            "standalone_query": standalone_query,
            "referenced_turns": referenced_turns,
            "out_of_domain": True,
            "tasks": [],
            "planner_fallback": payload.get("planner_fallback"),
            "planner_validation_errors": [],
        }, []
    raw_tasks = payload.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        return safe_rag_fallback_plan(
            query, default_cohort, reason="invalid_plan_to_safe_rag"
        ), ["missing_tasks"]

    if len(raw_tasks) > MAX_RAW_QUERY_TASKS:
        return _too_many_tasks_plan(query, default_cohort), []

    errors: list[str] = []
    tasks: list[dict[str, Any]] = []
    for index, raw_task in enumerate(raw_tasks, start=1):
        if not isinstance(raw_task, dict):
            errors.append(f"task_{index}:invalid_object")
            continue
        # Only the unambiguous standalone, one-task/one-explicit-cohort case.
        # Do not globally overwrite task scopes in multi-target or follow-up plans.
        if (
            context_mode == "standalone"
            and len(raw_tasks) == 1
            and len(query_cohorts) == 1
        ):
            raw_task = {**raw_task, "cohorts": query_cohorts}
        task, task_errors = _normalize_task(
            raw_task,
            task_id=f"t{index}",
            original_query=query,
            selected_cohort=default_cohort,
            grounding_context=grounding_context,
            registry=registry,
            fallback_cohorts=fallback_cohorts,
        )
        tasks.append(task)
        errors.extend(f"{task['id']}:{error}" for error in task_errors)

    single_question = (query if context_mode == "standalone" else standalone_query)
    binding_errors = _validate_task_bindings(
        tasks, source_text=f"{query}\n{grounding_context}", registry=registry,
        single_question=single_question if len(raw_tasks) == 1 else None,
    )
    for index, task in enumerate(tasks):
        if task_errors := binding_errors.get(task["id"]):
            errors.extend(f"{task['id']}:{error}" for error in task_errors)
            tasks[index] = _clarify_task(
                task["id"], task.get("question") or query,
                cohorts=task.get("cohorts"),
                clarification="Mình chưa ghép chắc chắn yêu cầu này với đúng khóa và dữ kiện. "
                              "Bạn có thể nêu lại yêu cầu cùng khóa và các giá trị tương ứng không?",
                validation_errors=[*(task.get("validation_errors") or []), *task_errors],
                normalization_warnings=task.get("normalization_warnings"),
            )

    tasks = _merge_compatible_structured_tasks(tasks)
    tasks = _merge_cohort_variant_tasks(tasks)
    if (
        context_mode in {"standalone", "follow_up"}
        and len(tasks) == 1
        and tasks[0].get("mode") in {"rag", "structured"}
    ):
        # A single task has no decomposition benefit from rewriting its
        # question. Preserve the original user query, or the standalone
        # follow-up text that already includes the referenced history. Another
        # task-level paraphrase can drop its subject or applicability.
        task_query = query if context_mode == "standalone" else standalone_query
        if task_query:
            tasks[0]["question"] = task_query
    if len(tasks) > MAX_QUERY_TASKS:
        return _too_many_tasks_plan(query, default_cohort), []
    for index, task in enumerate(tasks, start=1):
        task["id"] = f"t{index}"

    if not tasks:
        return safe_rag_fallback_plan(
            query, default_cohort, reason="invalid_plan_to_safe_rag"
        ), (errors or ["missing_valid_tasks"])

    plan = {
        "schema_version": QUERY_PLAN_SCHEMA_VERSION,
        "context_mode": context_mode,
        "normalized_query": normalized_query,
        "standalone_query": standalone_query,
        "referenced_turns": referenced_turns,
        "out_of_domain": out_of_domain,
        "tasks": tasks,
        "planner_fallback": payload.get("planner_fallback"),
        "planner_validation_errors": errors,
    }
    if context_mode == "ambiguous" and not any(
        task["mode"] == "clarify" for task in tasks
    ):
        plan["tasks"] = [_clarify_task("t1", query)]
    return plan, errors


def visible_history_turns(
    chat_history: list[dict[str, str]] | None,
) -> dict[int, tuple[str, str]]:
    """One bounded history view for both prompt display and slot grounding."""
    turns: dict[int, tuple[str, str]] = {}
    for index, item in enumerate((chat_history or [])[-4:]):
        if not isinstance(item, dict):
            continue
        content = str(item.get("content") or "")[:300]
        if content.strip():
            turns[index] = (str(item.get("role") or "user"), content)
    return turns


def grounding_text(query: str, plan: dict[str, Any], chat_history: list[dict[str, str]] | None) -> str:
    """The student's words a plan's slot values must come from.

    The question, plus for a follow-up the history turns the plan references:
    the same text `normalize_query_plan` checked the plan against. A task's
    `question` is the planner's own rewording, so values are never grounded
    in it alone.
    """
    if plan.get("context_mode") != "follow_up":
        return query
    turns = visible_history_turns(chat_history)
    referenced = [turns[index][1] for index in plan.get("referenced_turns") or [] if index in turns]
    return "\n".join([query, *referenced])


def _history_references(
    payload: dict[str, Any],
    context_mode: str,
    visible_history: dict[int, str] | None,
    grounding_context: str,
) -> tuple[str | None, list[int], str] | None:
    """The standalone text, referenced turns and grounding text of a follow-up.

    Only a follow-up keeps them. With the visible history supplied (the
    runtime), the planner must give a standalone text and reference only turns
    the student can see; the grounding text is then those turns. Returns
    None when a follow-up breaks that rule.
    """
    standalone_query = str(payload.get("standalone_query") or "").strip() or None
    raw_references = payload.get("referenced_turns") or []
    referenced_turns = list(dict.fromkeys(
        value
        for value in (raw_references if isinstance(raw_references, list) else [])
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
    ))
    if context_mode != "follow_up":
        return None, [], ""
    if visible_history is None:
        return standalone_query, referenced_turns, grounding_context
    if (
        not isinstance(payload.get("standalone_query"), str)
        or not standalone_query
        or not referenced_turns
        or not isinstance(raw_references, list)
        or any(
            type(value) is not int or value not in visible_history
            for value in raw_references
        )
    ):
        return None
    return (
        standalone_query,
        referenced_turns,
        "\n".join(visible_history[index] for index in referenced_turns),
    )


def _clarification_plan(
    query: str,
    clarification: str,
    *,
    fallback: str | None,
    cohorts: list[str] | None = None,
    errors: list[str] | None = None,
    task_errors: list[str] | None = None,
) -> dict[str, Any]:
    """A plan whose only task asks the student one clarifying question."""
    return {
        "schema_version": QUERY_PLAN_SCHEMA_VERSION,
        "context_mode": "ambiguous",
        "normalized_query": query,
        "standalone_query": None,
        "referenced_turns": [],
        "out_of_domain": False,
        "tasks": [_clarify_task(
            "t1",
            query,
            cohorts=cohorts,
            clarification=clarification,
            validation_errors=task_errors,
        )],
        "planner_fallback": fallback,
        "planner_validation_errors": errors if errors is not None else [],
    }


def _task_numeric_operands(
    task: dict[str, Any], source_text: str, registry: dict[str, Any],
) -> dict[str, list[str]]:
    """Collect supplied scalar operands grounded in user text, never task prose."""
    if task.get("mode") != "structured":
        return {}
    schema = (registry.get("tools", {}).get(task.get("lookup_type")) or {}).get("slot_schema") or {}
    operands: dict[str, list[str]] = {}
    for name, value in (task.get("slots") or {}).items():
        spec = schema.get(name) or {}
        if spec.get("verification_role", "result_input") != "result_input" or spec.get("enum") or spec.get("canonical_values"):
            continue
        for item in slot_values(value):
            if parse_score(item) is None:
                continue
            score = grounded_score(item, (task.get("slot_spans") or {}).get(name), source_text)
            if score is not None:
                operands.setdefault(name, []).append(
                    f"{score.value}/{score.scale}" if score.scale is not None else str(score.value)
                )
    return operands


def _validate_task_bindings(
    tasks: list[dict[str, Any]], *, source_text: str, registry: dict[str, Any],
    single_question: str | None,
) -> dict[str, list[str]]:
    """Reject explicit self-contradictions, not missing or paraphrased information.

    This bounded consistency check does not reinterpret semantic selectors or
    assign an entity's value. Validated user grounding remains authoritative.
    A sibling-operand conflict additionally requires an anchored user clause;
    paraphrased omissions, unrelated quantities and source-book locators are
    not proof of ownership. Explicit denominator conflicts remain detectable.
    """
    numeric = [_task_numeric_operands(task, source_text, registry) for task in tasks]
    errors: dict[str, list[str]] = {}
    for index, task in enumerate(tasks):
        if task.get("mode") == "clarify":
            continue
        question = single_question or str(task.get("question") or "")
        # An explicitly printed source edition is not the student's execution
        # cohort. Plain "theo sổ tay K50" requests and comparisons are not removed.
        scope_question = re.sub(
            rf"(?i)(?:được\s+)?in\s+(?:trong|ở|tại)\s+(?:cuốn\s+)?sổ\s+tay"
            rf"(?:\s+sinh\s+viên)?\s*(?:khóa\s+)?{build_cohort_token_regex().pattern}", " ", question,
        )
        explicit = set(extract_cohorts_from_query(scope_question))
        comparison = any(phrase in _fold_query(scope_question) for phrase in _COMPARISON_PHRASES)
        task_errors: list[str] = []
        if (len(explicit) == 1 or (explicit and comparison)) and explicit != set(task.get("cohorts") or []):
            task_errors.append("task_cohort_conflict")
        # Article/paragraph locators and cohort IDs are not personal operands.
        numeric_question = re.sub(r"(?i)\b(?:điều|khoản|mục)\s+\d+[a-zđ]?\b", " ", question)
        numeric_question = re.sub(r"(?i)(?<!\w)[+-]?\d+(?:[.,]\d+)?\s*(?:tín\s+chỉ|credits?)\b", " ", numeric_question)
        clause = " ".join(question.casefold().split()).rstrip(" ?.!;")
        anchored_clause = bool(clause) and clause in " ".join(source_text.casefold().split())
        for name, values in numeric[index].items():
            peers = [value for other_index, other in enumerate(numeric) if other_index != index
                     for value in other.get(name, [])]
            for value in values:
                if grounded_score(value, numeric_question, numeric_question) is not None:
                    continue
                score = parse_score(value)
                local = grounded_score(str(score.value), numeric_question, numeric_question)
                scale_conflict = (local is not None and local.scale is not None
                                  and score.scale is not None and local.scale != score.scale)
                if scale_conflict or (anchored_clause and any(
                    grounded_score(peer, numeric_question, numeric_question) is not None for peer in peers
                )):
                    task_errors.append(f"task_operand_conflict:{name}")
                    break
        if task_errors:
            errors[task["id"]] = task_errors
    return errors


def _normalize_task(
    raw_task: dict[str, Any],
    *,
    task_id: str,
    original_query: str,
    selected_cohort: str | None,
    grounding_context: str,
    registry: dict[str, Any],
    fallback_cohorts: list[str] | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """Normalize and validate one planner task without invalidating siblings.

    A clarify or RAG task is kept as such (a RAG task with no cohort covers
    every cohort). A structured task with an unknown lookup asks what to look
    up; one that is valid runs as a lookup; one that lacks only the student's
    own inputs asks for them; any other contract error degrades that task to
    regulation RAG. The returned errors remain available for planner
    observability.
    """

    mode = str(raw_task.get("mode") or "").strip().lower()
    question = str(raw_task.get("question") or original_query).strip() or original_query
    errors: list[str] = []
    if mode not in ALLOWED_TASK_MODES:
        mode = "rag"
        errors.append("invalid_mode")
    cohorts, invalid_cohort = _task_cohorts(
        raw_task, question, selected_cohort, fallback_cohorts,
    )
    if invalid_cohort:
        errors.append("invalid_cohort")

    lookup_type = raw_task.get("lookup_type")
    lookup_type = str(lookup_type).strip().lower() if lookup_type else None
    intent = str(raw_task.get("intent") or "open_question").strip().lower()
    clarification = str(raw_task.get("clarification_question") or "").strip() or None
    slots, spans = _task_slots_and_spans(raw_task, lookup_type, registry, original_query)

    if mode == "structured" and intent == "compare":
        intent = _structured_lookup_intent(
            registry.get("tools", {}).get(lookup_type, {}),
            slots,
        )

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
        return _rag_task(task_id, question, cohorts, errors), errors

    if lookup_type not in registry.get("tools", {}):
        errors.append("unknown_lookup_type")
        return _clarify_task(
            task_id,
            question,
            cohorts=cohorts,
            clarification="Mình chưa xác định được loại thông tin cần tra. Bạn có thể nói rõ hơn không?",
            validation_errors=errors,
        ), errors

    return _normalize_structured_task(
        task_id,
        question,
        lookup_type=lookup_type,
        intent=intent,
        slots=slots,
        spans=spans,
        cohorts=cohorts,
        selected_cohort=selected_cohort,
        clarification=clarification,
        original_query=original_query,
        grounding_context=grounding_context,
        registry=registry,
        errors=errors,
    )


def _task_cohorts(
    raw_task: dict[str, Any],
    question: str,
    selected_cohort: str | None,
    fallback_cohorts: list[str] | None,
) -> tuple[list[str], bool]:
    """The task's supported cohorts, and whether the planner named an unsupported one.

    Without a valid cohort from the planner, the cohorts named in the task's
    own question are used, then the plan's fallback cohorts.
    """
    supported_cohorts = set(valid_cohorts())
    raw_cohorts = raw_task.get("cohorts")
    cohorts = []
    invalid_cohort = False
    if isinstance(raw_cohorts, list):
        cohorts = [normalize_cohort(value) for value in raw_cohorts]
        invalid_cohort = any(value and value not in supported_cohorts for value in cohorts)
        cohorts = [value for value in cohorts if value in supported_cohorts]
    cohorts = list(dict.fromkeys(cohorts))
    if cohorts:
        return cohorts, invalid_cohort
    fallback_cohort = normalize_cohort(selected_cohort)
    if fallback_cohort not in supported_cohorts:
        fallback_cohort = None
    task_question_cohorts = [
        normalized
        for value in extract_cohorts_from_query(question)
        if (normalized := normalize_cohort(value)) in supported_cohorts
    ]
    if fallback_cohorts is None:
        fallback_cohorts = [fallback_cohort] if fallback_cohort else []
    else:
        fallback_cohorts = [
            cohort for cohort in fallback_cohorts if cohort in supported_cohorts
        ]
    return list(dict.fromkeys(task_question_cohorts or fallback_cohorts)), invalid_cohort


def _task_slots_and_spans(
    raw_task: dict[str, Any],
    lookup_type: str | None,
    registry: dict[str, Any],
    original_query: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    slots = (
        dict(raw_task.get("slots")) if isinstance(raw_task.get("slots"), dict) else {}
    )
    # Strict structured output must serialize every declared key. Its nullable
    # placeholders mean absent inputs, never selector values for the executor.
    # Keep unknown keys (even null) so the contract validator can reject them.
    declared_slots = (registry.get("tools", {}).get(lookup_type) or {}).get("slot_schema", {})
    slots = {key: value for key, value in slots.items()
             if value is not None or key not in declared_slots}
    raw_spans = (
        dict(raw_task.get("slot_spans"))
        if isinstance(raw_task.get("slot_spans"), dict)
        else {}
    )
    spans = {
        key: value
        for key, raw_value in raw_spans.items()
        if (value := _normalize_span_value(raw_value, original_query))
        not in (None, "", [])
    }
    return slots, spans


def _rag_task(
    task_id: str,
    question: str,
    cohorts: list[str],
    errors: list[str],
    normalization_warnings: list[str] | None = None,
) -> dict[str, Any]:
    """A regulation RAG task.

    A regulation question without an explicit/UI cohort is applicable to every
    supported handbook edition. Keep one logical task and let the executor
    retrieve independently per cohort, matching the multi-cohort execution
    contract instead of using one biased global top-k pool.
    """
    return {
        "id": task_id,
        "question": question,
        "mode": "rag",
        "intent": "open_question",
        "lookup_type": None,
        "slots": {},
        "slot_spans": {},
        "cohorts": cohorts or list(valid_cohorts()),
        "clarification_question": None,
        "validation_errors": errors.copy(),
        **(
            {"normalization_warnings": normalization_warnings}
            if normalization_warnings
            else {}
        ),
    }


_SLOT_PROBLEMS = (
    "missing_slot_span",
    "ungrounded_slot",
    "misgrounded_slot",
    "invalid_slot_type",
    "invalid_slot_value",
    "slot_span_mismatch",
)


def _normalize_structured_task(
    task_id: str,
    question: str,
    *,
    lookup_type: str,
    intent: str,
    slots: dict[str, Any],
    spans: dict[str, Any],
    cohorts: list[str],
    selected_cohort: str | None,
    clarification: str | None,
    original_query: str,
    grounding_context: str,
    registry: dict[str, Any],
    errors: list[str],
) -> tuple[dict[str, Any], list[str]]:
    """Validate a structured task against its lookup contract and the question."""
    task_cohort = cohorts[0] if cohorts else normalize_cohort(selected_cohort)
    # Prepare only values/spans supplied by this task. Validate against the
    # complete user query so a task-local paraphrase cannot introduce factual
    # values absent from the original context.
    decision = prepare_structured_task(
        question,
        lookup_type=lookup_type,
        intent=intent,
        slots=slots,
        slot_spans=spans,
        cohort=task_cohort,
        registry=registry,
    )
    validate = partial(
        validate_structured_task,
        query=original_query,
        grounding_context=grounding_context,
        registry=registry,
    )
    validation_errors = validate(decision)
    spec = registry.get("tools", {}).get(lookup_type, {})
    required_slots = set(
        (spec.get("required_slots") or {}).get(decision.get("intent"), [])
    )
    reading_warnings = _apply_declared_reading_defaults(decision, spec, required_slots)
    if reading_warnings:
        validation_errors = validate(decision)
    normalization_warnings = reading_warnings + _drop_invalid_optional_slots(
        decision, validation_errors, spec=spec, required_slots=required_slots,
    )
    if normalization_warnings:
        validation_errors = validate(decision)
    if validation_errors:
        errors.extend(validation_errors)
        # Ask only when every error is a required input the student has not
        # given (or the cohort). The set is compared with the list, so a
        # repeated error also leads to RAG, as it always has.
        missing_student_input = {
            error
            for error in validation_errors
            if error == "missing_cohort"
            or (
                error.partition(":")[0] in {"missing_slot", *_SLOT_PROBLEMS}
                and error.partition(":")[2] in required_slots
            )
        }
        if len(missing_student_input) == len(validation_errors):
            return _clarify_task(
                task_id,
                question,
                cohorts=cohorts,
                clarification=clarification
                or _ask_for_missing_inputs(missing_student_input, spec)
                or "Bạn có thể nói rõ hơn phần thông tin cần tra cứu không?",
                validation_errors=errors,
                normalization_warnings=normalization_warnings,
            ), errors

        # A structured task must never reach the executor with unresolved
        # contract errors. Preserve sibling tasks by degrading only this task
        # to regulation RAG instead of invalidating the complete plan.
        return _rag_task(task_id, question, cohorts, errors, normalization_warnings), errors

    return {
        "id": task_id,
        "question": question,
        "mode": "structured",
        "intent": decision.get("intent"),
        "lookup_type": decision.get("lookup_type"),
        "slots": decision.get("slots") or {},
        "slot_spans": decision.get("slot_spans") or {},
        "cohorts": cohorts or ([task_cohort] if task_cohort else []),
        "clarification_question": clarification,
        "validation_errors": errors.copy(),
        **(
            {"normalization_warnings": normalization_warnings}
            if normalization_warnings
            else {}
        ),
    }, errors


def _apply_declared_reading_defaults(
    decision: dict[str, Any], spec: dict[str, Any], required_slots: set[str],
) -> list[str]:
    """Fall back to the registry's default when a field choice is unusable.

    A reading intent only names which field of a found record to show, so the
    student has already said it and cannot help; asking them would hand the
    planner's slip to them. Where the executor has a safe default anyway (a
    contact card holds every field; the program catalog resolves the faculty)
    the registry declares it as `default_reading` and it is used here. A slot
    with no declared default, such as which formula to read, still asks.
    """
    slots = dict(decision.get("slots") or {})
    warnings = []
    for name, schema in (spec.get("slot_schema") or {}).items():
        default = schema.get("default_reading")
        if (
            name not in required_slots
            or default is None
            or str(schema.get("verification_role") or "") != "reading_intent"
        ):
            continue
        enum = schema.get("enum") or []
        value = slots.get(name)
        chosen = [item for item in (value if isinstance(value, list) else [value]) if item not in (None, "")]
        if chosen and all(item in enum for item in chosen):
            continue
        slots[name] = default
        warnings.append(f"reading_default_applied:{name}")
    if warnings:
        decision["slots"] = slots
        decision["slot_spans"] = {k: v for k, v in (decision.get("slot_spans") or {}).items()
                                  if f"reading_default_applied:{k}" not in warnings}
    return warnings


COHORT_CLARIFICATION_LABEL = "khóa bạn đang học"


def _ask_for_missing_inputs(
    errors: set[str], spec: dict[str, Any],
) -> str | None:
    """Name what is missing, from the labels the registry declares.

    The fallback this replaces asked the student to "bổ sung thông tin còn
    thiếu để mình tra đúng bảng", which says nothing about what to add and
    mentions a table even for a directory question. Without a declared label
    the caller keeps its own wording.
    """
    slot_schema = spec.get("slot_schema") or {}
    labels: list[str] = []
    for error in sorted(errors):
        if error == "missing_cohort":
            labels.append(COHORT_CLARIFICATION_LABEL)
            continue
        label = (slot_schema.get(error.partition(":")[2]) or {}).get("clarification_label")
        if label:
            labels.append(str(label))
    labels = list(dict.fromkeys(labels))
    if not labels:
        return None
    return f"Bạn cho mình biết {' và '.join(labels)} nhé."


def _drop_invalid_optional_slots(
    decision: dict[str, Any],
    validation_errors: list[str],
    *,
    spec: dict[str, Any],
    required_slots: set[str],
) -> list[str]:
    """Remove optional slots that failed validation; return their errors as warnings.

    Invalid optional hints cannot determine execution. Table-first tasks keep
    their complete table; directory tasks let the catalog matcher consume the
    trusted task-local question. Required slots are never dropped.
    """
    slot_schema = spec.get("slot_schema") or {}
    optional_invalid = {
        error.partition(":")[2]
        for error in validation_errors
        if error.startswith(
            tuple(f"{problem}:" for problem in _SLOT_PROBLEMS) + ("unknown_slot:", "unknown_slot_span:")
        )
        and error.partition(":")[2] not in required_slots
        and (
            spec.get("selection_mode") == "table_first"
            or str(
                (slot_schema.get(error.partition(":")[2]) or {}).get(
                    "verification_role"
                )
            )
            == "directory_entity"
        )
    }
    if not optional_invalid:
        return []
    decision["slots"] = {
        key: value
        for key, value in (decision.get("slots") or {}).items()
        if key not in optional_invalid
    }
    decision["slot_spans"] = {
        key: value
        for key, value in (decision.get("slot_spans") or {}).items()
        if key not in optional_invalid
    }
    return list(
        dict.fromkeys(
            error
            for error in validation_errors
            if error.partition(":")[2] in optional_invalid
        )
    )


def _structured_lookup_intent(
    spec: dict[str, Any],
    slots: dict[str, Any],
) -> str:
    """Map presentation wording to the underlying structured fetch operation.

    Comparison changes answer composition, not which reference table is fetched.
    Pick a supported base intent for compatibility with the existing QueryPlan
    schema.  The original task question retains the presentation request for the
    answer composer, for both single- and multi-cohort comparisons.
    """

    allowed = [
        str(intent) for intent in spec.get("intents") or [] if str(intent) != "compare"
    ]
    preferred = ["direct_value", "list_items"]
    default_intent = spec.get("default_intent")
    if default_intent:
        preferred.append(str(default_intent))
    preferred.extend(allowed)

    for candidate in dict.fromkeys(preferred):
        if candidate not in allowed:
            continue
        required = (spec.get("required_slots") or {}).get(candidate, [])
        if all(_task_slot_is_present(slots.get(name)) for name in required):
            return candidate
    return "compare"


def _task_slot_is_present(value: Any) -> bool:
    return value is not None and value not in ("", [], {})


def _clarify_task(
    task_id: str,
    question: str,
    *,
    cohorts: list[str] | None = None,
    clarification: str | None = None,
    validation_errors: list[str] | None = None,
    normalization_warnings: list[str] | None = None,
) -> dict[str, Any]:
    task = {
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
    if normalization_warnings:
        task["normalization_warnings"] = list(dict.fromkeys(normalization_warnings))
    return task


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
            if (item := _normalize_span_value(raw_item, source_text))
            not in (None, "", [])
        ]
        return normalized
    return str(value).strip() if value is not None else None


def _merge_compatible_structured_tasks(
    tasks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Deduplicate identical lookups without discarding distinct task text."""
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
            " ".join(str(task.get("question") or "").casefold().split()),
        )
        existing_index = index_by_key.get(key)
        if existing_index is None:
            index_by_key[key] = len(merged)
            merged.append(task)
            continue
        existing = merged[existing_index]
        # Missing and conflicting selectors are both meaningful. Never repair
        # a merge by deleting operands and re-reading the compound question.
        if (existing.get("slots") or {}) != (task.get("slots") or {}):
            merged.append(task)
            continue
        # With identical selectors, retain the first grounded task unchanged.
        existing["validation_errors"] = list(
            dict.fromkeys(
                (existing.get("validation_errors") or [])
                + (task.get("validation_errors") or [])
            )
        )
        warnings = list(
            dict.fromkeys(
                (existing.get("normalization_warnings") or [])
                + (task.get("normalization_warnings") or [])
            )
        )
        if warnings:
            existing["normalization_warnings"] = warnings
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
    return _clarification_plan(
        query,
        "Câu hỏi đang có nhiều hơn ba yêu cầu độc lập. "
        "Bạn có thể chọn tối đa ba nội dung cần tra trước không?",
        cohorts=[normalized_cohort] if normalized_cohort else [],
        fallback=None,
        errors=["too_many_tasks"],
        task_errors=["too_many_tasks"],
    )
