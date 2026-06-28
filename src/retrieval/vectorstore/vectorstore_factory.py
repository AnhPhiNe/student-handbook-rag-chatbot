"""Factory for creating vector store connections.

Supports ChromaDB (local, default) and Qdrant Cloud.
Controlled via environment variable VECTORDB_PROVIDER.

Usage:
    # In .env:
    # VECTORDB_PROVIDER=chroma  (default, local ChromaDB)
    # VECTORDB_PROVIDER=qdrant_cloud
    # QDRANT_URL=https://xxx.qdrant.io
    # QDRANT_API_KEY=your_key
"""

import os
from typing import Any

from src.common.env_loader import load_project_env


def get_vectordb_provider() -> str:
    """Return the configured vector database provider name."""
    load_project_env()
    return os.environ.get("VECTORDB_PROVIDER", "chroma").strip().lower()


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def create_collection(
    persist_dir: str,
    collection_name: str,
) -> Any:
    """Create a vector store collection based on the configured provider.

    For ChromaDB (default):
        Uses local persistent storage at *persist_dir*.

    For Qdrant Cloud:
        Requires QDRANT_URL and QDRANT_API_KEY environment variables.
        *persist_dir* is ignored; the collection is stored in the cloud.
    """
    provider = get_vectordb_provider()

    if provider == "qdrant_cloud":
        print(
            f"☁️  [VectorDB] Đang kết nối đến Qdrant Cloud cho collection '{collection_name}'..."
        )
        return _create_qdrant_collection(collection_name)

    print(f"📁 [VectorDB] Đang sử dụng ChromaDB Local tại '{persist_dir}'...")
    return _create_chroma_collection(persist_dir, collection_name)


def _create_chroma_collection(persist_dir: str, collection_name: str) -> Any:
    """Create a local ChromaDB collection (current default)."""
    import chromadb

    client = chromadb.PersistentClient(
        path=persist_dir, settings=chromadb.Settings(anonymized_telemetry=False)
    )
    return client.get_collection(name=collection_name)


def ensure_payload_indexes(client: Any, collection_name: str) -> None:
    """Tự động tạo các Payload Index cần thiết trên Qdrant Cloud.

    Qdrant (khác với ChromaDB) yêu cầu phải khai báo Index tường minh
    trước khi có thể lọc (filter) theo metadata field.
    """
    from qdrant_client.http.models import PayloadSchemaType

    required_indexes = {
        "chunk_type": PayloadSchemaType.KEYWORD,
        "source": PayloadSchemaType.KEYWORD,
        "title": PayloadSchemaType.TEXT,
        "cohort": PayloadSchemaType.KEYWORD,
    }

    try:
        collection_info = client.get_collection(collection_name)
        existing_indexes = (
            set(collection_info.payload_schema.keys())
            if collection_info.payload_schema
            else set()
        )

        for field_name, field_type in required_indexes.items():
            if field_name not in existing_indexes:
                client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=field_type,
                )
                print(f"   ✅ Đã tạo Index cho field '{field_name}'")
    except Exception as e:
        print(f"   ⚠️ Không thể tạo payload index: {e}")


def _create_qdrant_collection(collection_name: str) -> Any:
    """Create a Qdrant Cloud collection.

    Requires:
        pip install qdrant-client
        QDRANT_URL and QDRANT_API_KEY in .env
    """
    try:
        from qdrant_client import QdrantClient
    except ImportError as exc:
        raise RuntimeError(
            "qdrant-client is required for Qdrant Cloud. "
            "Install it with: pip install qdrant-client"
        ) from exc

    url = os.environ.get("QDRANT_URL")
    api_key = os.environ.get("QDRANT_API_KEY")
    if not url or not api_key:
        raise RuntimeError(
            "QDRANT_URL and QDRANT_API_KEY must be set in .env for Qdrant Cloud."
        )

    client = QdrantClient(url=url, api_key=api_key, timeout=60.0)

    # Tự động tạo payload index nếu chưa có
    if _env_bool("QDRANT_CREATE_PAYLOAD_INDEXES", default=False):
        ensure_payload_indexes(client, collection_name)
    print("   ✅ Kết nối Qdrant Cloud thành công!")

    # Return a thin wrapper that matches the ChromaDB collection interface
    # used by the existing vector_retriever.py
    return QdrantCollectionAdapter(client=client, collection_name=collection_name)


class QdrantCollectionAdapter:
    """Adapter to make Qdrant client match the ChromaDB collection.query() interface.

    This allows the existing vector_retriever.py to work with Qdrant
    without changing its code. The adapter translates query() calls
    to Qdrant's search API.
    """

    def __init__(self, client: Any, collection_name: str) -> None:
        self.client = client
        self.collection_name = collection_name

    def query(
        self,
        query_embeddings: list[list[float]],
        n_results: int = 10,
        where: dict[str, Any] | None = None,
        include: list[str] | None = None,
    ) -> dict[str, Any]:
        """Translate ChromaDB-style query to Qdrant search."""
        from qdrant_client.models import Filter, FieldCondition, MatchAny

        qdrant_filter = None
        if where:
            from qdrant_client.models import (
                Filter,
                FieldCondition,
                MatchAny,
                MatchValue,
            )

            must_conditions = []

            def parse_condition(key, val):
                if key == "chunk_type":
                    if isinstance(val, str):
                        must_conditions.append(
                            FieldCondition(key="chunk_type", match=MatchAny(any=[val]))
                        )
                    elif isinstance(val, dict) and "$in" in val:
                        must_conditions.append(
                            FieldCondition(
                                key="chunk_type", match=MatchAny(any=val["$in"])
                            )
                        )
                elif key == "cohort":
                    must_conditions.append(
                        FieldCondition(key="cohort", match=MatchValue(value=val))
                    )

            if "$and" in where:
                for cond in where["$and"]:
                    for k, v in cond.items():
                        parse_condition(k, v)
            else:
                for k, v in where.items():
                    parse_condition(k, v)

            if must_conditions:
                qdrant_filter = Filter(must=must_conditions)

        results = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embeddings[0],
            limit=n_results,
            query_filter=qdrant_filter,
        ).points

        # Convert Qdrant response to ChromaDB-compatible format
        ids = [[str(hit.id) for hit in results]]
        documents = [[hit.payload.get("content", "") for hit in results]]
        metadatas = [[hit.payload for hit in results]]
        distances = [[1.0 - hit.score for hit in results]]

        return {
            "ids": ids,
            "documents": documents,
            "metadatas": metadatas,
            "distances": distances,
        }
