"""Offline contract self-tests. Never instantiate the system under evaluation."""
import copy
import time
from collections import Counter

from scripts.build_official_deterministic import BUNDLE, build, read
from src.evaluation.dataset import validate_deterministic_case
from src.evaluation.deterministic import _evaluate_outcome_case, _task_execution_checks
import src.evaluation.deterministic as deterministic_suite


def fixture_result(case):
    outcome = case["accepted_outcomes"][0]
    tasks, results = [], []
    for index, expected in enumerate(outcome["required_tasks"]):
        task = {"id": f"t{index}", "mode": expected["mode"], "cohorts": expected["cohorts"],
                "lookup_type": expected.get("lookup_type"),
                "slots": {key: values[0] for key, values in expected.get("slot_value_alternatives", {}).items()}}
        for key in expected.get("required_slot_keys", []):
            task["slots"].setdefault(key, "fixture")
        evidence = {"rows": copy.deepcopy([expected.get("expected_evidence_fields", {}), *expected.get("expected_evidence_rows", [])]),
                    "source_ids": expected.get("expected_source_ids", [])}
        evidence["tables"] = [{"table_id": sid} for sid in expected.get("expected_source_ids", [])]
        if expected.get("fact_lock_applicable"):
            evidence["resolved_result"] = {"result": copy.deepcopy(expected["expected_resolved_fields"])}
        tasks.append(task)
        results.append({**task, "task_id": task["id"], "coverage": "covered", "evidence": [evidence]})
    if outcome["state"] == "clarify" and not tasks:
        tasks = [{"mode": "clarify", "cohorts": [case["cohort"]]}]
    if outcome.get("clarification_question_required") and tasks:
        tasks[0]["clarification_question"] = "Bạn cần hỗ trợ cụ thể về mảng nào?"
    return {"query_plan": {"tasks": tasks, "out_of_domain": outcome["state"] == "out_of_domain"},
            "task_results": results, "needs_clarification": outcome["state"] == "clarify"}


def test_135_schema_and_source_backing():
    cases = build()
    assert cases == read(BUNDLE / "deterministic_tool_cases.json")
    assert Counter(c["cohort"] for c in cases) == {"K48-K49": 45, "K50": 45, "K51": 45}
    errors = []
    for case in cases:
        validate_deterministic_case(case, errors)
    assert not errors
    assert len({c["query"].casefold() for c in cases}) == 135


def test_all_contracts_accept_their_fixture_and_reject_wrong_plan_cohort():
    for case in build():
        result = fixture_result(case)
        row = _evaluate_outcome_case(case, result, started=time.perf_counter())
        assert row["passed"], (case["id"], row["accepted_outcome_evaluations"])
        if case["accepted_outcomes"][0]["required_tasks"]:
            bad = copy.deepcopy(result)
            for task in bad["query_plan"]["tasks"]:
                task["cohorts"] = ["K50" if case["cohort"] != "K50" else "K51"]
            assert not _evaluate_outcome_case(case, bad, started=time.perf_counter())["passed"]


def test_fact_lock_cannot_pass_using_full_display_table():
    expected = {"mode": "structured", "lookup_type": "scoring", "fact_lock_applicable": True,
                "expected_resolved_fields": {"letter_grade": "B"}}
    task = {"mode": "structured", "lookup_type": "scoring", "evidence": [{"resolved_result": {
        "result": {"letter_grade": "C"}, "display_rows": [{"letter_grade": "B"}]}}]}
    assert _task_execution_checks(expected, [task])["resolved_result"] is False


def test_list_slot_is_compared_without_hashing_or_automatic_acceptance():
    from src.evaluation.deterministic import _task_matches
    actual = {"slots": {"requested_field": ["email", "office"]}}
    assert not _task_matches({"slot_value_alternatives": {"requested_field": ["all"]}}, actual)
    assert _task_matches({"slot_value_alternatives": {"requested_field": [["office", "email"]]}}, actual)


def test_grouped_directory_requires_every_entity_and_field():
    case = copy.deepcopy(build()[114])
    case["accepted_outcomes"] = [case["accepted_outcomes"][1]]
    result = fixture_result(case)
    assert _evaluate_outcome_case(case, result, started=time.perf_counter())["passed"]
    for removed in (1, 2):
        bad = copy.deepcopy(result)
        del bad["task_results"][0]["evidence"][0]["rows"][removed]
        assert not _evaluate_outcome_case(case, bad, started=time.perf_counter())["passed"]


