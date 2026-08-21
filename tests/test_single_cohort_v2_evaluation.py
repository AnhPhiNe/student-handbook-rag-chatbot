from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.evaluation.single_cohort_gold import (
    apply_approved_rag_source_expansions,
    apply_hidden_review,
    audit_bundle,
    legacy_compatibility_report,
)
from src.evaluation.single_cohort_v2 import (
    BUNDLE_DIR,
    evaluate_development_gates,
    evaluate_release_gates,
    execution_plan_match,
    exact_plan_match,
    semantic_plan_match,
    validate_bundle,
)
from scripts import evaluate_single_cohort_v2 as evaluator
from scripts import replay_single_cohort_v2_dev as replay
from scripts import rebind_single_cohort_v2_planner as planner_rebind
from scripts.evaluate_single_cohort_v2 import (
    _actual_ok_requests,
    _expected_rag_gold_requests,
    _citation_isolated,
    _finish_hidden_attempt,
    _final_composition_contract_passed,
    _reuse_answer_report_evaluation,
    _start_hidden_attempt,
    _structured_result_matches,
    _structured_source_bound,
    run_answers,
    run_executor_retrieval,
)


def test_contract_checks_only_requests_with_actual_verified_output() -> None:
    requests = [
        {
            "request_id": "r1",
            "request_kind": "structured",
            "expected_status": "ok",
        },
        {
            "request_id": "r2",
            "request_kind": "rag",
            "expected_status": "ok",
        },
        {
            "request_id": "r3",
            "request_kind": "rag",
            "expected_status": "no_match",
        },
    ]

    assert _actual_ok_requests(requests, {"r1": "no_match", "r2": "ok"}) == [
        requests[1]
    ]
    assert _expected_rag_gold_requests(requests) == [requests[1]]


def test_planner_rebind_allows_only_declared_retrieval_and_eval_paths() -> None:
    assert planner_rebind._path_is_allowed(
        "src/retrieval/core/bm25_retriever.py"
    )
    assert planner_rebind._path_is_allowed(
        "data/processed/retrieval/bm25_index.json"
    )
    assert planner_rebind._path_is_allowed("scripts/evaluate_single_cohort_v2.py")
    assert planner_rebind._path_is_allowed(
        "scripts/selective_single_cohort_answer_reuse.py"
    )
    assert planner_rebind._path_is_allowed(
        "scripts/run_single_cohort_production_smoke.py"
    )
    assert planner_rebind._path_is_allowed("tests/test_bm25_retriever.py")
    assert not planner_rebind._path_is_allowed("src/retrieval/core/ai_router.py")
    assert not planner_rebind._path_is_allowed("configs/structured_lookup_registry.yaml")


def test_execution_results_output_requires_executor(monkeypatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        [
            "evaluate_single_cohort_v2.py",
            "--execution-results-output",
            "execution.json",
        ],
    )
    with pytest.raises(SystemExit):
        evaluator.main()


def test_offline_replay_keeps_safe_no_match_as_semantic_failure_only() -> None:
    expected = {
        "outcome": "execute",
        "effective_cohort": "K51",
        "atomic_requests": [
            {
                "request_id": "r1",
                "request_kind": "structured",
                "tool_name": "student_service",
                "intent": "contact",
                "query_span": "đơn vị hỗ trợ dịch vụ",
                "slots": {"service": "dịch vụ", "requested_field": "unit"},
                "cohort_refs": ["K51"],
                "expected_status": "ok",
                "expected_source_records": [{"record_id": "unit-a"}],
                "expected_result": {"result": [{"unit_name": "Đơn vị A"}]},
            }
        ],
    }
    row = {
        "id": "dev-safe-no-match",
        "router_decision": {
            "outcome": "execute",
            "cohort": "K51",
            "lookup_requests": [
                {
                    "request_kind": "structured",
                    "lookup_type": "student_service",
                    "intent": "contact",
                    "query_span": "đơn vị hỗ trợ dịch vụ",
                    "slots": {"service": "dịch vụ", "requested_field": "all"},
                    "cohort_refs": ["K51"],
                }
            ],
        },
        "request_results": [{"request_id": "r1", "status": "no_match"}],
        "citations": [],
        "answer_composition": {},
        "provider_failure": False,
    }
    case = {"id": row["id"], "category": "robustness", "expected": expected}

    execution = replay._reevaluate_execution(case, row)
    answer = replay._reevaluate_answer(case, row)

    assert execution["semantic_executable"] is False
    assert execution["structured_bindings"] == []
    assert answer["answer_contract_bound"] is True


