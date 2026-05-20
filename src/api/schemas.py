from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str
    include_debug: bool = False


class ChatResponse(BaseModel):
    answer: str
    status: str
    request_id: str | None = None
    latency_ms: float | None = None
    citations_used: list[dict[str, Any]] = Field(default_factory=list)
    clarification_needed: bool = False
    intent: str | None = None
    strategy: str | None = None
    llm_called: bool = False
    used_cache: bool = False
    error_type: str | None = None
    error_message: str | None = None
    debug: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class ArtifactStatus(BaseModel):
    path: str
    exists: bool
    kind: str


class ArtifactHealthResponse(BaseModel):
    status: str
    required_artifacts: list[ArtifactStatus]
