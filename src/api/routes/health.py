from __future__ import annotations

from fastapi import APIRouter

from src.api.schemas import HealthResponse


router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="student_handbook_rag",
        version="0.1.0",
    )