def test_offline_replay_rebinds_answer_to_additive_rag_gold() -> None:
    parent_id = "K51_regulation_scope_b"
    expected = {
        "outcome": "execute",
        "effective_cohort": "K51",
        "atomic_requests": [
            {
                "request_id": "r1",
                "request_kind": "rag",
                "tool_name": None,
                "intent": "policy",
                "query_span": "quy định đó",
                "slots": {},
                "cohort_refs": ["K51"],
                "expected_status": "ok",
                "expected_evidence": {"parent_section_ids": [parent_id]},
            }
        ],
    }
    row = {
        "id": "dev-additive-gold",
        "router_decision": {
            "outcome": "execute",
            "cohort": "K51",
            "lookup_requests": [
                {
                    "request_kind": "rag",
                    "lookup_type": None,
                    "intent": "policy",
                    "query_span": "quy định đó",
                    "slots": {},
                    "cohort_refs": ["K51"],
                }
            ],
        },
        "request_results": [{"request_id": "r1", "status": "ok"}],
        "citations": [{"request_id": "r1", "parent_section_id": parent_id}],
        "answer_composition": {
            "final_contract_passed": True,
            "request_results": [
                {
                    "request_id": "r1",
                    "request_kind": "rag",
                    "claim_count": 1,
                    "contract_passed": True,
                }
            ],
        },
        "provider_failure": False,
    }
    case = {"id": row["id"], "category": "follow_up", "expected": expected}

    assert replay._reevaluate_answer(case, row)["answer_contract_bound"] is True


def test_offline_replay_preserves_bound_hit_when_answer_omits_retrieval_pool() -> None:
    expected = {
        "outcome": "execute",
        "effective_cohort": "K51",
        "atomic_requests": [
            {
                "request_id": "r1",
                "request_kind": "rag",
                "tool_name": None,
                "intent": "policy",
                "query_span": "quy định đó",
                "slots": {},
                "cohort_refs": ["K51"],
                "expected_status": "ok",
                "expected_evidence": {"parent_section_ids": ["source-a"]},
            }
        ],
    }
    row = {
        "id": "dev-replay-hit",
        "router_decision": {
            "outcome": "execute",
            "cohort": "K51",
            "lookup_requests": [
                {
                    "request_kind": "rag",
                    "lookup_type": None,
                    "intent": "policy",
                    "query_span": "quy định đó",
                    "slots": {},
                    "cohort_refs": ["K51"],
                }
            ],
        },
        "request_results": [{"request_id": "r1", "status": "ok"}],
        "citations": [{"request_id": "r1", "parent_section_id": "source-a"}],
    }
    case = {"id": row["id"], "category": "single_rag", "expected": expected}

    execution = replay._reevaluate_execution(case, row, {"rag_hits": [True]})

    assert execution["rag_hits"] == [True]
    assert execution["semantic_executable"] is True


def test_offline_replay_fails_closed_without_bound_hit_data() -> None:
    case = {
        "id": "dev-missing-replay-hit",
        "category": "single_rag",
        "expected": {
            "outcome": "execute",
            "effective_cohort": "K51",
            "atomic_requests": [
                {
                    "request_id": "r1",
                    "request_kind": "rag",
                    "tool_name": None,
                    "intent": "policy",
                    "query_span": "quy định đó",
                    "slots": {},
                    "cohort_refs": ["K51"],
                    "expected_status": "ok",
                    "expected_evidence": {"parent_section_ids": ["source-a"]},
                }
            ],
        },
    }
    row = {
        "id": case["id"],
        "router_decision": {
            "outcome": "execute",
            "cohort": "K51",
            "lookup_requests": [
                {
                    "request_kind": "rag",
                    "lookup_type": None,
                    "intent": "policy",
                    "query_span": "quy định đó",
                    "slots": {},
                    "cohort_refs": ["K51"],
                }
            ],
        },
        "request_results": [{"request_id": "r1", "status": "ok"}],
        "citations": [{"request_id": "r1", "parent_section_id": "source-a"}],
    }

    with pytest.raises(ValueError, match="lacks bound RAG Hit@5"):
        replay._reevaluate_execution(case, row, {"rag_hits": []})


