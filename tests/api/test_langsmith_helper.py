from __future__ import annotations

import threading
from concurrent.futures import Future
from unittest.mock import patch

from src.api import langsmith_helper
from src.api.langsmith_helper import (
    build_trace_metadata,
    get_langsmith_client,
    push_trace_to_langsmith,
)
from src.generation.answer_pipeline import PIPELINE_VERSION
from src.generation.prompt_builder import ANSWER_PROMPT_VERSION
from src.retrieval.core.ai_router import ROUTER_PROMPT_VERSION
from src.retrieval.core.query_plan import (
    QUERY_PLAN_NORMALIZER_VERSION,
    QUERY_PLAN_SCHEMA_VERSION,
)


def _query_plan_result() -> dict:
    return {
        "status": "partial",
        "effective_query": "So sánh K50 và K51 rồi giải thích thủ tục",
        "model_used": "gpt-6-luna",
        "llm_called": True,
        "used_cache": False,
        "retrieved_chunks_count": 9,
        "query_plan": {
            "schema_version": "v1",
            "context_mode": "follow_up",
            "tasks": [
                {
                    "id": "t1",
                    "question": "So sánh thời gian K50 và K51",
                    "mode": "structured",
                    "lookup_type": "study_duration",
                    "intent": "direct_value",
                    "cohorts": ["K50", "K51"],
                    "clarification_question": None,
                },
                {
                    "id": "t2",
                    "question": "Thủ tục còn thiếu là gì?",
                    "mode": "rag",
                    "lookup_type": None,
                    "intent": "open_question",
                    "cohorts": ["K51"],
                    "clarification_question": None,
                },
            ],
        },
        "task_results": [
            {
                "task_id": "t1",
                "coverage": "covered",
                "coverage_by_cohort": {"K50": "covered", "K51": "covered"},
                "evidence": [{"large": "payload"}, {"large": "payload"}],
                "citation_count": 2,
            },
            {
                "task_id": "t2",
                "coverage": "uncovered",
                "coverage_by_cohort": {"K51": "uncovered"},
                "evidence": [],
                "citation_count": 0,
            },
        ],
        "coverage_by_task": {"t1": "covered", "t2": "uncovered"},
        "citations_used": [
            {
                "chunk_id": "K50_Dieu1",
                "parent_section_id": "K50_Dieu1",
                "title": "Điều 1",
                "cohort": "K50",
                "supports_task_ids": ["t1"],
                "content": "full source text must not be traced",
                "parent_content": "another full source copy",
                "dense_score": 0.91,
            }
        ],
        "related_references": [
            {
                "chunk_id": "K50_Dieu2",
                "title": "Điều 2",
                "cohort": "K50",
                "content": "related full text must not be traced",
            }
        ],
        "structured_results": [
            {
                "id": "study_duration:K50:0",
                "lookup_type": "study_duration",
                "title": "Thời gian đào tạo",
                "cohort": "K50",
                "rows": [{"mode": "regular"}, {"mode": "part-time"}],
                "provenance": {
                    "source_type": "structured_dataset",
                    "document_id": "handbook_k50",
                    "source_pages": [20],
                },
            }
        ],
    }


def test_build_trace_metadata_matches_query_plan_runtime_without_raw_payloads() -> None:
    with patch.dict(
        "os.environ",
        {
            "QDRANT_COLLECTION_NAME": "student_handbook_semantic_v31",
            "MONGODB_PARENT_COLLECTION": "parent_docs_v31",
        },
    ):
        metadata = build_trace_metadata(
            _query_plan_result(),
            query="Câu hỏi gốc",
            cohort="K51",
            chat_history=[{"role": "user", "content": "private history"}],
            latency_ms=1250,
            ttft_ms=410,
        )

    assert metadata["pipeline_version"] == PIPELINE_VERSION
    assert metadata["answer_prompt_version"] == ANSWER_PROMPT_VERSION
    assert metadata["router_prompt_version"] == ROUTER_PROMPT_VERSION
    assert metadata["query_plan_schema_version"] == QUERY_PLAN_SCHEMA_VERSION
    assert metadata["query_plan_normalizer_version"] == QUERY_PLAN_NORMALIZER_VERSION
    assert metadata["context_mode"] == "follow_up"
    assert metadata["task_count"] == 2
    assert metadata["task_modes"] == ["structured", "rag"]
    assert metadata["lookup_types"] == ["study_duration"]
    assert metadata["cohorts"] == ["K50", "K51"]
    assert metadata["is_multi_cohort"] is True
    assert metadata["covered_task_count"] == 1
    assert metadata["uncovered_task_count"] == 1
    assert metadata["task_summaries"][0]["evidence_count"] == 2
    assert "evidence" not in metadata["task_summaries"][0]
    assert metadata["citations_used"][0]["chunk_id"] == "K50_Dieu1"
    assert "content" not in metadata["citations_used"][0]
    assert "parent_content" not in metadata["citations_used"][0]
    assert "dense_score" not in metadata["citations_used"][0]
    assert "content" not in metadata["related_references"][0]
    assert metadata["structured_result_summaries"][0]["row_count"] == 2
    assert "rows" not in metadata["structured_result_summaries"][0]
    assert metadata["chat_history_turns"] == 1
    assert metadata["has_chat_history"] is True
    # The history is kept as the planner saw it, so a follow-up can be replayed.
    assert metadata["visible_history"] == [{"index": 0, "role": "user", "content": "private history"}]
    assert "chat_history" not in metadata
    assert "raw_query" not in metadata
    assert [task["question"] for task in metadata["query_plan"]["tasks"]] == [
        "So sánh thời gian K50 và K51", "Thủ tục còn thiếu là gì?"]


