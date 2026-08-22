"""Stable hashes for release reports and human-review preservation."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

from src.retrieval.core.structured_routing import registry_digest


ARTIFACT_PATHS = {
    "structured_registry": "configs/structured_lookup_registry.yaml",
    "entity_registry": "data/processed/entities/entity_registry.json",
    "office_aliases": "configs/office_aliases.yaml",
    "acronym_vocabulary": "configs/hcmue_slang_dictionary.yaml",
    "structured_manifest": "data/processed/metadata/structured_data_manifest.json",
    "formula_rules": "data/processed/tables/formula_rules.json",
    "scoring_tables": "data/processed/tables/scoring_tables.json",
    "structured_tables_registry": "data/processed/tables/structured_tables_registry.json",
    "foreign_language_equivalency": "data/processed/tables/foreign_language_equivalency_table.json",
    "student_service_directory": "data/processed/directories/student_service_directory.json",
    "student_office_profiles": "data/processed/directories/student_office_profiles.json",
    "student_faculty_profiles": "data/processed/directories/student_faculty_profiles.json",
    "program_directory": "data/processed/directories/program_directory.json",
    "chunk_index_manifest": "data/processed/chunks/index_manifest.json",
    "bm25_index": "data/processed/retrieval/bm25_index.json",
    "ai_router_config": "configs/ai_router.yaml",
    "ai_router_prompt_source": "src/retrieval/core/ai_router.py",
    "answer_config": "configs/answer_generation.yaml",
    "answer_prompt_source": "src/generation/prompt_builder.py",
}

IMPLEMENTATION_PATTERNS = (
    "src/**/*.py",
    "scripts/*.py",
    "tests/**/*.py",
    "frontend/src/**/*",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/tsconfig*.json",
    "frontend/vite.config.*",
)


def file_hash(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def tree_hash(root: Path, patterns: Iterable[str] = IMPLEMENTATION_PATTERNS) -> str:
    files = {
        path
        for pattern in patterns
        for path in root.glob(pattern)
        if path.is_file()
    }
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda value: value.as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        content = path.read_bytes()
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def release_artifact_fingerprint(root: Path) -> dict[str, str | None]:
    values = {
        name: file_hash(root / relative)
        for name, relative in ARTIFACT_PATHS.items()
    }
    values["implementation_tree"] = tree_hash(root)
    values["planner_registry_digest"] = registry_digest()
    return values
