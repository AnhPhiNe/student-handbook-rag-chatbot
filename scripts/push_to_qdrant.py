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

from src.common.storage_config import require_qdrant_collection_name


DATA_PATH = Path("data/processed/chunks/child_parent_chunks.json")
BUILD_MANIFEST_PATH = Path("data/processed/metadata/build_manifest.json")


def string_to_uuid(value: str) -> str:
    digest = hashlib.md5(value.encode("utf-8")).hexdigest()
    return str(uuid.UUID(digest))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_build_contract(
    chunks: list[dict],
    *,
    collection_name: str,
) -> str:
    if not BUILD_MANIFEST_PATH.is_file():
        raise RuntimeError(f"Missing build manifest: {BUILD_MANIFEST_PATH}")
    manifest = json.loads(BUILD_MANIFEST_PATH.read_text(encoding="utf-8"))
    build_id = str(manifest.get("build_id") or "")
    if not build_id:
        raise RuntimeError("Build manifest does not contain build_id.")
    targets = manifest.get("storage_targets") or {}
    if targets.get("qdrant_collection") != collection_name:
        raise RuntimeError(
            "Qdrant target does not match the collection locked in the build manifest."
        )
    child_artifact = (manifest.get("artifacts") or {}).get("child_chunks") or {}
    if child_artifact.get("sha256") != sha256_file(DATA_PATH):
        raise RuntimeError("Child chunk file hash does not match the build manifest.")
    if int(child_artifact.get("count") or 0) != len(chunks):
        raise RuntimeError("Child chunk count does not match the build manifest.")
    build_ids = {
        str((chunk.get("metadata") or {}).get("build_id") or "")
        for chunk in chunks
    }
    if build_ids != {build_id}:
        raise RuntimeError(
            "Child chunks are not uniformly tagged with the manifest build_id."
        )
    return build_id


def validate_embedding_contract(model_name: str, vector_size: int) -> None:
    manifest = json.loads(BUILD_MANIFEST_PATH.read_text(encoding="utf-8"))
    embedding = manifest.get("embedding") or {}
    if embedding.get("model") != model_name:
        raise RuntimeError("Embedding model does not match the build manifest.")
    if int(embedding.get("dimension") or 0) != vector_size:
        raise RuntimeError("Embedding dimension does not match the build manifest.")


def ensure_new_collection(client: QdrantClient, collection_name: str) -> None:
    if client.collection_exists(collection_name):
        raise RuntimeError(
            f"Refusing to overwrite existing Qdrant collection {collection_name!r}. "
            "Publish to a new versioned collection and switch the environment "
            "only after verification."
        )


def main() -> None:
    load_dotenv()
    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_api_key = os.getenv("QDRANT_API_KEY")
    collection_name = require_qdrant_collection_name()
    if not qdrant_url or not qdrant_api_key:
        print("Missing QDRANT_URL or QDRANT_API_KEY.")
        sys.exit(1)
    if not DATA_PATH.exists():
        print(f"Missing {DATA_PATH}. Run scripts/build_child_parent_index.py first.")
        sys.exit(1)

    chunks = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    print(f"Loaded {len(chunks)} child-parent chunks from {DATA_PATH}")
    
    if not isinstance(chunks, list) or not chunks:
        raise RuntimeError(
            "Refusing to push Qdrant because the child-parent chunk file is empty "
            "or malformed."
        )

    expected_cohorts = {"K48-K49", "K50", "K51"}

    actual_cohorts = {
        str((chunk.get("metadata") or {}).get("cohort"))
        for chunk in chunks
        if (chunk.get("metadata") or {}).get("cohort")
    }

    print(f"Child-parent cohorts: {sorted(actual_cohorts)}")

    if actual_cohorts != expected_cohorts:
        raise RuntimeError(
            "Refusing to overwrite Qdrant because the child-parent chunk file "
            f"does not contain all 3 cohorts. Current cohorts: {sorted(actual_cohorts)}"
        )
        
    allowed_content_types = {
        "regulation_text",
        "regulation_sections",
        "regulation",
    }

    invalid_content_types = sorted(
        {
            str((chunk.get("metadata") or {}).get("content_type"))
            for chunk in chunks
            if (chunk.get("metadata") or {}).get("content_type")
            not in allowed_content_types
        }
    )

    if invalid_content_types:
        raise RuntimeError(
            "Child-parent chunks still contain non-indexable content_type values: "
            + ", ".join(invalid_content_types)
        )

    build_id = validate_build_contract(
        chunks,
        collection_name=collection_name,
    )
    print(f"Validated build contract: {build_id}")

    model_name = os.getenv("STUDENT_RAG_EMBEDDING_MODEL", "BAAI/bge-m3")
    encode_batch_size = int(os.getenv("STUDENT_RAG_EMBEDDING_BATCH_SIZE", "32"))
    print(f"Loading embedding model: {model_name}")
    model = SentenceTransformer(model_name)
    vector_size = model.get_sentence_embedding_dimension()
    validate_embedding_contract(model_name, vector_size)

    texts = [str(chunk.get("content") or "") for chunk in chunks]
    embeddings = model.encode(
        texts,
        batch_size=encode_batch_size,
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

    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key, timeout=90.0)
    ensure_new_collection(client, collection_name)
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )
    print(f"Created {collection_name} with vector size {vector_size}")
    create_payload_indexes(client, collection_name)

    batch_size = 64
    for start in tqdm(range(0, len(points), batch_size), desc="Upserting chunks"):
        client.upsert(
            collection_name=collection_name,
            points=points[start : start + batch_size],
        )

    print(f"Done. Upserted {len(points)} points into {collection_name}.")


def create_payload_indexes(client: QdrantClient, collection_name: str) -> None:
    for field in (
        "chunk_type",
        "content_type",
        "cohort",
        "applicable_cohorts",
        "chunk_granularity",
        "parent_section_id",
    ):
        client.create_payload_index(
            collection_name=collection_name,
            field_name=field,
            field_schema=PayloadSchemaType.KEYWORD,
            wait=True,
        )
    print(
        "Created payload indexes for chunk_type, content_type, cohort, "
        "chunk_granularity, parent_section_id"
    )


if __name__ == "__main__":
    main()
