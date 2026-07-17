from typing import Any, Optional

import torch
from sentence_transformers import SentenceTransformer

from src.common.cohort import normalize_cohort
from src.retrieval.vectorstore.vectorstore_factory import create_collection


def get_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def load_embedding_model(model_name: str) -> SentenceTransformer:
    return SentenceTransformer(model_name, device=get_device())


def get_chroma_collection(persist_dir: str, collection_name: str) -> Any:
    return create_collection(persist_dir, collection_name)


def build_where_filter(
    chunk_types: Optional[list[str]],
    cohort: Optional[str] = None,
    content_types: Optional[list[str]] = None,
) -> Optional[dict[str, Any]]:
    conditions = []

    if chunk_types:
        if len(chunk_types) == 1:
            conditions.append({"chunk_type": chunk_types[0]})
        else:
            conditions.append({"chunk_type": {"$in": chunk_types}})

    if content_types:
        if len(content_types) == 1:
            conditions.append({"content_type": content_types[0]})
        else:
            conditions.append({"content_type": {"$in": content_types}})

    cohort = normalize_cohort(cohort)
    if cohort:
        conditions.append({"cohort": cohort})

    if not conditions:
        return None

    if len(conditions) == 1:
        return conditions[0]

    return {"$and": conditions}


def vector_search(
    query: str,
    model: SentenceTransformer,
    collection: Any,
    chunk_types: Optional[list[str]] = None,
    top_k: int = 5,
    batch_size: int = 8,
    normalize_embeddings: bool = True,
    cohort: Optional[str] = None,
    content_types: Optional[list[str]] = None,
) -> list[dict[str, Any]]:
    query_embedding = model.encode(
        [query],
        batch_size=batch_size,
        normalize_embeddings=normalize_embeddings,
    ).tolist()

    where_filter = build_where_filter(chunk_types, cohort, content_types)

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
