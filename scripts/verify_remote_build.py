from __future__ import annotations

import json
import os
import sys
import argparse
from pathlib import Path
from typing import Any

from pymongo import MongoClient
from qdrant_client import QdrantClient

from src.common.env_loader import load_project_env
from src.common.storage_config import (
    require_mongo_parent_collection_name,
    require_qdrant_collection_name,
)


MANIFEST_PATH = Path("data/processed/metadata/build_manifest.json")


def _load_manifest_and_targets() -> tuple[dict[str, Any], str, str, str]:
    load_project_env(override=False)
    if not MANIFEST_PATH.is_file():
        raise FileNotFoundError(f"Missing build manifest: {MANIFEST_PATH}")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    build_id = str(manifest.get("build_id") or "")
    if not build_id:
        raise RuntimeError("Build manifest does not contain build_id.")
    qdrant_collection = require_qdrant_collection_name()
    mongo_collection = require_mongo_parent_collection_name()
    targets = manifest.get("storage_targets") or {}
    if targets.get("qdrant_collection") != qdrant_collection:
        raise RuntimeError("Qdrant collection does not match the build manifest.")
    if targets.get("mongo_parent_collection") != mongo_collection:
        raise RuntimeError("MongoDB collection does not match the build manifest.")
    return manifest, build_id, qdrant_collection, mongo_collection


def _connection_settings() -> tuple[str, str, str, str]:
    qdrant_url = os.environ.get("QDRANT_URL") or ""
    qdrant_key = os.environ.get("QDRANT_API_KEY") or ""
    mongo_url = os.environ.get("MONGODB_URL") or ""
    database_name = os.environ.get("MONGODB_DB_NAME", "chatbotHCMUE")
    if not qdrant_url or not qdrant_key or not mongo_url:
        raise RuntimeError("Qdrant and MongoDB connection settings are required.")
    return qdrant_url, qdrant_key, mongo_url, database_name


def verify_remote_targets_available() -> dict[str, Any]:
    _, build_id, qdrant_collection, mongo_collection = _load_manifest_and_targets()
    qdrant_url, qdrant_key, mongo_url, database_name = _connection_settings()
    qdrant = QdrantClient(
        url=qdrant_url,
        api_key=qdrant_key,
        timeout=90.0,
        check_compatibility=False,
    )
    if qdrant.collection_exists(qdrant_collection):
        raise RuntimeError(
            f"Qdrant target already exists: {qdrant_collection!r}."
        )
    mongo = MongoClient(
        mongo_url,
        serverSelectionTimeoutMS=30000,
        connectTimeoutMS=30000,
        socketTimeoutMS=30000,
    )
    existing_parents = mongo[database_name][
        mongo_collection
    ].estimated_document_count()
    if existing_parents:
        raise RuntimeError(
            f"MongoDB target is not empty: {mongo_collection!r} "
            f"({existing_parents} documents)."
        )
    return {
        "status": "available",
        "build_id": build_id,
        "qdrant_collection": qdrant_collection,
        "mongo_collection": mongo_collection,
    }


def verify_remote_build() -> dict[str, Any]:
    manifest, build_id, qdrant_collection, mongo_collection = (
        _load_manifest_and_targets()
    )
    qdrant_url, qdrant_key, mongo_url, database_name = _connection_settings()

    qdrant = QdrantClient(
        url=qdrant_url,
        api_key=qdrant_key,
        timeout=90.0,
        check_compatibility=False,
    )
    qdrant_info = qdrant.get_collection(qdrant_collection)
    qdrant_parent_ids: set[str] = set()
    qdrant_build_ids: set[str] = set()
    qdrant_chunk_ids: set[str] = set()
    offset = None
    scanned_points = 0
    while True:
        points, offset = qdrant.scroll(
            collection_name=qdrant_collection,
            limit=1000,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        scanned_points += len(points)
        for point in points:
            payload = dict(point.payload or {})
            qdrant_build_ids.add(str(payload.get("build_id") or ""))
            qdrant_parent_ids.add(str(payload.get("parent_section_id") or ""))
            qdrant_chunk_ids.add(str(payload.get("chunk_id") or point.id))
        if offset is None:
            break

    mongo = MongoClient(
        mongo_url,
        serverSelectionTimeoutMS=30000,
        connectTimeoutMS=30000,
        socketTimeoutMS=30000,
    )
    documents = list(
        mongo[database_name][mongo_collection].find(
            {}, {"_id": 1, "build_id": 1, "metadata.build_id": 1}
        )
    )
    mongo_parent_ids = {str(document.get("_id") or "") for document in documents}
    mongo_build_ids = {
        str(
            document.get("build_id")
            or (document.get("metadata") or {}).get("build_id")
            or ""
        )
        for document in documents
    }

    expected_child_count = int(
        ((manifest.get("artifacts") or {}).get("child_chunks") or {}).get("count")
        or 0
    )
    expected_parent_count = int(
        ((manifest.get("artifacts") or {}).get("parent_docstore") or {}).get("count")
        or 0
    )
    errors: list[str] = []
    if qdrant_build_ids != {build_id}:
        errors.append(f"Qdrant build ids do not equal {build_id!r}.")
    if mongo_build_ids != {build_id}:
        errors.append(f"MongoDB build ids do not equal {build_id!r}.")
    if scanned_points != expected_child_count:
        errors.append(
            f"Qdrant point count {scanned_points} != expected {expected_child_count}."
        )
    if len(documents) != expected_parent_count:
        errors.append(
            f"MongoDB parent count {len(documents)} != expected {expected_parent_count}."
        )
    if qdrant_parent_ids != mongo_parent_ids:
        errors.append("Qdrant parent ids and MongoDB parent ids do not match.")
    if len(qdrant_chunk_ids) != scanned_points:
        errors.append("Qdrant contains duplicate or missing chunk ids.")
    if "" in qdrant_parent_ids or "" in mongo_parent_ids:
        errors.append("Remote stores contain empty parent ids.")
    if int(qdrant_info.points_count or 0) != scanned_points:
        errors.append("Qdrant reported count differs from the scanned count.")
    expected_dimension = int((manifest.get("embedding") or {}).get("dimension") or 0)
    vector_params = qdrant_info.config.params.vectors
    remote_dimension = int(getattr(vector_params, "size", 0) or 0)
    if remote_dimension != expected_dimension:
        errors.append(
            f"Qdrant vector dimension {remote_dimension} != expected "
            f"{expected_dimension}."
        )
    if errors:
        raise RuntimeError("Remote build verification failed:\n- " + "\n- ".join(errors))

    return {
        "status": "ok",
        "build_id": build_id,
        "qdrant_collection": qdrant_collection,
        "qdrant_points": scanned_points,
        "mongo_collection": mongo_collection,
        "mongo_parents": len(documents),
        "linked_parent_ids": len(qdrant_parent_ids),
    }


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Verify one versioned remote build.")
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Require both remote targets to be absent/empty before publishing.",
    )
    args = parser.parse_args()
    result = (
        verify_remote_targets_available()
        if args.preflight
        else verify_remote_build()
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
