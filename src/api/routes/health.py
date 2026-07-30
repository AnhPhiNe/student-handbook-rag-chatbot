from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends

from src.api.deps import verify_admin_api_key
from src.api.schemas import ArtifactHealthResponse, ArtifactStatus, HealthResponse, ReadinessResponse


router = APIRouter(tags=["health"])
SERVICE_NAME = "student_handbook_rag"
SERVICE_VERSION = "0.1.0"


def _artifact(path: str, exists: bool, kind: str) -> ArtifactStatus:
    return ArtifactStatus(path=path, exists=exists, kind=kind)


def _uses_qdrant_provider(provider: str) -> bool:
    return provider.strip().lower() in {"qdrant", "qdrant_cloud"}


def _required_artifacts() -> list[ArtifactStatus]:
    required = [
        _artifact(
            "configs/answer_generation.yaml",
            Path("configs/answer_generation.yaml").is_file(),
            "config",
        ),
        _artifact(
            "configs/hcmue_slang_dictionary.yaml",
            Path("configs/hcmue_slang_dictionary.yaml").is_file(),
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
            Path("data/processed/tables/foreign_language_equivalency_table.json").is_file(),
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
            "data/processed/entities/entity_registry.json",
            Path("data/processed/entities/entity_registry.json").is_file(),
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
            "data/processed/graphs/document_edges.json",
            Path("data/processed/graphs/document_edges.json").is_file(),
            "processed_json",
        ),
    ]

    vectordb_provider = os.environ.get("VECTORDB_PROVIDER", "qdrant").strip().lower()
    if _uses_qdrant_provider(vectordb_provider):
        required.extend(
            [
                _artifact("QDRANT_URL", bool(os.environ.get("QDRANT_URL")), "env"),
                _artifact("QDRANT_API_KEY", bool(os.environ.get("QDRANT_API_KEY")), "env"),
                _artifact(
                    "QDRANT_COLLECTION_NAME",
                    bool(os.environ.get("QDRANT_COLLECTION_NAME")),
                    "env",
                ),
            ]
        )
    else:
        required.append(
            _artifact(
                "data/vectorstore/chroma",
                Path("data/vectorstore/chroma").is_dir(),
                "vectorstore",
            )
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
            _artifact("GEMINI_API_KEYS", bool(os.environ.get("GEMINI_API_KEYS")), "env"),
        ]
    )
    return required


def _artifact_health_response() -> ArtifactHealthResponse:
    required = _required_artifacts()
    status = "ok" if all(item.exists for item in required) else "missing_artifacts"
    return ArtifactHealthResponse(status=status, required_artifacts=required)


@router.api_route("/health", methods=["GET", "HEAD"], response_model=HealthResponse)
def health() -> HealthResponse:
    """
    Kiểm tra trạng thái hoạt động của dịch vụ.

    Hàm này cung cấp một điểm cuối (endpoint) để kiểm tra xem dịch vụ có đang chạy
    và phản hồi bình thường hay không. Nó trả về thông tin cơ bản về trạng thái
    của dịch vụ.

    Returns:
        HealthResponse: Một đối tượng chứa thông tin về trạng thái của dịch vụ,
                        bao gồm:
                        - `status`: Trạng thái chung của dịch vụ (ví dụ: "ok").
                        - `service`: Tên của dịch vụ (ví dụ: "student_handbook_rag").
                        - `version`: Phiên bản hiện tại của dịch vụ (ví dụ: "0.1.0").
    """
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
    missing_count = sum(1 for item in artifact_status.required_artifacts if not item.exists)
    ready = artifact_status.status == "ok"
    return ReadinessResponse(
        status="ok" if ready else "degraded",
        service=SERVICE_NAME,
        version=SERVICE_VERSION,
        ready=ready,
        missing_count=missing_count,
    )


@router.get(
    "/health/artifacts",
    response_model=ArtifactHealthResponse,
    dependencies=[Depends(verify_admin_api_key)],
)
def artifact_health() -> ArtifactHealthResponse:
    """
    Kiểm tra trạng thái của các tài nguyên (artifacts) cần thiết cho dịch vụ.

    Hàm này kiểm tra sự tồn tại của các file cấu hình, dữ liệu đã xử lý và
    kho vector (vectorstore) mà dịch vụ cần để hoạt động. Nó cũng kiểm tra
    các biến môi trường cần thiết nếu dịch vụ sử dụng kho vector đám mây.
    Chỉ những người dùng có quyền quản trị (admin) mới có thể truy cập điểm cuối này.

    Returns:
        ArtifactHealthResponse: Một đối tượng chứa thông tin về trạng thái của
                                các tài nguyên, bao gồm:
                                - `status`: Trạng thái chung của các tài nguyên
                                            ("ok" nếu tất cả đều tồn tại,
                                            "missing_artifacts" nếu có cái bị thiếu).
                                - `required_artifacts`: Một danh sách các đối tượng
                                                        `ArtifactStatus`, mỗi đối tượng
                                                        mô tả một tài nguyên cụ thể:
                                                        - `path`: Đường dẫn hoặc tên
                                                                  của tài nguyên.
                                                        - `exists`: `True` nếu tài nguyên
                                                                    tồn tại, `False` nếu
                                                                    không.
                                                        - `kind`: Loại của tài nguyên
                                                                  (ví dụ: "config",
                                                                  "processed_json",
                                                                  "vectorstore", "env").
    """
    return _artifact_health_response()