def test_evaluator_exception_retains_raw_runtime_result(monkeypatch):
    case = build()[0]
    result = fixture_result(case)
    class Pipeline:
        def _run_retrieval(self, *args, **kwargs):
            return result
    def fail(*args, **kwargs):
        raise TypeError("fixture evaluator error")
    monkeypatch.setattr(deterministic_suite, "_evaluate_outcome_case", fail)
    report = deterministic_suite.evaluate_deterministic([case], pipeline_factory=Pipeline,
                                             evaluation_contract=case["contract_version"])
    row = report["cases"][0]
    assert row["error_stage"] == "evaluator"
    assert row["raw_result"] == result
    assert "TypeError" in row["traceback"]


def test_execution_clarification_is_bound_to_task_cohort_and_question():
    case = build()[123]
    result = fixture_result(case)
    result.pop("needs_clarification")
    task = result["query_plan"]["tasks"][1]
    task.update(mode="structured", lookup_type="scoring")
    execution = result["task_results"][1]
    execution.update(mode="structured", coverage="needs_clarification",
                     coverage_by_cohort={case["cohort"]: "needs_clarification"},
                     clarification_by_cohort={case["cohort"]: "Bạn được bao nhiêu điểm?"})
    assert _evaluate_outcome_case(case, result, started=time.perf_counter())["passed"]
    for field, value in [("task_id", "wrong"), ("clarification_by_cohort", {}),
                         ("coverage_by_cohort", {"K51": "needs_clarification"})]:
        bad = copy.deepcopy(result)
        bad["task_results"][1][field] = value
        assert not _evaluate_outcome_case(case, bad, started=time.perf_counter())["passed"]


def test_contact_field_list_is_accepted_only_with_both_outputs():
    case = build()[122]
    result = fixture_result(case)
    result["query_plan"]["tasks"][0]["slots"]["requested_field"] = ["email", "office"]
    assert _evaluate_outcome_case(case, result, started=time.perf_counter())["passed"]
    del result["task_results"][0]["evidence"][0]["rows"][0]["email"]
    assert not _evaluate_outcome_case(case, result, started=time.perf_counter())["passed"]


def test_full_table_assertion_rejects_missing_rows():
    expected = {"mode": "structured", "lookup_type": "scoring", "fact_lock_applicable": False,
                "expected_evidence_rows": [{"letter_grade": "A"}, {"letter_grade": "B"}]}
    task = {"mode": "structured", "lookup_type": "scoring", "evidence": [{"letter_grade": "A"}]}
    checks = _task_execution_checks(expected, [task])
    assert checks["evidence_fields"] is False
    assert checks["resolved_result"] is None


def test_execution_evidence_cannot_borrow_explicit_wrong_cohort():
    expected = {"mode": "structured", "lookup_type": "scoring", "cohorts": ["K51"],
                "expected_evidence_fields": {"letter_grade": "B"}}
    task = {"mode": "structured", "lookup_type": "scoring", "cohorts": ["K50"],
            "evidence": [{"letter_grade": "B"}]}
    assert _task_execution_checks(expected, [task])["evidence_fields"] is False


def test_underspecified_course_does_not_force_one_fact_lock():
    case = build()[14]
    assert len(case["accepted_outcomes"]) == 2
    assert case["accepted_outcomes"][0]["required_tasks"][0]["fact_lock_applicable"] is False
    result = {"query_plan": {"tasks": [{"mode": "clarify"}]}, "needs_clarification": True}
    assert _evaluate_outcome_case(case, result, started=time.perf_counter())["passed"]


def test_scholarship_overview_accepts_one_task_or_two_aspect_tasks():
    case = build()[59]
    assert len(case["accepted_outcomes"]) == 2
    assert case["accepted_outcomes"][0]["task_count"] == {"min": 1, "max": 1}
    assert case["accepted_outcomes"][1]["task_count"] == {"min": 2, "max": 2}
    for outcome in case["accepted_outcomes"]:
        fixture_case = copy.deepcopy(case)
        fixture_case["accepted_outcomes"] = [outcome]
        result = fixture_result(fixture_case)
        assert _evaluate_outcome_case(
            case, result, started=time.perf_counter()
        )["passed"]


def test_ambiguous_service_request_accepts_safe_clarification():
    case = build()[91]
    clarification = next(
        outcome
        for outcome in case["accepted_outcomes"]
        if outcome["name"] == "safe-clarification"
    )
    fixture_case = copy.deepcopy(case)
    fixture_case["accepted_outcomes"] = [clarification]
    result = fixture_result(fixture_case)
    assert _evaluate_outcome_case(
        case, result, started=time.perf_counter()
    )["passed"]
    result["query_plan"]["tasks"][0].pop("clarification_question")
    assert not _evaluate_outcome_case(
        case, result, started=time.perf_counter()
    )["passed"]


