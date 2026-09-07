"""Snapshot local runtime and source inventory before authoring official_v1.

No model requests, database writes, or imports that initialize the runtime.
Never overwrite an existing snapshot: use --verify for subsequent checks.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "data/eval/official_v1"
RUNTIME_COMMIT = "7d9dc3ca87f124be1282c2f01d7a42983badbad2"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def constant(relative: str, name: str):
    for node in ast.parse((ROOT / relative).read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError(f"Missing constant: {name}")


def write_new(name: str, value) -> None:
    BUNDLE.mkdir(parents=True, exist_ok=True)
    with (BUNDLE / name).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def prepare() -> None:
    if (BUNDLE / "runtime_freeze.json").exists():
        raise FileExistsError("Snapshot exists; use --verify, do not overwrite it.")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if head != RUNTIME_COMMIT:
        raise ValueError("Runtime HEAD differs from the approved freeze commit")
    runtime_roots = ["src/api", "src/common", "src/generation", "src/retrieval", "src/services", "configs"]
    names = subprocess.check_output(["git", "ls-files", *runtime_roots], cwd=ROOT, text=True).splitlines()
    for name in names:
        committed = subprocess.check_output(["git", "show", f"{RUNTIME_COMMIT}:{name}"], cwd=ROOT)
        # Git may normalize CRLF in this Windows checkout.
        current = (ROOT / name).read_bytes().replace(b"\r\n", b"\n")
        if current != committed.replace(b"\r\n", b"\n"):
            raise ValueError(f"Uncommitted runtime change: {name}")
    build = json.loads((ROOT / "data/processed/metadata/build_manifest.json").read_text(encoding="utf-8"))
    targets = build["storage_targets"]
    assert targets == {"qdrant_collection": "student_handbook_semantic_v33", "mongo_parent_collection": "parent_docs_v33"}
    artifact_names = {record["path"] for record in build["artifacts"].values()}
    answer = yaml.safe_load((ROOT / "configs/answer_generation.yaml").read_text(encoding="utf-8"))
    router = yaml.safe_load((ROOT / "configs/ai_router.yaml").read_text(encoding="utf-8"))
    artifact_names.update(answer["input"].values())
    artifact_names.add("data/processed/metadata/build_manifest.json")
    artifact_names.update(["requirements.txt", "constraints-runtime.txt", "Dockerfile", ".dockerignore"])
    for record in build["artifacts"].values():
        if digest(ROOT / record["path"]) != record["sha256"]:
            raise ValueError(f"Artifact differs from build manifest: {record['path']}")
    packages = ["google-genai", "groq", "qdrant-client", "pymongo", "pydantic", "fastapi", "torch", "transformers", "sentence-transformers", "numpy"]
    versions = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    freeze = {
        "schema_version": "official-runtime-freeze-v1", "created_at": datetime.now(timezone.utc).isoformat(),
        "evaluated_system_commit": head, "runtime_frozen": True, "dataset_frozen": False,
        "deployment_verified": False, "build_id": build["build_id"], "storage_targets": targets,
        "pipeline_version": constant("src/generation/answer_pipeline.py", "PIPELINE_VERSION"),
        "composer_prompt_version": constant("src/generation/prompt_builder.py", "ANSWER_PROMPT_VERSION"),
        "planner_prompt_version": constant("src/retrieval/core/ai_router.py", "ROUTER_PROMPT_VERSION"),
        "normalizer_version": constant("src/retrieval/core/query_plan.py", "QUERY_PLAN_NORMALIZER_VERSION"),
        "schema_version_query_plan": constant("src/retrieval/core/query_plan.py", "QUERY_PLAN_SCHEMA_VERSION"),
        "planner": {k: router[k] for k in ("model_name", "reasoning_effort", "response_format", "temperature")},
        "composer": {k: answer["llm"][k] for k in ("model_name", "temperature", "max_output_tokens", "request_timeout_seconds")},
        "judge_model": "openai/gpt-oss-120b", "retrieval_mode": "vector_primary_graph_supplement",
        "reranker_enabled": False, "dependency_versions": versions,
        "quality_cache_policy": {"response_cache": False, "router_cache": False},
        "production_cache_policy": "measure cold and warm separately on HF after deployment",
        "file_hashes": {name: digest(ROOT / name) for name in sorted(set(names) | artifact_names)},
        "accepted_limitations": [
            "Owner accepted remaining-course interpretation for the reviewed K51 specialist-course case; not a universal synonym across courses/cohorts.",
            "Fact-lock evidence does not guarantee Composer obedience.",
        ],
        "secrets": "Not included; .env and credential values are never serialized.",
    }
    parents = json.loads((ROOT / "data/processed/chunks/all_docstore_items.json").read_text(encoding="utf-8"))
    inventory = []
    for parent in parents:
        meta = parent.get("metadata") or {}
        inventory.append({"source_id": parent["_id"], "cohort": meta.get("cohort") or parent.get("cohort"),
                          "title": meta.get("title"), "article": meta.get("article"),
                          "document_title": meta.get("document_title"), "source_pages": meta.get("source_pages"),
                          "content_sha256": hashlib.sha256(parent["content"].encode("utf-8")).hexdigest()})
    old_files = sorted(p for p in (ROOT / "data/eval").rglob("*.json") if BUNDLE not in p.parents)
    previous = {p.relative_to(ROOT).as_posix(): digest(p) for p in old_files}
    write_new("runtime_freeze.json", freeze)
    write_new("source_inventory.json", {"build_id": build["build_id"], "parents": inventory,
                                       "cohort_counts": dict(Counter(r["cohort"] for r in inventory))})
    write_new("prior_eval_inventory.json", {"purpose": "preserve identities before overlap review or cleanup", "files": previous,
                                          "overlap_review_complete": False, "manual_prompt_coverage": "pending"})
    print(f"Frozen runtime {head}; {len(freeze['file_hashes'])} hashes; {len(inventory)} parent sources; {len(previous)} historical JSON artifacts.")


def verify() -> None:
    freeze = json.loads((BUNDLE / "runtime_freeze.json").read_text(encoding="utf-8"))
    mismatches = [name for name, expected in freeze["file_hashes"].items() if not (ROOT / name).is_file() or digest(ROOT / name) != expected]
    if mismatches:
        raise ValueError(f"Frozen files changed: {mismatches}")
    print(f"Runtime/artifact hashes verified: {len(freeze['file_hashes'])}. No evaluation executed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    verify() if args.verify else prepare()
