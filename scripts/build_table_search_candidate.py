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


def apply_reviewed_descriptions(handles: list[dict], path: Path, source_hashes: dict) -> tuple[list[dict], dict]:
    """Override search text only, with exact coverage and pinned source artifacts."""
    raw = path.read_bytes()
    review = yaml.safe_load(raw)
    if not isinstance(review, dict) or set(review) != {"schema_version", "description_version", "source_hashes", "descriptions"}:
        raise ValueError("Invalid reviewed-description document")
    if review["schema_version"] != "table-search-reviewed-text-v1" or review["source_hashes"] != source_hashes:
        raise ValueError("Reviewed descriptions require the exact source tables and parents")
    version = review["description_version"]
    if not isinstance(version, str) or not version.startswith("table-description-reviewed-"):
        raise ValueError("Reviewed descriptions require a separate version")
    records = review["descriptions"]
    if not isinstance(records, list):
        raise ValueError("Reviewed descriptions must be a list")
    texts = {}
    for record in records:
        if not isinstance(record, dict) or set(record) != {"key", "content"}:
            raise ValueError("Reviewed records may supply only identity and text, not metadata")
        key, content = record["key"], record["content"]
        if not isinstance(key, str) or key in texts:
            raise ValueError("Duplicate or invalid reviewed table identity")
        if not isinstance(content, str) or not content.strip() or len(content) > 1600:
            raise ValueError("Reviewed search text must be nonempty and at most 1600 characters")
        texts[key] = content.strip()
    if set(texts) != {h["metadata"]["table_search_key"] for h in handles}:
        raise ValueError("Reviewed descriptions must cover every approved table exactly once")
    updated = [{**h, "content": texts[h["metadata"]["table_search_key"]],
                "metadata": {**h["metadata"], "description_version": version}} for h in handles]
    return updated, {"path": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(), "version": version}


def build_candidate(root: Path, output: Path, descriptions_path: Path | None = None) -> dict:
    root, output = root.resolve(), output.resolve()
    assert_separate_output(root, output)
    generated_names = ("table_descriptions.json", "child_chunks.json", "retrieval.yaml", "candidate_manifest.json")
    if any((output / name).exists() for name in generated_names):
        raise FileExistsError("Preserve existing candidate artifacts; choose a new output directory")
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
    description_source = None
    version = VERSION
    identity_input = source_path.read_text(encoding="utf-8") + version
    if descriptions_path is not None:
        source_hashes = {name: manifest["artifacts"][name]["sha256"] for name in ("structured_tables", "parent_docstore")}
        handles, description_source = apply_reviewed_descriptions(handles, descriptions_path, source_hashes)
        version = description_source["version"]
        identity_input = source_path.read_text(encoding="utf-8") + version + description_source["sha256"]
    identity = hashlib.sha256(identity_input.encode()).hexdigest()[:12]
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
              "description_version": version, "artifacts": artifacts, "embedding": manifest["embedding"],
              "storage_targets": {"qdrant_collection": collection, "mongo_parent_collection": f"parent_docs_table_search_{identity}"},
              "parent_source": manifest["artifacts"]["parent_docstore"], "model_calls": 0,
              "requires_separate_publish_approval": True, "embedding_created": False}
    if description_source is not None:
        report["description_source"] = description_source
    (output / "candidate_manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--descriptions", type=Path, help="Optional frozen source-reviewed search text; default keeps metadata v1")
    args = parser.parse_args()
    print(json.dumps(build_candidate(ROOT, args.output, args.descriptions), ensure_ascii=False, indent=2))
