from __future__ import annotations

import hashlib
import json
import shutil

import pytest

from src.evaluation.single_cohort_gold import (
    apply_hidden_review,
    audit_bundle,
    legacy_compatibility_report,
)
from src.evaluation.single_cohort_v2 import (
    BUNDLE_DIR,
    evaluate_development_gates,
    evaluate_release_gates,
    exact_plan_match,
    semantic_plan_match,
    validate_bundle,
)
from scripts import evaluate_single_cohort_v2 as evaluator
from scripts.evaluate_single_cohort_v2 import (
    _citation_isolated,
    _finish_hidden_attempt,
    _reuse_answer_report_evaluation,
    _start_hidden_attempt,
    _structured_result_matches,
    _structured_source_bound,
    run_answers,
    run_executor_retrieval,
)


def test_answer_report_reuses_planner_and_executor_rows() -> None:
    planner_row = {"id": "dev-1", "passed": True}
    execution_row = {"id": "dev-1", "retrieval_hit_at_5": 1.0}
    answer_row = {"id": "dev-1", "answer": "verified"}

    planner, execution, answers = _reuse_answer_report_evaluation(
        {
            "planner": {"dev": {"rows": [planner_row]}},
            "executor_retrieval": {"rows": [execution_row]},
            "answers": [answer_row],
        }
    )

    assert planner == {"dev": [planner_row]}
    assert execution == [execution_row]
    assert answers == [answer_row]


def test_answer_report_rejects_unbound_answer_rows() -> None:
    with pytest.raises(ValueError, match="passed Planner"):
        _reuse_answer_report_evaluation(
            {
                "planner": {"dev": {"rows": [{"id": "dev-1", "passed": False}]}},
                "executor_retrieval": {"rows": [{"id": "dev-1"}]},
                "answers": [{"id": "dev-1"}],
            }
        )


@pytest.fixture(scope="module")
def gold_audit():
    return audit_bundle()


def test_frozen_bundle_has_required_counts_and_contract() -> None:
    result = validate_bundle()
    assert result.valid, result.errors
    assert result.counts == {"dev": 150, "hidden": 60}
    assert set(result.coverage["request_counts"]) >= {3, 4, 5, 6}
    assert set(result.coverage["statuses"]) == {
        "ok", "no_match", "invalid", "unresolved", "error"
    }
    assert result.coverage["same_tool_pair"]
    assert result.coverage["different_tool_pair"]
    assert result.coverage["case_annotation_states"]


def test_release_validation_accepts_frozen_human_gold_review() -> None:
    result = validate_bundle(require_gold_complete=True)
    assert result.valid, result.errors


def test_exact_plan_requires_request_order_and_slots() -> None:
    expected = {"outcome": "execute", "context_mode": "standalone", "effective_cohort": "K51", "effective_cohort_source": "raw_query", "atomic_requests": [{"request_id": "r1", "request_kind": "structured", "tool_name": "scoring", "intent": "direct_value", "query_span": "GPA 3.2", "slots": {"score": "3.2"}, "cohort_refs": ["K51"]}]}
    assert exact_plan_match(expected, expected)
    changed = {**expected, "atomic_requests": [{**expected["atomic_requests"][0], "slots": {}}]}
    assert not exact_plan_match(expected, changed)