def test_offline_replay_retains_only_deterministic_fault_rows_without_answers() -> None:
    fault_row = {
        "id": "dev-fault",
        "skipped": True,
        "semantic_executable": None,
        "failure_type": "deterministic_fault_suite",
    }

    rows = replay._replay_execution_rows(
        {"dev-fault": {"id": "dev-fault", "expected": {}}},
        [],
        [fault_row],
    )

    assert rows == [fault_row]
    assert rows[0] is not fault_row


def test_offline_replay_rejects_regular_execution_row_without_answer() -> None:
    source_row = {
        "id": "dev-unbound",
        "semantic_executable": True,
        "failure_type": "pass",
    }

    with pytest.raises(ValueError, match="has no answer"):
        replay._replay_execution_rows(
            {"dev-unbound": {"id": "dev-unbound", "expected": {}}},
            [],
            [source_row],
        )


def test_offline_replay_change_allowlist_excludes_runtime_code() -> None:
    assert replay._allowed_replay_change("scripts/evaluate_single_cohort_v2.py")
    assert replay._allowed_replay_change("data/eval/single_cohort_v2/dev.json")
    assert replay._allowed_replay_change("tests/test_single_cohort_v2_evaluation.py")
    assert not replay._allowed_replay_change("src/generation/prompt_builder.py")


def test_final_composition_contract_accepts_source_bound_structured_fallback() -> None:
    composition = {
        "contract_passed": False,
        "request_results": [
            {
                "request_id": "r1",
                "request_kind": "structured",
                "claim_count": 1,
                "contract_passed": False,
                "used_fallback": True,
            }
        ],
    }

    assert _final_composition_contract_passed(composition)


def test_final_composition_contract_rejects_empty_or_rag_fallback() -> None:
    assert not _final_composition_contract_passed(
        {
            "contract_passed": False,
            "request_results": [
                {
                    "request_kind": "structured",
                    "claim_count": 0,
                    "contract_passed": False,
                    "used_fallback": True,
                }
            ],
        }
    )
    assert not _final_composition_contract_passed(
        {
            "final_contract_passed": True,
            "request_results": ["malformed"],
        }
    )
    assert not _final_composition_contract_passed(
        {
            "contract_passed": False,
            "request_results": [
                {
                    "request_kind": "rag",
                    "claim_count": 1,
                    "contract_passed": False,
                    "used_fallback": True,
                }
            ],
        }
    )


def test_approved_rag_source_expansion_is_additive_and_source_bound() -> None:
    cases = [
        {
            "id": "dev-case",
            "annotation": {"state": "human_approved"},
            "expected": {
                "atomic_requests": [
                    {
                        "request_id": "r1",
                        "request_kind": "rag",
                        "cohort_refs": ["K51"],
                        "expected_evidence": {
                            "document_ids": ["handbook-k51"],
                            "parent_section_ids": ["K51_Old"],
                            "chunk_ids": ["old-chunk"],
                            "source_pages": [1],
                            "relevance_grade": 2,
                            "evidence_excerpts": ["old evidence"],
                            "source_bindings": [
                                {
                                    "document_id": "handbook-k51",
                                    "parent_section_id": "K51_Old",
                                    "chunk_ids": ["old-chunk"],
                                    "source_pages": [1],
                                    "relevance_grade": 2,
                                }
                            ],
                        },
                        "evidence_candidates": [],
                        "gold_audit": {"annotation_state": "human_approved"},
                    }
                ]
            },
        }
    ]
    approval = {
        "approved_by": "project_owner",
        "approved_at": "2026-08-21T00:00:00Z",
        "approval_statement": "approve additive source",
        "approval_base_commit": "abc",
        "expansions": [
            {
                "case_id": "dev-case",
                "request_id": "r1",
                "add_parent_section_ids": ["K51_New"],
            }
        ],
    }
    chunks = [
        {
            "chunk_id": "new-heading",
            "content": "direct source heading",
            "metadata": {
                "parent_section_id": "K51_New",
                "chunk_granularity": "section_heading",
                "document_id": "handbook-k51",
                "cohort": "K51",
                "source_pages": [2],
                "source_section": "New source",
            },
        }
    ]

    expanded = apply_approved_rag_source_expansions(cases, approval, chunks)
    request = expanded[0]["expected"]["atomic_requests"][0]

    assert cases[0]["expected"]["atomic_requests"][0]["expected_evidence"][
        "parent_section_ids"
    ] == ["K51_Old"]
    assert request["expected_evidence"]["parent_section_ids"] == [
        "K51_New",
        "K51_Old",
    ]
    assert len(request["expected_evidence"]["source_bindings"]) == 2
    assert request["evidence_candidates"][0]["origin"] == (
        "human_approved_source_expansion"
    )
    assert request["gold_audit"]["approval_base_commit"] == "abc"


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


