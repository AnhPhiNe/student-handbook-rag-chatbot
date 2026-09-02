from __future__ import annotations

import json
import os
import shutil
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError

import pytest

from scripts.evaluate_system import _normalized_text_hash, _provenance
import src.evaluation.suites as evaluation_suites
from src.evaluation.dataset import _structured_source_index, validate_bundle
from src.evaluation.gates import evaluate_gates
from src.evaluation.judge import (
    PINNED_JUDGE_MODEL,
    GroqJudgeClient,
    JudgeConfig,
    JudgeQuotaPool,
    build_judge_prompt,
    compact_judge_packet,
    estimate_tokens,
    key_fingerprint,
    parse_judge_json,
)
from src.retrieval.core.retrieval_mode import DEFAULT_RETRIEVAL_MODE
from src.evaluation.metrics import retrieval_metrics, wilson_interval
from src.evaluation.reporting import write_report_bundle
from src.evaluation.suites import (
    _answer_checks,
    _deterministic_actual_group,
    _expected_response_status,
    _response_status_matches_expected,
    _retrieval_summary,
    _summarize_production_rows,
    evaluate_graph_supplement,
    evaluate_production,
    evaluate_retrieval,
    generate_answers,
    summarize_deterministic_rows,
)
from src.evaluation.human_audit import summarize_human_audit
from src.generation.gemini_client import GeminiKeyPool, GeminiKeyPoolConfig
from src.generation.gemini_client import GeminiClient


ROOT = Path(__file__).resolve().parents[1]
DOCSTORE_PATH = ROOT / "data" / "processed" / "chunks" / "all_docstore_items.json"


def _require_docstore_artifact() -> Path:
    if not DOCSTORE_PATH.is_file():
        pytest.skip("deploy-time docstore artifact is not committed in CI checkout")
    return DOCSTORE_PATH


def _valid_judge_payload() -> str:
    return json.dumps(
        {
            "faithfulness": 0.9,
            "answer_relevancy": 0.8,
            "answer_correctness": 0.85,
            "context_precision": 0.75,
            "context_recall": 1.0,
            "citation_correctness": 0.95,
            "unsupported_claim": False,
            "critical_false_pass": False,
            "rationale": "supported",
        }
    )


def test_frozen_final_bundle_is_compatible_with_current_sources() -> None:
    result = validate_bundle(
        ROOT / "data" / "eval" / "final_holdout",
        _require_docstore_artifact(),
        enforce_docstore_hash=False,
    )
    assert result["valid"], result["errors"]
    assert "manifest docstore hash mismatch" in result["warnings"]
    assert result["counts"] == {
        "deterministic": 120,
        "retrieval": 180,
        "answers": 100,
        "production": 60,
    }


def test_frozen_architecture_v5_holdout_is_valid() -> None:
    result = validate_bundle(
        ROOT / "data" / "eval" / "architecture_v5_holdout",
        _require_docstore_artifact(),
        enforce_docstore_hash=True,
    )
    assert result["valid"], result["errors"]
    assert result["counts"] == {
        "deterministic": 140,
        "retrieval": 160,
        "answers": 150,
        "production": 60,
    }


def test_frozen_architecture_v4_bundle_is_valid() -> None:
    bundle = ROOT / "data" / "eval" / "architecture_v4"
    if not bundle.is_dir():
        pytest.skip("architecture_v4 bundle has not been built")
    result = validate_bundle(
        bundle,
        _require_docstore_artifact(),
        enforce_docstore_hash=False,
    )
    assert result["valid"], result["errors"]
    assert "manifest docstore hash mismatch" in result["warnings"]
    assert result["counts"]["answers"] == 150


def test_program_source_aliases_preserve_cohort_identity() -> None:
    index = _structured_source_index(ROOT)
    assert index[("program", "K50_program_2")]["cohort"] == "K50"
    assert index[("program", "K51_program_2")]["cohort"] == "K51"


def test_legacy_compatibility_provenance_records_both_docstore_hashes() -> None:
    provenance = _provenance(
        ROOT / "data" / "eval" / "final_holdout",
        "qdrant",
        allow_docstore_drift=True,
    )

    assert provenance["compatibility_diagnostic"] is True
    assert provenance["docstore_hash"] == provenance["expected_docstore_hash"]
    assert provenance["actual_docstore_hash"]
    assert provenance["answer_generation_retrieval_mode"] == DEFAULT_RETRIEVAL_MODE
    assert provenance["phoranker_used_for_answer_generation"] is False


def test_v8_provenance_hashes_every_manifest_config() -> None:
    provenance = _provenance(
        ROOT / "data" / "eval" / "architecture_v8",
        "qdrant",
    )

    assert provenance["config_hashes_match_manifest"] is True
    assert provenance["config_hashes"].keys() == provenance[
        "expected_config_hashes"
    ].keys()
    assert "slang_dictionary" in provenance["config_hashes"]


