from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.common.io import load_yaml


DEFAULT_RETRIEVAL_CONFIG_PATH = Path("configs/retrieval.yaml")


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
