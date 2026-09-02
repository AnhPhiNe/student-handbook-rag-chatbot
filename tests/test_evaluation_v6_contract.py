from __future__ import annotations

import json
import os
from argparse import Namespace
from io import BytesIO
from pathlib import Path

import pytest

import scripts.evaluate_system as runner
import src.evaluation.dataset as dataset
import src.evaluation.suites as suites
from src.evaluation.metrics import retrieval_metrics


def test_v6_deterministic_contract_is_resolved_from_cases() -> None:
    cases = [
        {"id": "one", "contract_version": "query-plan-target-holdout-v6"},
        {"id": "two", "contract_version": "query-plan-target-holdout-v6"},
    ]
    assert (
        runner._resolve_deterministic_contract(
            {"evaluation_contract": "comprehensive-question-scenario-holdout-v6"},
            cases,
        )
        == "query-plan-target-holdout-v6"
    )


def test_deterministic_contract_resolution_fails_closed() -> None:
    with pytest.raises(ValueError, match="contract is missing"):
        runner._resolve_deterministic_contract({}, [{"id": "one"}])
    with pytest.raises(ValueError, match="Unsupported"):
        runner._resolve_deterministic_contract(
            {"deterministic_contract": "legacy-implicit"}, [{"id": "one"}]
        )
    with pytest.raises(ValueError, match="conflicting"):
        runner._resolve_deterministic_contract(
            {},
            [
                {"id": "one", "contract_version": "query-plan-a"},
                {"id": "two", "contract_version": "query-plan-b"},
            ],
        )


def test_deterministic_gate_skips_non_applicable_metrics() -> None:
    gate = runner.evaluate_gates(
        "deterministic",
        {
            "precision": 1.0,
            "recall": 1.0,
            "false_positive_rate": 0.0,
            "citation_metadata_accuracy": None,
            "cross_cohort_leak": 0.0,
        },
    )
    assert gate["passed"] is True
    assert gate["checks"]["citation_metadata_accuracy"] == {
        "actual": None,
        "operator": ">=",
        "threshold": 1.0,
        "applicable": False,
        "passed": None,
    }


def test_post_fix_regression_is_not_labeled_original_holdout() -> None:
    report = {"suite": "deterministic", "summary": {"n": 140}}
    runner._finalize_report(
        report,
        expected_n=140,
        provenance={"benchmark_run_kind": "post_fix_regression"},
    )
    assert report["completeness"]["complete"] is True
    assert (
        report["completeness"]["publication_status"]
        == "post_fix_regression_not_original_holdout"
    )


def test_v6_deterministic_gold_contract_requires_plan_and_tasks() -> None:
    errors: list[str] = []
    dataset._validate_deterministic_contract(
        {"id": "missing", "contract_version": "query-plan-target-holdout-v6"},
        errors,
    )
    assert "missing: expected_plan must be an object" in errors

    errors = []
    dataset._validate_deterministic_contract(
        {
            "id": "valid",
            "contract_version": "query-plan-target-holdout-v6",
            "expected_plan": {
                "task_count": 1,
                "allowed_modes": ["rag"],
                "required_modes": ["rag"],
                "mode_counts": {"rag": 1},
                "lookup_types": [],
                "cohorts": ["K51"],
                "out_of_domain": False,
                "needs_clarification": False,
            },
            "expected_tasks": [
                {
                    "mode": "rag",
                    "intent": "open_question",
                    "cohorts": ["K51"],
                }
            ],
        },
        errors,
    )
    assert errors == []


def test_v7_outcome_contract_accepts_equivalent_task_shape() -> None:
    errors: list[str] = []
    case = {
        "id": "v7-equivalent",
        "contract_version": "query-plan-outcome-equivalent-v7",
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
                    }
                ],
                "structured_evidence": "required",
            }
        ],
    }
    dataset._validate_deterministic_v7_contract(case, errors)
    assert errors == []
    assert suites._v7_required_tasks_match(
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


def test_v7_outcome_contract_allows_task_level_clarification() -> None:
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
        "contract_version": "query-plan-outcome-equivalent-v7",
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
    report = suites.evaluate_deterministic_v2([case], pipeline_factory=Pipeline)
    assert report["summary"]["passed"] == 1
    assert report["cases"][0]["matched_outcome"] == "task-level-clarification"


def test_v8_contract_validates_grounded_execution_assertions() -> None:
    errors: list[str] = []
    case = {
        "id": "v8-grounded",
        "contract_version": "query-plan-grounded-outcome-v8",
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
                    }
                ],
                "structured_evidence": "required",
            }
        ],
    }
    dataset._validate_deterministic_v8_contract(case, errors)
    assert errors == []

    case["accepted_outcomes"][0]["required_tasks"][0]["expected_source_ids"] = []
    dataset._validate_deterministic_v8_contract(case, errors)
    assert any("expected_source_ids must be a non-empty string list" in error for error in errors)