def test_queries_do_not_leak_table_storage_instructions():
    forbidden = ("xem hàng", "cột bậc", "theo bảng", "bảng tham chiếu", "chưa đưa điểm",
                 "chưa nhập điểm", "không phải nền tảng", "trong danh mục")
    for case in build():
        assert not any(phrase in case["query"].casefold() for phrase in forbidden), case["id"]


def test_narrow_question_requires_requested_fact_not_whole_record():
    cases = build()
    task = cases[48]["accepted_outcomes"][0]["required_tasks"][0]
    assert task["expected_resolved_fields"] == {"scholarship_level": "Khá", "multiplier": 1.0}
    result = fixture_result(cases[48])
    assert _evaluate_outcome_case(cases[48], result, started=time.perf_counter())["passed"]
    result["task_results"][0]["evidence"][0]["resolved_result"]["result"]["multiplier"] = 1.5
    assert not _evaluate_outcome_case(cases[48], result, started=time.perf_counter())["passed"]
    duration = cases[40]["accepted_outcomes"][0]["required_tasks"][0]
    assert duration["expected_resolved_fields"] == {"Thời gian học tập tối đa": "3 năm học"}


def test_input_identity_is_checked_without_decimal_spelling_false_negative():
    case = build()[6]
    for value in (2.76, "2.76", "2,76"):
        result = fixture_result(case)
        result["query_plan"]["tasks"][0]["slots"]["score_or_grade"] = value
        assert _evaluate_outcome_case(case, result, started=time.perf_counter())["passed"]
    result = fixture_result(case)
    result["query_plan"]["tasks"][0]["slots"]["score_or_grade"] = 2.8
    # Same classification, different user input: it must not pass this contract.
    assert not _evaluate_outcome_case(case, result, started=time.perf_counter())["passed"]


def test_compound_contract_rejects_dropped_task_and_accepts_reordering():
    for case in build():
        required = case["accepted_outcomes"][0]["required_tasks"]
        if len(required) < 2:
            continue
        result = fixture_result(case)
        result["query_plan"]["tasks"].reverse()
        result["task_results"].reverse()
        assert _evaluate_outcome_case(case, result, started=time.perf_counter())["passed"]
        result["query_plan"]["tasks"].pop()
        result["task_results"].pop()
        assert not _evaluate_outcome_case(case, result, started=time.perf_counter())["passed"], case["id"]


def test_missing_input_cannot_pass_as_empty_or_answered_request():
    for case in build():
        if case["category"] != "insufficient_input":
            continue
        for result in (
            {"query_plan": {"tasks": []}, "task_results": []},
            {"query_plan": {"tasks": [{"mode": "structured", "cohorts": [case["cohort"]]}]},
             "needs_clarification": False, "task_results": []},
        ):
            assert not _evaluate_outcome_case(case, result, started=time.perf_counter())["passed"], case["id"]


def test_contact_outputs_accept_grouped_and_split_tasks():
    for case in build()[121:123]:
        assert len(case["accepted_outcomes"]) == 2
        for outcome in case["accepted_outcomes"]:
            fixture_case = copy.deepcopy(case)
            fixture_case["accepted_outcomes"] = [outcome]
            result = fixture_result(fixture_case)
            assert _evaluate_outcome_case(case, result, started=time.perf_counter())["passed"]


def test_evidence_cannot_be_swapped_between_same_type_tasks():
    case = build()[16]
    result = fixture_result(case)
    first, second = result["task_results"]
    first["evidence"], second["evidence"] = second["evidence"], first["evidence"]
    assert not _evaluate_outcome_case(case, result, started=time.perf_counter())["passed"]


def test_partial_clarification_keeps_answerable_task():
    case = build()[123]
    result = fixture_result(case)
    assert _evaluate_outcome_case(case, result, started=time.perf_counter())["passed"]
    result["task_results"] = []
    assert not _evaluate_outcome_case(case, result, started=time.perf_counter())["passed"]


def test_regulation_multi_cohort_accepts_grouped_plan():
    case = build()[38]
    for outcome in case["accepted_outcomes"]:
        fixture_case = copy.deepcopy(case)
        fixture_case["accepted_outcomes"] = [outcome]
        result = fixture_result(fixture_case)
        assert _evaluate_outcome_case(case, result, started=time.perf_counter())["passed"]


