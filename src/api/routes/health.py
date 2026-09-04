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


def _artifact(path: str, exists: bool, kind: str) -> ArtifactStatus:
    return ArtifactStatus(path=path, exists=exists, kind=kind)


def _build_manifest_matches_environment() -> bool:
    try:
        contract = load_retrieval_build_contract(BUILD_MANIFEST_PATH)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    qdrant_collection = os.environ.get(
        "STUDENT_RAG_HYBRID_COLLECTION"
    ) or os.environ.get("QDRANT_COLLECTION_NAME")
    mongo_collection = os.environ.get("MONGODB_PARENT_COLLECTION")
    return bool(
        contract.get("build_id")
        and qdrant_collection
        and mongo_collection
        and contract.get("qdrant_collection") == qdrant_collection
        and contract.get("mongo_parent_collection") == mongo_collection
    )


def _required_artifacts() -> list[ArtifactStatus]:
    retrieval_config_path = Path(
        os.environ.get("STUDENT_RAG_RETRIEVAL_CONFIG")
        or DEFAULT_RETRIEVAL_CONFIG_PATH
    )
    required = [
        _artifact(
            "configs/ai_router.yaml",
            Path("configs/ai_router.yaml").is_file(),
            "config",
        ),
        _artifact(
            "configs/answer_generation.yaml",
            Path("configs/answer_generation.yaml").is_file(),
            "config",
        ),
        _artifact(
            retrieval_config_path.as_posix(),
            retrieval_config_path.is_file(),
            "config",
        ),
        _artifact(
            "configs/hcmue_slang_dictionary.yaml",
            Path("configs/hcmue_slang_dictionary.yaml").is_file(),
            "config",
        ),
        _artifact(
            "configs/structured_lookup_registry.yaml",
            Path("configs/structured_lookup_registry.yaml").is_file(),
            "config",
        ),
        _artifact(
            "configs/office_aliases.yaml",
            Path("configs/office_aliases.yaml").is_file(),
            "config",
        ),
        _artifact(
            "data/processed/tables/scoring_tables.json",
            Path("data/processed/tables/scoring_tables.json").is_file(),
            "processed_json",
        ),
        _artifact(
            "data/processed/tables/formula_rules.json",
            Path("data/processed/tables/formula_rules.json").is_file(),
            "processed_json",
        ),
        _artifact(
            "data/processed/tables/structured_tables_registry.json",
            Path("data/processed/tables/structured_tables_registry.json").is_file(),
            "processed_json",
        ),
        _artifact(
            "data/processed/tables/foreign_language_equivalency_table.json",
            Path(
                "data/processed/tables/foreign_language_equivalency_table.json"
            ).is_file(),
            "processed_json",
        ),
        _artifact(
            "data/processed/directories/student_service_directory.json",
            Path("data/processed/directories/student_service_directory.json").is_file(),
            "processed_json",
        ),
        _artifact(
            "data/processed/directories/student_office_profiles.json",
            Path("data/processed/directories/student_office_profiles.json").is_file(),
            "processed_json",
        ),
        _artifact(
            "data/processed/directories/student_faculty_profiles.json",
            Path("data/processed/directories/student_faculty_profiles.json").is_file(),
            "processed_json",
        ),
        _artifact(
            "data/processed/directories/program_directory.json",
            Path("data/processed/directories/program_directory.json").is_file(),
            "processed_json",
        ),
        _artifact(
            "data/processed/amendments/amendments.json",
            Path("data/processed/amendments/amendments.json").is_file(),
            "processed_json",
        ),
        _artifact(
            "data/processed/chunks/all_docstore_items.json",
            Path("data/processed/chunks/all_docstore_items.json").is_file(),
            "processed_json",
        ),
        _artifact(
            "data/processed/chunks/child_parent_chunks.json",
            Path("data/processed/chunks/child_parent_chunks.json").is_file(),
            "processed_json",
        ),
        _artifact(
            "data/processed/metadata/build_manifest.json",
            BUILD_MANIFEST_PATH.is_file(),
            "processed_json",
        ),
        _artifact(
            "build_manifest:storage_targets",
            _build_manifest_matches_environment(),
            "build_identity",
        ),
        _artifact(
            "data/processed/graphs/document_edges.json",
            Path("data/processed/graphs/document_edges.json").is_file(),
            "processed_json",
        ),
    ]

    required.extend(
        [
            _artifact("QDRANT_URL", bool(os.environ.get("QDRANT_URL")), "env"),
            _artifact("QDRANT_API_KEY", bool(os.environ.get("QDRANT_API_KEY")), "env"),
            _artifact(
                "QDRANT_COLLECTION_NAME",
                bool(
                    os.environ.get("STUDENT_RAG_HYBRID_COLLECTION")
                    or os.environ.get("QDRANT_COLLECTION_NAME")
                ),
                "env",
            ),
        ]
    )

    required.extend(
        [
            _artifact("MONGODB_URL", bool(os.environ.get("MONGODB_URL")), "env"),
            _artifact(
                "MONGODB_PARENT_COLLECTION",
                bool(os.environ.get("MONGODB_PARENT_COLLECTION")),
                "env",
            ),
            _artifact("GROQ_API_KEYS", bool(os.environ.get("GROQ_API_KEYS")), "env"),
            _artifact(
                "GEMINI_API_KEYS", bool(os.environ.get("GEMINI_API_KEYS")), "env"
            ),
        ]
    )
    return required


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
