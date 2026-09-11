from __future__ import annotations

import json
import os
from io import BytesIO
from pathlib import Path

import pytest

import src.evaluation.dataset as dataset
import src.evaluation.suites as suites
from src.evaluation.metrics import retrieval_metrics


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        (0.0, "0,0"),
        ("3.2-dưới 3.6", "Từ 3,2 đến dưới 3,6"),
        ("dưới 35", "Dưới 35 điểm"),
        ("65-dưới 80", "Từ 65 đến dưới 80 điểm"),
        ("90-100", "Từ 90 đến 100 điểm"),
    ],
)
def test_contract_values_accept_equivalent_numeric_and_range_renderings(
    actual: object, expected: object
) -> None:
    assert suites._contract_values_equal(actual, expected)


@pytest.mark.parametrize(
    ("actual", "expected"),
    [
        ("65-dưới 80", "65-80"),
        ("dưới 35", "35-50"),
        ("90-100", "80-dưới 90"),
    ],
)
def test_contract_values_preserve_range_semantics(
    actual: object, expected: object
) -> None:
    assert not suites._contract_values_equal(actual, expected)


def test_scoring_grade_four_heading_accepts_classification_range_schema() -> None:
    assert suites._mapping_contains_fields(
        {"range": "3.2-dưới 3.6", "label": "Giỏi"},
        {"Thang điểm 4": "Từ 3,2 đến dưới 3,6", "Xếp loại": "Giỏi"},
        lookup_type="scoring",
    )


def test_outcome_contract_accepts_equivalent_task_shape() -> None:
    errors: list[str] = []
    case = {
        "id": "v7-equivalent",
        "contract_version": "query-plan-grounded-outcome-v9",
        "accepted_outcomes": [
            {
                "name": "structured-evidence",
                "state": "answer",
                "allowed_modes": ["structured"],
                "task_count": {"min": 1, "max": 1},
                "required_tasks": [
                    {
                        "mode": "structured",
                        "lookup_type": "scoring",
                        "required_slot_keys": ["operation", "score_or_grade"],
                        "slot_value_alternatives": {
                            "score_or_grade": ["B+", "b+"]
                        },
                        "fact_lock_applicable": False,
                    }
                ],
                "structured_evidence": "required",
            }
        ],
    }
    dataset.validate_deterministic_case(case, errors)
    assert errors == []
    assert suites._required_tasks_match(
        case["accepted_outcomes"][0]["required_tasks"],
        [
            {
                "task_id": "implementation-detail",
                "mode": "structured",
                "lookup_type": "scoring",
                "intent": "direct_value",
                "cohorts": ["K51"],
                "slots": {"operation": "letter_to_grade_4", "score_or_grade": "b+"},
            }
        ],
    )


def test_outcome_contract_allows_task_level_clarification() -> None:
    class Pipeline:
        def _run_retrieval(self, query, cohort=None):
            return {
                "query_plan": {
                    "tasks": [
                        {
                            "mode": "structured",
                            "lookup_type": "foreign_language",
                            "intent": "direct_value",
                            "cohorts": ["K51"],
                            "slots": {"certificate_or_language": "TOEIC"},
                        }
                    ]
                },
                "needs_clarification": True,
                "task_results": [
                    {
                        "mode": "structured",
                        "lookup_type": "foreign_language",
                        "coverage": "uncovered",
                        "evidence": [],
                    }
                ],
            }

    case = {
        "id": "v7-clarify",
        "query": "TOEIC bốn kỹ năng nhưng thiếu điểm Viết",
        "cohort": "K51",
        "expected_llm_called": True,
        "contract_version": "query-plan-grounded-outcome-v9",
        "accepted_outcomes": [
            {
                "name": "task-level-clarification",
                "state": "clarify",
                "allowed_modes": ["structured", "clarify"],
                "task_count": {"min": 1, "max": 1},
                "required_tasks": [],
            }
        ],
    }
    report = suites.evaluate_deterministic([case], pipeline_factory=Pipeline)
    assert report["summary"]["passed"] == 1
    assert report["cases"][0]["matched_outcome"] == "task-level-clarification"