def grouped_scholarship_fixture():
    case = build()[112]
    split = fixture_result(case)
    result = copy.deepcopy(split)
    result["query_plan"]["tasks"] = [{"id": "group", "mode": "structured",
        "lookup_type": "scholarship_classification", "cohorts": ["K50", "K51"]}]
    evidence = []
    for unit in split["task_results"]:
        evidence.extend({**item, "cohort": unit["cohorts"][0], "task_id": "group"}
                        for item in unit["evidence"])
    result["task_results"] = [{"task_id": "group", "mode": "structured",
        "lookup_type": "scholarship_classification", "cohorts": ["K50", "K51"],
        "coverage": "covered", "evidence": evidence}]
    return case, result


def test_grouped_structured_cohorts_require_their_own_facts():
    case, result = grouped_scholarship_fixture()
    assert _evaluate_outcome_case(case, result, started=time.perf_counter())["passed"]
    evidence = result["task_results"][0]["evidence"]
    evidence[0]["resolved_result"], evidence[1]["resolved_result"] = (
        evidence[1]["resolved_result"], evidence[0]["resolved_result"])
    assert not _evaluate_outcome_case(case, result, started=time.perf_counter())["passed"]


def test_shared_applicability_does_not_replace_missing_cohort_execution():
    case, result = grouped_scholarship_fixture()
    evidence = result["task_results"][0]["evidence"]
    evidence.pop()
    evidence[0]["applicable_cohorts"] = ["K50", "K51"]
    evidence[0]["applicability_validated"] = True
    assert not _evaluate_outcome_case(case, result, started=time.perf_counter())["passed"]


def test_grouped_gold_rejects_missing_cohort_unit():
    case = copy.deepcopy(build()[112])
    case["accepted_outcomes"][1]["required_tasks"][0]["execution_units"].pop()
    errors = []
    validate_deterministic_case(case, errors)
    assert any("execution_units" in error for error in errors)


def test_builder_compiles_a_holdout_bundle_with_history_and_slices(tmp_path):
    import yaml
    from src.evaluation.dataset import _validate_common

    history = [{"role": "user", "content": "GPA 2,76 của K51 là loại gì?"},
               {"role": "assistant", "content": "GPA 2,76 thuộc loại khá."}]
    authoring = {
        "settings": {"id_prefix": "official_v2_det", "independent_holdout": True,
                     "overlap_policy": "Held-out set; never used to tune the system.",
                     "expected": {"cases": 2}},
        "cases": [
            {"query": "GPA 2,76 là loại gì?", "category": "scoring", "selected_cohort": "K51",
             "table": ["academic_classification", 2, "academic_classification"],
             "input_slots": {"score_or_grade": 2.76}, "slice": "single.structured", "author": "owner"},
            {"query": "Còn K50 thì sao?", "category": "scoring", "selected_cohort": "K50",
             "table": ["academic_classification", 2, "academic_classification"],
             "history": history, "slice": "memory.cohort_switch", "stress": True, "stress_type": "ellipsis"},
        ],
    }
    bundle = tmp_path / "official_v2"
    bundle.mkdir()
    (bundle / "deterministic_authoring.yaml").write_text(yaml.safe_dump(authoring, allow_unicode=True), encoding="utf-8")

    cases = build(bundle)

    assert [c["id"] for c in cases] == ["official_v2_det_001", "official_v2_det_002"]
    assert [c["cohort"] for c in cases] == ["K51", "K50"]
    assert cases[0]["history"] == [] and cases[1]["history"] == history
    assert cases[1]["accepted_outcomes"][0]["required_tasks"][0]["cohorts"] == ["K50"]
    assert [c["slice"] for c in cases] == ["single.structured", "memory.cohort_switch"]
    assert cases[1]["stress_type"] == "ellipsis" and cases[1]["question_style"] == "stress"
    assert all(c["tags"][0] == "official_v2" and c["independent_holdout"] for c in cases)
    errors = []
    for case in cases:
        _validate_common(case, "deterministic", errors)
        validate_deterministic_case(case, errors)
    assert errors == []


def test_runner_requires_current_worktree_for_a_bundle_without_runtime_freeze(tmp_path):
    import pytest
    from scripts.run_official_deterministic import verify_runtime

    with pytest.raises(ValueError, match="pass --current-worktree"):
        verify_runtime(tmp_path, current_worktree=False)