def test_v8_evaluator_checks_source_row_and_resolved_result() -> None:
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
        "contract_version": "query-plan-grounded-outcome-v8",
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
    report = suites.evaluate_deterministic_v2([case], pipeline_factory=Pipeline)
    row = report["cases"][0]
    assert row["passed"] is True
    assert row["structured_source_correct"] is True
    assert row["structured_row_correct"] is True
    assert row["resolved_result_correct"] is True
    assert report["summary"]["assertion_support"]["resolved_result"] == 1


def test_v8_evaluator_fails_wrong_resolved_value_without_inflating_na() -> None:
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
        "contract_version": "query-plan-grounded-outcome-v8",
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
    report = suites.evaluate_deterministic_v2([case], pipeline_factory=Pipeline)
    row = report["cases"][0]
    assert row["passed"] is False
    assert row["structured_source_correct"] is None
    assert row["structured_row_correct"] is None
    assert row["resolved_result_correct"] is False
    assert report["summary"]["structured_source_accuracy"] is None


def test_v8_evaluator_recognizes_service_catalog_identity() -> None:
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
        "contract_version": "query-plan-grounded-outcome-v8",
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
    report = suites.evaluate_deterministic_v2([case], pipeline_factory=Pipeline)
    row = report["cases"][0]
    assert row["passed"] is True, json.dumps(
        row["accepted_outcome_evaluations"], ensure_ascii=False, indent=2
    )
    assert row["structured_source_correct"] is True
    assert row["structured_row_correct"] is True
    assert row["resolved_result_correct"] is None


def test_mutable_dataset_report_is_never_headline_eligible() -> None:
    report = runner._finalize_report(
        {"suite": "deterministic", "summary": {"n": 140}},
        expected_n=140,
        provenance={"dataset_frozen": False},
        profile="full",
    )
    assert (
        report["completeness"]["publication_status"]
        == "draft_dataset_not_for_headline"
    )

    errors = []
    dataset._validate_deterministic_contract(
        {
            "id": "clarify",
            "contract_version": "query-plan-target-holdout-v6",
            "expected_plan": {
                "task_count": 1,
                "allowed_modes": ["clarify"],
                "required_modes": ["clarify"],
                "mode_counts": {"clarify": 1},
                "lookup_types": [],
                "cohorts": ["K51"],
                "out_of_domain": False,
                "needs_clarification": True,
            },
            "expected_tasks": [{"mode": "clarify", "cohorts": ["K51"]}],
        },
        errors,
    )
    assert errors == []


def test_architecture_v7_release_bundle_is_valid_and_frozen() -> None:
    project_root = Path(__file__).resolve().parents[1]
    bundle_dir = project_root / "data" / "eval" / "architecture_v7"
    docstore_path = (
        project_root
        / "data"
        / "processed"
        / "chunks"
        / "all_docstore_items.json"
    )

    draft_report = dataset.validate_bundle(
        bundle_dir,
        docstore_path,
        require_frozen=False,
    )
    assert draft_report["valid"] is True
    assert draft_report["errors"] == []
    assert draft_report["warnings"] == []
    assert draft_report["counts"] == {
        "deterministic": 140,
        "retrieval": 160,
        "answers": 150,
        "production": 60,
    }

    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    overlap = json.loads(
        (bundle_dir / "overlap_audit.json").read_text(encoding="utf-8")
    )
    assert manifest["frozen"] is True
    assert manifest["system_executed_on_dataset"] is True
    assert manifest["user_review_approved"] is True
    assert overlap["exact_historical_match_count"] == 0
    assert overlap["high_similarity_review_count"] == 0

    frozen_report = dataset.validate_bundle(
        bundle_dir,
        docstore_path,
        require_frozen=True,
    )
    assert frozen_report["valid"] is True
    assert frozen_report["errors"] == []


