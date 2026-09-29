"""Offline regressions for the independently audited planner contract.

Fixtures are synthetic development cases, not a new accuracy benchmark.
No provider, catalog service, or retrieval service is contacted.
"""

from copy import deepcopy
import json
from types import SimpleNamespace

from jsonschema import Draft202012Validator
import pytest

from src.common.cohort import valid_cohorts
from src.common.key_pool import KeyPoolConfig
from src.generation.plan_executor import PlanExecutor
from src.retrieval.core import ai_router as router_module
from src.retrieval.core import structured_dispatcher as dispatcher
from src.retrieval.core.ai_router import AIRouter, _RouterCompletion
from src.retrieval.core.query_plan import (
    normalize_query_plan,
    query_plan_response_schema,
)
from src.retrieval.core.structured_routing import (
    compact_registry_for_prompt,
    load_lookup_registry,
    validate_structured_task,
)


REGISTRY = load_lookup_registry()
TOOL_INTENTS = [
    (tool, intent)
    for tool, spec in REGISTRY["tools"].items()
    for intent in spec["intents"]
]


@pytest.fixture
def validator():
    schema = query_plan_response_schema()
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _plan(
    mode="rag",
    *,
    query="Xin hỏi thông tin.",
    tool=None,
    intent=None,
    slots=None,
    spans=None,
):
    return {
        "schema_version": "v1",
        "context_mode": "standalone",
        "normalized_query": query,
        "standalone_query": None,
        "referenced_turns": [],
        "out_of_domain": False,
        "tasks": [
            {
                "id": "t1",
                "question": query,
                "mode": mode,
                "intent": intent
                or {
                    "rag": "open_question",
                    "clarify": "clarify",
                    "structured": "contact",
                }[mode],
                "lookup_type": tool,
                "slots": slots or {},
                "slot_spans": spans or {},
                "cohorts": ["K50"],
                "clarification_question": "Bạn muốn hỏi nội dung nào?"
                if mode == "clarify"
                else None,
            }
        ],
    }


def _structured(tool, intent):
    # Independent authored input, not generated from required_slots or gold.
    question = "Cho biết bảng tham chiếu."
    slots, spans = {}, {}
    if tool in {"office", "faculty"}:
        entity = "Phòng Đào tạo" if tool == "office" else "Khoa Toán"
        question = f"Email {entity} là gì?"
        slots = {tool: entity, "requested_field": "email"}
        spans = {tool: entity, "requested_field": "Email"}
    elif tool == "student_service":
        question = "Đơn vị nào hướng dẫn dùng thư viện?"
        slots = {"service": "hướng dẫn dùng thư viện", "requested_field": "unit"}
        spans = {"service": "hướng dẫn dùng thư viện", "requested_field": "Đơn vị"}
    elif tool == "program":
        question = "Ngành Toán thuộc khoa nào?"
        if intent == "list_items":
            question, slots = "Trường có những ngành nào?", {"scope": "school"}
        else:
            slots = {"program_or_faculty": "Toán"}
            spans = {"program_or_faculty": "Toán"}
            if intent == "direct_value":
                slots["requested_field"] = "faculty"
            else:
                question = "Trường có ngành Toán không?"
    elif tool == "formula":
        question = "Công thức GPA có trọng số là gì?"
        slots = {"formula_type": "gpa_weighted_average"}
    return _plan(
        "structured", query=question, tool=tool, intent=intent, slots=slots, spans=spans
    )


def test_schema_enums_and_prompt_registry_match_current_registry(validator):
    task = validator.schema["properties"]["tasks"]["items"]["properties"]
    assert set(task["lookup_type"]["anyOf"][0]["enum"]) == set(REGISTRY["tools"])
    assert task["cohorts"]["items"]["enum"] == list(valid_cohorts())
    lines = compact_registry_for_prompt().splitlines()
    assert len(lines) == len(REGISTRY["tools"])
    for line in lines:
        tool, rest = line.split("|use=", 1)
        _, rest = rest.split("|intents=", 1)
        intents, rest = rest.split("|required=", 1)
        required, slots = rest.split("|slots=", 1)
        spec = REGISTRY["tools"][tool]
        assert intents.split(",") == spec["intents"]
        assert json.loads(required) == spec["required_slots"]
        compact_slots = json.loads(slots)
        assert set(compact_slots) == set(spec["slot_schema"])
        for required_slots in spec["required_slots"].values():
            assert set(required_slots) <= set(compact_slots)
        for name, slot in spec["slot_schema"].items():
            assert compact_slots[name]["type"] == slot["type"]
            allowed = slot.get("enum") or slot.get("canonical_values") or []
            assert set(compact_slots[name].get("values", [])) == set(allowed)


