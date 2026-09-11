from __future__ import annotations

from contextlib import nullcontext
from typing import Any
from unittest.mock import patch

from src.api.langsmith_helper import build_trace_metadata
from src.api.routes.chat import chat
from src.api.schemas import ChatRequest
from src.common.cohort import valid_cohorts
from src.generation.answer_pipeline import AnswerPipeline
from src.retrieval.core.query_plan import normalize_query_plan, safe_rag_fallback_plan
from src.retrieval.core.slang_normalizer import SlangNormalizer


def _rag_task(question: str = "Quy định học vụ?") -> dict[str, Any]:
    return {
        "id": "t1",
        "question": question,
        "mode": "rag",
        "intent": "open_question",
        "lookup_type": None,
        "slots": {},
        "slot_spans": {},
        "cohorts": [],
        "clarification_question": None,
    }


def _plan(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "v1",
        "context_mode": "standalone",
        "normalized_query": "Quy định học vụ?",
        "standalone_query": None,
        "referenced_turns": [],
        "out_of_domain": False,
        "tasks": tasks,
    }


class _Cache:
    def __init__(self, value: dict[str, Any] | None = None) -> None:
        self.value = value

    def make_cache_key(self, **kwargs: Any) -> str:
        del kwargs
        return "release-regression"

    def get(self, key: str) -> dict[str, Any] | None:
        del key
        return self.value

    def set(self, key: str, value: dict[str, Any]) -> None:
        del key
        self.value = value


def _pipeline(plan: dict[str, Any]) -> AnswerPipeline:
    pipeline = AnswerPipeline.__new__(AnswerPipeline)
    pipeline.router = type("Planner", (), {"plan": lambda self, *args, **kwargs: plan})()
    pipeline.slang_normalizer = SlangNormalizer()
    pipeline.config = {
        "planning": {"max_citations": 10},
        "citations": {"selection_max_sources": 5, "public_max_sources": 10},
        "guardrails": {"skip_llm_on_low_confidence": False},
    }
    pipeline.model = None
    pipeline.formula_rules = []
    pipeline.student_office_profiles = []
    pipeline.student_service_directory = []
    pipeline.student_faculty_profiles = []
    pipeline.structured_tables_registry = []
    pipeline.program_directory = []
    pipeline.parent_sources_by_id = {}
    pipeline.max_context_chars = 10000
    pipeline.llm_config = {"model_name": "fake"}
    pipeline.request_sleep_seconds = 0
    pipeline._last_llm_call_at = 0
    pipeline.response_cache = _Cache()
    return pipeline


def _retrieval_result(plan: dict[str, Any], *, cohort: str = "K51") -> dict[str, Any]:
    citation = {
        "chunk_id": "p1",
        "source_parent_id": "p1",
        "cohort": cohort,
        "content": "Nguồn hợp lệ.",
        "supports_task_ids": ["t1"],
    }
    return {
        "query_plan": plan,
        "task_results": [
            {
                "task_id": "t1",
                "question": "Quy định học vụ?",
                "mode": "rag",
                "cohorts": [cohort],
                "coverage": "covered",
                "coverage_by_cohort": {cohort: "covered"},
            }
        ],
        "coverage_by_task": {"t1": "covered"},
        "effective_query": "Quy định học vụ?",
        "execution_mode": "rag",
        "selected_cohort": cohort,
        "evidence_citations": [citation],
        "citations": [citation],
        "retrieved_items": [{"chunk_id": "p1", "content": "Nguồn hợp lệ."}],
        "needs_clarification": False,
        "out_of_domain": False,
    }


def test_single_and_general_scope_defaults_remain_explicit() -> None:
    single, _ = normalize_query_plan(
        _plan([_rag_task()]),
        query="K51 quy định học vụ là gì?",
        selected_cohort="K50",
    )
    assert single["tasks"][0]["cohorts"] == ["K51"]

    selected_ui, _ = normalize_query_plan(
        _plan([_rag_task()]),
        query="Quy định học vụ là gì?",
        selected_cohort="K50",
    )
    assert selected_ui["tasks"][0]["cohorts"] == ["K50"]

    general, _ = normalize_query_plan(
        _plan([_rag_task()]),
        query="Quy định học vụ là gì?",
        selected_cohort=None,
    )
    assert general["tasks"][0]["cohorts"] == list(valid_cohorts())


