from __future__ import annotations

import json

from src.api.routes import health


def test_build_manifest_identity_matches_both_runtime_collections(
    tmp_path,
    monkeypatch,
) -> None:
    manifest_path = tmp_path / "build_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "build_id": "build-test",
                "storage_targets": {
                    "qdrant_collection": "qdrant-v30",
                    "mongo_parent_collection": "parents-v30",
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(health, "BUILD_MANIFEST_PATH", manifest_path)
    monkeypatch.delenv("STUDENT_RAG_HYBRID_COLLECTION", raising=False)
    monkeypatch.setenv("QDRANT_COLLECTION_NAME", "qdrant-v30")
    monkeypatch.setenv("MONGODB_PARENT_COLLECTION", "parents-v30")

    assert health._build_manifest_matches_environment() is True
    monkeypatch.setenv("MONGODB_PARENT_COLLECTION", "parents-v29")
    assert health._build_manifest_matches_environment() is False
