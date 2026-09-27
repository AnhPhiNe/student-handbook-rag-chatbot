"""Offline executor/evaluator regressions; scripted plans are not model runs."""

import copy
import json
import time
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.regrade_saved_deterministic_v10 import regrade
import src.evaluation.deterministic as deterministic
import src.generation.plan_executor as executor_module
from src.generation.plan_executor import PlanExecutor, StructuredCatalogs
from src.generation.prompt_builder import build_authorized_evidence_packet
from src.retrieval.core.slang_normalizer import SlangNormalizer


ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def _catalogs():
    base = ROOT / "data/processed"

    def read(relative):
        return json.loads((base / relative).read_text(encoding="utf-8"))

    return StructuredCatalogs(
        formula_rules=[],
        office_directory=read("directories/student_office_profiles.json"),
        student_service_directory=read("directories/student_service_directory.json"),
        student_faculty_profiles=read("directories/student_faculty_profiles.json"),
        structured_tables_registry=read("tables/structured_tables_registry.json"),
        program_directory=read("directories/program_directory.json"),
    )


def _execute(query, task, cohort):
    class ScriptedRouter:
        def plan(self, *_args, **_kwargs):
            return {"schema_version": "v1", "context_mode": "standalone",
                    "normalized_query": query, "standalone_query": None,
                    "referenced_turns": [], "out_of_domain": False,
                    "tasks": [copy.deepcopy(task)]}

    executor = PlanExecutor(
        router=ScriptedRouter(), slang_normalizer=SlangNormalizer(),
        catalogs=_catalogs(), parent_sources_by_id={}, top_k=5,
        public_source_limit=5, model=None,
        graph=SimpleNamespace(expand_context=lambda *_args, **_kwargs: []),
    )
    return executor.run(query=query, cohort=cohort, chat_history=None)


def _task(query, *, scope="pass_fail_ungraded", operand=4.9, span="4,9"):
    return {
        "id": "t1", "question": query, "mode": "structured",
        "intent": "direct_value", "lookup_type": "scoring", "cohorts": ["K51"],
        "slots": {"operation": "pass_threshold", "score_or_grade": operand,
                  "course_scope": scope},
        "slot_spans": {"operation": "qua", "score_or_grade": span,
                       "course_scope": "không tính GPA, chỉ xét đạt hay trượt"},
        "clarification_question": None,
    }


def test_018_executor_keeps_literal_grounding_and_delivers_lock_to_composer():
    query = "Môn không tính GPA, chỉ xét đạt hay trượt, 4,9 có qua không?"
    result = _execute(query, _task(query), "K51")
    # Retrieval expansion is still available, but no longer invalidates spans.
    assert "GPA điểm trung bình học kỳ" in result["retrieval_query"]
    assert result["task_results"][0]["resolution_by_cohort"] == {"K51": "resolved"}
    evidence = result["structured_result"]
    assert evidence["input_value"] == query
    assert evidence["table_id"] == "K51_QuyCheDaoTao_Chuong3_Dieu10_pass_fail_ungraded"
    assert evidence["resolved_result"]
    packet = build_authorized_evidence_packet(
        query=query, retrieval_result=result,
        selected_citations=result["citations"], fallback_cohort="K51",
        max_context_chars=30000,
    )
    primary = [item for unit in packet["units"] for item in unit["primary_evidence"]]
    assert any(item.get("resolved_result") for item in primary)


@pytest.mark.parametrize("bad_input", ["ungrounded_scope", "wrong_scale"])
def test_executor_does_not_lock_ungrounded_or_wrong_scale_inputs(bad_input):
    query = "Môn không tính GPA, chỉ xét đạt hay trượt, 4,9 có qua không?"
    task = _task(query)
    if bad_input == "ungrounded_scope":
        task["slot_spans"]["course_scope"] = "môn khác không có trong câu hỏi"
    else:
        query = query.replace("4,9", "4,9/4")
        task = _task(query, operand="4,9/4", span="4,9/4")
    result = _execute(query, task, "K51")
    assert result["task_results"][0]["resolution_by_cohort"] == {"K51": "evidence_only"}
    assert "resolved_result" not in result["structured_result"]


def test_executor_keeps_k51_graded_scope_ambiguous_without_foundation_or_remaining():
    query = "Môn tính GPA được 3,6/10 có qua không?"
    task = _task(query, scope="graded", operand="3,6/10", span="3,6/10")
    task["slot_spans"]["course_scope"] = "Môn tính GPA"
    result = _execute(query, task, "K51")
    assert result["task_results"][0]["resolution_by_cohort"] == {"K51": "evidence_only"}
    evidence = result["structured_result"]
    assert "resolved_result" not in evidence
    assert sum(bool(item.get("resolved_rows")) for item in evidence["sub_lookups"]) == 2