def test_normalized_text_hash_is_stable_across_line_endings(tmp_path: Path) -> None:
    lf_path = tmp_path / "lf.yaml"
    crlf_path = tmp_path / "crlf.yaml"
    lf_path.write_bytes(b"key: value\nitems:\n  - one\n")
    crlf_path.write_bytes(b"key: value\r\nitems:\r\n  - one\r\n")

    assert _normalized_text_hash(lf_path) == _normalized_text_hash(crlf_path)


def test_validator_rejects_query_reused_from_legacy_eval(tmp_path: Path) -> None:
    eval_root = tmp_path / "eval"
    bundle_dir = eval_root / "final_holdout"
    shutil.copytree(ROOT / "data" / "eval" / "final_holdout", bundle_dir)
    deterministic = json.loads(
        (bundle_dir / "deterministic_tool_cases.json").read_text(encoding="utf-8")
    )
    (eval_root / "legacy_cases.json").write_text(
        json.dumps([{"query": deterministic[0]["query"]}], ensure_ascii=False),
        encoding="utf-8",
    )

    result = validate_bundle(
        bundle_dir,
        _require_docstore_artifact(),
    )

    assert result["valid"] is False
    assert any("legacy query overlap" in error for error in result["errors"])


def test_retrieval_metrics_are_graded_and_rank_sensitive() -> None:
    scores = retrieval_metrics([0, 2, 1, 0, 0])
    assert scores["hit_at_1"] == 0
    assert scores["hit_at_3"] == 1
    assert scores["reciprocal_rank"] == pytest.approx(0.5)
    assert 0 < scores["ndcg_at_5"] < 1


def test_retrieval_summary_excludes_graph_supplement_metrics() -> None:
    rows = [
        {
            "case_type": "regulation_true_rag",
            "hit_at_1": 1.0,
            "hit_at_3": 1.0,
            "hit_at_5": 1.0,
            "mrr": 1.0,
            "ndcg_at_5": 1.0,
            "citation_binding": True,
            "cohort_match": True,
            "content_type_match": True,
            "empty_retrieval": False,
            "cohort_leak": False,
            "synthetic_leak": False,
            "context_hit_at_10": True,
            "graph_related_hit": True,
            "related_cohort_leak": False,
            "latency_ms": 10.0,
            "eval_split": "realistic",
        }
    ]

    summary = _retrieval_summary(rows, rows)

    assert "graph_related_hit_rate" not in summary
    assert "graph_supporting_hit_rate" not in summary
    assert "context_hit_at_10" not in summary
    assert summary["hit_at_5"] == 1.0


def test_graph_supplement_eval_scores_related_selection_cap(tmp_path: Path) -> None:
    edges = [
        {"source": "K50_Source", "target": f"K50_Target_{index}", "relation": "ref"}
        for index in range(6)
    ]
    edges_path = tmp_path / "document_edges.json"
    edges_path.write_text(json.dumps(edges), encoding="utf-8")

    report = evaluate_graph_supplement(edges_path=edges_path, related_limit=5)

    selected = {
        row["target_parent_id"] for row in report["cases"] if row["target_selected"]
    }
    assert len(report["cases"]) == 6
    assert report["summary"]["direct_expansion_recall"] == 1.0
    assert report["summary"]["related_selection_recall_at_5"] == pytest.approx(5 / 6)
    assert selected == {f"K50_Target_{index}" for index in range(5)}


def test_wilson_interval_bounds_probability() -> None:
    interval = wilson_interval(98, 100)
    assert 0 <= interval["low"] <= interval["high"] <= 1


def test_deterministic_summary_counts_nested_router_validation_errors() -> None:
    rows = [
        {
            "expected_group": "structured",
            "actual_group": "rag",
            "passed": False,
            "router_api_success": True,
            "router_cache_hit": False,
            "router_validation_errors": [],
            "router_decision": {
                "router_validation_errors": ["missing_slot:score_or_level"]
            },
            "latency_ms": 10.0,
            "eval_split": "realistic",
        },
        {
            "expected_group": "rag",
            "actual_group": "rag",
            "passed": True,
            "router_api_success": True,
            "router_cache_hit": False,
            "router_decision": {"router_validation_errors": []},
            "latency_ms": 20.0,
            "eval_split": "stress",
        },
    ]

    summary = summarize_deterministic_rows(rows)

    assert summary["router_validation_failure_rate"] == 0.5


def test_deterministic_group_uses_query_plan_modes_with_composer_enabled() -> None:
    structured = {"lookup_type": "foreign_language", "items": [{"value": "B1"}]}
    result = {
        "strategy": "query_plan_execution",
        "needs_llm_answer": True,
        "query_plan": {"tasks": [{"mode": "structured"}]},
    }

    assert _deterministic_actual_group(result, structured) == "structured"


