from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Depends

from src.api.deps import verify_admin_api_key
from src.api.dependency_health import get_dependency_runtime_statuses
from src.api.schemas import (
    ArtifactHealthResponse,
    ArtifactStatus,
    HealthResponse,
    ReadinessResponse,
    RetrievalComponentStatus,
)
from src.common.runtime_artifacts import RUNTIME_FILES
from src.retrieval.core.retrieval_mode import resolve_retrieval_mode
from src.retrieval.core.runtime_health import get_bm25_runtime_status
from src.retrieval.runtime_config import (
    DEFAULT_RETRIEVAL_CONFIG_PATH,
    load_retrieval_build_contract,
)


router = APIRouter(tags=["health"])
SERVICE_NAME = "student_handbook_rag"
SERVICE_VERSION = "0.1.0"
BUILD_MANIFEST_PATH = Path("data/processed/metadata/build_manifest.json")


REQUIRED_ENV_VARS = (
    "QDRANT_URL",
    "QDRANT_API_KEY",
    "QDRANT_COLLECTION_NAME",
    "MONGODB_URL",
    "MONGODB_PARENT_COLLECTION",
    "GROQ_API_KEYS",
    "GEMINI_API_KEYS",
)


def _env_value(name: str) -> str | None:
    """Read an env var; the Qdrant collection may also come from the hybrid override."""

    if name == "QDRANT_COLLECTION_NAME":
        return os.environ.get("STUDENT_RAG_HYBRID_COLLECTION") or os.environ.get(name)
    return os.environ.get(name)


def _build_manifest_matches_environment() -> bool:
    """Check that the build manifest targets the configured runtime stores."""

    try:
        contract = load_retrieval_build_contract(BUILD_MANIFEST_PATH)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    qdrant_collection = _env_value("QDRANT_COLLECTION_NAME")
    mongo_collection = _env_value("MONGODB_PARENT_COLLECTION")
    return bool(
        contract.get("build_id")
        and qdrant_collection
        and mongo_collection
        and contract.get("qdrant_collection") == qdrant_collection
        and contract.get("mongo_parent_collection") == mongo_collection
    )


def _required_artifacts() -> list[ArtifactStatus]:
    """Resolve required files, store identity, and environment configuration."""

    retrieval_config = Path(
        os.environ.get("STUDENT_RAG_RETRIEVAL_CONFIG") or DEFAULT_RETRIEVAL_CONFIG_PATH
    )
    artifacts = [
        ArtifactStatus(
            path=retrieval_config.as_posix(),
            exists=retrieval_config.is_file(),
            kind="config",
        )
    ]
    artifacts += [
        ArtifactStatus(
            path=path,
            exists=Path(path).is_file(),
            kind="config" if path.startswith("configs/") else "processed_json",
        )
        for path in RUNTIME_FILES
    ]
    artifacts.append(
        ArtifactStatus(
            path="build_manifest:storage_targets",
            exists=_build_manifest_matches_environment(),
            kind="build_identity",
        )
    )
    artifacts += [
        ArtifactStatus(path=name, exists=bool(_env_value(name)), kind="env")
        for name in REQUIRED_ENV_VARS
    ]
    return artifacts


def _artifact_health_response() -> ArtifactHealthResponse:
    required = _required_artifacts()
    status = "ok" if all(item.exists for item in required) else "missing_artifacts"
    return ArtifactHealthResponse(status=status, required_artifacts=required)


@router.api_route("/health", methods=["GET", "HEAD"], response_model=HealthResponse)
def health() -> HealthResponse:
    """Return a lightweight liveness response without probing dependencies."""
    return HealthResponse(
        status="ok",
        service=SERVICE_NAME,
        version=SERVICE_VERSION,
    )


@router.get("/health/readiness", response_model=ReadinessResponse)
def readiness() -> ReadinessResponse:
    """
    Public readiness check for the frontend status badge.

    This endpoint does not expose secret values. It only reports whether the
    current container has the required runtime files and environment variables.
    """
    artifact_status = _artifact_health_response()
    missing_count = sum(
        1 for item in artifact_status.required_artifacts if not item.exists
    )
    dependencies = get_dependency_runtime_statuses()
    qdrant_status = dependencies["qdrant"]
    mongodb_status = dependencies["mongodb"]
    try:
        retrieval_mode = resolve_retrieval_mode()
        retrieval_mode_valid = True
    except ValueError:
        retrieval_mode = "invalid"
        retrieval_mode_valid = False
    stores_ready = all(
        dependency.get("status") == "ready"
        for dependency in (qdrant_status, mongodb_status)
    )
    ready = artifact_status.status == "ok" and stores_ready and retrieval_mode_valid
    bm25_status = RetrievalComponentStatus(**get_bm25_runtime_status())
    return ReadinessResponse(
        status="ok" if ready and bm25_status.status != "degraded" else "degraded",
        service=SERVICE_NAME,
        version=SERVICE_VERSION,
        ready=ready,
        missing_count=missing_count,
        bm25=bm25_status,
        qdrant=qdrant_status,
        mongodb=mongodb_status,
        retrieval_mode=retrieval_mode,
    )


@router.get(
    "/health/artifacts",
    response_model=ArtifactHealthResponse,
    dependencies=[Depends(verify_admin_api_key)],
)
def artifact_health() -> ArtifactHealthResponse:
    """Return admin-only availability for required files and environment keys."""
    return _artifact_health_response()
