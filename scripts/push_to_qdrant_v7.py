from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

COLLECTION_NAME = "student_handbook_semantic_v7"
DATA_PATH = Path("data/processed/chunks/v7_child_parent_chunks.json")


def string_to_uuid(value: str) -> str:
    digest = hashlib.md5(value.encode("utf-8")).hexdigest()
    return str(uuid.UUID(digest))


def main() -> None:
    load_dotenv()
    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_api_key = os.getenv("QDRANT_API_KEY")
    if not qdrant_url or not qdrant_api_key:
        print("Missing QDRANT_URL or QDRANT_API_KEY.")
        sys.exit(1)
    if not DATA_PATH.exists():
        print(f"Missing {DATA_PATH}. Run scripts/build_v7_child_parent_index.py first.")
        sys.exit(1)

    chunks = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(chunks)} V7 child-parent chunks from {DATA_PATH}")

    model_name = os.getenv("STUDENT_RAG_EMBEDDING_MODEL", "BAAI/bge-m3")
    print(f"Loading embedding model: {model_name}")
    model = SentenceTransformer(model_name)
    vector_size = model.get_sentence_embedding_dimension()

    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key, timeout=90.0)
    if client.collection_exists(COLLECTION_NAME):
        print(f"Collection {COLLECTION_NAME} exists. Deleting before reload.")
        client.delete_collection(COLLECTION_NAME)

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )
    print(f"Created {COLLECTION_NAME} with vector size {vector_size}")
    create_payload_indexes(client)

    texts = [str(chunk.get("content") or "") for chunk in chunks]
    embeddings = model.encode(
        texts,
        batch_size=8,
        show_progress_bar=True,
        normalize_embeddings=True,
    )

    points: list[PointStruct] = []
    for index, chunk in enumerate(chunks):
        chunk_id = str(chunk.get("_id") or chunk.get("chunk_id"))
        metadata = dict(chunk.get("metadata") or {})
        metadata["content"] = chunk.get("content") or ""
        metadata["chunk_id"] = chunk_id
        points.append(
            PointStruct(
                id=string_to_uuid(chunk_id),
                vector=embeddings[index].tolist(),
                payload=metadata,
            )
        )

    batch_size = 64
    for start in tqdm(range(0, len(points), batch_size), desc="Upserting V7"):
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=points[start : start + batch_size],
        )

    print(f"Done. Upserted {len(points)} points into {COLLECTION_NAME}.")


def create_payload_indexes(client: QdrantClient) -> None:
    for field in ("content_type", "cohort", "chunk_granularity", "parent_section_id"):
        client.create_payload_index(
            collection_name=COLLECTION_NAME,
            field_name=field,
            field_schema=PayloadSchemaType.KEYWORD,
            wait=True,
        )
    print("Created payload indexes for content_type, cohort, chunk_granularity, parent_section_id")


if __name__ == "__main__":
    main()