def test_contract_validates_grounded_execution_assertions() -> None:
    errors: list[str] = []
    case = {
        "id": "v8-grounded",
        "contract_version": "query-plan-grounded-outcome-v9",
        "accepted_outcomes": [
            {
                "name": "grounded-structured-answer",
                "state": "answer",
                "allowed_modes": ["structured"],
                "task_count": {"min": 1, "max": 1},
                "required_tasks": [
                    {
                        "mode": "structured",
                        "lookup_type": "scoring",
                        "expected_source_ids": ["score-table"],
                        "expected_evidence_fields": {"letter_grade": "B+"},
                        "expected_resolved_fields": {
                            "letter_grade": "B+",
                            "grade_4": 3.5,
                        },
                        "resolved_result_required": True,
                        "fact_lock_applicable": True,
                    }
                ],
                "structured_evidence": "required",
            }
        ],
    }
    dataset.validate_deterministic_case(case, errors)
    assert errors == []

    case["accepted_outcomes"][0]["required_tasks"][0]["expected_source_ids"] = []
    dataset.validate_deterministic_case(case, errors)
    assert any("expected_source_ids must be a non-empty string list" in error for error in errors)


def test_contract_requires_explicit_fact_lock_scope() -> None:
    errors: list[str] = []
    task = {
        "mode": "structured",
        "lookup_type": "office",
        "expected_source_ids": ["office-record"],
        "expected_evidence_fields": {"unit_name": "Phòng Đào tạo"},
        "fact_lock_applicable": False,
    }
    case = {
        "id": "v9-directory-evidence-only",
        "contract_version": "query-plan-grounded-outcome-v9",
        "accepted_outcomes": [
            {
                "name": "grounded-structured-answer",
                "state": "answer",
                "allowed_modes": ["structured"],
                "task_count": {"min": 1, "max": 1},
                "required_tasks": [task],
                "structured_evidence": "required",
            }
        ],
    }

    dataset.validate_deterministic_case(case, errors)
    assert errors == []

    task["expected_resolved_fields"] = {"unit_name": "Phòng Đào tạo"}
    dataset.validate_deterministic_case(case, errors)
    assert any("must not assert resolved_result" in error for error in errors)


def test_evidence_only_task_reports_resolved_result_as_na() -> None:
    class Pipeline:
        def _run_retrieval(self, query, cohort=None):
            evidence = {
                "office_profile_id": "office-record",
                "unit_name": "Phòng Đào tạo",
                "resolved_result": {"unit_name": "Phòng Đào tạo"},
            }
            return {
                "query_plan": {
                    "tasks": [
                        {
                            "mode": "structured",
                            "lookup_type": "office",
                            "cohorts": ["K51"],
                            "slots": {"requested_field": "phone"},
                        }
                    ]
                },
                "task_results": [
                    {
                        "mode": "structured",
                        "lookup_type": "office",
                        "coverage": "covered",
                        "evidence": [evidence],
                    }
                ],
                "structured_result": evidence,
            }

    case = {
        "id": "v9-directory-evidence-only",
        "query": "Số điện thoại Phòng Đào tạo là gì?",
        "cohort": "K51",
        "contract_version": "query-plan-grounded-outcome-v9",
        "accepted_outcomes": [
            {
                "name": "grounded-structured-answer",
                "state": "answer",
                "allowed_modes": ["structured"],
                "task_count": {"min": 1, "max": 1},
                "required_tasks": [
                    {
                        "mode": "structured",
                        "lookup_type": "office",
                        "required_slot_keys": ["requested_field"],
                        "expected_evidence_fields": {
                            "unit_name": "Phòng Đào tạo"
                        },
                        "fact_lock_applicable": False,
                    }
                ],
                "structured_evidence": "required",
            }
        ],
    }

    report = suites.evaluate_deterministic([case], pipeline_factory=Pipeline)
    row = report["cases"][0]
    assert row["passed"] is True
    assert row["structured_row_correct"] is True
    assert row["resolved_result_correct"] is None
    assert report["summary"]["assertion_support"]["resolved_result"] == 0


