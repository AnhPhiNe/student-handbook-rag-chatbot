from __future__ import annotations

import json
import os
from argparse import Namespace
from io import BytesIO
from pathlib import Path

import pytest

import scripts.evaluate_system as runner
import src.evaluation.suites as suites
from src.evaluation.metrics import retrieval_metrics


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