def test_all_declared_required_fields_are_enforced_by_schema(validator):
    payload = _plan()
    for field in validator.schema["required"]:
        incomplete = deepcopy(payload)
        del incomplete[field]
        assert not validator.is_valid(incomplete), field
    for field in validator.schema["properties"]["tasks"]["items"]["required"]:
        incomplete = deepcopy(payload)
        del incomplete["tasks"][0][field]
        assert not validator.is_valid(incomplete), field


def _resolve(task, query):
    return dispatcher.resolve_structured_task(
        task,
        query=query,
        cohort="K50",
        formula_rules=[],
        office_directory=[],
        student_service_directory=[],
        student_faculty_profiles=[],
        structured_tables_registry=[],
        program_directory=[],
        directory_selector=None,
    )


@pytest.mark.parametrize("tool", list(REGISTRY["tools"]))
def test_each_registered_tool_has_a_dispatch_path(monkeypatch, tool):
    calls = []

    def record(name):
        def lookup(*args, **kwargs):
            calls.append(name)
            return None

        return lookup

    for name in (
        "_reference_table_lookup",
        "office_lookup",
        "program_lookup",
        "formula_lookup",
    ):
        monkeypatch.setattr(dispatcher, name, record(name))
    expected = {
        "foreign_language": "_reference_table_lookup",
        "study_duration": "_reference_table_lookup",
        "scholarship_classification": "_reference_table_lookup",
        "scoring": "_reference_table_lookup",
        "student_service": "office_lookup",
        "office": "office_lookup",
        "faculty": "office_lookup",
        "program": "program_lookup",
        "formula": "formula_lookup",
    }
    payload = _structured(tool, REGISTRY["tools"][tool]["intents"][0])
    normalized, errors = normalize_query_plan(
        payload, query=payload["normalized_query"]
    )
    assert errors == []
    _resolve(normalized["tasks"][0], payload["normalized_query"])
    assert calls == [expected[tool]]


def test_multiple_requested_fields_keep_machine_readable_structure(
    validator, monkeypatch
):
    query = "Email và số điện thoại Phòng Đào tạo là gì?"
    payload = _structured("office", "contact")
    payload["normalized_query"] = query
    payload["tasks"][0].update(
        question=query,
        slots={"office": "Phòng Đào tạo", "requested_field": ["email", "phone"]},
        slot_spans={
            "office": "Phòng Đào tạo",
            "requested_field": ["Email", "số điện thoại"],
        },
    )
    validator.validate(payload)
    normalized, errors = normalize_query_plan(payload, query=query)
    assert errors == []
    monkeypatch.setattr(
        dispatcher,
        "office_lookup",
        lambda *args, **kwargs: {
            "email": "example@example.invalid",
            "phone": "000",
            "content_type": "student_office_profile",
        },
    )
    result = _resolve(normalized["tasks"][0], query)
    assert result.result["requested_field"] == ["email", "phone"]


@pytest.mark.parametrize(("tool", "intent"), TOOL_INTENTS)
def test_every_registered_tool_intent_has_a_valid_normalized_example(
    validator, tool, intent
):
    payload = _structured(tool, intent)
    validator.validate(payload)
    normalized, errors = normalize_query_plan(
        payload, query=payload["normalized_query"]
    )
    task = normalized["tasks"][0]
    assert errors == []
    assert task["mode"] == "structured"
    assert (task["lookup_type"], task["intent"]) == (tool, intent)
    assert task["slots"] == payload["tasks"][0]["slots"]
    assert (
        validate_structured_task(
            {**task, "cohort": "K50"}, query=payload["normalized_query"]
        )
        == []
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", "v99"),
        ("out_of_domain", "false"),
        ("context_mode", "unknown"),
        ("referenced_turns", [True]),
        ("tasks", None),
        ("undeclared", "value"),
    ],
)
def test_schema_rejects_invalid_top_level_values(validator, field, value):
    payload = _plan()
    payload[field] = value
    assert not validator.is_valid(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mode", "sql"),
        ("lookup_type", "invented_tool"),
        ("cohorts", ["K999"]),
        ("slots", []),
        ("slot_spans", {"office": {"start": 1, "end": 5}}),
        ("resolved_result", {"answer": "invented"}),
    ],
)
def test_schema_rejects_invalid_task_values(validator, field, value):
    payload = _plan()
    payload["tasks"][0][field] = value
    assert not validator.is_valid(payload)


