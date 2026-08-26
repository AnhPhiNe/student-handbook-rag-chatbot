from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import push_to_mongo, push_to_qdrant, verify_remote_build


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def test_qdrant_publish_requires_matching_manifest_and_build_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_path = tmp_path / "children.json"
    manifest_path = tmp_path / "manifest.json"
    chunks = [
        {
            "_id": "child-1",
            "metadata": {"build_id": "build-test", "parent_section_id": "p1"},
        }
    ]
    _write_json(data_path, chunks)
    _write_json(
        manifest_path,
        {
            "build_id": "build-test",
            "storage_targets": {"qdrant_collection": "qdrant-v30"},
            "artifacts": {
                "child_chunks": {
                    "sha256": push_to_qdrant.sha256_file(data_path),
                    "count": 1,
                }
            },
            "embedding": {"model": "BAAI/bge-m3", "dimension": 1024},
        },
    )
    monkeypatch.setattr(push_to_qdrant, "DATA_PATH", data_path)
    monkeypatch.setattr(push_to_qdrant, "BUILD_MANIFEST_PATH", manifest_path)

    assert (
        push_to_qdrant.validate_build_contract(
            chunks,
            collection_name="qdrant-v30",
        )
        == "build-test"
    )
    with pytest.raises(RuntimeError, match="target does not match"):
        push_to_qdrant.validate_build_contract(
            chunks,
            collection_name="qdrant-v31",
        )
    push_to_qdrant.validate_embedding_contract("BAAI/bge-m3", 1024)
    with pytest.raises(RuntimeError, match="model does not match"):
        push_to_qdrant.validate_embedding_contract("different-model", 1024)


def test_mongo_publish_requires_matching_manifest_and_build_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_path = tmp_path / "parents.json"
    manifest_path = tmp_path / "manifest.json"
    parents = [{"_id": "p1", "build_id": "build-test", "metadata": {}}]
    _write_json(data_path, parents)
    _write_json(
        manifest_path,
        {
            "build_id": "build-test",
            "storage_targets": {"mongo_parent_collection": "parents-v30"},
            "artifacts": {
                "parent_docstore": {
                    "sha256": push_to_mongo.sha256_file(data_path),
                    "count": 1,
                }
            },
        },
    )
    monkeypatch.setattr(push_to_mongo, "BUILD_MANIFEST_PATH", manifest_path)

    assert (
        push_to_mongo.validate_build_contract(
            parents,
            docstore_path=data_path,
            collection_name="parents-v30",
        )
        == "build-test"
    )


def test_publish_refuses_existing_remote_targets() -> None:
    qdrant_client = SimpleNamespace(collection_exists=lambda _: True)
    with pytest.raises(RuntimeError, match="Refusing to overwrite"):
        push_to_qdrant.ensure_new_collection(qdrant_client, "qdrant-v30")

    mongo_collection = SimpleNamespace(
        name="parents-v30",
        estimated_document_count=lambda: 10,
    )
    with pytest.raises(RuntimeError, match="Từ chối ghi đè"):
        push_to_mongo.ensure_empty_collection(mongo_collection)


def test_remote_preflight_requires_both_targets_to_be_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        verify_remote_build,
        "_load_manifest_and_targets",
        lambda: ({}, "build-test", "qdrant-v30", "parents-v30"),
    )
    monkeypatch.setattr(
        verify_remote_build,
        "_connection_settings",
        lambda: ("https://qdrant", "key", "mongodb://mongo", "db"),
    )

    class FakeQdrant:
        def __init__(self, **_: object) -> None:
            pass

        def collection_exists(self, _: str) -> bool:
            return False

    collection = SimpleNamespace(estimated_document_count=lambda: 0)
    database = {"parents-v30": collection}
    mongo = {"db": database}
    monkeypatch.setattr(verify_remote_build, "QdrantClient", FakeQdrant)
    monkeypatch.setattr(verify_remote_build, "MongoClient", lambda *_args, **_kwargs: mongo)

    assert verify_remote_build.verify_remote_targets_available()["status"] == "available"


def test_remote_preflight_rejects_existing_qdrant_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        verify_remote_build,
        "_load_manifest_and_targets",
        lambda: ({}, "build-test", "qdrant-v30", "parents-v30"),
    )
    monkeypatch.setattr(
        verify_remote_build,
        "_connection_settings",
        lambda: ("https://qdrant", "key", "mongodb://mongo", "db"),
    )
    qdrant = SimpleNamespace(collection_exists=lambda _name: True)
    monkeypatch.setattr(
        verify_remote_build,
        "QdrantClient",
        lambda **_kwargs: qdrant,
    )

    with pytest.raises(RuntimeError, match="already exists"):
        verify_remote_build.verify_remote_targets_available()
