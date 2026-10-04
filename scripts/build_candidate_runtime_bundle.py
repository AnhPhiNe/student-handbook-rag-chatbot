"""Prepare a portable runtime overlay for an already-published candidate. Offline only."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path

import yaml

from scripts.build_table_search_candidate import ROOT, assert_separate_output
from scripts.publish_table_search_candidate import prepare_candidate
from src.common.runtime_artifacts import RUNTIME_FILES

DESCRIPTIONS_PATH = "data/processed/metadata/table_search_descriptions.json"
MANIFEST_PATH = "data/processed/metadata/build_manifest.json"
CONFIG_PATH = "configs/retrieval.yaml"


def build_runtime_bundle(root: Path, candidate: Path, output: Path) -> dict:
    """Pin the frozen corpus/publication and overlay only runtime index identity.

    build_id remains the unchanged source snapshot used by existing remote
    payloads. indexed_artifacts explicitly describes the extended index, so
    narrative separation audits are not rewritten to pretend handles are rows.
    """
    root, candidate, output = root.resolve(), candidate.resolve(), output.resolve()
    assert_separate_output(root, output)
    if output == candidate or output.is_relative_to(candidate) or candidate.is_relative_to(output):
        raise ValueError("Runtime bundle must be separate from frozen candidate artifacts")
    prepared = prepare_candidate(root, candidate)
    manifest = copy.deepcopy(prepared["source"])
    frozen = prepared["manifest"]
    publication_path = candidate / "publication_report.json"
    publication = json.loads(publication_path.read_text(encoding="utf-8"))
    verification = publication.get("verification") or {}
    baseline_counts = {"qdrant": manifest["artifacts"]["child_chunks"]["count"],
                       "mongo": manifest["artifacts"]["parent_docstore"]["count"]}
    if (publication.get("completed") is not True or publication.get("stage") != "complete"
            or publication.get("storage_targets") != frozen["storage_targets"]
            or publication.get("model") != frozen["embedding"]["model"]
            or verification.get("verified_vectors") != len(prepared["chunks"])
            or verification.get("verified_parents") != len(prepared["parents"])
            or verification.get("dimension") != frozen["embedding"]["dimension"]
            or verification.get("distance") != "Cosine"
            or any(verification.get(k) != 0 for k in ("payload_mismatches", "vector_mismatches", "parent_mismatches"))
            or publication.get("baseline_before") != baseline_counts
            or publication.get("baseline_after") != baseline_counts):
        raise ValueError("Candidate lacks a complete matching publication verification")
    # Permit the deploy script's copied baseline, never clobber another bundle.
    for relative in (MANIFEST_PATH, CONFIG_PATH):
        path = output / relative
        if path.exists() and path.read_bytes() != (root / relative).read_bytes():
            raise FileExistsError("Refuse to replace an existing runtime overlay")
    if (output / DESCRIPTIONS_PATH).exists() or (output / "candidate_runtime_bundle.json").exists():
        raise FileExistsError("Preserve the existing runtime bundle")
    sample_path = output / ".env.example"
    if sample_path.exists() and sample_path.read_bytes() != (root / ".env.example").read_bytes():
        raise FileExistsError("Refuse to replace a custom environment sample")

    manifest["storage_targets"] = frozen["storage_targets"]
    record = frozen["artifacts"]["table_descriptions"]
    manifest["artifacts"]["table_search_descriptions"] = {
        "path": DESCRIPTIONS_PATH, "sha256": record["sha256"], "count": record["count"]}
    contract = manifest["index_contract"]
    contract["indexed_artifacts"] = ["child_chunks", "table_search_descriptions"]
    contract["table_search"] = {
        "description_version": frozen["description_version"],
        "review_sha256": frozen["description_source"]["sha256"],
        "source_manifest_sha256": frozen["source_manifest_sha256"],
        "candidate_manifest_sha256": hashlib.sha256((candidate / "candidate_manifest.json").read_bytes()).hexdigest(),
        "publication_report_sha256": hashlib.sha256(publication_path.read_bytes()).hexdigest(),
    }
    config = copy.deepcopy(prepared["config"])
    config["retrieval"]["table_search"]["registry_path"] = manifest["artifacts"]["structured_tables"]["path"]
    release_env = {"QDRANT_COLLECTION_NAME": frozen["storage_targets"]["qdrant_collection"],
                   "STUDENT_RAG_HYBRID_COLLECTION": frozen["storage_targets"]["qdrant_collection"],
                   "MONGODB_PARENT_COLLECTION": frozen["storage_targets"]["mongo_parent_collection"],
                   "STUDENT_RAG_RETRIEVAL_CONFIG": CONFIG_PATH}
    writes = {MANIFEST_PATH: (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode(),
              CONFIG_PATH: yaml.safe_dump(config, allow_unicode=True, sort_keys=False).encode(),
              DESCRIPTIONS_PATH: Path(record["path"]).read_bytes()}
    # Keep every canonical source byte unchanged in the portable overlay.
    for source in manifest["artifacts"].values():
        if source["path"] == DESCRIPTIONS_PATH:
            continue
        if source["path"] not in {*RUNTIME_FILES, "data/processed/metadata/structured_table_embedding_audit.json"}:
            raise ValueError("Source artifact is outside the runtime allowlist")
        raw = (root / source["path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != source["sha256"]:
            raise ValueError("Source artifact changed before packaging")
        path = output / source["path"]
        if path.exists() and path.read_bytes() != raw:
            raise FileExistsError("Runtime source artifact differs from pinned baseline")
        writes[source["path"]] = raw
    # This sample is not .env and contains no secrets; repo sample stays unchanged.
    sample = (root / ".env.example").read_text(encoding="utf-8")
    lines = []
    seen = set()
    for line in sample.splitlines():
        name = line.split("=", 1)[0] if "=" in line and not line.startswith("#") else None
        if name in release_env:
            line = f"{name}={release_env[name]}"
            seen.add(name)
        lines.append(line)
    lines.extend(f"{name}={value}" for name, value in release_env.items() if name not in seen)
    writes[".env.example"] = ("\n".join(lines) + "\n").encode()
    for relative, raw in writes.items():
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    report = {"schema_version": "candidate-runtime-bundle-v1", "source_build_id": manifest["build_id"],
              "storage_targets": manifest["storage_targets"], "indexed_record_count": len(prepared["chunks"]),
              "narrative_child_count": manifest["artifacts"]["child_chunks"]["count"],
              "description_count": record["count"], "parent_count": len(prepared["parents"]),
              "release_env": release_env, "local_only": True, "remote_reverified": False,
              "model_calls": 0, "remote_writes": 0,
              "runtime_manifest_sha256": hashlib.sha256(writes[MANIFEST_PATH]).hexdigest(),
              "runtime_config_sha256": hashlib.sha256(writes[CONFIG_PATH]).hexdigest()}
    (output / "candidate_runtime_bundle.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_runtime_bundle(ROOT, args.candidate, args.output), ensure_ascii=False, indent=2))