def test_semantic_plan_accepts_only_proven_representation_differences() -> None:
    expected = {
        "outcome": "execute",
        "context_mode": "standalone",
        "query_mode": "validated",
        "effective_cohort": "K51",
        "effective_cohort_source": "raw_query",
        "atomic_requests": [
            {
                "request_id": "r1",
                "request_kind": "structured",
                "tool_name": "scoring",
                "intent": "direct_value",
                "query_span": "GPA 3.2",
                "slots": {"score": 3.2, "label": "Giỏi"},
                "cohort_refs": ["K51"],
            }
        ],
    }
    actual = {
        **expected,
        "atomic_requests": [
            {
                **expected["atomic_requests"][0],
                "query_span": "tra cứu GPA 3.2",
                "slots": {"score": "3.20", "label": "gioi"},
            }
        ],
    }
    assert not exact_plan_match(expected, actual)
    assert semantic_plan_match(expected, actual)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("effective_cohort", "K50"),
        ("outcome", "clarify"),
    ],
)
def test_semantic_plan_rejects_critical_top_level_changes(field, value) -> None:
    expected = {
        "outcome": "execute",
        "context_mode": "standalone",
        "query_mode": "validated",
        "effective_cohort": "K51",
        "effective_cohort_source": "raw_query",
        "atomic_requests": [],
    }
    assert not semantic_plan_match(expected, {**expected, field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("context_mode", "follow_up"),
        ("query_mode", "raw"),
        ("effective_cohort_source", "selected_cohort"),
    ],
)
def test_semantic_plan_leaves_provenance_representation_to_contract_gate(
    field, value
) -> None:
    expected = {
        "outcome": "execute",
        "context_mode": "standalone",
        "query_mode": "validated",
        "effective_cohort": "K51",
        "effective_cohort_source": "raw_query",
        "atomic_requests": [],
    }
    actual = {**expected, field: value}

    assert not exact_plan_match(expected, actual)
    assert semantic_plan_match(expected, actual)


def test_semantic_plan_rejects_wrong_tool_entity_request_count_and_unregistered_alias() -> None:
    request = {
        "request_id": "r1",
        "request_kind": "structured",
        "tool_name": "foreign_language",
        "intent": "direct_value",
        "query_span": "IELTS 5.5",
        "slots": {"certificate_or_language": "IELTS", "score_or_level": "5.5"},
        "cohort_refs": ["K51"],
    }
    expected = {
        "outcome": "execute",
        "context_mode": "standalone",
        "query_mode": "validated",
        "effective_cohort": "K51",
        "effective_cohort_source": "raw_query",
        "atomic_requests": [request],
    }
    wrong_tool = {**expected, "atomic_requests": [{**request, "tool_name": "scoring"}]}
    wrong_entity = {
        **expected,
        "atomic_requests": [
            {
                **request,
                "query_span": "TOEFL 5.5",
                "slots": {"certificate_or_language": "TOEFL", "score_or_level": "5.5"},
            }
        ],
    }
    unknown_alias = {
        **expected,
        "atomic_requests": [
            {
                **request,
                "slots": {"certificate_or_language": "English test", "score_or_level": "5.5"},
            }
        ],
    }
    extra_request = {**expected, "atomic_requests": [request, request]}
    assert not semantic_plan_match(expected, wrong_tool)
    assert not semantic_plan_match(expected, wrong_entity)
    assert not semantic_plan_match(expected, unknown_alias)
    assert not semantic_plan_match(expected, extra_request)


def test_semantic_plan_rejects_changed_negation_number_and_condition() -> None:
    request = {
        "request_id": "r1",
        "request_kind": "rag",
        "tool_name": None,
        "intent": "policy",
        "query_span": "nếu GPA 2.5 thì không được tốt nghiệp",
        "slots": {},
        "cohort_refs": ["K51"],
    }
    expected = {
        "outcome": "execute",
        "context_mode": "standalone",
        "query_mode": "validated",
        "effective_cohort": "K51",
        "effective_cohort_source": "raw_query",
        "atomic_requests": [request],
    }
    for span in (
        "nếu GPA 3.0 thì không được tốt nghiệp",
        "nếu GPA 2.5 thì được tốt nghiệp",
        "GPA 2.5 thì không được tốt nghiệp",
    ):
        actual = {**expected, "atomic_requests": [{**request, "query_span": span}]}
        assert not semantic_plan_match(expected, actual)


def test_semantic_plan_uses_registry_declared_rag_intent_equivalence() -> None:
    request = {
        "request_id": "r1",
        "request_kind": "rag",
        "tool_name": None,
        "intent": "policy",
        "query_span": "rút học phần",
        "slots": {},
        "cohort_refs": ["K51"],
    }
    expected = {
        "outcome": "execute",
        "context_mode": "standalone",
        "query_mode": "validated",
        "effective_cohort": "K51",
        "effective_cohort_source": "raw_query",
        "atomic_requests": [request],
    }
    equivalent = {
        **expected,
        "atomic_requests": [{**request, "intent": "procedure"}],
    }
    different_contract = {
        **expected,
        "atomic_requests": [{**request, "intent": "open_question"}],
    }
    assert semantic_plan_match(expected, equivalent)
    assert not semantic_plan_match(expected, different_contract)


