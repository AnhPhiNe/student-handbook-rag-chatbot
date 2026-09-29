"""Offline regressions for the audited request-to-answer boundaries."""

import importlib
import json
from unittest.mock import Mock

import pytest

from src.api.chat_controls import ChatCapacityLimiter, QueueTicket
from src.api.schemas import ChatRequest
from src.generation.answer_formatter import format_final_response, sources_section_start
from src.generation.answer_pipeline import AnswerPipeline
from src.generation.plan_executor import PlanExecutor
from src.generation.response_cache import ResponseCache


@pytest.mark.parametrize("queued", [True, False])
def test_closing_route_stream_releases_queue_or_active_slot(monkeypatch, queued):
    route = importlib.import_module("src.api.routes.chat_stream")
    limiter = ChatCapacityLimiter(max_concurrent=1, max_queue_size=10)
    if queued:
        assert limiter.enter_queue().try_acquire(0)
    monkeypatch.setattr(route, "enforce_chat_rate_limit", lambda request: None)
    monkeypatch.setattr(route, "chat_capacity_settings", lambda: (1, 10, 15))
    monkeypatch.setattr(route, "_chat_capacity_limiter", lambda settings: limiter)
    # Capture the real route generator; no ASGI server or elapsed wait needed.
    monkeypatch.setattr(route, "StreamingResponse", lambda body, **kwargs: body)
    monkeypatch.setattr(
        QueueTicket, "try_acquire",
        lambda ticket, timeout: ticket.limiter.try_acquire(ticket.ticket_id, 0),
    )
    service = Mock()
    service.answer_stream.return_value = iter([{"type": "progress", "message": "work"}])
    stream = route.chat_stream(ChatRequest(query="Câu hỏi hợp lệ"), None, service)
    try:
        assert next(stream).startswith("event: queued" if queued else "event: progress")
    finally:
        stream.close()
    assert not limiter._queue
    assert limiter._active_count == int(queued)
    if queued:
        service.answer_stream.assert_not_called()
        limiter.release()
    following = limiter.enter_queue()
    try:
        assert following.try_acquire(0)
    finally:
        following.leave_queue()
        limiter.release()


def _pipeline(chunks):
    task = {"id": "t1", "mode": "rag", "question": "Quy định?", "cohorts": ["K51"]}
    citation = {
        "chunk_id": "p1", "cohort": "K51", "content": "Nội dung quy định.",
        "supports_task_ids": ["t1"],
    }
    result = {
        "query_plan": {"tasks": [task]},
        "task_results": [{"task_id": "t1", "coverage": "covered"}],
        "coverage_by_task": {"t1": "covered"},
        "citations": [citation], "evidence_citations": [citation],
        "retrieved_items": [{"chunk_id": "p1", "content": citation["content"]}],
    }
    pipeline = object.__new__(AnswerPipeline)
    pipeline.config = {"guardrails": {"skip_llm_on_low_confidence": True}}
    pipeline.llm_config = {"model_name": "offline-fake"}
    pipeline.model_name = "offline-fake"
    pipeline.max_context_chars = 10000
    pipeline.response_cache = ResponseCache()
    pipeline._run_retrieval = lambda *args, **kwargs: result
    pipeline._throttle_llm_call = lambda: None
    llm = Mock()
    llm.generate.return_value = {"ok": True, "text": "".join(chunks), "usage": {}}
    llm.generate_stream.side_effect = lambda prompt: iter(chunks)
    pipeline._get_llm_client = lambda: llm
    return pipeline, llm


def _answer(pipeline, transport):
    if transport == "sync":
        result = pipeline.answer("Quy định?", cohort="K51")
        return result["status"], result["answer"]
    events = list(pipeline.answer_stream("Quy định?", cohort="K51"))
    return events[-1]["status"], "".join(e["text"] for e in events if e["type"] == "token")


@pytest.mark.parametrize("transport", ["sync", "stream"])
@pytest.mark.parametrize("chunks", [[], [" \n\t"], ["```markdown\n", "Nguồn:\n- S1"]])
def test_empty_final_answer_falls_back_without_caching(transport, chunks):
    pipeline, _ = _pipeline(chunks)
    status, answer = _answer(pipeline, transport)
    assert status == "api_error"
    assert answer.strip()
    assert not pipeline.response_cache._entries


