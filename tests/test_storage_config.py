from __future__ import annotations

import pytest

from src.common.storage_config import (
    require_mongo_parent_collection_name,
    require_qdrant_collection_name,
)


def test_qdrant_collection_requires_explicit_configuration() -> None:
    with pytest.raises(RuntimeError, match="must be configured explicitly"):
        require_qdrant_collection_name({})


def test_qdrant_collection_supports_runtime_alias_without_fallback() -> None:
    assert (
        require_qdrant_collection_name(
            {"STUDENT_RAG_HYBRID_COLLECTION": " student_handbook_v30 "}
        )
        == "student_handbook_v30"
    )


def test_qdrant_runtime_alias_has_precedence() -> None:
    assert (
        require_qdrant_collection_name(
            {
                "STUDENT_RAG_HYBRID_COLLECTION": "runtime_collection",
                "QDRANT_COLLECTION_NAME": "publish_collection",
            }
        )
        == "runtime_collection"
    )


def test_mongo_collection_requires_explicit_configuration() -> None:
    with pytest.raises(RuntimeError, match="must be configured explicitly"):
        require_mongo_parent_collection_name({})


def test_mongo_collection_is_normalized() -> None:
    assert (
        require_mongo_parent_collection_name(
            {"MONGODB_PARENT_COLLECTION": " parent_docs_v30 "}
        )
        == "parent_docs_v30"
    )
