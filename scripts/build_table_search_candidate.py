"""Build separate table-description experiment artifacts; no embeddings/uploads."""
import argparse
import hashlib
import json
from pathlib import Path

import yaml

from src.retrieval.core.table_search import VERSION, build_table_descriptions

ROOT = Path(__file__).resolve().parents[1]


def assert_separate_output(root: Path, output: Path) -> None:
    """Reject canonical/source/report destinations, including other checkouts."""
    output = output.resolve()
    protected = {"data", "configs", "src", "tests", "docs", ".git"}
    if output == root.resolve() or protected.intersection(part.casefold() for part in output.parts) or output.name.casefold() == "readme.md":
        raise ValueError("Candidate output must be separate from protected source/evaluation files")


def build_candidate(root: Path, output: Path) -> dict:
    root, output = root.resolve(), output.resolve()
    assert_separate_output(root, output)
    source_path = root / "data/processed/metadata/build_manifest.json"
    manifest = json.loads(source_path.read_text(encoding="utf-8"))
    loaded = {}
    for name in ("parent_docstore", "child_chunks", "structured_tables"):
        record = manifest["artifacts"][name]
        raw = (root / record["path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != record["sha256"]:
            raise ValueError("Baseline artifact hash mismatch")
        loaded[name] = json.loads(raw)
    handles = build_table_descriptions(loaded["structured_tables"], loaded["parent_docstore"])
    identity = hashlib.sha256((source_path.read_text(encoding="utf-8") + VERSION).encode()).hexdigest()[:12]
    output.mkdir(parents=True, exist_ok=True)
    artifacts = {}
    for name, data in (("table_descriptions", handles), ("child_chunks", loaded["child_chunks"] + handles)):
        path = output / f"{name}.json"
        raw = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode()
        path.write_bytes(raw)
        artifacts[name] = {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "count": len(data)}
    collection = f"student_handbook_table_search_{identity}"
    config = yaml.safe_load((root / "configs/retrieval.yaml").read_text(encoding="utf-8"))
    source_registry = manifest["artifacts"]["structured_tables"]
    config["retrieval"]["table_search"] = {"collection_name": collection,
        "baseline_collection": manifest["storage_targets"]["qdrant_collection"],
        "registry_path": str(root / source_registry["path"]), "registry_sha256": source_registry["sha256"]}
    (output / "retrieval.yaml").write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    report = {"schema_version": "table-search-candidate-v1", "source_build_id": manifest["build_id"],
              "source_manifest_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
              "description_version": VERSION, "artifacts": artifacts, "embedding": manifest["embedding"],
              "storage_targets": {"qdrant_collection": collection, "mongo_parent_collection": f"parent_docs_table_search_{identity}"},
              "parent_source": manifest["artifacts"]["parent_docstore"], "model_calls": 0,
              "requires_separate_publish_approval": True, "embedding_created": False}
    (output / "candidate_manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build_candidate(ROOT, args.output), ensure_ascii=False, indent=2))