@pytest.mark.parametrize(
    ("slots", "spans", "error"),
    [
        ({"requested_field": "email"}, {}, "missing_slot:office"),
        (
            {"office": 123, "requested_field": "email"},
            {"office": "123"},
            "invalid_slot_type:office",
        ),
        (
            {"office": "Phòng Đào tạo", "requested_field": "fax"},
            {"office": "Phòng Đào tạo"},
            "invalid_slot_value:requested_field",
        ),
        (
            {"office": "Phòng Tài chính", "requested_field": "email"},
            {"office": "Phòng Tài chính"},
            "ungrounded_slot:office",
        ),
        (
            {"office": "Phòng Đào tạo", "requested_field": "email", "sql": "SELECT 1"},
            {"office": "Phòng Đào tạo"},
            "unknown_slot:sql",
        ),
    ],
)
def test_shape_valid_but_unsafe_structured_task_does_not_execute(
    validator, slots, spans, error
):
    query = "Email Phòng Đào tạo là gì?"
    payload = _plan("structured", query=query, tool="office", slots=slots, spans=spans)
    validator.validate(payload)  # Deliberately open slots in the raw schema.
    normalized, errors = normalize_query_plan(payload, query=query)
    assert f"t1:{error}" in errors
    assert normalized["tasks"][0]["mode"] in {"rag", "clarify"}


def test_rag_with_lookup_is_shape_valid_but_normalizer_removes_lookup(validator):
    payload = _plan(tool="office")
    validator.validate(payload)
    normalized, errors = normalize_query_plan(payload, query="Xin hỏi thông tin.")
    assert errors == ["t1:rag_must_not_select_lookup"]
    assert normalized["tasks"][0]["lookup_type"] is None


def test_raw_task_tolerance_is_not_execution_limit(validator):
    payload = _plan()
    payload["tasks"] = [deepcopy(payload["tasks"][0]) for _ in range(4)]
    for index, task in enumerate(payload["tasks"]):
        task.update(id=f"t{index + 1}", question=f"Chủ đề độc lập {index}")
    validator.validate(payload)
    normalized, errors = normalize_query_plan(payload, query="Bốn chủ đề độc lập.")
    assert errors == []
    assert len(normalized["tasks"]) == 1
    assert normalized["tasks"][0]["mode"] == "clarify"


@pytest.fixture
def offline_router(monkeypatch):
    monkeypatch.setattr(router_module, "load_project_env", lambda: None)
    monkeypatch.setenv("OPENAI_API_KEY", "offline-dummy")
    router = AIRouter(
        cache_enabled=False,
        max_retries=0,
        key_pool_config=KeyPoolConfig(
            name="audit", rpm_limit_per_key=600, state_path=None
        ),
    )

    # All calls must be replaced explicitly by the test. No accidental inference.
    def forbidden(**kwargs):
        raise AssertionError("Provider calls are forbidden in contract audit")

    monkeypatch.setattr(router, "_chat_completion", forbidden)
    return router


def _respond(monkeypatch, router, payload):
    monkeypatch.setattr(
        router,
        "_chat_completion",
        lambda **kwargs: _RouterCompletion(
            json.dumps(payload), {"input": 1, "output": 1, "total": 2}, "stop"
        ),
    )


def test_string_false_must_not_silently_become_out_of_domain(
    validator, offline_router, monkeypatch
):
    payload = _structured("office", "contact")
    payload["out_of_domain"] = "false"
    assert not validator.is_valid(payload)
    _respond(monkeypatch, offline_router, payload)
    result = offline_router.plan(payload["normalized_query"], cohort="K50")
    assert result["out_of_domain"] is False
    assert result["planner_fallback"] == "invalid_plan_control"
    assert result["planner_validation_errors"] == ["invalid_out_of_domain_type"]