def test_deterministic_group_recognizes_mixed_query_plan() -> None:
    result = {
        "strategy": "query_plan_execution",
        "needs_llm_answer": True,
        "query_plan": {
            "tasks": [{"mode": "structured"}, {"mode": "rag"}],
        },
    }

    assert _deterministic_actual_group(result, {"items": [{"value": "x"}]}) == "mixed"


def test_deterministic_group_preserves_guardrail_names() -> None:
    assert (
        _deterministic_actual_group(
            {"out_of_domain": True, "query_plan": {"tasks": []}}, {}
        )
        == "out_of_domain"
    )
    assert (
        _deterministic_actual_group(
            {
                "needs_clarification": True,
                "query_plan": {"tasks": [{"mode": "clarify"}]},
            },
            {},
        )
        == "clarification"
    )


def test_production_summary_separates_ttft_paths_and_cache_protocol() -> None:
    rows = [
        {
            "scenario": "cold_rag",
            "expected_path": "regulation_rag",
            "success": True,
            "transport_success": True,
            "payload_success": True,
            "expected_status_match": True,
            "status_code": 200,
            "latency_ms": 1_000.0,
            "ttft_ms": None,
            "used_cache": False,
            "telemetry": {"retrieval_ms": 100},
            "eval_split": "realistic",
        },
        {
            "scenario": "cold_rag",
            "expected_path": "structured",
            "success": True,
            "transport_success": True,
            "payload_success": True,
            "expected_status_match": True,
            "status_code": 200,
            "latency_ms": 300.0,
            "ttft_ms": None,
            "used_cache": False,
            "telemetry": {"routing_ms": 100},
            "eval_split": "realistic",
        },
        {
            "scenario": "deterministic",
            "expected_path": "structured",
            "success": True,
            "transport_success": True,
            "payload_success": True,
            "expected_status_match": True,
            "status_code": 200,
            "latency_ms": 200.0,
            "ttft_ms": None,
            "used_cache": False,
            "telemetry": {"routing_ms": 100},
            "eval_split": "realistic",
        },
        {
            "scenario": "warm_cache",
            "expected_path": "regulation_rag",
            "success": True,
            "transport_success": True,
            "payload_success": True,
            "expected_status_match": True,
            "status_code": 200,
            "latency_ms": 100.0,
            "ttft_ms": None,
            "used_cache": True,
            "telemetry": {"cache_hit": True},
            "eval_split": "realistic",
        },
        {
            "scenario": "streaming",
            "expected_path": "regulation_rag",
            "success": True,
            "transport_success": True,
            "payload_success": True,
            "expected_status_match": True,
            "status_code": 200,
            "latency_ms": 800.0,
            "ttft_ms": 120.0,
            "used_cache": None,
            "telemetry": {},
            "eval_split": "realistic",
        },
    ]

    summary = _summarize_production_rows(rows)

    assert summary["streaming_ttft_ms"]["mean"] == 120.0
    assert summary["streaming_ttft_coverage"] == 1.0
    assert summary["cold_regulation_rag_latency_ms"]["p95"] == 1_000.0
    assert summary["cold_cache_hit_rate"] == 0.0
    assert summary["warm_cache_hit_rate"] == 1.0
    assert summary["cache_protocol_valid"] is True
    assert summary["response_status_accuracy"] == 1.0
    assert summary["by_expected_path"]["structured"]["n"] == 2
    assert evaluate_gates("production", summary)["passed"] is True

    summary["cold_cache_hit_rate"] = 0.5
    assert evaluate_gates("production", summary)["passed"] is False


def test_production_clarify_abstain_accepts_guardrail_statuses() -> None:
    expected_status = _expected_response_status(
        {
            "expected_path": "clarify",
            "expected_answer_behavior": "abstain",
        }
    )

    assert expected_status == "answered_or_guardrail"
    assert _response_status_matches_expected("answered", expected_status)
    assert _response_status_matches_expected("needs_clarification", expected_status)
    assert _response_status_matches_expected("out_of_domain", expected_status)
    assert not _response_status_matches_expected("error", expected_status)


def test_production_eval_records_http_error_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def raise_rate_limit(*_args, **_kwargs):
        raise HTTPError(
            url="http://127.0.0.1:8000/chat",
            code=429,
            msg="Too Many Requests",
            hdrs=None,
            fp=BytesIO(b'{"detail":"Rate limit exceeded"}'),
        )

    monkeypatch.setattr(
        "src.evaluation.suites.urllib_request.urlopen", raise_rate_limit
    )
    report = evaluate_production(
        [
            {
                "id": "rate-limit",
                "scenario": "cold_rag",
                "query": "q",
                "cohort": "K50",
                "expected_path": "regulation_rag",
                "eval_split": "stress",
            }
        ],
        base_url="http://127.0.0.1:8000",
    )

    assert report["cases"][0]["status_code"] == 429
    assert report["summary"]["http_429_rate"] == 1.0