def test_deterministic_v2_reports_non_applicable_assertions_as_na() -> None:
    class Pipeline:
        def _run_retrieval(self, query, cohort=None):
            return {
                "query_plan": {
                    "tasks": [
                        {
                            "mode": "rag",
                            "intent": "open_question",
                            "cohorts": ["K51"],
                        }
                    ]
                },
                "needs_llm_answer": True,
                "task_results": [],
            }

    case = {
        "id": "one",
        "query": "quy định nào?",
        "cohort": "K51",
        "expected_llm_called": True,
        "expected_plan": {
            "task_count": 1,
            "allowed_modes": ["rag"],
            "lookup_types": [],
            "cohorts": ["K51"],
            "out_of_domain": False,
            "needs_clarification": False,
        },
        "expected_tasks": [
            {"mode": "rag", "intent": "open_question", "cohorts": ["K51"]}
        ],
    }
    report = suites.evaluate_deterministic_v2([case], pipeline_factory=Pipeline)
    row = report["cases"][0]
    assert row["citation_metadata_correct"] is None
    assert row["structured_value_exact"] is None
    assert row["numeric_value_correct"] is None
    assert report["summary"]["citation_metadata_accuracy"] is None
    assert report["summary"]["assertion_support"]["citation_metadata"] == 0
    assert report["summary"]["passed"] == 1


def test_v6_runtime_storage_identity_requires_qdrant_and_mongo_v32() -> None:
    manifest = {
        "schema_version": "architecture-evaluation-v6",
        "hybrid_collection": "student_handbook_semantic_v32",
        "mongodb_parent_collection": "parent_docs_v32",
    }
    provenance = {
        "qdrant_collection": "student_handbook_semantic_v32",
        "mongodb_parent_collection": "parent_docs_v32",
    }
    assert runner._runtime_storage_errors(manifest, provenance, "qdrant") == []

    provenance["mongodb_parent_collection"] = "parent_docs_v31"
    assert runner._runtime_storage_errors(manifest, provenance, "qdrant") == [
        "runtime storage mismatch: mongodb_parent_collection='parent_docs_v31', "
        "expected 'parent_docs_v32'"
    ]


def test_v6_runtime_storage_identity_rejects_missing_manifest_field() -> None:
    errors = runner._runtime_storage_errors(
        {
            "schema_version": "architecture-evaluation-v6",
            "hybrid_collection": "student_handbook_semantic_v32",
        },
        {
            "qdrant_collection": "student_handbook_semantic_v32",
            "mongodb_parent_collection": "parent_docs_v32",
        },
        "qdrant",
    )
    assert errors == [
        "manifest missing storage identity: mongodb_parent_collection"
    ]