def test_case_id_filter_accepts_human_attention_review_file(tmp_path: Path) -> None:
    path = tmp_path / "audit.json"
    path.write_text(
        json.dumps(
            {
                "reviews": [
                    {"id": "dev-a", "requires_human_attention": True},
                    {"id": "dev-b", "requires_human_attention": False},
                ]
            }
        ),
        encoding="utf-8",
    )

    assert evaluator._load_case_ids(path) == {"dev-a"}


def test_answer_report_rejects_unbound_answer_rows() -> None:
    with pytest.raises(ValueError, match="executable Planner"):
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


def test_release_validation_follows_fail_closed_hidden_freeze_state() -> None:
    result = validate_bundle(require_gold_complete=True)
    manifest = json.loads(
        (BUNDLE_DIR / "manifest.json").read_text(encoding="utf-8")
    )
    frozen = bool(
        manifest.get("hidden_frozen")
        and manifest.get("hidden_human_review_complete")
    )
    assert result.valid is frozen
    if not frozen:
        assert "gold audit is incomplete or hidden is not human-approved" in (
            result.errors
        )


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


def test_execution_plan_defers_structured_slot_representation_to_adapter() -> None:
    request = {
        "request_id": "r1",
        "request_kind": "structured",
        "tool_name": "program",
        "intent": "direct_value",
        "query_span": "ngành Công nghệ Thông tin thuộc khoa nào",
        "slots": {
            "program_or_faculty": "Công nghệ Thông tin",
            "requested_field": "faculty",
        },
        "cohort_refs": ["K51"],
    }
    expected = {
        "outcome": "execute",
        "effective_cohort": "K51",
        "atomic_requests": [request],
    }
    alias_representation = {
        **expected,
        "atomic_requests": [
            {
                **request,
                "slots": {
                    "program_or_faculty": "ngành Công nghệ Thông tin",
                    "requested_field": "faculty",
                },
            }
        ],
    }
    wrong_tool = {
        **alias_representation,
        "atomic_requests": [
            {**alias_representation["atomic_requests"][0], "tool_name": "faculty"}
        ],
    }

    assert not semantic_plan_match(expected, alias_representation)
    assert execution_plan_match(expected, alias_representation)
    assert not execution_plan_match(expected, wrong_tool)


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


def test_requested_field_result_ignores_candidate_representation() -> None:
    request = {
        "request_id": "r1",
        "expected_status": "ok",
        "slots": {"requested_field": "website"},
        "expected_result": {
            "lookup_scope": "faculty",
            "result": [
                {
                    "record_id": "legacy-record",
                    "unit_name": "Khoa Công nghệ Thông tin",
                    "websites": ["khoacntt.hcmue.edu.vn"],
                }
            ],
        },
    }
    result = {
        "structured_result": {
            "request_id": "r1",
            "lookup_scope": "faculty",
            "result": [
                {
                    "record_id": "canonical-record",
                    "unit_name": "Khoa Công nghệ Thông tin",
                    "websites": ["khoacntt.hcmue.edu.vn"],
                },
                {
                    "record_id": "lower-ranked-record",
                    "unit_name": "Khoa Tiếng Nhật",
                    "websites": ["khoatiengnhat.hcmue.edu.vn"],
                },
            ],
        }
    }

    assert _structured_result_matches(result, request)