def test_production_eval_rejects_terminal_stream_api_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class StreamResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def __iter__(self):
            payload = (
                'event: metadata\ndata: {"status":"streaming"}\n\n'
                'event: token\ndata: {"text":"fallback"}\n\n'
                'event: metadata\ndata: '
                '{"status":"api_error","error_type":"RuntimeError"}\n\n'
                'event: done\ndata: {"status":"api_error"}\n\n'
            )
            return iter(payload.encode("utf-8").splitlines(keepends=True))

    monkeypatch.setattr(
        "src.evaluation.suites.urllib_request.urlopen",
        lambda *_args, **_kwargs: StreamResponse(),
    )
    report = evaluate_production(
        [
            {
                "id": "stream-api-error",
                "scenario": "streaming",
                "query": "q",
                "cohort": "K50",
                "expected_path": "regulation_rag",
                "eval_split": "stress",
            }
        ],
        base_url="http://127.0.0.1:8000",
    )

    row = report["cases"][0]
    assert row["transport_success"] is True
    assert row["payload_success"] is False
    assert row["success"] is False
    assert row["response_status"] == "api_error"
    assert row["response_error_type"] == "RuntimeError"


def test_human_audit_uses_template_size_and_repeat_flags() -> None:
    audit_rows = [
        {
            "id": f"case-{index}",
            "human_score": 1.0 if index < 24 else None,
            "repeat_for_consistency": index < 5,
            "repeat_score": 1.0 if index < 5 else None,
            "critical_false_pass": False,
        }
        for index in range(25)
    ]
    judge_rows = [{"id": f"case-{index}", "judge": {}} for index in range(25)]

    incomplete = summarize_human_audit(audit_rows, judge_rows)
    audit_rows[-1]["human_score"] = 1.0
    complete = summarize_human_audit(audit_rows, judge_rows)

    assert incomplete["required_n"] == 25
    assert incomplete["completed_n"] == 24
    assert incomplete["complete"] is False
    assert complete["complete"] is True
    assert complete["repeat_required_n"] == 5
    assert complete["repeat_completed_n"] == 5


def test_human_audit_must_match_frozen_template_and_repeat_contract() -> None:
    template = [
        {
            "id": f"case-{index}",
            "repeat_for_consistency": index < 2,
        }
        for index in range(4)
    ]
    audit_rows = [
        {
            **row,
            "human_score": 1.0,
            "repeat_score": 1.0 if row["repeat_for_consistency"] else None,
        }
        for row in template[:3]
    ]
    judge_rows = [{"id": row["id"], "judge": {}} for row in template]

    missing_case = summarize_human_audit(
        audit_rows,
        judge_rows,
        template_rows=template,
    )
    assert missing_case["required_n"] == 4
    assert missing_case["complete"] is False
    assert missing_case["contract_errors"] == [
        "human_audit_missing_template_ids:case-3"
    ]

    audit_rows.append(
        {
            **template[3],
            "human_score": 1.0,
            "repeat_score": None,
        }
    )
    audit_rows[0]["repeat_score"] = None
    missing_repeat = summarize_human_audit(
        audit_rows,
        judge_rows,
        template_rows=template,
    )
    assert missing_repeat["contract_errors"] == []
    assert missing_repeat["repeat_required_n"] == 2
    assert missing_repeat["repeat_completed_n"] == 1
    assert missing_repeat["complete"] is False


def test_compact_packet_keeps_required_fact() -> None:
    case = {
        "id": "a",
        "query": "Học tối đa bao lâu?",
        "cohort": "K50",
        "answerability": "answerable",
        "ground_truth": "Tối đa 8 năm học.",
        "required_facts": ["Tối đa 8 năm học."],
        "forbidden_claims": [],
        "expected_citations": [],
    }
    answer = {
        "answer": "Tối đa 8 năm học.",
        "context_used": ("Nội dung phụ không liên quan. " * 500) + "Tối đa 8 năm học.",
    }
    packet = compact_judge_packet(case, answer, max_input_tokens=200)
    assert "Tối đa 8 năm học." in packet["retrieved_context"]
    assert packet["required_facts_present_in_packet"] == ["Tối đa 8 năm học."]