def test_missing_task_cohorts_preserve_explicit_multi_cohort_scope() -> None:
    plan, errors = normalize_query_plan(
        _plan([_rag_task()]),
        query="So sánh K50 và K51 về quy định học vụ.",
        selected_cohort="K48-K49",
    )

    assert errors == []
    assert plan["tasks"][0]["cohorts"] == ["K50", "K51"]


def test_valid_multi_task_plan_keeps_each_task_cohort_assignment() -> None:
    first = {**_rag_task("Quy định đăng ký học phần của K50?"), "id": "t1", "cohorts": ["K50"]}
    second = {**_rag_task("Quy định hoãn thi của K51?"), "id": "t2", "cohorts": ["K51"]}

    plan, errors = normalize_query_plan(
        _plan([first, second]),
        query="So sánh K50 và K51 về đăng ký học phần và hoãn thi.",
        selected_cohort="K48-K49",
    )

    assert errors == []
    assert [task["cohorts"] for task in plan["tasks"]] == [["K50"], ["K51"]]


def test_missing_task_cohorts_use_task_question_before_global_scope() -> None:
    first = {**_rag_task("Quy định đăng ký học phần của K50?"), "id": "t1"}
    second = {**_rag_task("Quy định hoãn thi của K51?"), "id": "t2"}

    plan, errors = normalize_query_plan(
        _plan([first, second]),
        query="So sánh K50 và K51 về đăng ký học phần và hoãn thi.",
        selected_cohort="K48-K49",
    )

    assert errors == []
    assert [task["cohorts"] for task in plan["tasks"]] == [["K50"], ["K51"]]


def test_safe_fallback_preserves_multi_scope_and_general_default() -> None:
    multi = safe_rag_fallback_plan(
        "So sánh K50 và K51 về quy định học vụ.",
        "K50",
        reason="safe_rag",
    )
    assert multi["tasks"][0]["cohorts"] == ["K50", "K51"]

    selected_ui = safe_rag_fallback_plan("Quy định học vụ là gì?", "K50")
    assert selected_ui["tasks"][0]["cohorts"] == ["K50"]

    # A query without explicit/UI scope remains the existing general-query
    # fallback; it must not invent one canonical cohort to mean "all".
    general = safe_rag_fallback_plan("Quy định học vụ là gì?", None)
    assert general["tasks"][0]["cohorts"] == []


def test_output_stream_and_trace_use_resolved_scope_without_collapsing_multi_metadata() -> None:
    plan = _plan([_rag_task()])
    retrieval_result = _retrieval_result(plan, cohort="K51")
    pipeline = _pipeline(plan)

    output = pipeline._build_output(
        query="K51 quy định học vụ là gì?",
        retrieval_result=retrieval_result,
        final_answer="a",
        context_used="",
        selected_citations=retrieval_result["citations"],
        status="answered",
        error_type=None,
        error_message=None,
        llm_called=True,
        used_cache=False,
    )
    metadata = pipeline._build_stream_metadata(
        retrieval_result,
        status="answered",
        effective_query="K51 quy định học vụ là gì?",
        citations_used=retrieval_result["citations"],
        llm_called=True,
    )
    trace = build_trace_metadata(
        output,
        query="K51 quy định học vụ là gì?",
        cohort=None,
    )

    assert output["cohort"] == "K51"
    assert metadata["cohort"] == "K51"
    assert trace["cohort"] == "K51"

    multi_result = _retrieval_result(plan, cohort="K50")
    multi_result["query_plan"]["tasks"][0]["cohorts"] = ["K50", "K51"]
    multi_result["task_results"][0]["cohorts"] = ["K50", "K51"]
    multi_output = pipeline._build_output(
        query="So sánh K50 và K51.",
        retrieval_result=multi_result,
        final_answer="a",
        context_used="",
        selected_citations=multi_result["citations"],
        status="answered",
        error_type=None,
        error_message=None,
        llm_called=True,
        used_cache=False,
    )
    multi_trace = build_trace_metadata(
        multi_output,
        query="So sánh K50 và K51.",
        cohort=None,
    )
    assert multi_trace["cohort"] == "K50"
    assert multi_trace["cohorts"] == ["K50", "K51"]
    assert multi_trace["is_multi_cohort"] is True