def test_rag_execution_still_receives_retrieval_expansion(monkeypatch):
    seen = []

    def retrieve(query, **kwargs):
        seen.append((query, kwargs["retrieval_query"]))
        return {"retrieved_items": [], "citations": []}

    monkeypatch.setattr(executor_module, "run_hybrid_retrieval_pipeline", retrieve)
    query = "Quy định GPA của khóa K51?"
    task = {"id": "t1", "question": query, "mode": "rag", "cohorts": ["K51"]}
    _execute(query, task, "K51")
    assert seen == [(query, SlangNormalizer().normalize_for_retrieval(query))]
    assert seen[0][1] != query


@pytest.mark.parametrize("actual,alternatives,expected", [
    (["unit", "email"], ["email", "all"], True),
    (["email", "unit"], ["unit", "all"], True),
    (["email"], ["email", "all"], True),
    ("email", ["email", "all"], True),
    (["email", "office"], [["office", "email"]], True),
    (["email"], [["office", "email"]], False),
    ("office", ["unit", "all"], False),
    (["office", "email"], ["unit", "all"], False),
    (["unit", "email"], ["all"], False),
    (["all"], ["email", "all"], True),
    (["all"], ["email"], False),
    (["email", "not_a_field"], ["email", "all"], False),
    (["email", {"unit": "email"}], ["email", "all"], False),
    ([], ["email", "all"], False),
])
def test_requested_field_coverage_preserves_field_meaning(actual, alternatives, expected):
    gold = {"mode": "structured", "lookup_type": "student_service", "cohorts": ["K50"],
            "slot_value_alternatives": {"requested_field": alternatives}}
    task = {"mode": "structured", "lookup_type": "student_service", "cohorts": ["K50"],
            "slots": {"requested_field": actual}}
    assert deterministic._task_matches(gold, task) is expected


@lru_cache(maxsize=1)
def _v10_cases():
    cases = json.loads((ROOT / "data/eval/official_v1/deterministic_tool_cases_v10.json").read_text(encoding="utf-8"))
    return {case["id"]: case for case in cases}


def _case122_result():
    case = _v10_cases()["official_det_122"]
    task = {
        "id": "t1", "question": case["query"], "mode": "structured",
        "intent": "contact", "lookup_type": "student_service", "cohorts": ["K50"],
        "slots": {"service": "Giấy chứng nhận điểm", "requested_field": ["unit", "email"]},
        "slot_spans": {"service": "Giấy chứng nhận điểm", "requested_field": ["đơn vị nào", "email"]},
        "clarification_question": None,
    }
    return copy.deepcopy(_execute(case["query"], task, "K50"))


def test_122_correct_selected_record_passes_with_multi_field_request():
    result = _case122_result()
    scored = deterministic._evaluate_outcome_case(
        _v10_cases()["official_det_122"], result, started=time.perf_counter(),
    )
    assert scored["passed"]
    assert scored["structured_row_correct"]
    assert result["query_plan"]["tasks"][0]["slots"]["requested_field"] == ["unit", "email"]


@pytest.mark.parametrize("corruption", ["missing_email", "other_record_email", "cross_cohort", "wrong_task",
                                       "wrong_tool", "wrong_unit", "wrong_email"])
def test_multi_field_coverage_does_not_excuse_wrong_or_unbound_evidence(corruption):
    result = _case122_result()
    execution = result["task_results"][0]
    if corruption == "wrong_task":
        execution["task_id"] = "unrelated-task"
    elif corruption == "wrong_tool":
        result["query_plan"]["tasks"][0]["lookup_type"] = "office"
        execution["lookup_type"] = "office"
    else:
        for mapping in deterministic._nested_mappings(execution["evidence"]):
            if corruption == "cross_cohort":
                if "cohort" in mapping:
                    mapping["cohort"] = "K51"
            elif corruption == "wrong_unit":
                if "unit_name" in mapping:
                    mapping["unit_name"] = "Một đơn vị khác"
            elif corruption == "wrong_email":
                if "emails" in mapping:
                    mapping["emails"] = ["wrong@example.test"]
                if "email" in mapping:
                    mapping["email"] = "wrong@example.test"
            else:
                mapping.pop("email", None)
                mapping.pop("emails", None)
        if corruption == "other_record_email":
            execution["evidence"].append({
                "unit_name": "Một đơn vị khác", "cohort": "K50",
                "emails": ["phongkhaothi@hcmue.edu.vn"],
            })
    scored = deterministic._evaluate_outcome_case(
        _v10_cases()["official_det_122"], result, started=time.perf_counter(),
    )
    assert not scored["passed"]


def test_096_office_instead_of_unit_still_fails_even_with_the_correct_record():
    case = _v10_cases()["official_det_096"]
    task = {"id": "t1", "question": case["query"], "mode": "structured",
            "intent": "contact", "lookup_type": "student_service", "cohorts": ["K51"],
            "slots": {"service": "nhận bằng tốt nghiệp", "requested_field": "office"},
            "slot_spans": {"service": "Nhận bằng tốt nghiệp", "requested_field": "phòng nào"}}
    result = _execute(case["query"], task, "K51")
    scored = deterministic._evaluate_outcome_case(case, result, started=time.perf_counter())
    assert not scored["task_semantics_correct"]
    assert not scored["passed"]