def test_visible_history_is_the_last_four_turns_cut_to_300_characters() -> None:
    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"{i}" + "x" * 400} for i in range(6)]
    visible = build_trace_metadata({}, query="q", chat_history=history)["visible_history"]
    assert [turn["content"][0] for turn in visible] == ["2", "3", "4", "5"]
    assert all(len(turn["content"]) == 300 for turn in visible)


class _FakeLangSmithClient:
    def __init__(self) -> None:
        self.runs: list[dict] = []

    def create_run(self, **kwargs) -> None:
        self.runs.append(kwargs)


class _ControlledExecutor:
    def __init__(self) -> None:
        self.futures: list[Future] = []

    def submit(self, *args, **kwargs) -> Future:
        del args, kwargs
        future = Future()
        self.futures.append(future)
        return future


class _RejectingExecutor:
    def submit(self, *args, **kwargs) -> Future:
        del args, kwargs
        raise RuntimeError("executor unavailable")


def test_explicit_langsmith_switch_disables_client_creation() -> None:
    with (
        patch.dict(
            "os.environ",
            {
                "LANGSMITH_TRACING": "false",
                "LANGSMITH_API_KEY": "secret-key",
            },
            clear=True,
        ),
        patch("src.api.langsmith_helper.Client") as client_class,
    ):
        assert get_langsmith_client() is None

    client_class.assert_not_called()


def test_background_submission_is_bounded_and_releases_capacity() -> None:
    executor = _ControlledExecutor()
    slots = threading.BoundedSemaphore(1)

    with (
        patch.object(langsmith_helper, "_langsmith_executor", executor),
        patch.object(langsmith_helper, "_langsmith_slots", slots),
        patch.object(langsmith_helper, "_tracing_enabled", return_value=True),
    ):
        assert langsmith_helper._try_submit_langsmith(lambda: None) is True
        assert langsmith_helper._try_submit_langsmith(lambda: None) is False

        executor.futures[0].set_result(None)

        assert langsmith_helper._try_submit_langsmith(lambda: None) is True
        executor.futures[1].set_result(None)


def test_background_submit_failure_does_not_escape_request_path() -> None:
    slots = threading.BoundedSemaphore(1)

    with (
        patch.object(langsmith_helper, "_langsmith_executor", _RejectingExecutor()),
        patch.object(langsmith_helper, "_langsmith_slots", slots),
        patch.object(langsmith_helper, "_tracing_enabled", return_value=True),
    ):
        assert langsmith_helper._try_submit_langsmith(lambda: None) is False

    assert slots.acquire(blocking=False) is True
    slots.release()


def test_push_trace_uses_task_tags_and_compact_root_outputs() -> None:
    client = _FakeLangSmithClient()
    metadata = build_trace_metadata(
        _query_plan_result(),
        query="Câu hỏi gốc",
        cohort="K51",
    )
    original = dict(metadata)

    with patch(
        "src.api.langsmith_helper.get_langsmith_client",
        return_value=client,
    ):
        push_trace_to_langsmith(
            "trace-123",
            input_text="Câu hỏi gốc",
            output_text="Câu trả lời",
            metadata=metadata,
            tags=["stream"],
        )

    assert metadata == original
    assert len(client.runs) == 1
    root = client.runs[0]
    assert "multi_task:true" in root["tags"]
    assert "multi_cohort:true" in root["tags"]
    assert "task_mode:structured" in root["tags"]
    assert "task_mode:rag" in root["tags"]
    assert "coverage:covered" in root["tags"]
    assert "coverage:uncovered" in root["tags"]
    assert "comparison:true" not in root["tags"]
    assert root["outputs"]["task_count"] == 2
    assert root["outputs"]["citations"][0]["chunk_id"] == "K50_Dieu1"
    assert "content" not in root["outputs"]["citations"][0]
    assert root["outputs"]["structured_results"][0]["row_count"] == 2


