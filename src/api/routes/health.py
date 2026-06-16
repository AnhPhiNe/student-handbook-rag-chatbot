from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends

from src.api.deps import verify_admin_api_key
from src.api.schemas import ArtifactHealthResponse, ArtifactStatus, HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="student_handbook_rag",
        version="0.1.0",
    )


@router.get(
    "/health/artifacts",
    response_model=ArtifactHealthResponse,
    dependencies=[Depends(verify_admin_api_key)],
)
def artifact_health() -> ArtifactHealthResponse:
    required = [
        ArtifactStatus(
            path="configs/answer_generation.yaml",
            exists=Path("configs/answer_generation.yaml").is_file(),
            kind="config",
        ),
        ArtifactStatus(
            path="data/processed/tables/scoring_tables.json",
            exists=Path("data/processed/tables/scoring_tables.json").is_file(),
            kind="processed_json",
        ),
        ArtifactStatus(
            path="data/processed/tables/formula_rules.json",
            exists=Path("data/processed/tables/formula_rules.json").is_file(),
            kind="processed_json",
        ),
        ArtifactStatus(
            path="data/processed/entities/entity_registry.json",
            exists=Path("data/processed/entities/entity_registry.json").is_file(),
            kind="processed_json",
        ),
        ArtifactStatus(
            path="data/processed/entities/query_expansion_rules.json",
            exists=Path("data/processed/entities/query_expansion_rules.json").is_file(),
            kind="processed_json",
        ),
    ]

    vectordb_provider = os.environ.get("VECTORDB_PROVIDER", "chroma").strip().lower()
    if vectordb_provider == "qdrant_cloud":
        # Khi deploy tren Hugging Face bang Qdrant Cloud, vectorstore nam tren cloud
        # nen health check chi can dam bao secret ket noi da duoc cau hinh.
        required.extend(
            [
                ArtifactStatus(
                    path="QDRANT_URL",
                    exists=bool(os.environ.get("QDRANT_URL")),
                    kind="env",
                ),
                ArtifactStatus(
                    path="QDRANT_API_KEY",
                    exists=bool(os.environ.get("QDRANT_API_KEY")),
                    kind="env",
                ),
            ]
        )
    else:
        required.append(
            ArtifactStatus(
                path="data/vectorstore/chroma",
                exists=Path("data/vectorstore/chroma").is_dir(),
                kind="vectorstore",
            )
        )

    status = "ok" if all(item.exists for item in required) else "missing_artifacts"
    return ArtifactHealthResponse(status=status, required_artifacts=required)