def test_evaluator_checks_source_row_and_resolved_result() -> None:
    class Pipeline:
        def _run_retrieval(self, query, cohort=None):
            evidence = {
                "table_id": "score-table",
                "rows": [{"letter_grade": "B+", "grade_4": 3.5}],
                "resolved_result": {
                    "result": {"letter_grade": "B+", "grade_4": 3.5}
                },
            }
            return {
                "query_plan": {
                    "tasks": [
                        {
                            "mode": "structured",
                            "lookup_type": "scoring",
                            "cohorts": ["K51"],
                            "slots": {"score_or_grade": "B+"},
                        }
                    ]
                },
                "task_results": [
                    {
                        "mode": "structured",
                        "lookup_type": "scoring",
                        "coverage": "covered",
                        "evidence": [evidence],
                    }
                ],
                "structured_result": evidence,
            }

    case = {
        "id": "v8-grounded",
        "query": "B+ đổi sang hệ 4 là bao nhiêu?",
        "cohort": "K51",
        "contract_version": "query-plan-grounded-outcome-v9",
        "accepted_outcomes": [
            {
                "name": "grounded-structured-answer",
                "state": "answer",
                "allowed_modes": ["structured"],
                "task_count": {"min": 1, "max": 1},
                "required_tasks": [
                    {
                        "mode": "structured",
                        "lookup_type": "scoring",
                        "required_slot_keys": ["score_or_grade"],
                        "expected_source_ids": ["score-table"],
                        "expected_evidence_fields": {"letter_grade": "B+"},
                        "expected_resolved_fields": {"grade_4": 3.5},
                        "resolved_result_required": True,
                    }
                ],
                "structured_evidence": "required",
            }
        ],
    }
    report = suites.evaluate_deterministic([case], pipeline_factory=Pipeline)
    row = report["cases"][0]
    assert row["passed"] is True
    assert row["structured_source_correct"] is True
    assert row["structured_row_correct"] is True
    assert row["resolved_result_correct"] is True
    assert report["summary"]["assertion_support"]["resolved_result"] == 1


def test_evaluator_fails_wrong_resolved_value_without_inflating_na() -> None:
    class Pipeline:
        def _run_retrieval(self, query, cohort=None):
            evidence = {
                "table_id": "score-table",
                "rows": [{"letter_grade": "B+", "grade_4": 3.5}],
                "resolved_result": {
                    "result": {"letter_grade": "B", "grade_4": 3.0}
                },
            }
            return {
                "query_plan": {
                    "tasks": [
                        {
                            "mode": "structured",
                            "lookup_type": "scoring",
                            "cohorts": ["K51"],
                            "slots": {},
                        }
                    ]
                },
                "task_results": [
                    {
                        "mode": "structured",
                        "lookup_type": "scoring",
                        "coverage": "covered",
                        "evidence": [evidence],
                    }
                ],
                "structured_result": evidence,
            }

    case = {
        "id": "v8-wrong-resolved",
        "query": "B+ đổi sang hệ 4 là bao nhiêu?",
        "cohort": "K51",
        "contract_version": "query-plan-grounded-outcome-v9",
        "accepted_outcomes": [
            {
                "name": "grounded-structured-answer",
                "state": "answer",
                "allowed_modes": ["structured"],
                "task_count": {"min": 1, "max": 1},
                "required_tasks": [
                    {
                        "mode": "structured",
                        "lookup_type": "scoring",
                        "expected_resolved_fields": {"grade_4": 3.5},
                    }
                ],
                "structured_evidence": "required",
            }
        ],
    }
    report = suites.evaluate_deterministic([case], pipeline_factory=Pipeline)
    row = report["cases"][0]
    assert row["passed"] is False
    assert row["structured_source_correct"] is None
    assert row["structured_row_correct"] is None
    assert row["resolved_result_correct"] is False
    assert report["summary"]["structured_source_accuracy"] is None


def test_evaluator_recognizes_service_catalog_identity() -> None:
    class Pipeline:
        def _run_retrieval(self, query, cohort=None):
            evidence = {
                "service_id": "K51_service_print_transcript",
                "unit_name": "Phòng Khảo thí",
            }
            return {
                "query_plan": {
                    "tasks": [
                        {
                            "mode": "structured",
                            "lookup_type": "student_service",
                            "cohorts": ["K51"],
                            "slots": {"requested_field": "unit"},
                        }
                    ]
                },
                "task_results": [
                    {
                        "mode": "structured",
                        "lookup_type": "student_service",
                        "coverage": "covered",
                        "evidence": [evidence],
                    }
                ],
                "structured_result": evidence,
            }

    case = {
        "id": "v8-service-source",
        "query": "Đơn vị nào hỗ trợ in bảng điểm?",
        "cohort": "K51",
        "contract_version": "query-plan-grounded-outcome-v9",
        "accepted_outcomes": [
            {
                "name": "grounded-service-answer",
                "state": "answer",
                "allowed_modes": ["structured"],
                "task_count": {"min": 1, "max": 1},
                "required_tasks": [
                    {
                        "mode": "structured",
                        "lookup_type": "student_service",
                        "expected_source_ids": ["K51_service_print_transcript"],
                        "expected_evidence_fields": {
                            "unit_name": "Phòng Khảo thí"
                        },
                    }
                ],
                "structured_evidence": "required",
            }
        ],
    }
    report = suites.evaluate_deterministic([case], pipeline_factory=Pipeline)
    row = report["cases"][0]
    assert row["passed"] is True, json.dumps(
        row["accepted_outcome_evaluations"], ensure_ascii=False, indent=2
    )
    assert row["structured_source_correct"] is True
    assert row["structured_row_correct"] is True
    assert row["resolved_result_correct"] is None


