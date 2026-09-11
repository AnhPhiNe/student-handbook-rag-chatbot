import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


def load_json(path: str | Path) -> Any:
    """Load a UTF-8 JSON artifact."""

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Missing JSON file: {source}")
    with source.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_json(data: Any, path: str | Path) -> None:
    """Persist a UTF-8 JSON artifact with stable formatting."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a UTF-8 YAML configuration file."""

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(f"Missing YAML file: {source}")
    with source.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def sha256_file(path: str | Path) -> str:
    """Return the SHA-256 hex digest of a file, read in 1 MiB blocks."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
