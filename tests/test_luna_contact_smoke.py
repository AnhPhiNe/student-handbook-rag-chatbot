from copy import deepcopy
import hashlib
import json
import pytest
import yaml
from scripts.run_luna_contact_smoke import CASES, grade_contact, regrade_contact_report


def test_contact_rubrics_and_wrong_field():
    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))["cases"]
    assert len(cases) == 8
    for case in cases:
        task = {**deepcopy(case["expected"]), "mode": "structured", "cohorts": [case["cohort"]]}
        plan = {"tasks": [task]}
        assert grade_contact(case, plan) == []
        task["slots"]["requested_field"] = "phone"
        assert "requested_field" in grade_contact(case, plan)
        task["lookup_type"] = "faculty"
        assert "lookup_type" in grade_contact(case, plan)


def test_contact_all_only_substitutes_multi_fields():
    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))["cases"]
    for case in cases:
        task = {**deepcopy(case["expected"]), "mode": "structured", "cohorts": [case["cohort"]]}
        task["slots"]["requested_field"] = "all"
        errors = grade_contact(case, {"tasks": [task]})
        wanted = case["expected"]["slots"]["requested_field"]
        assert (not errors) == (isinstance(wanted, list) or wanted == "all")


def test_equivalent_service_intents_do_not_relax_tool_field_or_cohort():
    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))["cases"]
    for case in cases:
        task = {**deepcopy(case["expected"]), "mode": "structured", "cohorts": [case["cohort"]]}
        task["intent"] = "direct_value"
        errors = grade_contact(case, {"tasks": [task]})
        if task["lookup_type"] == "student_service":
            assert errors == []
            task["slots"]["requested_field"] = "office" if case["expected"]["slots"]["requested_field"] == "unit" else "unit"
            assert "requested_field" in grade_contact(case, {"tasks": [task]})
            task["cohorts"] = ["K49"]
            assert "cohorts" in grade_contact(case, {"tasks": [task]})
        else:
            assert "intent" in errors
        task["intent"] = "invented"
        assert "intent" in grade_contact(case, {"tasks": [task]})


def test_offline_regrade_retains_original_report_and_runs_no_planner(tmp_path, monkeypatch):
    from scripts import run_luna_contact_smoke as module
    monkeypatch.setattr(module.AIRouter, "from_config", lambda *_: pytest.fail("Offline regrading must not initialize a planner"))
    cases = yaml.safe_load(CASES.read_text(encoding="utf-8"))["cases"]
    case = cases[0]
    task = {**deepcopy(case["expected"]), "mode": "structured", "cohorts": [case["cohort"]], "intent": "direct_value"}
    source = tmp_path / "saved.json"
    source.write_text(json.dumps({"scope": "contact_intent_only_not_answer_or_execution_accuracy",
        "requested_n": 8, "rows": [{"id": case["id"], "query": case["query"],
        "expected": case["expected"], "plan": {"tasks": [task]}, "passed": False,
        "failures": ["intent"], "runtime_error": False}]}), encoding="utf-8")
    before = source.read_bytes()
    report = regrade_contact_report(source, tmp_path / "regraded")
    assert report["original_passed"] == 0 and report["passed"] == 1
    assert report["inference_calls"] == 0
    assert report["not_run_n"] == 7
    assert report["source_sha256"] == hashlib.sha256(before).hexdigest()
    assert source.read_bytes() == before
    assert report["rows"][0]["original_failures"] == ["intent"]
    with pytest.raises(FileExistsError):
        regrade_contact_report(source, tmp_path / "regraded")