def test_requested_field_result_rejects_wrong_business_value() -> None:
    request = {
        "request_id": "r1",
        "expected_status": "ok",
        "slots": {"requested_field": "unit"},
        "expected_result": {"result": [{"unit_name": "Trạm Y tế"}]},
    }
    result = {
        "structured_result": {
            "request_id": "r1",
            "result": [{"unit_name": "Phòng Đào tạo"}],
        }
    }

    assert not _structured_result_matches(result, request)


def test_requested_field_source_binding_accepts_approved_alternative() -> None:
    request = {
        "request_id": "r1",
        "slots": {"requested_field": "unit"},
        "expected_source_records": [
            {"record_id": "source-a", "document_id": "handbook", "parent_section_id": ""},
            {"record_id": "source-b", "document_id": "handbook", "parent_section_id": ""},
        ],
    }
    result = {
        "structured_result": {
            "request_id": "r1",
            "source_records": [
                {"source_record_id": "source-a", "document_id": "handbook", "parent_section_id": ""}
            ],
        }
    }

    assert _structured_source_bound(result, request)


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
            {
                "id": "dev-tampering",
                "category": "failure_isolation",
                "planner_skipped": True,
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


def test_live_planner_skips_plan_tampering_without_constructing_router(
    monkeypatch,
) -> None:
    cases = [
        {
            "id": "dev-tampering",
            "category": "failure_isolation",
            "fault_injection": {"type": "plan_tampering"},
        }
    ]

    def _unexpected_router_construction():
        raise AssertionError("deterministic tampering must not call the live planner")

    monkeypatch.setattr(evaluator.AIRouter, "from_config", _unexpected_router_construction)

    rows = evaluator.run_live_planner(cases)

    assert rows == [
        {
            "id": "dev-tampering",
            "category": "failure_isolation",
            "planner_skipped": True,
            "passed": False,
            "exact_passed": False,
            "semantic_passed": False,
            "failure_type": "deterministic_fault_suite",
            "reason": "Plan tampering is exercised after a valid plan by deterministic conformance.",
            "provider_failure": False,
        }
    ]


def test_live_planner_uses_production_catalog_hint_and_fails_router_fallback() -> None:
    captured: dict[str, object] = {}

    class FallbackRouter:
        model_name = evaluator.PLANNER_MODEL

        def route(self, query, *, chat_history, cohort, routing_hint):
            captured.update(
                {
                    "query": query,
                    "chat_history": chat_history,
                    "cohort": cohort,
                    "routing_hint": routing_hint,
                }
            )
            return {
                "router_error_type": "timeout",
                "router_error": "provider timed out",
                "outcome": "clarify",
            }

    rows = evaluator.run_live_planner(
        [
            {
                "id": "dev-directory",
                "category": "single_structured",
                "query": "Email PĐT là gì?",
                "selected_cohort": "K51",
                "chat_history": [],
            }
        ],
        router=FallbackRouter(),
        catalogs={
            "office": [
                {
                    "record_id": "office-pdt",
                    "unit_name": "Phòng Đào tạo",
                    "aliases": ["PĐT"],
                }
            ],
            "student_service": [],
            "faculty": [],
        },
    )

    assert captured["routing_hint"] == {
        "lookup_type": "office",
        "entity_text": "PĐT",
        "unit_name": "Phòng Đào tạo",
        "match_type": "exact_catalog_span",
    }
    assert rows[0]["failure_type"] == "provider"
    assert rows[0]["provider_failure"] is True
    assert not rows[0]["semantic_passed"]


def test_live_planner_rejects_router_cache_hits_from_live_metrics() -> None:
    class CachedRouter:
        model_name = evaluator.PLANNER_MODEL

        def route(self, *_args, **_kwargs):
            return {"router_cache_hit": True, "outcome": "execute"}

    rows = evaluator.run_live_planner(
        [{"id": "dev-cached", "category": "single_rag", "query": "K51 học phí?"}],
        router=CachedRouter(),
        catalogs={"office": [], "student_service": [], "faculty": []},
    )

    assert rows[0]["failure_type"] == "evaluation_integrity"
    assert rows[0]["provider_failure"] is True


def test_planner_checkpoint_exposes_execution_and_provider_counts(
    monkeypatch,
) -> None:
    monkeypatch.setattr(evaluator, "_commit", lambda: "commit-current")
    monkeypatch.setattr(
        evaluator,
        "_artifact_fingerprint",
        lambda: {"code": "fingerprint-current"},
    )
    validation = SimpleNamespace(
        valid=True,
        errors=[],
        coverage={"cases": 3},
        hashes={"dev.json": "dev-hash"},
    )
    rows = [
        {
            "id": "dev-ok",
            "passed": True,
            "exact_passed": False,
            "semantic_passed": True,
            "execution_eligible": True,
            "provider_failure": False,
        },
        {
            "id": "dev-provider",
            "passed": False,
            "semantic_passed": False,
            "execution_eligible": False,
            "provider_failure": True,
            "failure_type": "provider",
        },
        {
            "id": "dev-tampering",
            "planner_skipped": True,
            "passed": False,
            "provider_failure": False,
            "failure_type": "deterministic_fault_suite",
        },
    ]

    report = evaluator._planner_checkpoint_report(
        {"dev": rows},
        manifest={
            "schema_version": "schema-v1",
            "prompt_version": "dataset-prompt",
            "registry_version": "registry-v2",
        },
        validation=validation,
    )

    assert report["report_type"] == "single_cohort_v2_planner_checkpoint"
    assert report["commit"] == "commit-current"
    assert report["dataset_hashes"] == {"dev.json": "dev-hash"}
    assert report["artifact_fingerprint"] == {"code": "fingerprint-current"}
    assert report["planner"]["dev"]["case_total"] == 3
    assert report["planner"]["dev"]["planner_evaluable_total"] == 2
    assert report["planner"]["dev"]["semantic_passed"] == 1
    assert report["planner"]["dev"]["execution_eligible"] == 1
    assert report["planner"]["dev"]["provider_failures"] == 1
    assert report["planner"]["dev"]["rows"] == rows


def test_bound_planner_report_rejects_stale_freeze(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(evaluator, "_commit", lambda: "commit-current")
    monkeypatch.setattr(
        evaluator,
        "_artifact_fingerprint",
        lambda: {"code": "fingerprint-current"},
    )
    validation = SimpleNamespace(
        valid=True,
        errors=[],
        coverage={},
        hashes={"dev.json": "dev-hash"},
    )
    manifest = {
        "prompt_version": "dataset-prompt",
        "registry_version": "registry-v2",
    }
    report = evaluator._planner_checkpoint_report(
        {"dev": [{"id": "dev-ok", "execution_eligible": True}]},
        manifest=manifest,
        validation=validation,
    )
    path = tmp_path / "planner.json"
    evaluator._write_json_atomic(path, report)

    loaded = evaluator._load_bound_planner_report(
        path,
        manifest=manifest,
        validation=validation,
    )
    assert loaded["dev"][0]["id"] == "dev-ok"
    assert not list(tmp_path.glob(".*.tmp"))

    report["commit"] = "stale-commit"
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="commit"):
        evaluator._load_bound_planner_report(
            path,
            manifest=manifest,
            validation=validation,
        )


def test_development_planner_requires_checkpoint_and_separate_downstream() -> None:
    assert evaluator._development_stage_error(
        hidden_requested=False,
        planner="dev",
        run_executor="none",
        run_answers="none",
        planner_output=None,
    ) == "Development Planner evaluation requires --planner-output."

    assert "must run alone" in str(
        evaluator._development_stage_error(
            hidden_requested=False,
            planner="dev",
            run_executor="dev",
            run_answers="dev",
            planner_output=Path("planner.json"),
        )
    )

    assert (
        evaluator._development_stage_error(
            hidden_requested=False,
            planner="dev",
            run_executor="none",
            run_answers="none",
            planner_output=Path("planner.json"),
        )
        is None
    )
    assert (
        evaluator._development_stage_error(
            hidden_requested=True,
            planner="hidden",
            run_executor="hidden",
            run_answers="hidden",
            planner_output=None,
        )
        is None
    )


def test_hidden_freeze_requires_a_current_passing_development_report(
    tmp_path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(evaluator, "_commit", lambda: "commit-current")
    monkeypatch.setattr(
        evaluator,
        "_artifact_fingerprint",
        lambda: {"code": "fingerprint-current"},
    )
    manifest = {"prompt_version": "dataset-prompt", "registry_version": "registry-v2"}
    report = {
        "commit": "commit-current",
        "dataset_hashes": {"dev.json": "hash"},
        "artifact_fingerprint": {"code": "fingerprint-current"},
        "prompt_version": evaluator.ROUTER_PROMPT_VERSION,
        "dataset_prompt_version": "dataset-prompt",
        "registry_version": "registry-v2",
        "development_gates": {"passed": True},
    }
    path = tmp_path / "dev-report.json"
    path.write_text(json.dumps(report), encoding="utf-8")

    assert evaluator._verify_hidden_development_freeze(
        path,
        dataset_hashes={"dev.json": "hash"},
        manifest=manifest,
    ) == report

    report["development_gates"]["passed"] = False
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="did not pass"):
        evaluator._verify_hidden_development_freeze(
            path,
            dataset_hashes={"dev.json": "hash"},
            manifest=manifest,
        )


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


def test_bundle_validation_rejects_hidden_reuse_of_legacy_user_inputs(
    tmp_path,
) -> None:
    bundle = tmp_path / "single_cohort_v2"
    shutil.copytree(BUNDLE_DIR, bundle)
    shutil.copyfile(bundle / "hidden.json", bundle / "legacy_hidden_rc1.json")

    result = validate_bundle(bundle)

    assert not result.valid
    assert "hidden/legacy user-visible input overlap: 60 cases" in result.errors


def test_bundle_validation_rejects_structured_adapter_claim_for_rag_gold(
    tmp_path,
) -> None:
    bundle = tmp_path / "single_cohort_v2"
    shutil.copytree(BUNDLE_DIR, bundle)
    hidden_path = bundle / "hidden.json"
    hidden = json.loads(hidden_path.read_text(encoding="utf-8"))
    request = next(
        request
        for case in hidden
        for request in case["expected"]["atomic_requests"]
        if request["request_kind"] == "rag"
    )
    request["gold_audit"]["audit_method"] = "direct_tool_adapter"
    hidden_path.write_text(
        json.dumps(hidden, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["hidden.json"] = hashlib.sha256(
        hidden_path.read_bytes()
    ).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    result = validate_bundle(bundle)

    assert not result.valid
    assert any(
        "RAG gold cannot use structured adapter audit" in error
        for error in result.errors
    )


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
                    "execution_eligible": True,
                    "validated_decision": decision,
                }
        },
        result_sink=result_sink,
    )

    assert pipeline.executed_decision == decision
    assert result_sink["case-1"]["router_decision"] == decision
    assert rows[0]["plan_correct"] is True
    assert rows[0]["status_match"] is True


def test_answer_composer_reuses_validated_execution_without_router_call(
    monkeypatch,
) -> None:
    monkeypatch.setenv("STUDENT_RAG_EVAL_TELEMETRY", "0")
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
            assert os.environ["STUDENT_RAG_EVAL_TELEMETRY"] == "1"
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
                "evaluation_telemetry": {"safe_ttft_ms": 12.0, "total_ms": 15.0},
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
        planner_rows={
            "case-1": {
                "id": "case-1",
                "passed": True,
                "execution_eligible": True,
            }
        },
        execution_results={"case-1": execution},
    )

    assert rows[0]["provider_failure"] is False
    assert rows[0]["answer_contract_bound"] is True
    assert rows[0]["evaluation_telemetry"]["safe_ttft_ms"] == 12.0
    assert os.environ["STUDENT_RAG_EVAL_TELEMETRY"] == "0"


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
