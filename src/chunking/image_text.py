"""Write back content the handbook PDF prints as an image (configs/image_text.yaml)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.common.io import load_yaml

CONFIG_PATH = Path("configs/image_text.yaml")


def restore_image_text(parents: list[dict[str, Any]], cohort: str | None,
                       config_path: Path = CONFIG_PATH) -> None:
    """Insert each configured text before its anchor, in the one parent that holds it."""
    for entry in load_yaml(config_path).get("entries") or []:
        if cohort not in entry["cohorts"]:
            continue
        anchor, text = entry["before"], entry["text"]
        holders = [parent for parent in parents if anchor in parent.get("content", "")]
        if len(holders) != 1:
            raise ValueError(f"{entry['id']}: anchor found in {len(holders)} parents of {cohort}, expected 1")
        parent = holders[0]
        for field in ("content", "normalized_content"):
            value = parent.get(field)
            if isinstance(value, str) and anchor in value and text not in value:
                parent[field] = value.replace(anchor, f"{text}\n{anchor}", 1)
