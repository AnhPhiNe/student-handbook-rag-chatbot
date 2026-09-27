"""Strict transport contract checks, without asserting provider acceptance."""
from copy import deepcopy

from jsonschema import Draft202012Validator
import pytest
import yaml

from scripts.run_luna_contact_smoke import CASES
from src.retrieval.core.query_plan import (
    normalize_query_plan, query_plan_strict_response_schema,
)
from src.retrieval.core.structured_routing import load_lookup_registry, validate_structured_task


def _payload(task, query="Xin hỏi thông tin."):
    return {"schema_version": "v1", "context_mode": "standalone",
            "normalized_query": query, "standalone_query": None,
            "referenced_turns": [], "out_of_domain": False, "tasks": [task]}


def _task(lookup_type, slots, spans=None):
    spec = load_lookup_registry()["tools"][lookup_type]
    return {"id": "t1", "question": "Xin hỏi thông tin.", "mode": "structured",
            "intent": spec["intents"][0], "lookup_type": lookup_type,
            "cohorts": ["K51"], "clarification_question": None,
            "slots": {key: slots.get(key) for key in spec["slot_schema"]},
            "slot_spans": {key: (spans or {}).get(key) for key in spec["slot_schema"]}}


def test_schema_objects_are_closed_required_and_within_provider_limits():
    schema = query_plan_strict_response_schema()
    Draft202012Validator.check_schema(schema)
    assert schema["type"] == "object" and "anyOf" not in schema
    counts = {"properties": 0, "enum": 0}
    unsupported = {"allOf", "not", "if", "then", "else", "dependentRequired", "dependentSchemas", "patternProperties"}

    def visit(node, depth=0):
        if isinstance(node, list):
            for value in node:
                visit(value, depth)
        elif isinstance(node, dict):
            assert not unsupported & node.keys()
            if node.get("type") == "object":
                depth += 1
                assert node["additionalProperties"] is False
                assert set(node["properties"]) == set(node["required"])
                counts["properties"] += len(node["properties"])
            counts["enum"] += len(node.get("enum", []))
            assert depth <= 10
            for value in node.values():
                visit(value, depth)
    visit(schema)
    assert counts["properties"] <= 5000
    assert counts["enum"] <= 1000


@pytest.mark.parametrize("lookup_type", list(load_lookup_registry()["tools"]))
def test_every_registry_slot_enum_and_homogeneous_list_matches_runtime(lookup_type):
    registry = load_lookup_registry()
    spec = registry["tools"][lookup_type]
    schema = query_plan_strict_response_schema()
    branch = next(branch for branch in schema["properties"]["tasks"]["items"]["anyOf"]
                  if branch["properties"]["lookup_type"].get("enum") == [lookup_type])
    assert set(branch["properties"]["slots"]["properties"]) == set(spec["slot_schema"])
    assert branch["properties"]["intent"]["enum"] == spec["intents"]
    for name, slot in spec["slot_schema"].items():
        validator = Draft202012Validator(branch["properties"]["slots"]["properties"][name])
        kinds = slot["type"] if isinstance(slot["type"], list) else [slot["type"]]
        values = slot.get("enum") or slot.get("canonical_values") or [
            "dữ kiện" if kind == "string" else 3.6 for kind in kinds]
        assert validator.is_valid(None)
        for value in values:
            assert validator.is_valid(value)
            assert validator.is_valid([value, value])
        if slot.get("enum") or slot.get("canonical_values"):
            assert not validator.is_valid("mô tả không phải mã")
            assert not validator.is_valid([values[0], "mô tả không phải mã"])
        if kinds == ["string", "number"]:
            assert not validator.is_valid(["dữ kiện", 3.6])
        assert not validator.is_valid(True)


@pytest.mark.parametrize("value", ["địa chỉ", ["unit", "địa chỉ"]])
def test_illegal_field_codes_are_rejected_by_schema(value):
    task = _task("student_service", {"service": "mượn sách", "requested_field": value})
    assert not Draft202012Validator(query_plan_strict_response_schema()).is_valid(_payload(task))