def test_compact_packet_prefers_normalized_citation_over_execution_json() -> None:
    case = {
        "id": "a",
        "query": "Hạn nộp hồ sơ là khi nào?",
        "cohort": "K51",
        "answerability": "answerable",
        "ground_truth": "Hạn nộp hồ sơ là sau khi học kỳ bắt đầu 04 tuần.",
        "required_facts": ["Hạn nộp hồ sơ là sau khi học kỳ bắt đầu 04 tuần."],
        "forbidden_claims": [],
        "expected_citations": [],
    }
    answer = {
        "answer": "Hạn nộp hồ sơ là sau khi học kỳ bắt đầu 04 tuần.",
        "context_used": '[{"chunk_id":"noise","metadata":"' + ("x" * 8_000) + '"}]',
        "citations": [
            {
                "chunk_id": "article-30",
                "content": "Hạn nộp hồ sơ là sau khi học kỳ bắt đầu 04 tuần.",
            }
        ],
    }

    packet = compact_judge_packet(case, answer, max_input_tokens=200)

    assert "sau khi học kỳ bắt đầu 04 tuần" in packet["retrieved_context"]
    assert "metadata" not in packet["retrieved_context"]
    assert '"chunk_id"' not in packet["retrieved_context"]


def test_compact_packet_uses_full_readable_context_seen_by_composer() -> None:
    case = {
        "id": "general-cohort",
        "query": "Thời gian học tối đa của K51 là bao lâu?",
        "cohort": "general",
        "answerability": "answerable",
        "ground_truth": "K51 học chính quy tối đa 06 năm.",
        "required_facts": ["K51 học chính quy tối đa 06 năm."],
        "forbidden_claims": [],
        "expected_citations": [],
    }
    answer = {
        "answer": "K51 học chính quy tối đa 06 năm.",
        "context_used": (
            "PRIMARY SOURCES\n\n[1]\nCohort: K48-K49\nContent: tối đa 8 năm.\n\n"
            "---\n\n"
            "[11]\nCohort: K51\nContent: K51 học chính quy tối đa 06 năm."
        ),
        # The public list can be shorter than the evidence packet Composer saw.
        "citations": [{"chunk_id": "public-source", "content": "tối đa 8 năm."}],
    }

    packet = compact_judge_packet(case, answer, max_input_tokens=300)

    assert "K51 học chính quy tối đa 06 năm." in packet["retrieved_context"]
    assert "Cohort: K51" in packet["retrieved_context"]
    assert packet["required_facts_present_in_packet"] == [
        "K51 học chính quy tối đa 06 năm."
    ]


def test_compact_packet_reads_current_authorized_evidence_json() -> None:
    case = {
        "id": "authorized-packet",
        "query": "Thời gian học tối đa của K51 là bao lâu?",
        "cohort": "general",
        "answerability": "answerable",
        "ground_truth": "K51 học chính quy tối đa 06 năm.",
        "required_facts": ["K51 học chính quy tối đa 06 năm."],
        "forbidden_claims": [],
        "expected_citations": [],
    }
    context_used = json.dumps(
        {
            "answer_prompt_version": "test",
            "units": [
                {
                    "task_id": "t1",
                    "cohort": "K51",
                    "primary_evidence": [
                        {
                            "source_ref": "S11",
                            "title": "Điều 5",
                            "content": "K51 học chính quy tối đa 06 năm.",
                            "resolved_result": {"maximum_years": 6},
                        }
                    ],
                    "applicable_amendments": [
                        {
                            "amendment_source": "Quyết định sửa đổi",
                            "effective_rule": "Áp dụng cho K51.",
                            "replacement_text": "Thời hạn mới là 06 năm.",
                        }
                    ],
                }
            ],
        },
        ensure_ascii=False,
    )
    answer = {
        "answer": "K51 học chính quy tối đa 06 năm.",
        "context_used": context_used,
        "citations": [{"chunk_id": "public-source", "content": "tối đa 8 năm."}],
    }

    packet = compact_judge_packet(case, answer, max_input_tokens=300)

    assert "K51 học chính quy tối đa 06 năm." in packet["retrieved_context"]
    assert "Task: t1" in packet["retrieved_context"]
    assert 'Resolved result: {"maximum_years": 6}' in packet["retrieved_context"]
    assert "Amendment: Quyết định sửa đổi" in packet["retrieved_context"]
    assert packet["required_facts_present_in_packet"] == [
        "K51 học chính quy tối đa 06 năm."
    ]