def test_retrieval_completeness_uses_dataset_count(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = []
    monkeypatch.setattr(runner, "evaluate_retrieval", lambda *args, **kwargs: {"suite": "retrieval", "summary": {"n": 160}})
    monkeypatch.setattr(runner, "_write", lambda report, *args: captured.append(report))
    runner._run_retrieval_modes(
        [{}] * 160,
        Namespace(ablation="vector_primary_graph_supplement", backend="qdrant", retrieval_scope="end_to_end", limit=None, output=Path("unused"), profile="full", resume=False),
        {},
    )
    assert captured[0]["completeness"]["complete"] is True
    assert captured[0]["completeness"]["expected_n"] == 160


@pytest.mark.parametrize("suite", ["deterministic", "retrieval", "answer_generation", "judge", "production"])
def test_completed_smoke_sample_is_never_headline_eligible(suite: str) -> None:
    report = runner._finalize_report(
        {"suite": suite, "summary": {"n": 5, "judged_n": 5}},
        expected_n=5, provenance={}, profile="smoke",
    )
    assert report["completeness"]["profile"] == "smoke"
    assert report["completeness"]["complete"] is False
    assert report["completeness"]["publication_status"] == "smoke_not_for_headline"
    if "gates" in report:
        assert report["gates"]["passed"] is False


@pytest.mark.parametrize("suite,count", [("deterministic", 140), ("retrieval", 160), ("judge", 150)])
def test_full_v6_counts_remain_headline_eligible(suite: str, count: int) -> None:
    report = runner._finalize_report(
        {"suite": suite, "summary": {"n": count, "judged_n": count}},
        expected_n=count, provenance={}, profile="full",
    )
    assert report["completeness"]["expected_n"] == count
    assert report["completeness"]["complete"] is True
    assert report["completeness"]["publication_status"] == "headline_eligible"


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
    changed_mode = suites._eval_checkpoint_identity(cases, **{**kwargs, "mode": "full"})
    with pytest.raises(ValueError, match="identity mismatch"):
        suites._load_eval_checkpoint(path, resume=True, identity=changed_mode)
    changed_runtime = suites._eval_checkpoint_identity(
        cases, **kwargs, context={"router_model": "different-test-model"}
    )
    with pytest.raises(ValueError, match="identity mismatch"):
        suites._load_eval_checkpoint(path, resume=True, identity=changed_runtime)


def test_failed_judge_records_do_not_make_headline_complete() -> None:
    report = runner._finalize_report(
        {"suite": "judge", "summary": {"n": 150, "judged_n": 149}},
        expected_n=150, provenance={},
    )
    assert report["completeness"]["complete"] is False
    assert report["completeness"]["publication_status"] == "partial_judge_not_for_headline"
    assert report["gates"]["passed"] is False


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


def test_expected_tasks_match_semantics_unordered_without_rejecting_optional_slots() -> None:
    expected = [
        {"mode": "structured", "lookup_type": "office", "intent": "lookup", "slots": {"office_name": "Phòng Đào tạo"}, "cohorts": ["K51"]},
        {"mode": "rag", "intent": "open_question", "cohorts": ["K51"]},
    ]
    actual = [
        {"mode": "rag", "intent": "open_question", "cohorts": ["K51"]},
        {"mode": "structured", "lookup_type": "office", "intent": "lookup", "slots": {"office_name": "phong dao tao", "table": "grounded-extra"}, "cohorts": ["K51"]},
    ]
    assert suites._expected_tasks_match(expected, actual)
    actual[1]["slots"]["office_name"] = "Phòng khác"
    assert not suites._expected_tasks_match(expected, actual)
    assert not suites._expected_tasks_match(
        [{"slots": {"letter_grade": "B+"}}], [{"slots": {"letter_grade": "B"}}]
    )
    assert suites._expected_tasks_match(
        [{"required_slot_keys": ["score"], "slots": {"score": 367}}],
        [{"slots": {"score": "367", "harmless_hint": "x"}}],
    )
    assert not suites._expected_tasks_match(
        [{"required_slot_keys": ["office"]}], [{"slots": {"requested_field": "email"}}]
    )


def test_deterministic_counts_compound_structured_and_preserves_failed_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    history = [{"role": "user", "content": "ngữ cảnh đã biết"}]
    calls = []
    cases = [
        {"id": "compound", "query": "q", "cohort": "K51", "history": history,
         "case_type": "architecture", "expected_llm_called": True,
         "expected_plan": {"task_count": 2, "allowed_modes": ["structured", "rag"], "mode_counts": {"structured": 1, "rag": 1}}},
        {"id": "failure", "query": "fail", "cohort": "K51", "case_type": "hard_negative",
         "expected_plan": {"task_count": 1, "allowed_modes": ["rag"]}},
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
    report = suites.evaluate_deterministic_v2(cases, pipeline_factory=Pipeline, checkpoint_path=checkpoint)
    assert report["summary"]["precision"] == 1.0
    assert report["summary"]["structured_selection_counts"]["expected_positive_n"] == 1
    assert report["summary"]["passed"] == 1
    assert calls == [("q", history), ("fail", None)]
    assert os.environ["STUDENT_RAG_DISABLE_ROUTER_CACHE"] == "previous"
    with pytest.raises(FileExistsError):
        suites.evaluate_deterministic_v2(cases, pipeline_factory=Pipeline, checkpoint_path=checkpoint)
    resumed = suites.evaluate_deterministic_v2(cases, pipeline_factory=Pipeline, checkpoint_path=checkpoint, resume=True)
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