def test_evaluator_matches_public_directory_schema() -> None:
    class Pipeline:
        def _run_retrieval(self, query, cohort=None):
            evidence = {
                "record_id": "K51_faculty_16",
                "unit_name": "Khoa Tâm lý học",
                "cohort": "K51",
                "emails": ["khoatlh@hcmue.edu.vn"],
                "phones": ["(028) 38352020"],
                "office": "Nhà A, tầng 4, P.402",
                "source_section": "student_faculty_profiles",
            }
            return {
                "query_plan": {
                    "tasks": [
                        {
                            "mode": "structured",
                            "lookup_type": "faculty",
                            "cohorts": ["K51"],
                            "slots": {"requested_field": "office"},
                        }
                    ]
                },
                "task_results": [
                    {
                        "mode": "structured",
                        "lookup_type": "faculty",
                        "coverage": "covered",
                        "evidence": [evidence],
                    }
                ],
                "structured_result": evidence,
            }

    case = {
        "id": "v8-public-directory",
        "query": "Khoa Tâm lý học ở đâu?",
        "cohort": "K51",
        "contract_version": "query-plan-grounded-outcome-v9",
        "accepted_outcomes": [
            {
                "name": "grounded-directory-answer",
                "state": "answer",
                "allowed_modes": ["structured"],
                "task_count": {"min": 1, "max": 1},
                "required_tasks": [
                    {
                        "mode": "structured",
                        "lookup_type": "faculty",
                        "required_slot_keys": ["requested_field"],
                        "expected_source_ids": ["legacy-faculty-id"],
                        "expected_evidence_fields": {
                            "faculty_profile_id": "legacy-faculty-id",
                            "cohort": "K51",
                            "unit": "Khoa Tâm lý học",
                            "unit_name": "Khoa Tâm lý học",
                            "email": "khoatlh@hcmue.edu.vn",
                            "phone": "(028) 38352020",
                            "office": "Nhà A, tầng 4, P.402",
                            "source_section": "student_faculty_profiles",
                        },
                    }
                ],
                "structured_evidence": "required",
            }
        ],
    }
    row = suites.evaluate_deterministic([case], pipeline_factory=Pipeline)["cases"][0]
    assert row["passed"] is True
    assert row["structured_source_correct"] is None
    assert row["structured_row_correct"] is True


def test_evaluator_matches_display_row_to_canonical_resolved_row() -> None:
    class Pipeline:
        def _run_retrieval(self, query, cohort=None):
            evidence = {
                "table_id": "score-table",
                "rows": [
                    {
                        "Loại": "Đạt",
                        "Thang điểm 10": "7,8 - 8,4",
                        "Thang điểm chữ": "B+",
                    }
                ],
                "resolved_result": {
                    "result": {
                        "status": "Đạt",
                        "score_10_range": "7.8-8.4",
                        "letter_grade": "B+",
                    }
                },
            }
            return {
                "query_plan": {
                    "tasks": [
                        {
                            "mode": "structured",
                            "lookup_type": "scoring",
                            "cohorts": ["K51"],
                            "slots": {"score_or_grade": "8.1"},
                        }
                    ]
                },
                "task_results": [
                    {
                        "mode": "structured",
                        "lookup_type": "scoring",
                        "coverage": "covered",
                        "evidence": [evidence],
                    }
                ],
                "structured_result": evidence,
            }

    expected_row = {
        "Loại": "Đạt",
        "Thang điểm 10": "7,8 - 8,4",
        "Thang điểm chữ": "B+",
    }
    case = {
        "id": "v8-canonical-resolved-row",
        "query": "8,1 được điểm chữ gì?",
        "cohort": "K51",
        "contract_version": "query-plan-grounded-outcome-v9",
        "accepted_outcomes": [
            {
                "name": "grounded-structured-answer",
                "state": "answer",
                "allowed_modes": ["structured"],
                "task_count": {"min": 1, "max": 1},
                "required_tasks": [
                    {
                        "mode": "structured",
                        "lookup_type": "scoring",
                        "expected_source_ids": ["score-table"],
                        "expected_evidence_fields": expected_row,
                        "expected_resolved_fields": expected_row,
                        "resolved_result_required": True,
                    }
                ],
                "structured_evidence": "required",
            }
        ],
    }
    row = suites.evaluate_deterministic([case], pipeline_factory=Pipeline)["cases"][0]
    assert row["passed"] is True
    assert row["structured_source_correct"] is True
    assert row["structured_row_correct"] is True
    assert row["resolved_result_correct"] is True