def test_checkpoint_and_report_bind_evaluator_revision(monkeypatch, tmp_path):
    case = _v10_cases()["official_det_122"]
    result = _case122_result()

    class Pipeline:
        def _run_retrieval(self, *_args, **_kwargs):
            return result

    path = tmp_path / "checkpoint.json"
    report = deterministic.evaluate_deterministic(
        [case], pipeline_factory=Pipeline, checkpoint_path=path,
        evaluation_contract=case["contract_version"],
    )
    assert report["evaluator_revision"] == deterministic.DETERMINISTIC_EVALUATOR_REVISION
    identity = json.loads(path.with_suffix(".json.identity.json").read_text(encoding="utf-8"))
    assert identity["settings"]["evaluator_revision"] == report["evaluator_revision"]
    monkeypatch.setattr(deterministic, "DETERMINISTIC_EVALUATOR_REVISION", "another-revision")
    with pytest.raises(ValueError, match="identity mismatch"):
        deterministic.evaluate_deterministic(
            [case], pipeline_factory=Pipeline, checkpoint_path=path, resume=True,
            evaluation_contract=case["contract_version"],
        )


def _saved_report(tmp_path, case, result):
    row = deterministic._evaluate_outcome_case(case, result, started=time.perf_counter())
    # Reconstruct the previous scalar-only grading failure without changing
    # the saved task or evidence; timings are synthetic test values.
    row["passed"] = False
    row["latency_ms"] = 120.0
    row["planner_latency_ms"] = 110.0
    path = tmp_path / "source.json"
    path.write_text(json.dumps({"evaluation_contract": case["contract_version"],
                               "cases": [row]}), encoding="utf-8")
    return path


def test_regrade_subset_preserves_source_and_labels_evaluator_only_change(tmp_path):
    source = _saved_report(tmp_path, _v10_cases()["official_det_122"], _case122_result())
    original_bytes = source.read_bytes()
    output = tmp_path / "regraded.json"
    report = regrade(source, output)
    assert source.read_bytes() == original_bytes
    assert report["summary"]["passed"] == 1
    assert report["cases"][0]["planner_latency_ms"] == 110.0
    assert report["offline_regrade"]["mode"] == "same_saved_outputs"
    assert report["offline_regrade"]["changed_cases"] == [{
        "id": "official_det_122", "source_passed": False,
        "regraded_passed": True, "matched_outcome": "source-grounded-contract",
    }]
    assert report["evaluator_revision"] == deterministic.DETERMINISTIC_EVALUATOR_REVISION
    with pytest.raises(FileExistsError):
        regrade(source, output)
    with pytest.raises(FileExistsError):
        regrade(source, source)
    assert source.read_bytes() == original_bytes


def test_replay_saved_structured_plan_changes_execution_not_planning_or_latency(tmp_path):
    case = _v10_cases()["official_det_018"]
    result = _execute(case["query"], _task(case["query"]), "K51")
    # The old execution lacked a lock, although the same task now resolves.
    for mapping in deterministic._nested_mappings(result):
        mapping.pop("resolved_result", None)
    source = _saved_report(tmp_path, case, result)
    original_bytes = source.read_bytes()
    same_evidence = regrade(source, tmp_path / "regraded.json")
    assert same_evidence["summary"]["passed"] == 0
    replay = regrade(source, tmp_path / "replayed.json", replay_structured=True)
    assert replay["summary"]["passed"] == 1
    assert replay["summary"]["planner_latency_p95_ms"] is None
    assert replay["summary"]["planner_latency_support_n"] == 0
    assert replay["cases"][0]["source_planner_latency_ms"] == 110.0
    assert replay["cases"][0]["query_plan"] == result["query_plan"]
    assert replay["offline_regrade"]["mode"] == "saved_plan_structured_replay"
    assert replay["offline_regrade"]["runtime_replay_hashes"]
    assert source.read_bytes() == original_bytes


@pytest.mark.parametrize("corruption", ["unknown_id", "duplicate_id", "changed_query"])
def test_regrade_rejects_mismatched_source_inputs(tmp_path, corruption):
    source = _saved_report(tmp_path, _v10_cases()["official_det_122"], _case122_result())
    report = json.loads(source.read_text(encoding="utf-8"))
    if corruption == "unknown_id":
        report["cases"][0]["id"] = "not_in_v10"
    elif corruption == "duplicate_id":
        report["cases"].append(copy.deepcopy(report["cases"][0]))
    else:
        report["cases"][0]["query"] = "another question"
    source.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError):
        regrade(source, tmp_path / "not_created.json")
    assert not (tmp_path / "not_created.json").exists()


def test_structured_replay_rejects_rag_before_any_retriever_is_created(tmp_path):
    case = _v10_cases()["official_det_122"]
    result = _case122_result()
    result["query_plan"]["tasks"][0]["mode"] = "rag"
    source = _saved_report(tmp_path, case, result)
    with pytest.raises(ValueError, match="requires successful, non-formula structured plans"):
        regrade(source, tmp_path / "not_created.json", replay_structured=True)
    assert not (tmp_path / "not_created.json").exists()
