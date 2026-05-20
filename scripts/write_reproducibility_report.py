from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

from src.common.console import configure_utf8_stdio


DEFAULT_OUTPUT_PATH = Path("data/processed/metadata/reproducibility_report.json")
TRACKED_FILES = [
    "requirements.txt",
    "requirements-dev.txt",
    "requirements.lock",
    "configs/phase4_parser.yaml",
    "configs/phase5_chunking.yaml",
    "configs/phase6_embedding.yaml",
    "configs/phase7_retrieval.yaml",
    "configs/phase8_answer_generation.yaml",
    "configs/query_routing_rules.yaml",
    "data/eval/golden_queries.json",
    "data/eval/router_behavior_queries.json",
    "data/eval/answer_eval_cases.json",
]
IMPORTANT_PACKAGES = [
    "streamlit",
    "fastapi",
    "uvicorn",
    "sentence-transformers",
    "chromadb",
    "torch",
    "google-genai",
    "PyMuPDF",
    "pydantic",
    "requests",
    "PyYAML",
    "python-dotenv",
]


def sha256_file(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None

    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for package in IMPORTANT_PACKAGES:
        try:
            versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            versions[package] = None
    return versions


def git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def build_report() -> dict[str, Any]:
    return {
        "python": {
            "version": sys.version,
            "executable": sys.executable,
            "implementation": platform.python_implementation(),
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "git": {
            "commit": git_commit(),
            "dirty_worktree_expected": True,
        },
        "packages": package_versions(),
        "files": {
            item: {
                "exists": Path(item).exists(),
                "sha256": sha256_file(Path(item)),
            }
            for item in TRACKED_FILES
        },
    }


def save_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        f.write("\n")


def main() -> None:
    configure_utf8_stdio()
    save_json(build_report(), DEFAULT_OUTPUT_PATH)
    print(f"Saved reproducibility report: {DEFAULT_OUTPUT_PATH}")


if __name__ == "__main__":
    main()
