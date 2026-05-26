from typing import Any, Optional

import chromadb
import torch
from sentence_transformers import SentenceTransformer


def get_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def load_embedding_model(model_name: str) -> SentenceTransformer:
    return SentenceTransformer(model_name, device=get_device())


def get_chroma_collection(persist_dir: str, collection_name: str) -> chromadb.Collection:
    client = chromadb.PersistentClient(path=persist_dir)
    return client.get_collection(name=collection_name)


def build_where_filter(chunk_types: Optional[list[str]]) -> Optional[dict[str, Any]]:
    if not chunk_types:
        return None

    if len(chunk_types) == 1:
        return {"chunk_type": chunk_types[0]}

    return {"chunk_type": {"$in": chunk_types}}


def vector_search(
    query: str,
    model: SentenceTransformer,
    collection: chromadb.Collection,
    chunk_types: Optional[list[str]] = None,
    top_k: int = 5,
    batch_size: int = 8,
    normalize_embeddings: bool = True,
) -> list[dict[str, Any]]:
    query_embedding = model.encode(
        [query],
        batch_size=batch_size,
        normalize_embeddings=normalize_embeddings,
    ).tolist()

    where_filter = build_where_filter(chunk_types)

    response = collection.query(
        query_embeddings=query_embedding,
        n_results=top_k,
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )

    results = []

    if not response["ids"]:
        return results

    for idx in range(len(response["ids"][0])):
        results.append(
            {
                "chunk_id": response["ids"][0][idx],
                "distance": response["distances"][0][idx],
                "content": response["documents"][0][idx],
                "metadata": response["metadatas"][0][idx],
            }
        )

    return results