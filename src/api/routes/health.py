from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from src.api.schemas import ArtifactHealthResponse, ArtifactStatus, HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="student_handbook_rag",
        version="0.1.0",
    )


@router.get("/health/artifacts", response_model=ArtifactHealthResponse)
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
        ArtifactStatus(
            path="data/vectorstore/chroma",
            exists=Path("data/vectorstore/chroma").is_dir(),
            kind="vectorstore",
        ),
    ]
    status = "ok" if all(item.exists for item in required) else "missing_artifacts"
    return ArtifactHealthResponse(status=status, required_artifacts=required)