def test_wrong_task_cohort_cannot_silently_override_explicit_query(validator):
    query = "K50 được bảo lưu thế nào?"
    payload = _plan(query=query)
    payload["tasks"][0]["cohorts"] = ["K51"]
    validator.validate(payload)
    result, errors = normalize_query_plan(payload, query=query, selected_cohort="K51")
    assert errors == []
    assert result["tasks"][0]["cohorts"] == ["K50"]
    assert payload["tasks"][0]["cohorts"] == ["K51"]  # No mutation of the raw log.


@pytest.mark.parametrize("context_mode", ["standalone", "follow_up"])
def test_unseen_history_reference_is_rejected_or_cleared(
    validator, offline_router, monkeypatch, context_mode
):
    payload = _plan()
    payload.update(
        context_mode=context_mode,
        standalone_query="Thông tin được nhắc trước đó.",
        referenced_turns=[999],
    )
    validator.validate(payload)
    _respond(monkeypatch, offline_router, payload)
    result = offline_router.plan("Xin hỏi thông tin.", cohort="K50", chat_history=[])
    assert result.get("planner_validation_errors") or result["referenced_turns"] == []
    assert result["standalone_query"] is None
    if context_mode == "follow_up":
        assert result["tasks"][0]["mode"] == "clarify"
        assert result["planner_fallback"] == "invalid_history_reference"


@pytest.mark.parametrize("variant", ["standalone", "truncated"])
def test_grounding_cannot_use_forbidden_or_invisible_history(
    validator, offline_router, monkeypatch, variant
):
    query = "Email đơn vị đó là gì?"
    payload = _structured("office", "contact")
    payload["normalized_query"] = query
    payload["tasks"][0]["question"] = query
    history_text = "Phòng Đào tạo"
    if variant == "truncated":
        history_text = "x" * 310 + history_text
        payload.update(
            context_mode="follow_up",
            standalone_query="Email Phòng Đào tạo là gì?",
            referenced_turns=[0],
        )
    history = [{"role": "user", "content": history_text}]
    if variant == "truncated":
        assert (
            "Phòng Đào tạo"
            not in offline_router._build_plan_prompt(
                query, cohort="K50", chat_history=history
            ).split("CHAT HISTORY:", 1)[1]
        )
    validator.validate(payload)
    _respond(monkeypatch, offline_router, payload)
    result = offline_router.plan(query, cohort="K50", chat_history=history)
    assert result["tasks"][0]["mode"] != "structured"


def test_mixed_domain_keeps_only_in_domain_target_without_count_fallback(
    validator, offline_router, monkeypatch
):
    query = "Thứ nhất, email Phòng Đào tạo là gì? Thứ hai, dự báo thời tiết ngày mai?"
    payload = _structured("office", "contact")
    payload["normalized_query"] = query
    validator.validate(payload)
    _respond(monkeypatch, offline_router, payload)
    result = offline_router.plan(query, cohort="K50")
    assert not result.get("planner_fallback")
    assert len(result["tasks"]) == 1
    assert result["tasks"][0]["mode"] == "structured"


@pytest.mark.parametrize("value", ["true", "false", 0, 1, [], {}, [False]])
def test_invalid_ood_types_fail_safely_with_diagnostics(value):
    payload = _plan()
    payload["out_of_domain"] = value
    result, errors = normalize_query_plan(payload, query="Thông tin.")
    assert errors == ["invalid_out_of_domain_type"]
    assert result["out_of_domain"] is False
    assert result["planner_fallback"] == "invalid_plan_control"


@pytest.mark.parametrize("value", [False, True, None])
def test_valid_ood_values_keep_existing_semantics(value):
    payload = _plan()
    payload["out_of_domain"] = value
    result, errors = normalize_query_plan(payload, query="Thông tin.")
    assert errors == []
    assert result["out_of_domain"] is (value is True)
    assert not result.get("planner_fallback")


@pytest.mark.parametrize("cohorts", [["K50", "K51"], ["K51", "K50"]])
def test_explicit_comparison_keeps_both_cohorts(cohorts):
    query = "So sánh K50 và K51 về bảo lưu."
    payload = _plan(query=query)
    payload["tasks"][0]["cohorts"] = cohorts
    result, errors = normalize_query_plan(payload, query=query, selected_cohort="K50")
    assert errors == []
    assert result["tasks"][0]["cohorts"] == cohorts


