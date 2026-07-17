from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends

from src.api.deps import verify_admin_api_key
from src.api.schemas import ArtifactHealthResponse, ArtifactStatus, HealthResponse


router = APIRouter(tags=["health"])


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
        service="student_handbook_rag",
        version="0.1.0",
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
            path="data/processed/tables/structured_tables_registry.json",
            exists=Path("data/processed/tables/structured_tables_registry.json").is_file(),
            kind="processed_json",
        ),
        ArtifactStatus(
            path="data/processed/tables/foreign_language_equivalency_table.json",
            exists=Path("data/processed/tables/foreign_language_equivalency_table.json").is_file(),
            kind="processed_json",
        ),
        ArtifactStatus(
            path="data/processed/directories/student_service_directory.json",
            exists=Path("data/processed/directories/student_service_directory.json").is_file(),
            kind="processed_json",
        ),
        ArtifactStatus(
            path="data/processed/directories/student_office_profiles.json",
            exists=Path("data/processed/directories/student_office_profiles.json").is_file(),
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
            path="data/processed/chunks/all_docstore_items.json",
            exists=Path("data/processed/chunks/all_docstore_items.json").is_file(),
            kind="processed_json",
        ),
        ArtifactStatus(
            path="data/processed/chunks/v7_child_parent_chunks.json",
            exists=Path("data/processed/chunks/v7_child_parent_chunks.json").is_file(),
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