def test_ndcg_uses_all_gold_and_reports_primary_source_coverage() -> None:
    metric = retrieval_metrics([2], gold_grades=[2, 2])
    assert 0 < metric["ndcg_at_5"] < 1
    metrics, scope = suites._retrieval_metrics_for_execution_units(
        case={"cohort": "K51"}, ranked_ids=["support"],
        grade_by_id={"support": 1, "main": 2}, scope="end_to_end",
    )
    assert scope == "request_global"
    assert metrics["hit_at_5"] == 1.0
    assert metrics["primary_hit_at_5"] == 0.0
    assert metrics["required_source_recall_at_5"] == 0.0
    assert metrics["ndcg_at_5"] < 1.0


@pytest.mark.parametrize("cohort", ["K51", "general"])
def test_retrieval_metrics_stable_deduplicate_parent_ids(cohort: str) -> None:
    judgments = [
        {"parent_section_id": "K51_main", "cohort": "K51", "grade": 2},
        {"parent_section_id": "K50_main", "cohort": "K50", "grade": 2},
    ]
    metrics, _ = suites._retrieval_metrics_for_execution_units(
        case={"cohort": cohort, "relevance_judgments": judgments},
        ranked_ids=["K51_main"] * 5 + ["K50_main"],
        grade_by_id={"K51_main": 2, "K50_main": 2}, scope="end_to_end",
    )
    assert metrics["ndcg_at_5"] == 1.0
    assert metrics["required_source_recall_at_5"] == 1.0


def test_generation_resume_rejects_changed_inputs_and_keeps_list_format(tmp_path: Path) -> None:
    calls = []

    class Pipeline:
        def answer(self, query, **kwargs):
            calls.append(query)
            return {"status": "answered", "answer": "supported"}

    cases = [{"id": "one", "query": "original"}]
    cache_path = tmp_path / "answers.json"
    context = {"profile": "full", "dataset_version": "v6"}
    suites.generate_answers(
        cases, cache_path=cache_path, resume=False,
        pipeline_factory=Pipeline, checkpoint_context=context,
    )
    original_bytes = cache_path.read_bytes()
    assert isinstance(json.loads(original_bytes), list)
    assert suites.load_answer_checkpoint(cases, cache_path, checkpoint_context=context)
    for changed_cases, changed_context in [
        ([{"id": "one", "query": "edited"}], context),
        (cases, {**context, "profile": "smoke"}),
    ]:
        with pytest.raises(ValueError, match="identity mismatch"):
            suites.generate_answers(
                changed_cases, cache_path=cache_path, resume=True,
                pipeline_factory=Pipeline, checkpoint_context=changed_context,
            )
    assert calls == ["original"]
    assert cache_path.read_bytes() == original_bytes


def test_legacy_answer_cache_is_not_silently_rebound(tmp_path: Path) -> None:
    cache_path = tmp_path / "legacy.json"
    original = '[{"id": "one", "answer": "historical"}]'
    cache_path.write_text(original, encoding="utf-8")
    with pytest.raises(ValueError, match="Legacy checkpoint"):
        suites.load_answer_checkpoint([{"id": "one", "query": "q"}], cache_path)
    assert cache_path.read_text(encoding="utf-8") == original
    assert not cache_path.with_suffix(".json.identity.json").exists()