def test_multitask_cohort_scopes_are_not_overwritten_globally():
    query = "K50 bảo lưu thế nào, K51 tính học phí thế nào?"
    payload = _plan(query=query)
    first = payload["tasks"][0]
    first.update(question="K50 bảo lưu thế nào?", cohorts=["K50"])
    payload["tasks"].append(
        {
            **deepcopy(first),
            "id": "t2",
            "question": "K51 tính học phí thế nào?",
            "cohorts": ["K51"],
        }
    )
    result, errors = normalize_query_plan(payload, query=query, selected_cohort="K50")
    assert errors == []
    assert [task["cohorts"] for task in result["tasks"]] == [["K50"], ["K51"]]


def test_ui_cohort_does_not_overwrite_populated_task_without_query_cohort():
    payload = _plan(query="Quy định bảo lưu?")
    payload["tasks"][0]["cohorts"] = ["K51"]
    result, errors = normalize_query_plan(
        payload, query="Quy định bảo lưu?", selected_cohort="K50"
    )
    assert errors == []
    assert result["tasks"][0]["cohorts"] == ["K51"]


def _follow_up_payload():
    payload = _structured("office", "contact")
    payload.update(
        context_mode="follow_up",
        normalized_query="Email đơn vị đó là gì?",
        standalone_query="Email Phòng Đào tạo là gì?",
        referenced_turns=[0],
    )
    return payload


@pytest.mark.parametrize("role", ["user", "assistant"])
def test_valid_visible_referenced_history_still_grounds_slots(
    offline_router, monkeypatch, role
):
    payload = _follow_up_payload()
    _respond(monkeypatch, offline_router, payload)
    result = offline_router.plan(
        payload["normalized_query"],
        cohort="K50",
        chat_history=[{"role": role, "content": "Phòng Đào tạo"}],
    )
    assert result["planner_validation_errors"] == []
    assert result["referenced_turns"] == [0]
    assert result["tasks"][0]["mode"] == "structured"


@pytest.mark.parametrize("references", [[True], [-1], [4], [0, 999], "0", 1, [], None])
def test_invalid_history_indices_cannot_drive_a_follow_up(
    offline_router, monkeypatch, references
):
    payload = _follow_up_payload()
    payload["referenced_turns"] = references
    _respond(monkeypatch, offline_router, payload)
    result = offline_router.plan(
        payload["normalized_query"],
        cohort="K50",
        chat_history=[{"role": "user", "content": "Phòng Đào tạo"}],
    )
    assert result["planner_fallback"] == "invalid_history_reference"
    assert result["referenced_turns"] == []
    assert result["tasks"][0]["mode"] == "clarify"


def test_history_window_keeps_displayed_indices_and_only_selected_content(
    offline_router, monkeypatch
):
    history = [
        {"role": "user", "content": content}
        for content in [
            "outside window",
            "",
            "Phòng Đào tạo",
            "other topic",
            "last topic",
        ]
    ]
    prompt = offline_router._build_plan_prompt(
        "Email đơn vị đó?", cohort="K50", chat_history=history
    )
    view = prompt.split("CHAT HISTORY:", 1)[1]
    assert "[1] user:Phòng Đào tạo" in view
    assert "outside window" not in view
    assert "[0]" not in view
    payload = _follow_up_payload()
    payload["referenced_turns"] = [1, 1]
    _respond(monkeypatch, offline_router, payload)
    result = offline_router.plan(
        payload["normalized_query"], cohort="K50", chat_history=history
    )
    assert result["tasks"][0]["mode"] == "structured"
    assert result["referenced_turns"] == [1]
    # An existing but unreferenced turn must not ground the same entity.
    payload["referenced_turns"] = [2]
    _respond(monkeypatch, offline_router, payload)
    result = offline_router.plan(
        payload["normalized_query"], cohort="K50", chat_history=history
    )
    assert result["tasks"][0]["mode"] == "clarify"
    assert "t1:ungrounded_slot:office" in result["planner_validation_errors"]


