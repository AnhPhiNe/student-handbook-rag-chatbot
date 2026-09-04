"""Stateful SSE event construction for the streaming chat endpoint."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from src.generation.structured_result_presenter import public_regulation_citations

_DEBUG_METADATA_KEYS = {
    "query_plan",
    "task_results",
    "coverage_by_task",
    "planner_fallback",
    "supports_task_ids",
}
_DEBUG_CITATION_KEYS = {"task_id", "supports_task_ids"}


def serialize_sse_event(event_type: str, data: dict[str, Any]) -> str:
    """Serialize one event and JSON payload using the SSE wire format."""

    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event_type}\ndata: {payload}\n\n"


def _public_citations(
    citations: list[Any],
    *,
    include_debug: bool,
) -> list[Any]:
    """Normalize citations and remove task-level fields from public streams."""

    normalized = public_regulation_citations(citations)
    if include_debug:
        return normalized
    return [
        {
            key: value
            for key, value in citation.items()
            if key not in _DEBUG_CITATION_KEYS
        }
        if isinstance(citation, dict)
        else citation
        for citation in normalized
    ]


@dataclass
class StreamEventBuilder:
    """Build SSE packets while tracking state needed by the terminal event."""

    request_id: str
    include_debug: bool = False
    started_at: float = field(default_factory=time.perf_counter)
    final_status: str = "unknown"
    final_metadata: dict[str, Any] = field(default_factory=dict)
    trace_source_metadata: dict[str, Any] = field(default_factory=dict)
    full_text: str = ""
    first_token_at: float | None = None
    tracker: Any = None

    @property
    def latency_ms(self) -> float:
        """Return elapsed stream latency in milliseconds."""

        return round((time.perf_counter() - self.started_at) * 1000, 2)

    @property
    def ttft_ms(self) -> float:
        """Return time to first token, or current latency when no token arrived."""

        if self.first_token_at is None:
            return self.latency_ms
        return round((self.first_token_at - self.started_at) * 1000, 2)

    @property
    def trace_metadata(self) -> dict[str, Any]:
        """Return internal metadata for tracing without public redaction."""

        return self.trace_source_metadata or self.final_metadata

    def queued(self, position: int) -> str:
        """Build a queue-position event."""

        return serialize_sse_event("queued", {"position": position})

    def metadata(self, chunk: dict[str, Any]) -> str:
        """Record internal metadata and build its public SSE representation."""

        self.trace_source_metadata = dict(chunk)
        payload = dict(chunk)
        payload["request_id"] = self.request_id
        payload["run_id"] = self.request_id
        payload["citations_used"] = _public_citations(
            payload.get("citations_used") or [],
            include_debug=self.include_debug,
        )
        if not self.include_debug:
            for debug_key in _DEBUG_METADATA_KEYS:
                payload.pop(debug_key, None)
        self.final_metadata = dict(payload)
        self.final_status = str(payload.get("status") or self.final_status)
        return serialize_sse_event("metadata", payload)

    def token(self, chunk: dict[str, Any]) -> str:
        """Record answer text and build a token event."""

        if self.first_token_at is None:
            self.first_token_at = time.perf_counter()
        text = str(chunk.get("text", ""))
        self.full_text += text
        return serialize_sse_event("token", {"text": text})

    def progress(self, chunk: dict[str, Any]) -> str:
        """Build a progress event."""

        return serialize_sse_event(
            "progress",
            {"message": chunk.get("message", "")},
        )

    def prepare_done(self, chunk: dict[str, Any]) -> None:
        """Merge terminal pipeline state before tracing and final SSE emission."""

        self.final_status = str(chunk.get("status") or self.final_status)
        self.final_metadata["status"] = self.final_status
        self.final_metadata["used_cache"] = bool(
            chunk.get("used_cache", self.final_metadata.get("used_cache", False))
        )
        if chunk.get("error_type"):
            self.final_metadata["error_type"] = chunk["error_type"]

        raw_citations = (
            chunk.get("citations_used")
            if "citations_used" in chunk
            else self.final_metadata.get("citations_used", [])
        )
        self.final_metadata["citations_used"] = _public_citations(
            raw_citations or [],
            include_debug=self.include_debug,
        )
        self.tracker = chunk.get("tracker")

        if self.trace_source_metadata:
            self.trace_source_metadata.update(
                {
                    "status": self.final_status,
                    "used_cache": self.final_metadata["used_cache"],
                    "error_type": self.final_metadata.get("error_type"),
                    "citations_used": raw_citations or [],
                }
            )

    def done(self, *, latency_ms: float | None = None) -> str:
        """Build the final event from the prepared terminal state."""

        return serialize_sse_event(
            "done",
            {
                "request_id": self.request_id,
                "latency_ms": self.latency_ms if latency_ms is None else latency_ms,
                "status": self.final_status,
                "error_type": self.final_metadata.get("error_type"),
                "used_cache": self.final_metadata.get("used_cache", False),
                "citations_used": self.final_metadata.get("citations_used", []),
            },
        )

    def failure(self, *, error_type: str, error_message: str) -> tuple[str, str]:
        """Build the terminal error and done events for a failed stream."""

        status = "api_error"
        return (
            serialize_sse_event(
                "error",
                {
                    "request_id": self.request_id,
                    "status": status,
                    "error_type": error_type,
                    "error_message": error_message,
                },
            ),
            serialize_sse_event(
                "done",
                {
                    "request_id": self.request_id,
                    "status": status,
                    "error_type": error_type,
                },
            ),
        )
