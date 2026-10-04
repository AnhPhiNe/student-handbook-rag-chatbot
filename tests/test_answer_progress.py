"""Progress a streamed answer reports while planning and retrieval run (offline)."""
import contextvars
import threading
import time

import yaml

from src.generation.answer_pipeline import AnswerPipeline
from src.generation.progress import (
    LOOKUP_LABELS,
    describe_plan,
    describe_sources,
    report,
    reporting_to,
)


def test_every_registry_tool_has_a_label_for_students():
    registry = yaml.safe_load(open("configs/structured_lookup_registry.yaml", encoding="utf-8"))
    assert set(registry["tools"]) <= set(LOOKUP_LABELS)


def test_plan_names_what_it_will_look_up_once_each():
    tasks = [{"mode": "structured", "lookup_type": "scoring"},
             {"mode": "rag"},
             {"mode": "structured", "lookup_type": "scoring"}]
    assert describe_plan(tasks, "K51") == (
        "Đang tra bảng quy đổi điểm và các quy định liên quan trong Sổ tay khóa K51…")
    three = [{"mode": "structured", "lookup_type": "program"},
             {"mode": "structured", "lookup_type": "faculty"}, {"mode": "rag"}]
    assert describe_plan(three, None) == (
        "Đang tra danh sách ngành đào tạo, danh bạ khoa và các quy định liên quan trong Sổ tay…")


def test_a_plan_that_only_asks_back_reports_nothing():
    assert describe_plan([{"mode": "clarify"}], "K50") is None
    assert describe_plan([], "K50") is None


def test_sources_message_counts_what_was_found():
    assert describe_sources(5, False) == "Đã tìm thấy 5 nguồn liên quan, đang soạn câu trả lời…"
    assert describe_sources(0, True) == "Đã có kết quả tra cứu, đang soạn câu trả lời…"
    assert describe_sources(0, False) == "Đang soạn câu trả lời…"


def test_report_outside_a_stream_goes_nowhere():
    report("không ai nghe")  # the /chat route and evaluations have no sink


def test_progress_is_yielded_while_preparation_runs_and_the_result_is_returned():
    request = contextvars.ContextVar("request", default=None)
    request.set("trace-1")
    seen = {}

    class Pipeline(AnswerPipeline):
        def __init__(self):
            pass

        def prepare_answer(self, query, **kwargs):
            seen["thread"] = threading.current_thread().name
            seen["request"] = request.get()  # the caller's context reaches the worker
            report("Đang tra bảng quy đổi điểm trong Sổ tay khóa K51…")
            time.sleep(0.2)
            report("bước hai")
            return {"query": query, **kwargs}

    stream = Pipeline()._prepare_reporting_progress("5.2 là điểm gì?", cohort="K51")
    events = []
    while True:
        try:
            events.append(next(stream))
        except StopIteration as done:
            prepared = done.value
            break
    assert events == [
        {"type": "progress", "message": "Đang tra bảng quy đổi điểm trong Sổ tay khóa K51…"},
        {"type": "progress", "message": "bước hai"},
    ]
    assert prepared == {"query": "5.2 là điểm gì?", "cohort": "K51"}
    assert seen["thread"].startswith("prepare-answer") and seen["request"] == "trace-1"


def test_a_failed_preparation_raises_in_the_stream():
    class Pipeline(AnswerPipeline):
        def __init__(self):
            pass

        def prepare_answer(self, query, **kwargs):
            raise RuntimeError("retrieval down")

    stream = Pipeline()._prepare_reporting_progress("q")
    try:
        next(stream)
    except RuntimeError as exc:
        assert str(exc) == "retrieval down"
    else:
        raise AssertionError("the failure must reach the stream")


def test_reporting_context_is_reset_after_use():
    received = []
    with reporting_to(received.append):
        report("một")
    report("hai")
    assert received == ["một"]