def test_compact_packet_prefers_complete_citations_for_single_cohort() -> None:
    case = {
        "id": "single-cohort",
        "query": "Hạn nộp hồ sơ là khi nào?",
        "cohort": "K51",
        "answerability": "answerable",
        "ground_truth": "Hạn nộp hồ sơ là sau khi học kỳ bắt đầu 04 tuần.",
        "required_facts": ["Hạn nộp hồ sơ là sau khi học kỳ bắt đầu 04 tuần."],
        "forbidden_claims": [],
        "expected_citations": [],
    }
    answer = {
        "answer": "Hạn nộp hồ sơ là sau khi học kỳ bắt đầu 04 tuần.",
        "context_used": "PRIMARY SOURCES\n\n[1]\nCohort: K51\nContent: nhiễu.",
        "citations": [
            {
                "chunk_id": "article-30",
                "content": "Hạn nộp hồ sơ là sau khi học kỳ bắt đầu 04 tuần.",
            }
        ],
    }

    packet = compact_judge_packet(case, answer, max_input_tokens=300)

    assert "sau khi học kỳ bắt đầu 04 tuần" in packet["retrieved_context"]
    assert "nhiễu" not in packet["retrieved_context"]


def test_default_judge_packet_keeps_long_answer_and_later_citation_evidence() -> None:
    answer_tail = "Kết luận quan trọng nằm ở cuối câu trả lời."
    later_evidence = "Nguồn thứ sáu xác lập kết luận quan trọng."
    case = {
        "id": "long-answer",
        "query": "Quy định gồm những gì?",
        "cohort": "K50",
        "answerability": "answerable",
        "ground_truth": ("Nội dung nguồn dài. " * 80) + later_evidence,
        "required_facts": [later_evidence],
        "forbidden_claims": [],
        "expected_citations": [],
    }
    answer = {
        "answer": ("Nội dung trả lời có căn cứ. " * 90) + answer_tail,
        "citations": [
            {"chunk_id": f"source-{index}", "content": f"Nguồn {index}."}
            for index in range(5)
        ]
        + [{"chunk_id": "source-6", "content": later_evidence}],
    }

    packet = compact_judge_packet(case, answer)

    assert answer_tail in packet["answer"]
    assert later_evidence in packet["retrieved_context"]
    assert len(packet["citations"]) == 6
    config = JudgeConfig()
    assert (
        estimate_tokens(build_judge_prompt(packet)) + config.max_output_tokens
        <= config.tpm_limit_per_key
    )


def test_judge_parser_rejects_out_of_range_score() -> None:
    payload = json.loads(_valid_judge_payload())
    payload["faithfulness"] = 1.1
    with pytest.raises(ValueError, match="out_of_range"):
        parse_judge_json(json.dumps(payload))


def test_required_fact_hit_allows_paraphrase_but_keeps_numeric_guardrail() -> None:
    case = {
        "answerability": "answerable",
        "required_facts": [
            "Thời gian học tập tối đa của hệ chính quy cấp bằng thứ nhất là 8 năm học."
        ],
        "expected_citations": [],
    }
    good = {
        "status": "answered",
        "answer": "Với hệ chính quy cấp bằng thứ nhất, sinh viên được học tối đa 8 năm.",
        "citations": [],
    }
    bad_number = {
        "status": "answered",
        "answer": "Với hệ chính quy cấp bằng thứ nhất, sinh viên được học tối đa 9 năm.",
        "citations": [],
    }

    assert _answer_checks(case, good)["required_fact_hit"] is True
    assert _answer_checks(case, bad_number)["required_fact_hit"] is False


def test_broad_question_handling_accepts_scoped_cited_answer() -> None:
    case = {
        "answerability": "answerable",
        "expected_answer_behavior": "scoped_summary",
        "required_facts": ["Một chi tiết rất cụ thể không bắt buộc với câu hỏi rộng."],
        "expected_citations": [{"parent_section_id": "p1"}],
    }
    answer = {
        "status": "answered",
        "answer": "Mình tóm tắt theo nguồn chính trong sổ tay.",
        "citations": [{"parent_section_id": "p1"}],
    }

    checks = _answer_checks(case, answer)

    assert checks["required_fact_hit"] is False
    assert checks["question_handling_correctness"] is True


def test_textual_abstention_counts_for_unanswerable_answer() -> None:
    case = {
        "answerability": "unanswerable",
        "expected_answer_behavior": "abstain",
        "required_facts": [],
        "expected_citations": [],
    }
    answer = {
        "status": "answered",
        "answer": "Mình chưa thấy căn cứ trực tiếp trong Sổ tay cho trường hợp này.",
        "citations": [],
    }

    checks = _answer_checks(case, answer)

    assert checks["abstention_correct"] is True
    assert checks["question_handling_correctness"] is True


def test_judge_prompt_is_fair_for_unanswerable_abstention() -> None:
    prompt = build_judge_prompt(
        {
            "case_id": "x",
            "query": "Trường có cấp laptop miễn phí không?",
            "answerability": "unanswerable",
            "expected_answer_behavior": "abstain",
            "answer": "Mình chưa thấy căn cứ trực tiếp trong Sổ tay.",
            "retrieved_context": "Nguồn chỉ nói về hỗ trợ học phí.",
        }
    )

    assert "do not require a citation that proves non-existence" in prompt
    assert "unsupported_claim is false" in prompt


