from __future__ import annotations

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

    with patch("qdrant_client.QdrantClient", return_value=client):
        first = probe_qdrant()
        second = probe_qdrant()

    assert first["status"] == "ready"
    assert second["status"] == "ready"
    client.get_collection.assert_called_once_with("student_handbook_semantic_v32")


def test_mongodb_probe_checks_configured_parent_collection(monkeypatch) -> None:
    reset_dependency_probe_cache()
    monkeypatch.setenv("MONGODB_URL", "mongodb://example")
    monkeypatch.setenv("MONGODB_PARENT_COLLECTION", "parent_docs_v32")
    collection = MagicMock()
    database = MagicMock()
    database.__getitem__.return_value = collection
    client = MagicMock()
    client.__getitem__.return_value = database

    with patch("pymongo.MongoClient", return_value=client):
        result = probe_mongodb()

    assert result["status"] == "ready"
    client.__getitem__.assert_called_once_with("chatbotHCMUE")
    database.__getitem__.assert_called_once_with("parent_docs_v32")
    collection.find_one.assert_called_once_with({}, {"_id": 1})