def test_semantic_plan_leaves_intent_effect_to_execution_result_gate() -> None:
    request = {
        "request_id": "r1",
        "request_kind": "structured",
        "tool_name": "scoring",
        "intent": "direct_value",
        "query_span": "GPA 3.2",
        "slots": {"operation": "academic_classification", "score_or_grade": 3.2},
        "cohort_refs": ["K51"],
    }
    expected = {
        "outcome": "execute",
        "context_mode": "standalone",
        "query_mode": "validated",
        "effective_cohort": "K51",
        "effective_cohort_source": "raw_query",
        "atomic_requests": [request],
    }
    actual = {
        **expected,
        "atomic_requests": [{**request, "intent": "list_items"}],
    }

    assert not exact_plan_match(expected, actual)
    assert semantic_plan_match(expected, actual)


def test_semantic_execution_rejects_correct_source_with_wrong_result() -> None:
    source = {
        "record_id": "table-1",
        "document_id": "handbook-k51",
        "parent_section_id": "section-1",
    }
    request = {
        "request_id": "r1",
        "expected_status": "ok",
        "expected_result": {"result": {"matched_level": "bac_4"}},
        "expected_source_records": [source],
    }
    result = {
        "structured_result": {
            "request_id": "r1",
            "result": {"matched_level": "bac_3"},
            "source_records": [source],
        }
    }
    assert _structured_source_bound(result, request)
    assert not _structured_result_matches(result, request)


def test_semantic_execution_ignores_non_semantic_input_echo() -> None:
    source = {
        "record_id": "table-1",
        "document_id": "handbook-k51",
        "parent_section_id": "section-1",
    }
    request = {
        "request_id": "r1",
        "expected_status": "ok",
        "expected_source_records": [source],
        "expected_result": {
            "lookup_type": "scholarship_classification",
            "input_value": "điểm học bổng loại Giỏi",
            "result": {
                "label": "Giỏi",
                "academic_score_range": "3.20-3.59",
                "score": 0.8,
                "selection_method": "catalog_fuzzy",
            },
            "source_records": [source],
        },
    }
    result = {
        "structured_result": {
            "request_id": "r1",
            "lookup_type": "scholarship_classification",
            "input_value": (
                "điểm học bổng học bổng khuyến khích học tập loại Giỏi"
            ),
            "result": {
                "label": "Giỏi",
                "academic_score_range": "3.20-3.59",
                "score": 0.97,
                "selection_method": "catalog_fuzzy_semantic",
            },
            "source_records": [source],
        }
    }

    assert _structured_source_bound(result, request)
    assert _structured_result_matches(result, request)


def test_semantic_execution_does_not_ignore_business_score() -> None:
    request = {
        "request_id": "r1",
        "expected_status": "ok",
        "expected_result": {
            "lookup_type": "academic_classification",
            "result": {"score": 3.2, "label": "Giỏi"},
        },
    }
    result = {
        "structured_result": {
            "request_id": "r1",
            "lookup_type": "academic_classification",
            "result": {"score": 3.0, "label": "Giỏi"},
        }
    }

    assert not _structured_result_matches(result, request)


def test_metrics_keep_exact_diagnostic_separate_from_semantic_execution() -> None:
    planner_rows = {
        "dev": [
            {
                "id": "dev-1",
                "category": "single_rag",
                "passed": True,
                "exact_passed": False,
                "semantic_passed": True,
            },
            {
                "id": "dev-2",
                "category": "single_rag",
                "passed": False,
                "exact_passed": False,
                "semantic_passed": False,
            },
        ]
    }
    metrics = evaluator._metrics(
        True,
        planner_rows,
        [{"id": "dev-1", "semantic_executable": True}],
        [],
        [],
        quality_checks_passed=True,
        parity_passed=True,
        conformance_passed=True,
    )
    assert metrics["dev_exact_plan"] == 0.0
    assert metrics["dev_semantic_plan"] == 0.5
    assert metrics["dev_semantic_executable"] == 0.5
    assert metrics["dev_semantic_category_floor"] == 0.5