def test_wrong_tool_slots_and_rag_payload_are_rejected():
    validator = Draft202012Validator(query_plan_strict_response_schema())
    task = _task("office", {"office": "Thư viện", "requested_field": "office"})
    assert validator.is_valid(_payload(task))
    task["slots"]["service"] = "mượn sách"
    assert not validator.is_valid(_payload(task))
    task = {**task, "mode": "rag", "intent": "open_question", "lookup_type": None}
    assert not validator.is_valid(_payload(task))
    task.update(slots={}, slot_spans={})
    assert validator.is_valid(_payload(task))
    task.update(mode="clarify", intent="clarify", clarification_question="Bạn cần tra gì?")
    assert validator.is_valid(_payload(task))
    task["clarification_question"] = None
    assert not validator.is_valid(_payload(task))
    payload = _payload(task)
    payload.update(out_of_domain=True, tasks=[])
    assert validator.is_valid(payload)


def test_nullable_placeholders_normalize_like_omitted_slots_and_do_not_hide_missing_input():
    query = "Thời gian tối đa hệ chính quy là bao lâu?"
    strict = _task("study_duration", {"training_mode": "chinh_quy"}, {"training_mode": "chính quy"})
    strict["question"] = query
    sparse = deepcopy(strict)
    sparse["slots"] = {key: value for key, value in strict["slots"].items() if value is not None}
    sparse["slot_spans"] = {key: value for key, value in strict["slot_spans"].items() if value is not None}
    actual, errors = normalize_query_plan(_payload(strict, query), query=query, selected_cohort="K51")
    expected, old_errors = normalize_query_plan(_payload(sparse, query), query=query, selected_cohort="K51")
    assert errors == old_errors == [] and actual == expected
    assert actual["tasks"][0]["slots"] == {"training_mode": "chinh_quy"}
    query = "Email của phòng nào?"
    task = _task("office", {"requested_field": "email"})
    task["question"] = query
    plan, errors = normalize_query_plan(_payload(task, query), query=query, selected_cohort="K51")
    assert plan["tasks"][0]["mode"] == "clarify"
    assert "t1:missing_slot:office" in errors


def test_strict_shape_does_not_replace_scale_grounding():
    query = "Điểm 3,6/4 có đạt không?"
    task = _task("scoring", {"operation": "pass_threshold", "score_or_grade": 3.6},
                 {"operation": "có đạt không", "score_or_grade": "3,6"})
    task["question"] = query
    assert Draft202012Validator(query_plan_strict_response_schema()).is_valid(_payload(task, query))
    plan, errors = normalize_query_plan(_payload(task, query), query=query, selected_cohort="K51")
    assert plan["tasks"][0]["slots"].get("score_or_grade") is None
    assert any("score_or_grade" in warning for warning in plan["tasks"][0]["normalization_warnings"])


def test_contact_fixtures_accept_strict_nullable_shape_and_normalize_identically():
    validator = Draft202012Validator(query_plan_strict_response_schema())
    for case in yaml.safe_load(CASES.read_text(encoding="utf-8"))["cases"]:
        expected = case["expected"]
        strict = _task(expected["lookup_type"], expected["slots"], expected["slot_spans"])
        strict.update(question=case["query"], intent=expected["intent"], cohorts=[case["cohort"]])
        assert validator.is_valid(_payload(strict, case["query"]))
        plan, errors = normalize_query_plan(_payload(strict, case["query"]), query=case["query"],
                                            selected_cohort=case["cohort"])
        assert errors == []
        task = plan["tasks"][0]
        assert task["slots"] == expected["slots"]
        assert validate_structured_task({**task, "cohort": case["cohort"]}, query=case["query"]) == []


def test_unknown_null_slot_is_not_silently_discarded():
    query = "Email Phòng Đào tạo là gì?"
    task = _task("office", {"office": "Phòng Đào tạo", "requested_field": "email"},
                 {"office": "Phòng Đào tạo", "requested_field": "Email"})
    task["question"] = query
    task["slots"]["invented"] = None
    _, errors = normalize_query_plan(_payload(task, query), query=query, selected_cohort="K51")
    assert "t1:unknown_slot:invented" in errors
