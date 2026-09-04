from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from src.common.io import load_yaml


DEFAULT_RETRIEVAL_CONFIG_PATH = Path("configs/retrieval.yaml")
DEFAULT_BUILD_MANIFEST_PATH = Path("data/processed/metadata/build_manifest.json")


def load_retrieval_runtime_config(
    path: str | Path | None = None,
) -> dict[str, Any]:
    """Load the single authoritative retrieval runtime configuration."""

    config_path = Path(
        os.environ.get("STUDENT_RAG_RETRIEVAL_CONFIG")
        or path
        or DEFAULT_RETRIEVAL_CONFIG_PATH
    )
    config = load_yaml(config_path)
    model_name = str((config.get("embedding") or {}).get("model_name") or "").strip()
    if not model_name:
        raise ValueError(f"Missing embedding.model_name in {config_path}")
    return config


def load_retrieval_build_contract(
    manifest_path: str | Path = DEFAULT_BUILD_MANIFEST_PATH,
) -> dict[str, Any]:
    """Validate and return the shared local retrieval build identity."""

    path = Path(manifest_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Build manifest must be a JSON object.")
    runtime_config = load_retrieval_runtime_config()
    manifest_embedding = manifest.get("embedding") or {}
    runtime_embedding = runtime_config.get("embedding") or {}

    build_id = str(manifest.get("build_id") or "").strip()
    runtime_model = str(runtime_embedding.get("model_name") or "").strip()
    manifest_model = str(manifest_embedding.get("model") or "").strip()
    try:
        runtime_dimension = int(runtime_embedding.get("dimension") or 0)
        manifest_dimension = int(manifest_embedding.get("dimension") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid retrieval embedding dimension.") from exc
    runtime_normalize = bool(runtime_embedding.get("normalize_embeddings", True))
    manifest_normalize = bool(manifest_embedding.get("normalize_embeddings", True))

    if not build_id:
        raise ValueError("Build manifest does not contain build_id.")
    if not runtime_model or runtime_model != manifest_model:
        raise ValueError("Runtime embedding model does not match build manifest.")
    if runtime_dimension <= 0 or runtime_dimension != manifest_dimension:
        raise ValueError("Runtime embedding dimension does not match build manifest.")
    if runtime_normalize != manifest_normalize:
        raise ValueError("Runtime embedding normalization does not match build manifest.")

    storage_targets = manifest.get("storage_targets") or {}
    return {
        "build_id": build_id,
        "embedding_model": runtime_model,
        "embedding_dimension": runtime_dimension,
        "normalize_embeddings": runtime_normalize,
        "qdrant_collection": str(
            storage_targets.get("qdrant_collection") or ""
        ).strip(),
        "mongo_parent_collection": str(
            storage_targets.get("mongo_parent_collection") or ""
        ).strip(),
    }
