from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from src.evaluation.dataset import validate_bundle
from src.evaluation.judge import (
    PINNED_JUDGE_MODEL,
    GroqJudgeClient,
    JudgeConfig,
    JudgeQuotaPool,
    build_judge_prompt,
    compact_judge_packet,
    key_fingerprint,
    parse_judge_json,
)
from src.evaluation.metrics import retrieval_metrics, wilson_interval
from src.evaluation.reporting import write_report_bundle
from src.evaluation.suites import _answer_checks, evaluate_retrieval, generate_answers
from src.generation.gemini_client import GeminiKeyPool, GeminiKeyPoolConfig
from src.generation.gemini_client import GeminiClient


ROOT = Path(__file__).resolve().parents[1]


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


def test_frozen_v83_bundle_is_valid() -> None:
    result = validate_bundle(
        ROOT / "data" / "eval" / "v8_3_holdout",
        ROOT / "data" / "processed" / "chunks" / "all_docstore_items.json",
    )
    assert result["valid"], result["errors"]
    assert result["counts"] == {
        "deterministic": 120,
        "retrieval": 180,
        "answers": 100,
        "production": 60,
    }


def test_frozen_v83_holdout_is_unseen_from_v8() -> None:
    holdout_dir = ROOT / "data" / "eval" / "v8_3_holdout"
    result = validate_bundle(
        holdout_dir,
        ROOT / "data" / "processed" / "chunks" / "all_docstore_items.json",
    )
    main_cases = json.loads(
        (ROOT / "data" / "eval" / "v8" / "deterministic_tool_cases.json").read_text(
            encoding="utf-8"
        )
    )
    holdout_cases = json.loads(
        (holdout_dir / "deterministic_tool_cases.json").read_text(encoding="utf-8")
    )

    assert result["valid"], result["errors"]
    assert {case["query"].casefold() for case in main_cases}.isdisjoint(
        {case["query"].casefold() for case in holdout_cases}
    )


def test_validator_rejects_query_reused_from_legacy_eval(tmp_path: Path) -> None:
    eval_root = tmp_path / "eval"
    bundle_dir = eval_root / "v8_3_holdout"
    shutil.copytree(ROOT / "data" / "eval" / "v8_3_holdout", bundle_dir)
    deterministic = json.loads(
        (bundle_dir / "deterministic_tool_cases.json").read_text(encoding="utf-8")
    )
    (eval_root / "legacy_cases.json").write_text(
        json.dumps([{"query": deterministic[0]["query"]}], ensure_ascii=False),
        encoding="utf-8",
    )

    result = validate_bundle(
        bundle_dir,
        ROOT / "data" / "processed" / "chunks" / "all_docstore_items.json",
    )

    assert result["valid"] is False
    assert any("legacy query overlap" in error for error in result["errors"])


def test_retrieval_metrics_are_graded_and_rank_sensitive() -> None:
    scores = retrieval_metrics([0, 2, 1, 0, 0])
    assert scores["hit_at_1"] == 0
    assert scores["hit_at_3"] == 1
    assert scores["reciprocal_rank"] == pytest.approx(0.5)
    assert 0 < scores["ndcg_at_5"] < 1


def test_wilson_interval_bounds_probability() -> None:
    interval = wilson_interval(98, 100)
    assert 0 <= interval["low"] <= interval["high"] <= 1


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
    client._generate_once = lambda _prompt: ""
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

    def fail_pipeline():
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


def test_report_bundle_writes_json_csv_and_markdown(tmp_path: Path) -> None:
    paths = write_report_bundle(
        {"evaluation": "V8", "summary": {"n": 1}, "cases": [{"id": "x", "ok": True}]},
        tmp_path / "report.json",
    )
    assert all(Path(path).exists() for path in paths.values())
