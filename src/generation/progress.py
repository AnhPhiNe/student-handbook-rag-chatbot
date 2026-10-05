"""Progress a streamed answer reports while it is prepared, shown to the student.

Planning, lookups and retrieval run before the composer writes its first word
(5 to 40 s on 2026-10-04). The stream reports each step as it completes: what
the plan will look up, then how many sources were found. Reporting goes through
a context variable, so the executor needs no reference to the stream, and calls
made outside a stream (the /chat route, evaluations) report to nobody.
"""
from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_sink: ContextVar[Callable[[str], None] | None] = ContextVar("answer_progress_sink", default=None)

# What each lookup reads, in the student's terms (configs/structured_lookup_registry.yaml).
LOOKUP_LABELS = {
    "scoring": "bảng quy đổi điểm",
    "foreign_language": "bảng chuẩn ngoại ngữ",
    "study_duration": "bảng thời gian học",
    "scholarship_classification": "bảng xếp loại học bổng",
    "formula": "công thức tính điểm",
    "student_service": "danh bạ dịch vụ sinh viên",
    "office": "danh bạ phòng ban",
    "faculty": "danh bạ khoa",
    "program": "danh sách ngành đào tạo",
}
RAG_LABEL = "các quy định liên quan"


@contextmanager
def reporting_to(sink: Callable[[str], None]) -> Iterator[None]:
    """Send progress reported in this context to `sink`."""
    token = _sink.set(sink)
    try:
        yield
    finally:
        _sink.reset(token)


def report(message: str | None) -> None:
    sink = _sink.get()
    if sink is not None and message:
        sink(message)


def describe_plan(tasks: list[dict[str, Any]], cohort: str | None) -> str | None:
    """What the plan will look up; None when it only asks the student back."""
    labels: list[str] = []
    for task in tasks:
        mode = task.get("mode")
        if mode == "structured":
            label = LOOKUP_LABELS.get(str(task.get("lookup_type") or ""), "dữ liệu tra cứu")
        elif mode == "rag":
            label = RAG_LABEL
        else:
            continue
        if label not in labels:
            labels.append(label)
    if not labels:
        return None
    joined = labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " và " + labels[-1]
    where = f" trong Sổ tay khóa {cohort}" if cohort else " trong Sổ tay"
    return f"Đang tra {joined}{where}…"


def describe_sources(citation_count: int, has_structured_result: bool) -> str:
    """What was found, said just before the composer starts writing."""
    if citation_count:
        return f"Đã tìm thấy {citation_count} nguồn liên quan, đang soạn câu trả lời…"
    if has_structured_result:
        return "Đã có kết quả tra cứu, đang soạn câu trả lời…"
    return "Đang soạn câu trả lời…"