def test_judge_is_pinned_and_fails_over_without_model_switch(tmp_path: Path) -> None:
    config = JudgeConfig(state_path=tmp_path / "judge_state.json", max_retries=2)
    pool = JudgeQuotaPool(["secret-one", "secret-two"], config)
    called: list[tuple[str, str]] = []

    def request_fn(key: str, _prompt: str, actual_config: JudgeConfig):
        called.append((key, actual_config.model_name))
        if len(called) == 1:
            raise RuntimeError("429 rate limit")
        return _valid_judge_payload(), {
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
        }

    result = GroqJudgeClient(config, pool=pool, request_fn=request_fn).judge(
        {"id": "x", "query": "q", "answer": "a", "retrieved_context": "c"}
    )
    assert result["ok"] is True
    assert result["attempts"] == 2
    assert {model for _, model in called} == {PINNED_JUDGE_MODEL}
    state_text = (tmp_path / "judge_state.json").read_text(encoding="utf-8")
    assert "secret-one" not in state_text
    assert "secret-two" not in state_text


def test_judge_rejects_any_other_model() -> None:
    with pytest.raises(ValueError, match="must use exactly"):
        JudgeConfig(model_name="another-model")


def test_all_judge_daily_quota_exhausted_is_explicit(tmp_path: Path) -> None:
    config = JudgeConfig(state_path=tmp_path / "judge_state.json", tpd_limit_per_key=10)
    pool = JudgeQuotaPool(["secret"], config)
    pool._state[key_fingerprint("secret")]["daily_tokens"] = 10
    with pytest.raises(RuntimeError, match="daily_token_quota_exhausted"):
        pool.acquire(1)


def test_judge_request_larger_than_per_key_tpm_is_explicit(tmp_path: Path) -> None:
    config = JudgeConfig(state_path=tmp_path / "judge_state.json", tpm_limit_per_key=10)
    pool = JudgeQuotaPool(["secret"], config)

    with pytest.raises(RuntimeError, match="request_exceeds_per_key_tpm_limit"):
        pool.acquire(11)


def test_gemini_pool_skips_rate_limited_key(tmp_path: Path) -> None:
    pool = GeminiKeyPool(
        ["gemini-one", "gemini-two"],
        model_name="gemini-3.1-flash-lite",
        config=GeminiKeyPoolConfig(
            state_path=str(tmp_path / "gemini_state.json"),
            wait_when_all_keys_limited=False,
        ),
    )
    first_key, first_id, _ = pool.acquire_key()
    pool.record_rate_limit(first_id)
    second_key, _, _ = pool.acquire_key()
    assert first_key != second_key
    state_text = (tmp_path / "gemini_state.json").read_text(encoding="utf-8")
    assert "gemini-one" not in state_text
    assert "gemini-two" not in state_text


def test_gemini_pool_reports_all_keys_temporarily_limited(tmp_path: Path) -> None:
    pool = GeminiKeyPool(
        ["gemini-one"],
        model_name="gemini-3.1-flash-lite",
        config=GeminiKeyPoolConfig(
            rpm_limit_per_key=1,
            state_path=str(tmp_path / "gemini_state.json"),
            wait_when_all_keys_limited=False,
        ),
    )
    pool.acquire_key()
    with pytest.raises(RuntimeError, match="temporarily_limited"):
        pool.acquire_key()


def test_gemini_empty_response_is_not_success() -> None:
    class Pool:
        def acquire_key(self):
            return "secret", "fingerprint", 0

        def record_failure(self, *_args):
            return None

        def record_rate_limit(self, *_args):
            return None

    client = object.__new__(GeminiClient)
    client.available_keys = ["secret"]
    client.model_name = "gemini-3.1-flash-lite"
    client.max_retries = 0
    client.retry_base_delay_seconds = 0
    client.retry_max_delay_seconds = 0
    client.key_pool = Pool()
    client._genai = type(
        "GenAI", (), {"Client": staticmethod(lambda api_key: object())}
    )()
    client._generate_once = lambda _prompt, **_kwargs: ""
    result = client.generate("prompt")
    assert result["ok"] is False
    assert "empty response" in result["error_message"]


def test_retrieval_exception_stays_in_denominator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FailingPipeline:
        def _run_retrieval(self, query: str, cohort: str | None = None):
            raise TimeoutError("Qdrant timeout")

    case = {
        "id": "r1",
        "suite": "retrieval",
        "case_type": "regulation_true_rag",
        "query": "quy định",
        "cohort": "K50",
        "tags": [],
        "topic": "test",
        "query_style": "keyword",
        "expected_content_types": ["regulation_text"],
        "relevance_judgments": [{"parent_section_id": "p1", "grade": 2}],
    }
    report = evaluate_retrieval(
        [case], backend="qdrant", pipeline_factory=FailingPipeline
    )
    assert report["summary"]["n"] == 1
    assert report["summary"]["hit_at_5"] == 0
    assert report["cases"][0]["empty_retrieval"] is True


