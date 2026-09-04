from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


MAX_CHAT_HISTORY_MESSAGES = 8
MAX_CHAT_HISTORY_CONTENT_CHARS = 16_000
MAX_FEEDBACK_COMMENT_CHARS = 2_000


class ChatRequest(BaseModel):
    """Validate the user query and bounded conversation context."""

    query: str = ""
    include_debug: bool = False
    chat_history: list[dict[str, Any]] = Field(
        default_factory=list,
        max_length=MAX_CHAT_HISTORY_MESSAGES,
    )
    cohort: str | None = Field(default=None, max_length=32)

    @field_validator("chat_history")
    @classmethod
    def validate_chat_history(
        cls,
        history: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        """Keep only the bounded role/content contract consumed by the Planner."""

        normalized: list[dict[str, str]] = []
        for message in history:
            role = message.get("role")
            content = message.get("content")
            if role not in {"user", "assistant"}:
                raise ValueError("chat history role must be user or assistant")
            if not isinstance(content, str):
                raise ValueError("chat history content must be a string")
            if len(content) > MAX_CHAT_HISTORY_CONTENT_CHARS:
                raise ValueError(
                    "chat history content must be at most "
                    f"{MAX_CHAT_HISTORY_CONTENT_CHARS} characters"
                )
            normalized.append({"role": role, "content": content})
        return normalized


class ChatResponse(BaseModel):
    """Expose the answer, evidence, status, and optional debug metadata."""

    answer: str
    status: str
    effective_query: str | None = None
    query_handling: dict[str, Any] | None = None
    request_id: str | None = None
    run_id: str | None = None
    latency_ms: float | None = None
    intent: str | None = None
    strategy: str | None = None
    citations: list[dict[str, Any]] | None = None
    citations_used: list[dict[str, Any]] | None = None
    structured_results: list[dict[str, Any]] = Field(default_factory=list)
    related_references: list[dict[str, Any]] | None = None
    llm_called: bool = False
    used_cache: bool = False
    clarification_needed: bool = False
    error_type: str | None = None
    error_message: str | None = None
    debug: dict[str, Any] | None = None


class ChatFeedbackRequest(BaseModel):
    """Validate bounded like/dislike feedback for one traced answer run."""

    run_id: str = Field(min_length=1, max_length=128)
    score: float = Field(ge=0.0, le=1.0)
    comment: str | None = Field(default=None, max_length=MAX_FEEDBACK_COMMENT_CHARS)


class HealthResponse(BaseModel):
    """Describe the basic liveness state of the API service."""

    status: str
    service: str
    version: str


class RetrievalComponentStatus(BaseModel):
    """Describe initialization state for an in-process retrieval component."""

    status: Literal["initializing", "ready", "degraded"]
    attempts: int = 0
    error_type: str | None = None


class DependencyComponentStatus(BaseModel):
    """Describe runtime connectivity for an external dependency."""

    status: Literal["ready", "degraded", "not_configured"]
    error_type: str | None = None
    latency_ms: float | None = None


class ReadinessResponse(BaseModel):
    """Summarize whether all resources required to serve RAG traffic are ready."""

    status: str
    service: str
    version: str
    ready: bool
    missing_count: int = 0
    bm25: RetrievalComponentStatus
    qdrant: DependencyComponentStatus
    mongodb: DependencyComponentStatus
    retrieval_mode: str


class ArtifactStatus(BaseModel):
    """Describe the availability of one required runtime artifact."""

    path: str
    exists: bool
    kind: str


class ArtifactHealthResponse(BaseModel):
    """Aggregate availability for artifacts required by the deployed service."""

    status: str
    required_artifacts: list[ArtifactStatus]