def test_checkpoint_identity_binds_mode_and_declared_context(tmp_path: Path) -> None:
    cases = [{"id": "one", "query": "q"}]
    path = tmp_path / "retrieval.json"
    kwargs = {"suite": "retrieval", "mode": "vector_only", "scope": "pure"}
    identity = suites._eval_checkpoint_identity(cases, **kwargs)
    suites._save_eval_checkpoint(path, [{"id": "one"}], identity=identity)
    changed_mode = suites._eval_checkpoint_identity(cases, **{**kwargs, "mode": "no_graph"})
    with pytest.raises(ValueError, match="identity mismatch"):
        suites._load_eval_checkpoint(path, resume=True, identity=changed_mode)
    changed_runtime = suites._eval_checkpoint_identity(
        cases, **kwargs, context={"router_model": "different-test-model"}
    )
    with pytest.raises(ValueError, match="identity mismatch"):
        suites._load_eval_checkpoint(path, resume=True, identity=changed_runtime)


@pytest.mark.parametrize(
    ("behavior", "status"),
    [("clarify_or_scope", "needs_clarification"), ("abstain", "out_of_domain")],
)
def test_safe_non_answer_is_not_counted_as_wrong_abstention(
    behavior: str, status: str,
) -> None:
    checks = suites._answer_checks(
        {
            "answerability": "answerable",
            "expected_answer_behavior": behavior,
            "required_facts": [],
            "expected_citations": [],
        },
        {"status": status, "answer": "Chưa đủ thông tin để kết luận."},
    )
    assert checks["abstention_correct"] is True


def test_deterministic_counts_compound_structured_and_preserves_failed_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = [{"role": "user", "content": "ngữ cảnh đã biết"}]
    calls = []
    cases = [
        {"id": "compound", "query": "q", "cohort": "K51", "history": history,
         "case_type": "architecture", "contract_version": "query-plan-grounded-outcome-v9",
         "accepted_outcomes": [{"name": "structured-plus-rag", "state": "answer",
                                "allowed_modes": ["structured", "rag"], "task_count": {"min": 2, "max": 2},
                                "required_tasks": [{"mode": "structured", "lookup_type": "office",
                                                    "fact_lock_applicable": False}, {"mode": "rag"}]}]},
        {"id": "failure", "query": "fail", "cohort": "K51", "case_type": "hard_negative",
         "contract_version": "query-plan-grounded-outcome-v9",
         "accepted_outcomes": [{"name": "rag", "state": "answer", "allowed_modes": ["rag"],
                                "task_count": {"min": 1, "max": 1}, "required_tasks": [{"mode": "rag"}]}]},
    ]

    class Pipeline:
        def _run_retrieval(self, query, cohort=None, chat_history=None):
            assert os.environ["STUDENT_RAG_DISABLE_ROUTER_CACHE"] == "1"
            calls.append((query, chat_history))
            if query == "fail":
                raise TimeoutError("test failure")
            return {
                "query_plan": {"tasks": [{"mode": "rag"}, {"mode": "structured", "lookup_type": "office"}]},
                "task_results": [{"mode": "structured", "lookup_type": "office", "coverage": "covered", "evidence": [{"value": "x"}]}],
                "needs_llm_answer": True,
            }

    checkpoint = tmp_path / "det.json"
    monkeypatch.setenv("STUDENT_RAG_DISABLE_ROUTER_CACHE", "previous")
    report = suites.evaluate_deterministic(cases, pipeline_factory=Pipeline, checkpoint_path=checkpoint)
    assert report["summary"]["precision"] == 1.0
    assert report["summary"]["structured_selection_counts"]["expected_positive_n"] == 1
    assert report["summary"]["passed"] == 1
    assert calls == [("q", history), ("fail", None)]
    assert os.environ["STUDENT_RAG_DISABLE_ROUTER_CACHE"] == "previous"
    with pytest.raises(FileExistsError):
        suites.evaluate_deterministic(cases, pipeline_factory=Pipeline, checkpoint_path=checkpoint)
    resumed = suites.evaluate_deterministic(cases, pipeline_factory=Pipeline, checkpoint_path=checkpoint, resume=True)
    assert len(calls) == 2
    assert resumed["cases"][1]["error"] == "test failure"


