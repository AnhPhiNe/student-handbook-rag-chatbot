from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.api.dependency_health import (
    probe_mongodb,
    probe_qdrant,
    reset_dependency_probe_cache,
)


def test_qdrant_probe_checks_configured_collection_and_uses_cache(monkeypatch) -> None:
    reset_dependency_probe_cache()
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example")
    monkeypatch.setenv("QDRANT_API_KEY", "secret")
    monkeypatch.setenv("STUDENT_RAG_HYBRID_COLLECTION", "student_handbook_semantic_v32")
    client = MagicMock()
    client.get_collection.return_value = SimpleNamespace(
        config=SimpleNamespace(
            params=SimpleNamespace(vectors=SimpleNamespace(size=1024))
        )
    )
    client.scroll.return_value = (
        [SimpleNamespace(payload={"build_id": "build-test"})],
        None,
    )

    with (
        patch("qdrant_client.QdrantClient", return_value=client),
        patch(
            "src.api.dependency_health.load_retrieval_build_contract",
            return_value={"build_id": "build-test", "embedding_dimension": 1024},
        ),
    ):
        first = probe_qdrant()
        second = probe_qdrant()

    assert first["status"] == "ready"
    assert second["status"] == "ready"
    client.get_collection.assert_called_once_with("student_handbook_semantic_v32")
    client.scroll.assert_called_once_with(
        collection_name="student_handbook_semantic_v32",
        limit=1,
        with_payload=True,
        with_vectors=False,
    )


def test_mongodb_probe_checks_configured_parent_collection(monkeypatch) -> None:
    reset_dependency_probe_cache()
    monkeypatch.setenv("MONGODB_URL", "mongodb://example")
    monkeypatch.setenv("MONGODB_PARENT_COLLECTION", "parent_docs_v32")
    collection = MagicMock()
    database = MagicMock()
    database.__getitem__.return_value = collection
    client = MagicMock()
    client.__getitem__.return_value = database
    collection.find_one.return_value = {
        "_id": "parent-1",
        "build_id": "build-test",
    }

    with (
        patch("pymongo.MongoClient", return_value=client),
        patch(
            "src.api.dependency_health.load_retrieval_build_contract",
            return_value={"build_id": "build-test"},
        ),
    ):
        result = probe_mongodb()

    assert result["status"] == "ready"
    client.__getitem__.assert_called_once_with("chatbotHCMUE")
    database.__getitem__.assert_called_once_with("parent_docs_v32")
    collection.find_one.assert_called_once_with(
        {},
        {"_id": 1, "build_id": 1, "metadata.build_id": 1},
    )


def test_mongodb_probe_rejects_empty_parent_collection(monkeypatch) -> None:
    reset_dependency_probe_cache()
    monkeypatch.setenv("MONGODB_URL", "mongodb://example")
    monkeypatch.setenv("MONGODB_PARENT_COLLECTION", "parent_docs_v32")
    collection = MagicMock()
    collection.find_one.return_value = None
    client = MagicMock()
    client.__getitem__.return_value.__getitem__.return_value = collection

    with (
        patch("pymongo.MongoClient", return_value=client),
        patch(
            "src.api.dependency_health.load_retrieval_build_contract",
            return_value={"build_id": "build-test"},
        ),
    ):
        result = probe_mongodb()

    assert result["status"] == "degraded"
    assert result["error_type"] == "RuntimeError"


def test_qdrant_probe_rejects_wrong_build_id(monkeypatch) -> None:
    reset_dependency_probe_cache()
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example")
    monkeypatch.setenv("STUDENT_RAG_HYBRID_COLLECTION", "student_handbook_semantic_v32")
    client = MagicMock()
    client.get_collection.return_value = SimpleNamespace(
        config=SimpleNamespace(
            params=SimpleNamespace(vectors=SimpleNamespace(size=1024))
        )
    )
    client.scroll.return_value = (
        [SimpleNamespace(payload={"build_id": "wrong-build"})],
        None,
    )

    with (
        patch("qdrant_client.QdrantClient", return_value=client),
        patch(
            "src.api.dependency_health.load_retrieval_build_contract",
            return_value={"build_id": "build-test", "embedding_dimension": 1024},
        ),
    ):
        result = probe_qdrant()

    assert result["status"] == "degraded"
    assert result["error_type"] == "RuntimeError"