@pytest.mark.parametrize("transport", ["sync", "stream"])
def test_old_empty_cached_answer_is_a_miss(transport):
    pipeline, llm = _pipeline(["Câu trả lời hợp lệ."])
    prepared = pipeline.prepare_answer(
        "Quy định?", cohort="K51", chat_history=None, tracker=Mock(), router_started_at="",
    )
    pipeline.response_cache.set(prepared.cache_key, {"answer": " \n", "status": "answered"})
    assert _answer(pipeline, transport) == ("answered", "Câu trả lời hợp lệ.")
    assert llm.generate.called if transport == "sync" else llm.generate_stream.called


@pytest.mark.parametrize("text", [
    "Kinh phí được cấp từ nguồn: ngân sách và tài trợ. Điều kiện áp dụng: theo quy định.",
    "| Nguồn: ngân sách | Mức hỗ trợ |\n|---|---|\n| A | 100 |",
    '> Trích dẫn: "Nguồn: ngân sách nhà trường".\nĐây là nội dung cần giữ.',
    "Nguồn kinh phí: ngân sách.\nĐiều kiện áp dụng vẫn cần giữ.",
])
def test_source_words_in_answer_body_are_not_a_footer(text):
    assert format_final_response(text) == text
    assert sources_section_start(text) is None


@pytest.mark.parametrize("footer", ["Nguồn:\n- Điều 1", "### Nguồn:\n- Điều 1", "**Nguồn:** Điều 1", "*(Nguồn: Điều 1)"])
def test_actual_source_footer_is_removed(footer):
    answer = "Nội dung hợp lệ.\n\n" + footer
    assert format_final_response(answer) == "Nội dung hợp lệ."


@pytest.mark.parametrize("transport", ["sync", "stream"])
def test_source_word_survives_generation_and_cache(transport):
    text = "Kinh phí được cấp từ nguồn: ngân sách. Điều kiện áp dụng: theo quy định."
    pipeline, _ = _pipeline([text[:28], text[28:]])
    assert _answer(pipeline, transport) == ("answered", text)
    assert _answer(pipeline, transport) == ("answered", text)


def test_stream_rolling_buffer_does_not_promote_inline_source_to_heading():
    # After the first chunk is flushed, the 256-character tail starts with
    # "nguồn:" even though that word is still in the middle of the same line.
    first = "X" * 300 + " " + "nguồn: " + "a" * 249
    chunks = [first, " Kết luận."]
    pipeline, _ = _pipeline(chunks)
    assert _answer(pipeline, "stream") == ("answered", "".join(chunks))


@pytest.mark.parametrize("other_coverage", ["needs_clarification", "uncovered"])
@pytest.mark.parametrize("transport", ["sync", "stream"])
def test_one_multicohort_task_preserves_answerable_unit(other_coverage, transport):
    pipeline, llm = _pipeline(["Trả lời phần đủ bằng chứng."])
    task = {"id": "t1", "mode": "structured", "question": "So sánh", "cohorts": ["K50", "K51"]}
    executor = object.__new__(PlanExecutor)
    executor.public_source_limit = 10

    def lookup(**kwargs):
        if kwargs["cohort"] == "K51":
            return {
                "coverage": other_coverage,
                "clarification_question": "Cần thông tin thêm cho K51?" if other_coverage == "needs_clarification" else None,
            }
        return {
            "coverage": "covered",
            "citations": [{"chunk_id": "p50", "cohort": "K50", "supports_task_ids": ["t1"], "content": "Bằng chứng K50."}],
        }

    executor._execute_planned_structured_task = lookup
    execution = executor.execute_task(task=task, task_index=0, default_cohort=None)
    plan = {"tasks": [task]}
    result = executor.aggregate_results(
        base_result={"query_plan": plan}, plan=plan, task_executions=[execution],
    )
    assert result["needs_llm_answer"] is True
    assert result["needs_clarification"] is False
    # The summary must not falsely claim that all cohorts are covered.
    assert result["coverage_by_task"]["t1"] != "covered"
    pipeline._run_retrieval = lambda *args, **kwargs: result
    prepared = pipeline.prepare_answer(
        "So sánh", cohort=None, chat_history=None, tracker=Mock(), router_started_at="",
    )
    assert prepared.terminal_status is None
    units = {u["cohort"]: u for u in json.loads(prepared.context_used)["units"]}
    assert units["K50"]["coverage"] == "covered"
    assert units["K50"]["allowed_source_refs"]
    assert units["K51"]["coverage"] == other_coverage
    assert not units["K51"]["allowed_source_refs"]
    if other_coverage == "needs_clarification":
        assert units["K51"]["clarification_question"] == "Cần thông tin thêm cho K51?"
    assert _answer(pipeline, transport) == ("answered", "Trả lời phần đủ bằng chứng.")
    generation = llm.generate if transport == "sync" else llm.generate_stream
    generation.assert_called_once()
