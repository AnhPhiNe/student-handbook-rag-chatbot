from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "student-handbook-build-v1"
EXPECTED_COHORTS = {"K48-K49", "K50", "K51"}
DEFAULT_PARENT_PATH = Path("data/processed/chunks/all_docstore_items.json")
DEFAULT_CHILD_PATH = Path("data/processed/chunks/child_parent_chunks.json")
DEFAULT_TABLE_PATH = Path("data/processed/tables/structured_tables_registry.json")
DEFAULT_GRAPH_PATH = Path("data/processed/graphs/document_edges.json")
DEFAULT_OUTPUT_PATH = Path("data/processed/metadata/build_manifest.json")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _without_build_id(value: Any) -> Any:
    if isinstance(value, list):
        return [_without_build_id(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _without_build_id(item)
            for key, item in value.items()
            if key != "build_id"
        }
    return value


def _load_json_array(path: Path) -> list[dict[str, Any]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, list) or not value:
        raise RuntimeError(f"Expected non-empty JSON array: {path}")
    if not all(isinstance(item, dict) for item in value):
        raise RuntimeError(f"Expected JSON objects in: {path}")
    return value


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _cohort_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(
        str(item.get("cohort") or (item.get("metadata") or {}).get("cohort") or "")
        for item in items
    )
    counts.pop("", None)
    return dict(sorted(counts.items()))


def _attach_build_id(
    parents: list[dict[str, Any]],
    children: list[dict[str, Any]],
    build_id: str,
) -> None:
    for parent in parents:
        parent["build_id"] = build_id
        metadata = parent.setdefault("metadata", {})
        if not isinstance(metadata, dict):
            raise RuntimeError(f"Invalid parent metadata: {parent.get('_id')}")
        metadata["build_id"] = build_id
    for child in children:
        metadata = child.setdefault("metadata", {})
        if not isinstance(metadata, dict):
            raise RuntimeError(f"Invalid child metadata: {child.get('_id')}")
        metadata["build_id"] = build_id


def build_artifact_manifest(
    *,
    pdf_paths: list[Path],
    parent_path: Path = DEFAULT_PARENT_PATH,
    child_path: Path = DEFAULT_CHILD_PATH,
    table_path: Path = DEFAULT_TABLE_PATH,
    graph_path: Path = DEFAULT_GRAPH_PATH,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    qdrant_collection: str,
    mongo_collection: str,
    embedding_model: str = "BAAI/bge-m3",
    embedding_dimension: int = 1024,
) -> dict[str, Any]:
    qdrant_collection = qdrant_collection.strip()
    mongo_collection = mongo_collection.strip()
    if not qdrant_collection or not mongo_collection:
        raise RuntimeError("Both target collection names must be explicit.")
    if embedding_dimension <= 0:
        raise RuntimeError("Embedding dimension must be positive.")
    if len(pdf_paths) != 3:
        raise RuntimeError(
            f"Expected exactly three handbook PDFs, received {len(pdf_paths)}."
        )

    required_paths = [*pdf_paths, parent_path, child_path, table_path, graph_path]
    missing = [str(path) for path in required_paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing build inputs: " + ", ".join(missing))

    parents = _load_json_array(parent_path)
    children = _load_json_array(child_path)
    tables = _load_json_array(table_path)
    graph_edges = _load_json_array(graph_path)

    parent_id_list = [str(parent.get("_id") or "") for parent in parents]
    child_id_list = [
        str(child.get("_id") or child.get("chunk_id") or "")
        for child in children
    ]
    parent_ids = set(parent_id_list)
    child_parent_ids = {
        str((child.get("metadata") or {}).get("parent_section_id") or "")
        for child in children
    }
    if "" in parent_ids or "" in child_parent_ids or "" in child_id_list:
        raise RuntimeError("Parent, child, and linkage identifiers must be non-empty.")
    if len(parent_ids) != len(parent_id_list):
        raise RuntimeError("Parent document ids must be unique.")
    if len(set(child_id_list)) != len(child_id_list):
        raise RuntimeError("Child chunk ids must be unique.")
    if child_parent_ids - parent_ids:
        raise RuntimeError(
            "Child-parent build contains orphan parent ids: "
            + ", ".join(sorted(child_parent_ids - parent_ids)[:10])
        )
    parent_cohorts = set(_cohort_counts(parents))
    child_cohorts = set(_cohort_counts(children))
    if parent_cohorts != EXPECTED_COHORTS or child_cohorts != EXPECTED_COHORTS:
        raise RuntimeError(
            "Parent and child artifacts must both contain exactly K48-K49, K50, K51. "
            f"Parents={sorted(parent_cohorts)}, children={sorted(child_cohorts)}"
        )

    source_pdf_hashes = {
        path.name: sha256_file(path) for path in sorted(pdf_paths, key=lambda item: item.name)
    }
    identity_inputs = {
        "schema_version": SCHEMA_VERSION,
        "source_pdfs": source_pdf_hashes,
        "artifacts_without_build_id": {
            "parent_docstore": _canonical_digest(_without_build_id(parents)),
            "child_chunks": _canonical_digest(_without_build_id(children)),
            "structured_tables": _canonical_digest(tables),
            "graph_edges": _canonical_digest(graph_edges),
        },
        "embedding": {
            "model": embedding_model,
            "dimension": embedding_dimension,
            "normalize_embeddings": True,
        },
    }
    build_id = "build-" + _canonical_digest(identity_inputs)[:20]
    _attach_build_id(parents, children, build_id)
    _write_json_atomic(parent_path, parents)
    _write_json_atomic(child_path, children)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "build_id": build_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_pdfs": source_pdf_hashes,
        "artifacts": {
            "parent_docstore": {
                "path": str(parent_path),
                "sha256": sha256_file(parent_path),
                "count": len(parents),
                "cohort_counts": _cohort_counts(parents),
            },
            "child_chunks": {
                "path": str(child_path),
                "sha256": sha256_file(child_path),
                "count": len(children),
                "cohort_counts": _cohort_counts(children),
            },
            "structured_tables": {
                "path": str(table_path),
                "sha256": sha256_file(table_path),
                "count": len(tables),
                "cohort_counts": _cohort_counts(tables),
            },
            "graph_edges": {
                "path": str(graph_path),
                "sha256": sha256_file(graph_path),
                "count": len(graph_edges),
                "cohort_counts": _cohort_counts(graph_edges),
            },
        },
        "embedding": identity_inputs["embedding"],
        "storage_targets": {
            "qdrant_collection": qdrant_collection,
            "mongo_parent_collection": mongo_collection,
        },
        "index_contract": {
            "embedding_input": str(child_path),
            "parent_input": str(parent_path),
            "structured_json_indexed_in_qdrant": False,
        },
    }
    _write_json_atomic(output_path, manifest)
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Attach one deterministic build id and write the artifact manifest."
    )
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--parent-path", type=Path, default=DEFAULT_PARENT_PATH)
    parser.add_argument("--child-path", type=Path, default=DEFAULT_CHILD_PATH)
    parser.add_argument("--table-path", type=Path, default=DEFAULT_TABLE_PATH)
    parser.add_argument("--graph-path", type=Path, default=DEFAULT_GRAPH_PATH)
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument(
        "--qdrant-collection",
        default=os.environ.get("QDRANT_COLLECTION_NAME"),
    )
    parser.add_argument(
        "--mongo-collection",
        default=os.environ.get("MONGODB_PARENT_COLLECTION"),
    )
    parser.add_argument(
        "--embedding-model",
        default=os.environ.get("STUDENT_RAG_EMBEDDING_MODEL", "BAAI/bge-m3"),
    )
    parser.add_argument(
        "--embedding-dimension",
        type=int,
        default=int(os.environ.get("STUDENT_RAG_EMBEDDING_DIMENSION", "1024")),
    )
    args = parser.parse_args()
    if not args.qdrant_collection or not args.mongo_collection:
        parser.error(
            "--qdrant-collection and --mongo-collection are required "
            "(or set their matching environment variables)."
        )
    return args


def main() -> None:
    args = parse_args()
    pdf_paths = sorted(args.raw_dir.glob("*.pdf"))
    if not pdf_paths:
        raise RuntimeError(f"No source PDFs found in {args.raw_dir}")
    manifest = build_artifact_manifest(
        pdf_paths=pdf_paths,
        parent_path=args.parent_path,
        child_path=args.child_path,
        table_path=args.table_path,
        graph_path=args.graph_path,
        output_path=args.output_path,
        qdrant_collection=args.qdrant_collection,
        mongo_collection=args.mongo_collection,
        embedding_model=args.embedding_model,
        embedding_dimension=args.embedding_dimension,
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
