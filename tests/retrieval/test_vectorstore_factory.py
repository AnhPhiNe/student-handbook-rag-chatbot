from __future__ import annotations

from unittest.mock import patch

from src.retrieval.vectorstore import vectorstore_factory


def test_create_collection_accepts_qdrant_provider_alias() -> None:
    sentinel = object()
    with (
        patch.dict("os.environ", {"VECTORDB_PROVIDER": "qdrant"}, clear=True),
        patch.object(
            vectorstore_factory,
            "_create_qdrant_collection",
            return_value=sentinel,
        ) as create_qdrant,
        patch.object(vectorstore_factory, "_create_chroma_collection") as create_chroma,
    ):
        collection = vectorstore_factory.create_collection(
            persist_dir="data/vectorstore/chroma",
            collection_name="student_handbook_semantic_v9_candidate",
        )

    assert collection is sentinel
    create_qdrant.assert_called_once_with("student_handbook_semantic_v9_candidate")
    create_chroma.assert_not_called()


def test_create_collection_keeps_qdrant_cloud_provider_alias() -> None:
    sentinel = object()
    with (
        patch.dict("os.environ", {"VECTORDB_PROVIDER": "qdrant_cloud"}, clear=True),
        patch.object(
            vectorstore_factory,
            "_create_qdrant_collection",
            return_value=sentinel,
        ) as create_qdrant,
        patch.object(vectorstore_factory, "_create_chroma_collection") as create_chroma,
    ):
        collection = vectorstore_factory.create_collection(
            persist_dir="data/vectorstore/chroma",
            collection_name="student_handbook_semantic_v9_candidate",
        )

    assert collection is sentinel
    create_qdrant.assert_called_once_with("student_handbook_semantic_v9_candidate")
    create_chroma.assert_not_called()