def test_llm_runs_name_the_provider_of_each_model() -> None:
    def provider(model: str, metadata: dict | None = None):
        return langsmith_helper._llm_run_extra(model, metadata or {})["metadata"].get("ls_provider")

    assert provider("gpt-6-luna") == "openai"
    assert provider("deepseek-flash") == "deepseek"
    # The provider the client reported wins; an unknown model gets none, not a guess.
    assert provider("some-model", {"provider": "deepseek"}) == "deepseek"
    assert provider("some-model") is None


def test_llm_runs_carry_tokens_where_langsmith_reads_them() -> None:
    from src.common.usage_tracker import UsageTracker

    tracker = UsageTracker()
    tracker.record_call(
        "AI Router", model="gpt-6-luna",
        usage={"input": 9200, "output": 400, "total": 9600, "cache_read": 8000, "reasoning": 300},
        start_time="2026-09-29T10:00:00+00:00", end_time="2026-09-29T10:00:05+00:00",
        metadata={"provider": "openai", "key_fingerprint": "31844edc170f"},
    )
    tracker.record_call(
        "LLM Generation", model="deepseek-flash", usage={"input": 5000, "output": 600, "total": 5600},
        start_time="2026-09-29T10:00:06+00:00", end_time="2026-09-29T10:00:09+00:00",
        metadata={"provider": "deepseek", "prompt": "full composer prompt"},
    )
    tracker.counters["identifier_corrected:email"] += 1
    client = _FakeLangSmithClient()
    with patch("src.api.langsmith_helper.get_langsmith_client", return_value=client):
        push_trace_to_langsmith("trace-1", input_text="q", output_text="a",
                                metadata=build_trace_metadata({}, query="q"), tracker=tracker)

    root, router, composer = client.runs
    assert "usage" not in root["extra"]  # LangSmith sums the children
    assert root["extra"]["metadata"]["counters"] == {"identifier_corrected:email": 1}
    router_meta = router["extra"]["metadata"]
    assert router_meta["usage_metadata"] == {
        "input_tokens": 9200, "output_tokens": 400, "total_tokens": 9600,
        "input_token_details": {"cache_read": 8000}, "output_token_details": {"reasoning": 300},
    }
    assert router_meta["ls_provider"] == "openai"
    assert router_meta["key_fingerprint"] == "31844edc170f"
    # A prompt, when kept, is the run's input, not a second copy in the metadata.
    assert composer["inputs"]["prompts"] == ["full composer prompt"]
    assert "prompt" not in composer["extra"]["metadata"]


def test_task_summaries_show_fact_locks_and_directory_decisions() -> None:
    result = _query_plan_result()
    result["task_results"][0]["evidence"] = [
        {"resolved_result": {"label": "Tốt"}},
        {"selection": [{"status": "match", "method": "llm_selector_thinking", "reply": "{}"}]},
    ]
    summary = build_trace_metadata(result, query="q")["task_summaries"][0]
    assert summary["fact_locked"] is True
    assert summary["directory_selection"] == [{"status": "match", "method": "llm_selector_thinking"}]


def test_trace_says_why_a_task_is_not_what_the_planner_proposed() -> None:
    """Without these a trace shows a clarification with no reason, which is how
    the 2026-10-05 "khoa tinesg PHap" failure resisted diagnosis."""
    result = _query_plan_result()
    task = result["query_plan"]["tasks"][0]
    task["validation_errors"] = ["t1:slot_span_mismatch:faculty"]
    task["normalization_warnings"] = ["reading_default_applied:requested_field"]

    meta = build_trace_metadata(result, query="văn phòng khoa tinesg PHap o dau")

    assert meta["plan_validation_errors"] == ["t1:slot_span_mismatch:faculty"]
    assert meta["plan_normalization_warnings"] == ["reading_default_applied:requested_field"]
    traced = meta["query_plan"]["tasks"][0]
    assert traced["validation_errors"] == ["t1:slot_span_mismatch:faculty"]
    assert traced["normalization_warnings"] == ["reading_default_applied:requested_field"]