def test_generation_restores_eval_environment_when_pipeline_init_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STUDENT_RAG_OFFLINE_EVAL", "previous-offline")
    monkeypatch.setenv("STUDENT_RAG_QUALITY_EVAL", "previous-quality")
    monkeypatch.setenv("STUDENT_RAG_EVAL_RETRIEVAL_MODE", "full")
    observed_modes: list[str | None] = []

    def fail_pipeline():
        observed_modes.append(os.environ.get("STUDENT_RAG_EVAL_RETRIEVAL_MODE"))
        raise RuntimeError("pipeline init failed")

    with pytest.raises(RuntimeError, match="pipeline init failed"):
        generate_answers(
            [],
            cache_path=tmp_path / "answers.json",
            resume=False,
            pipeline_factory=fail_pipeline,
        )

    assert os.environ["STUDENT_RAG_OFFLINE_EVAL"] == "previous-offline"
    assert os.environ["STUDENT_RAG_QUALITY_EVAL"] == "previous-quality"
    assert os.environ["STUDENT_RAG_EVAL_RETRIEVAL_MODE"] == "full"
    assert observed_modes == [DEFAULT_RETRIEVAL_MODE]


def test_answer_quality_wait_rejects_degraded_bm25(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        evaluation_suites,
        "get_bm25_runtime_status",
        lambda: {"status": "degraded", "attempts": 3, "error_type": "TimeoutError"},
    )

    with pytest.raises(RuntimeError, match="BM25 entered degraded state"):
        evaluation_suites._wait_for_bm25_ready(timeout_seconds=0)


def test_answer_quality_wait_accepts_ready_bm25(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        evaluation_suites,
        "get_bm25_runtime_status",
        lambda: {"status": "ready", "attempts": 1, "error_type": None},
    )

    evaluation_suites._wait_for_bm25_ready(timeout_seconds=0)


def test_mongo_parent_miss_cannot_count_as_retrieval_hit() -> None:
    class ParentMissPipeline:
        def _run_retrieval(self, query: str, cohort: str | None = None):
            return {
                "intent": "regulation_query",
                "strategy": "hybrid_graph_retrieval",
                "retrieved_items": [
                    {
                        "chunk_id": "orphan-child",
                        "metadata": {
                            "cohort": cohort,
                            "content_type": "regulation_text",
                        },
                    }
                ],
                "citations": [],
            }

    case = {
        "id": "r2",
        "suite": "retrieval",
        "case_type": "regulation_true_rag",
        "query": "quy định",
        "cohort": "K50",
        "tags": [],
        "topic": "test",
        "query_style": "keyword",
        "expected_content_types": ["regulation_text"],
        "relevance_judgments": [{"parent_section_id": "expected-parent", "grade": 2}],
    }
    report = evaluate_retrieval(
        [case], backend="qdrant", pipeline_factory=ParentMissPipeline
    )
    assert report["summary"]["hit_at_5"] == 0
    assert report["cases"][0]["citation_binding"] is False


def test_retrieval_cohort_check_uses_applicable_cohorts() -> None:
    class ApplicablePipeline:
        def _run_retrieval(self, query: str, cohort: str | None = None):
            return {
                "intent": "open_question",
                "strategy": "query_plan_execution",
                "retrieved_items": [
                    {
                        "parent_section_id": "policy-k50",
                        "metadata": {
                            "cohort": "K50",
                            "applicable_cohorts": ["K50", "K51"],
                            "content_type": "regulation_text",
                        },
                    }
                ],
                "citations": [{"parent_section_id": "policy-k50"}],
            }

    case = {
        "id": "r-applicability",
        "suite": "retrieval",
        "case_type": "regulation_true_rag",
        "query": "quy định áp dụng cho K51",
        "cohort": "K51",
        "tags": [],
        "topic": "test",
        "query_style": "natural",
        "expected_content_types": ["regulation_text"],
        "relevance_judgments": [{"parent_section_id": "policy-k50", "grade": 2}],
    }

    report = evaluate_retrieval(
        [case], backend="qdrant", pipeline_factory=ApplicablePipeline
    )

    assert report["cases"][0]["cohort_match"] is True
    assert report["cases"][0]["cohort_leak"] is False


def test_report_bundle_writes_json_csv_and_markdown(tmp_path: Path) -> None:
    paths = write_report_bundle(
        {"evaluation": "V8", "summary": {"n": 1}, "cases": [{"id": "x", "ok": True}]},
        tmp_path / "report.json",
    )
    assert all(Path(path).exists() for path in paths.values())
