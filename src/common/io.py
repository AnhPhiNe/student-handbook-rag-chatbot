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