def test_follow_up_cohort_comparison_not_replaced_by_current_explicit_cohort(
    offline_router, monkeypatch
):
    payload = _plan(query="Còn K51 thì so với khóa đó thế nào?")
    payload.update(
        context_mode="follow_up",
        standalone_query="So sánh K50 với K51.",
        referenced_turns=[0],
    )
    payload["tasks"][0].update(question="So sánh K50 với K51.", cohorts=["K50", "K51"])
    _respond(monkeypatch, offline_router, payload)
    result = offline_router.plan(
        payload["normalized_query"],
        cohort="K50",
        chat_history=[{"role": "user", "content": "K50"}],
    )
    assert result["tasks"][0]["cohorts"] == ["K50", "K51"]


def test_numbered_ood_query_does_not_trigger_count_repair(offline_router, monkeypatch):
    query = "Thứ nhất, thời tiết? Thứ hai, bóng đá?"
    payload = _plan(query=query)
    payload.update(out_of_domain=True, tasks=[])
    calls = []

    def request(**kwargs):
        calls.append(kwargs)
        return _RouterCompletion(
            json.dumps(payload), {"input": 1, "output": 1, "total": 2}, "stop"
        )

    monkeypatch.setattr(offline_router, "_chat_completion", request)
    result = offline_router.plan(query, cohort="K50")
    assert len(calls) == 1
    assert result["out_of_domain"] is True


@pytest.mark.parametrize("value", ["email", "all", ["email", "phone"]])
def test_directory_requested_field_scalar_and_list_contract(monkeypatch, value):
    payload = _structured("office", "contact")
    payload["tasks"][0]["slots"]["requested_field"] = value
    task = normalize_query_plan(payload, query=payload["normalized_query"])[0]["tasks"][
        0
    ]
    monkeypatch.setattr(
        dispatcher,
        "office_lookup",
        lambda *args, **kwargs: {"email": "example@example.invalid"},
    )
    result = _resolve(task, payload["normalized_query"])
    assert result.result["requested_field"] == value
    if isinstance(value, list):
        assert result.result["requested_field"] is not value


def test_numbered_compatible_contact_requests_can_remain_grouped(
    offline_router, monkeypatch
):
    query = "Thứ nhất, email Phòng Đào tạo? Thứ hai, số điện thoại Phòng Đào tạo?"
    payload = _structured("office", "contact")
    payload["normalized_query"] = query
    payload["tasks"][0].update(
        question=query,
        slots={"office": "Phòng Đào tạo", "requested_field": ["email", "phone"]},
    )
    calls = []
    monkeypatch.setattr(offline_router, "_chat_completion", lambda **kwargs: calls.append(1) or _RouterCompletion(
        json.dumps(payload), {"input": 1, "output": 1, "total": 2}, "stop"))
    result = offline_router.plan(query, cohort="K50")
    assert calls == [1]
    assert not result.get("planner_fallback")
    assert len(result["tasks"]) == 1
    assert result["tasks"][0]["slots"]["requested_field"] == ["email", "phone"]


@pytest.mark.parametrize("mode", ["rag", "structured", "clarify", "out_of_domain"])
def test_normalized_modes_reach_matching_executor_branch(validator, monkeypatch, mode):
    payload = (
        _structured("office", "contact")
        if mode == "structured"
        else _plan("clarify" if mode == "clarify" else "rag")
    )
    if mode == "out_of_domain":
        payload.update(out_of_domain=True, tasks=[])
    validator.validate(payload)
    normalized, errors = normalize_query_plan(
        payload, query=payload["normalized_query"]
    )
    assert errors == []
    executor = PlanExecutor(
        router=SimpleNamespace(plan=lambda *args, **kwargs: normalized),
        slang_normalizer=SimpleNamespace(
            replace_for_router=lambda q: q, normalize_for_retrieval=lambda q: q
        ),
        catalogs=None,
        parent_sources_by_id={},
        top_k=5,
        public_source_limit=3,
    )
    calls = []

    def record(kind):
        def execute(**kwargs):
            calls.append((kind, kwargs["cohort"]))
            return {"coverage": "uncovered"}

        return execute

    monkeypatch.setattr(executor, "_execute_planned_rag_task", record("rag"))
    monkeypatch.setattr(
        executor, "_execute_planned_structured_task", record("structured")
    )
    result = executor.run(
        query=payload["normalized_query"], cohort="K50", chat_history=[]
    )
    assert calls == ([(mode, "K50")] if mode in {"rag", "structured"} else [])
    if mode == "out_of_domain":
        assert result["out_of_domain"] is True
    else:
        assert result["query_plan"]["tasks"][0]["mode"] == mode
