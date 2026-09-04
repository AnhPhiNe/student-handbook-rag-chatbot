from __future__ import annotations

import json

from src.api.sse_events import StreamEventBuilder, serialize_sse_event


def _payload(packet: str) -> dict:
    """Extract the JSON payload from one serialized SSE packet."""

    data_line = next(line for line in packet.splitlines() if line.startswith("data: "))
    return json.loads(data_line.removeprefix("data: "))


def test_serialize_sse_event_preserves_unicode() -> None:
    packet = serialize_sse_event("progress", {"message": "Đang xử lý"})

    assert packet == 'event: progress\ndata: {"message": "Đang xử lý"}\n\n'


def test_public_metadata_is_redacted_without_mutating_pipeline_chunk() -> None:
    chunk = {
        "type": "metadata",
        "status": "streaming",
        "query_plan": {"tasks": [{"id": "t1"}]},
        "task_results": [{"task_id": "t1"}],
        "citations_used": [
            {"source": "rule.pdf", "task_id": "t1", "supports_task_ids": ["t1"]}
        ],
    }
    events = StreamEventBuilder("request-1")

    payload = _payload(events.metadata(chunk))

    assert "query_plan" not in payload
    assert "task_results" not in payload
    assert payload["citations_used"] == [{"source": "rule.pdf"}]
    assert payload["request_id"] == "request-1"
    assert events.trace_metadata["query_plan"] == {"tasks": [{"id": "t1"}]}
    assert chunk["citations_used"][0]["task_id"] == "t1"


def test_done_prefers_terminal_citations_and_updates_trace_state() -> None:
    events = StreamEventBuilder("request-2")
    tracker = object()
    events.metadata(
        {
            "type": "metadata",
            "status": "streaming",
            "citations_used": [{"source": "initial.pdf", "task_id": "t1"}],
        }
    )
    events.token({"type": "token", "text": "Answer"})

    events.prepare_done(
        {
            "type": "done",
            "status": "answered",
            "used_cache": True,
            "citations_used": [{"source": "final.pdf", "task_id": "t2"}],
            "tracker": tracker,
        }
    )
    payload = _payload(events.done())

    assert payload["status"] == "answered"
    assert payload["used_cache"] is True
    assert payload["citations_used"] == [{"source": "final.pdf"}]
    assert events.trace_metadata["citations_used"] == [
        {"source": "final.pdf", "task_id": "t2"}
    ]
    assert events.full_text == "Answer"
    assert events.tracker is tracker


def test_debug_metadata_keeps_task_fields() -> None:
    events = StreamEventBuilder("request-3", include_debug=True)

    payload = _payload(
        events.metadata(
            {
                "type": "metadata",
                "query_plan": {"tasks": []},
                "citations_used": [{"source": "rule.pdf", "task_id": "t1"}],
            }
        )
    )

    assert payload["query_plan"] == {"tasks": []}
    assert payload["citations_used"][0]["task_id"] == "t1"


def test_failure_builds_terminal_error_contract() -> None:
    events = StreamEventBuilder("request-4")

    error_packet, done_packet = events.failure(
        error_type="RuntimeError",
        error_message="Internal chatbot service error",
    )

    assert _payload(error_packet) == {
        "request_id": "request-4",
        "status": "api_error",
        "error_type": "RuntimeError",
        "error_message": "Internal chatbot service error",
    }
    assert _payload(done_packet) == {
        "request_id": "request-4",
        "status": "api_error",
        "error_type": "RuntimeError",
    }