def test_manifest_hash_detects_hidden_or_dev_tampering(tmp_path) -> None:
    bundle = tmp_path / "single_cohort_v2"
    shutil.copytree(BUNDLE_DIR, bundle)
    dev_path = bundle / "dev.json"
    cases = json.loads(dev_path.read_text(encoding="utf-8"))
    cases[0]["query"] += " tampered"
    dev_path.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
    result = validate_bundle(bundle)
    assert not result.valid
    assert "frozen hash mismatch: dev.json" in result.errors


def test_bundle_validation_rejects_incorrect_cohort_authority(tmp_path) -> None:
    bundle = tmp_path / "single_cohort_v2"
    shutil.copytree(BUNDLE_DIR, bundle)
    dev_path = bundle / "dev.json"
    dev = json.loads(dev_path.read_text(encoding="utf-8"))
    target = next(case for case in dev if case["id"] == "dev-robustness-02")
    target["expected"]["effective_cohort_source"] = "raw_query"
    dev_path.write_text(
        json.dumps(dev, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["dev.json"] = hashlib.sha256(dev_path.read_bytes()).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    result = validate_bundle(bundle)

    assert not result.valid
    assert any("cohort source mismatch" in error for error in result.errors)


def test_release_gates_fail_closed_when_metrics_are_missing() -> None:
    result = evaluate_release_gates({"contract_invariants": 1.0})
    assert not result.passed
    assert "hidden_semantic_executable" in result.missing_metrics


def test_development_gate_does_not_require_hidden_metric() -> None:
    result = evaluate_development_gates({"contract_invariants": 1.0})
    assert not result.passed
    assert "hidden_semantic_executable" not in result.missing_metrics
    assert "dev_semantic_executable" in result.missing_metrics


def test_gold_audit_uses_real_sources_and_requires_human_hidden_review(gold_audit) -> None:
    result = gold_audit
    assert len(result.dev) == 150
    assert len(result.hidden) == 60
    assert result.dev_review_queue
    assert len(result.review_queue) == 60
    assert all(case["annotation"]["state"] == "review_required" for case in result.hidden)
    structured = [
        request
        for case in result.dev
        for request in case["expected"]["atomic_requests"]
        if request["request_kind"] == "structured"
        and request["gold_audit"].get("actual_status") == "ok"
    ]
    assert structured
    assert all(request["expected_source_records"] for request in structured)
    assert all(
        {
            "record_id", "document_id", "parent_section_id",
            "source_pages", "cohort", "source_type",
        }
        <= set(record)
        for request in structured
        for record in request["expected_source_records"]
    )
    assert all(request["gold_audit"]["cohort_applicable"] for request in structured)
    inherited = [
        record
        for request in structured
        for record in request["expected_source_records"]
        if request["tool_name"] == "foreign_language"
        and record.get("cohort") == "K50"
    ]
    assert inherited
    assert all("K51" in record.get("applicable_cohorts", []) for record in inherited)
    formula_requests = [
        request for request in structured if request["tool_name"] == "formula"
    ]
    assert formula_requests
    assert all(
        request["gold_audit"]["annotation_state"] == "review_required"
        and request["gold_audit"]["source_data_verified"] is False
        for request in formula_requests
    )


def test_rag_candidate_discovery_uses_grounded_follow_up_context(gold_audit) -> None:
    by_id = {case["id"]: case for case in gold_audit.dev}
    follow_up = by_id["dev-follow_up-03"]["expected"]["atomic_requests"][0]
    learning_again = next(
        request
        for case in gold_audit.dev
        for request in case["expected"]["atomic_requests"]
        if request["request_kind"] == "rag" and request["query_span"] == "học lại"
    )

    expected_parent = "K51_QuyCheDaoTao_Chuong3_Dieu10"
    assert expected_parent in {
        candidate["parent_section_id"]
        for candidate in follow_up["evidence_candidates"]
    }
    assert expected_parent in {
        candidate["parent_section_id"]
        for candidate in learning_again["evidence_candidates"]
    }


def test_pending_hidden_review_cannot_be_applied(gold_audit) -> None:
    result = gold_audit
    with pytest.raises(ValueError, match="not human-approved"):
        apply_hidden_review(result.hidden, result.review_queue)


def test_fault_injection_review_does_not_require_fake_rag_evidence(
    gold_audit,
) -> None:
    case = next(case for case in gold_audit.hidden if case.get("fault_injection"))
    queue = next(
        row for row in gold_audit.review_queue if row["case_id"] == case["id"]
    )
    queue = json.loads(json.dumps(queue))
    queue.update(
        {
            "decision": "approved",
            "reviewer": "human-reviewer",
            "reviewed_at": "2026-08-19T00:00:00+00:00",
        }
    )
    for request in queue["request_reviews"]:
        request["decision"] = "approved"

    approved = apply_hidden_review([case], [queue])

    assert approved[0]["annotation"]["state"] == "human_approved"


def test_legacy_compatibility_classification_preserves_frozen_bundle() -> None:
    report = legacy_compatibility_report()
    assert report["legacy_bundle_preserved"] is True
    assert report["legacy_hashes"]["match"] is True
    assert report["suites"] == {
        "deterministic": {"regression": 120, "deferred_multi_cohort": 0},
        "retrieval": {"regression": 136, "deferred_multi_cohort": 44},
        "answers": {"regression": 85, "deferred_multi_cohort": 15},
        "production": {"regression": 60, "deferred_multi_cohort": 0},
    }


def test_formula_records_are_bound_to_real_parent_sections() -> None:
    formulas = json.loads(
        (BUNDLE_DIR.parents[1] / "processed/tables/formula_rules.json").read_text(
            encoding="utf-8"
        )
    )
    parents = json.loads(
        (BUNDLE_DIR.parents[1] / "processed/chunks/all_docstore_items.json").read_text(
            encoding="utf-8"
        )
    )
    parent_ids = {item["_id"] for item in parents}
    assert formulas
    assert all(record.get("source_parent_id") in parent_ids for record in formulas)


def test_citation_isolation_rejects_unscoped_or_cross_request_evidence() -> None:
    assert _citation_isolated(
        {
            "citations": [{"request_id": "r1"}],
            "retrieved_items": [{"metadata": {"request_id": "r2"}}],
        },
        {"r1", "r2"},
    )
    assert not _citation_isolated(
        {"citations": [{"request_id": None}], "retrieved_items": []},
        {"r1"},
    )
    assert not _citation_isolated(
        {"citations": [{"request_id": "r3"}], "retrieved_items": []},
        {"r1", "r2"},
    )


def test_executor_uses_the_already_validated_planner_decision() -> None:
    class _Normalizer:
        @staticmethod
        def normalize_for_retrieval(query):
            return query

    class _Pipeline:
        slang_normalizer = _Normalizer()

        def __init__(self):
            self.executed_decision = None

        def _execute_single_cohort_retrieval(self, **kwargs):
            self.executed_decision = kwargs["router_decision"]
            return {
                "router_decision": kwargs["router_decision"],
                "request_results": [{"request_id": "r1", "status": "no_match"}],
                "retrieved_items": [],
                "citations": [],
            }

    expected = {
        "outcome": "execute",
        "context_mode": "standalone",
        "query_mode": "validated",
        "effective_cohort": "K51",
        "effective_cohort_source": "selected_cohort",
        "atomic_requests": [
            {
                "request_id": "r1",
                "request_kind": "rag",
                "tool_name": None,
                "intent": "regulation",
                "query_span": "quy chế",
                "slots": {},
                "cohort_refs": ["K51"],
                "expected_status": "no_match",
            }
        ],
    }
    decision = {
        "outcome": "execute",
        "route": "rag",
        "execution_mode": "regulation",
        "context_mode": "standalone",
        "cohort": "K51",
        "effective_cohort_source": "selected_cohort",
        "effective_query": "quy chế",
        "query_handling": {"mode": "validated"},
        "lookup_requests": [
            {
                "request_kind": "rag",
                "lookup_type": None,
                "intent": "regulation",
                "query_span": "quy chế",
                "slots": {},
                "cohort_refs": ["K51"],
            }
        ],
    }
    pipeline = _Pipeline()
    result_sink = {}

    rows = run_executor_retrieval(
        [{"id": "case-1", "query": "quy chế", "expected": expected}],
        pipeline,
        planner_rows={
            "case-1": {
                "id": "case-1",
                "passed": True,
                "validated_decision": decision,
            }
        },
        result_sink=result_sink,
    )

    assert pipeline.executed_decision == decision
    assert result_sink["case-1"]["router_decision"] == decision
    assert rows[0]["plan_correct"] is True
    assert rows[0]["status_match"] is True


def test_answer_composer_reuses_validated_execution_without_router_call() -> None:
    expected = {
        "outcome": "execute",
        "context_mode": "standalone",
        "query_mode": "validated",
        "effective_cohort": "K51",
        "effective_cohort_source": "selected_cohort",
        "atomic_requests": [
            {
                "request_id": "r1",
                "request_kind": "rag",
                "tool_name": None,
                "intent": "regulation",
                "query_span": "quy chế",
                "slots": {},
                "cohort_refs": ["K51"],
                "expected_status": "no_match",
            }
        ],
    }
    decision = {
        "outcome": "execute",
        "context_mode": "standalone",
        "cohort": "K51",
        "effective_cohort_source": "selected_cohort",
        "effective_query": "quy chế",
        "query_handling": {"mode": "validated"},
        "lookup_requests": [
            {
                "request_kind": "rag",
                "lookup_type": None,
                "intent": "regulation",
                "query_span": "quy chế",
                "slots": {},
                "cohort_refs": ["K51"],
            }
        ],
    }
    execution = {
        "router_decision": decision,
        "effective_query": "quy chế",
        "request_results": [{"request_id": "r1", "status": "no_match"}],
        "retrieved_items": [],
        "citations": [],
    }

    class _Pipeline:
        def _run_retrieval(self, *_args, **_kwargs):
            raise AssertionError("router/retrieval must not run again")

        def answer(self, query, *, chat_history, cohort):
            result = self._run_retrieval(
                query, cohort, chat_history=chat_history
            )
            return {
                "status": "low_confidence",
                "answer": "Không đủ bằng chứng.",
                "model_used": None,
                "llm_called": False,
                "citations": result["citations"],
                "retrieved_items": result["retrieved_items"],
                "router_decision": result["router_decision"],
                "effective_query": result["effective_query"],
                "debug": {
                    "request_results": result["request_results"],
                    "partial_status": "failed",
                },
            }

    rows = run_answers(
        [
            {
                "id": "case-1",
                "query": "quy chế",
                "selected_cohort": "K51",
                "chat_history": [],
                "expected": expected,
            }
        ],
        _Pipeline(),
        planner_rows={"case-1": {"id": "case-1", "passed": True}},
        execution_results={"case-1": execution},
    )

    assert rows[0]["provider_failure"] is False
    assert rows[0]["answer_contract_bound"] is True


def test_hidden_attempt_retry_requires_zero_output_and_same_binding(
    tmp_path, monkeypatch
) -> None:
    attempt_path = tmp_path / "hidden_release_attempt.json"
    monkeypatch.setattr(evaluator, "HIDDEN_ATTEMPT_PATH", attempt_path)
    binding = {"commit": "abc", "dataset_hashes": {"hidden.json": "123"}}
    first = _start_hidden_attempt(binding, retry_provider_outage=False)
    finished = _finish_hidden_attempt(
        first,
        planner_rows=[{"provider_failure": True}],
        answer_rows=[],
    )
    assert finished["status"] == "provider_outage"
    assert finished["model_output_count"] == 0

    retried = _start_hidden_attempt(binding, retry_provider_outage=True)
    assert retried["attempt_id"] != first["attempt_id"]
    assert retried["incidents"][0]["type"] == "provider_outage_retry"
    with pytest.raises(ValueError, match="unchanged artifacts"):
        _start_hidden_attempt(
            {"commit": "changed"}, retry_provider_outage=True
        )