def test_retrieval_checkpoint_and_history_do_not_repeat_failures(tmp_path: Path) -> None:
    calls = []
    history = [{"role": "user", "content": "prior query"}]

    class Pipeline:
        def _run_retrieval(self, query, cohort=None, chat_history=None):
            calls.append(chat_history)
            raise TimeoutError("test-only")

    case = {"id": "ret", "query": "q", "history": history, "cohort": "K51", "case_type": "regulation_true_rag", "relevance_judgments": [{"parent_section_id": "p", "grade": 2}]}
    checkpoint = tmp_path / "ret.json"
    kwargs = {"backend": "qdrant", "mode": "vector_primary_graph_supplement", "pipeline_factory": Pipeline, "checkpoint_path": checkpoint}
    suites.evaluate_retrieval([case], **kwargs)
    report = suites.evaluate_retrieval([case], **kwargs, resume=True)
    assert calls == [history]
    assert report["summary"]["n"] == 1
    assert report["summary"]["hit_at_5"] == 0.0


def test_generation_passes_history_disables_router_cache_and_is_once_only(tmp_path: Path) -> None:
    calls = []
    history = [{"role": "user", "content": "prior"}]

    class Pipeline:
        def answer(self, query, cohort=None, chat_history=None):
            assert os.environ["STUDENT_RAG_DISABLE_ROUTER_CACHE"] == "1"
            calls.append(chat_history)
            return {"status": "answered", "answer": "supported answer"}

    case = {"id": "answer", "query": "q", "history": history}
    kwargs = {"cache_path": tmp_path / "answer.json", "pipeline_factory": Pipeline}
    suites.generate_answers([case], **kwargs, resume=False)
    with pytest.raises(FileExistsError):
        suites.generate_answers([case], **kwargs, resume=False)
    suites.generate_answers([case], **kwargs, resume=True)
    assert calls == [history]


@pytest.mark.parametrize("scenario", ["cold_rag", "streaming"])
def test_production_retains_auditable_answers_history_and_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scenario: str,
) -> None:
    history = [{"role": "user", "content": "prior"}]
    calls = []
    response_payload = {"status": "answered", "answer": "Có căn cứ.", "citations_used": [{"parent_section_id": "p"}]}
    if scenario == "streaming":
        body = (
            f"event: metadata\ndata: {json.dumps(response_payload)}\n\n"
            f"event: token\ndata: {json.dumps({'text': 'Có căn cứ.'})}\n\n"
            "event: done\ndata: {}\n\n"
        ).encode()
    else:
        body = json.dumps(response_payload).encode()

    class Response(BytesIO):
        status = 200

    def request(req, **kwargs):
        calls.append(json.loads(req.data))
        return Response(body)

    monkeypatch.setattr(suites.urllib_request, "urlopen", request)
    case = {"id": "prod", "query": "q", "cohort": "K51", "history": history, "scenario": scenario, "expected_path": "regulation_rag"}
    kwargs = {"base_url": "http://unused", "checkpoint_path": tmp_path / "production.json"}
    report = suites.evaluate_production([case], **kwargs)
    assert calls[0]["chat_history"] == history
    assert report["cases"][0]["answer"] == "Có căn cứ."
    assert report["cases"][0]["response_payload"]["citations_used"] == response_payload["citations_used"]
    resumed = suites.evaluate_production([case], **kwargs, resume=True)
    assert len(calls) == 1
    assert resumed["summary"]["n"] == 1


def test_production_uses_browser_identity_and_reuses_it_for_warm_repeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_ids: list[str] = []
    response_payload = {"status": "answered", "answer": "Có căn cứ."}

    class Response(BytesIO):
        status = 200

    def request(req, **_kwargs):
        client_ids.append(req.get_header("X-client-id"))
        return Response(json.dumps(response_payload).encode())

    monkeypatch.setattr(suites.urllib_request, "urlopen", request)
    cases = [
        {
            "id": "cold",
            "query": "q",
            "cohort": "K51",
            "scenario": "cold_rag",
            "expected_path": "regulation_rag",
        },
        {
            "id": "warm",
            "repeat_of": "cold",
            "query": "q",
            "cohort": "K51",
            "scenario": "warm_cache",
            "expected_path": "regulation_rag",
        },
        {
            "id": "independent",
            "query": "q2",
            "cohort": "K51",
            "scenario": "cold_rag",
            "expected_path": "regulation_rag",
        },
    ]

    report = suites.evaluate_production(cases, base_url="http://unused")

    assert report["summary"]["n"] == 3
    assert client_ids[0] == client_ids[1]
    assert client_ids[0] != client_ids[2]