def test_sync_route_traces_pipeline_scope_over_request_scope() -> None:
    captured: dict[str, Any] = {}

    class Service:
        def answer(self, query: str, **kwargs: Any) -> dict[str, Any]:
            del query, kwargs
            return {
                "answer": "a",
                "status": "answered",
                "cohort": "K51",
                "citations_used": [],
                "related_references": [],
                "llm_called": False,
                "used_cache": False,
            }

    def capture_trace(source: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        captured["source"] = source
        captured.update(kwargs)
        return {"model": "fake"}

    class Request:
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/chat",
            "headers": [],
            "query_string": b"",
        }

    with (
        patch("src.api.routes.chat.chat_capacity_slot", return_value=nullcontext()),
        patch("src.api.routes.chat.enforce_chat_rate_limit"),
        patch("src.api.routes.chat.should_include_debug", return_value=False),
        patch("src.api.routes.chat.build_trace_metadata", side_effect=capture_trace),
        patch("src.api.routes.chat.submit_trace_to_langsmith"),
    ):
        response = chat(
            ChatRequest(query="K51 quy định học vụ?", cohort="K50"),
            Request(),
            Service(),
        )

    assert response.status == "answered"
    assert captured["cohort"] == "K51"


def test_stream_llm_called_reflects_actual_backend_attempt(monkeypatch) -> None:
    task = _rag_task("Quy định học vụ?")
    task["cohorts"] = ["K51"]
    plan = _plan([task])
    retrieval_result = _retrieval_result(plan)
    pipeline = _pipeline(plan)
    pipeline._run_retrieval = lambda *args, **kwargs: retrieval_result

    def fail_to_initialize() -> Any:
        raise RuntimeError("client init failed")

    pipeline._get_llm_client = fail_to_initialize
    init_events = list(pipeline.answer_stream(task["question"], cohort="K51"))
    init_metadata = [
        event for event in init_events if event["type"] == "metadata"
    ]
    init_done = next(event for event in init_events if event["type"] == "done")
    assert [event["llm_called"] for event in init_metadata] == [False, False]
    assert init_done["status"] == "api_error"

    class AttemptFailingLLM:
        def generate_stream(self, prompt: str):
            del prompt
            raise RuntimeError("generation failed")
            yield "unreachable"

    pipeline.response_cache = _Cache()
    pipeline._get_llm_client = lambda: AttemptFailingLLM()
    attempt_events = list(pipeline.answer_stream(task["question"], cohort="K51"))
    attempt_metadata = [
        event for event in attempt_events if event["type"] == "metadata"
    ]
    attempt_done = next(event for event in attempt_events if event["type"] == "done")
    assert [event["llm_called"] for event in attempt_metadata] == [False, True]
    assert attempt_done["status"] == "api_error"

    cached_pipeline = _pipeline(plan)
    cached_pipeline._run_retrieval = lambda *args, **kwargs: retrieval_result
    cached_pipeline.response_cache = _Cache(
        {"answer": "cached", "status": "answered", "citations": []}
    )
    cached_pipeline._get_llm_client = lambda: (_ for _ in ()).throw(
        AssertionError("cache hit must not initialize the client")
    )
    cached_events = list(cached_pipeline.answer_stream(task["question"], cohort="K51"))
    cached_metadata = [
        event for event in cached_events if event["type"] == "metadata"
    ]
    cached_done = next(event for event in cached_events if event["type"] == "done")
    assert [event["llm_called"] for event in cached_metadata] == [False]
    assert cached_done["used_cache"] is True

    terminal_pipeline = _pipeline(plan)
    terminal_result = _retrieval_result(plan)
    terminal_result.update(
        {
            "needs_clarification": True,
            "clarification_question": "Bạn muốn hỏi nội dung nào?",
        }
    )
    terminal_pipeline._run_retrieval = lambda *args, **kwargs: terminal_result
    terminal_pipeline._get_llm_client = lambda: (_ for _ in ()).throw(
        AssertionError("terminal answer must not initialize the client")
    )
    terminal_events = list(
        terminal_pipeline.answer_stream(task["question"], cohort="K51")
    )
    terminal_metadata = [
        event for event in terminal_events if event["type"] == "metadata"
    ]
    terminal_done = next(event for event in terminal_events if event["type"] == "done")
    assert [event["llm_called"] for event in terminal_metadata] == [False]
    assert terminal_done["used_cache"] is False
