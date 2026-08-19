"""Typed execution state derived after planner validation.

Planner payloads stay immutable dictionaries at the trust boundary. Runtime-only
values such as retrieval queries live here instead of being injected back into
those dictionaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class RequestExecutionContext:
    request_id: str
    request_index: int
    request_kind: str
    query_span: str
    effective_query: str
    effective_cohort: str | None
    retrieval_query: str
    retrieval_config: Mapping[str, Any] = field(default_factory=dict)

    def debug_dict(self) -> dict[str, Any]:
        """Safe additive response metadata; never used as a planner input."""
        return {
            "request_id": self.request_id,
            "request_index": self.request_index,
            "request_kind": self.request_kind,
            "query_span": self.query_span,
            "effective_cohort": self.effective_cohort,
            "retrieval_query": self.retrieval_query,
        }

