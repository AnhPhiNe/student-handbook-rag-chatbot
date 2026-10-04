"""Re-embed a frozen candidate into NEW stores; never activate production."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import threading
import time
from collections import Counter
from pathlib import Path

import numpy as np
import requests
import yaml
from dotenv import load_dotenv
from pymongo import MongoClient
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from tqdm import tqdm

from scripts.build_table_search_candidate import ROOT, apply_reviewed_descriptions, assert_separate_output
from scripts.push_to_qdrant import create_payload_indexes, string_to_uuid
from src.retrieval.core.embedding_model import EmbeddingClient
from src.retrieval.core.table_search import build_table_descriptions


def prepare_candidate(root: Path, directory: Path) -> dict:
    """Check bytes, full corpus equality and namespace before any paid request."""
    root, directory = root.resolve(), directory.resolve()
    assert_separate_output(root, directory)
    candidate = json.loads((directory / "candidate_manifest.json").read_text(encoding="utf-8"))
    source_path = root / "data/processed/metadata/build_manifest.json"
    source_raw = source_path.read_bytes()
    source = json.loads(source_raw)
    if (candidate.get("schema_version") != "table-search-candidate-v1"
            or candidate.get("source_manifest_sha256") != hashlib.sha256(source_raw).hexdigest()
            or candidate.get("source_build_id") != source["build_id"]):
        raise ValueError("Candidate source manifest mismatch")
    loaded = {}
    for name in ("child_chunks", "parent_docstore", "structured_tables"):
        record = source["artifacts"][name]
        raw = (root / record["path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != record["sha256"]:
            raise ValueError("Source artifact mismatch")
        loaded[name] = json.loads(raw)
    handles = build_table_descriptions(loaded["structured_tables"], loaded["parent_docstore"])
    review = candidate["description_source"]
    handles, frozen = apply_reviewed_descriptions(handles, Path(review["path"]),
        {name: source["artifacts"][name]["sha256"] for name in ("structured_tables", "parent_docstore")})
    if frozen != review or candidate["description_version"] != frozen["version"]:
        raise ValueError("Frozen description source mismatch")
    identity = hashlib.sha256((source_path.read_text(encoding="utf-8") + frozen["version"] + frozen["sha256"]).encode()).hexdigest()[:12]
    targets = {"qdrant_collection": f"student_handbook_table_search_{identity}",
               "mongo_parent_collection": f"parent_docs_table_search_{identity}"}
    if candidate["storage_targets"] != targets or candidate["parent_source"] != source["artifacts"]["parent_docstore"]:
        raise ValueError("Candidate storage targets or parent source mismatch")
    for name, expected in (("table_descriptions", handles), ("child_chunks", loaded["child_chunks"] + handles)):
        record = candidate["artifacts"][name]
        path = Path(record["path"]).resolve()
        if path.parent != directory or path.name != f"{name}.json":
            raise ValueError("Candidate artifact must belong to its directory")
        raw = path.read_bytes()
        if (hashlib.sha256(raw).hexdigest() != record["sha256"]
                or json.loads(raw) != expected or record["count"] != len(expected)):
            raise ValueError("Candidate artifact mismatch")
    chunks, parents = loaded["child_chunks"] + handles, loaded["parent_docstore"]
    if len({c["_id"] for c in chunks}) != len(chunks) or len({p["_id"] for p in parents}) != len(parents):
        raise ValueError("Duplicate corpus identity")
    config = yaml.safe_load((directory / "retrieval.yaml").read_text(encoding="utf-8"))
    baseline_config = yaml.safe_load((root / "configs/retrieval.yaml").read_text(encoding="utf-8"))
    baseline_config["retrieval"]["table_search"] = config["retrieval"]["table_search"]
    if config != baseline_config:
        raise ValueError("Candidate provider/runtime configuration differs from source")
    embedding = config["embedding"]
    if (candidate["embedding"] != source["embedding"] or embedding["model_name"] != source["embedding"]["model"]
            or embedding["dimension"] != source["embedding"]["dimension"]
            or embedding["normalize_embeddings"] != source["embedding"]["normalize_embeddings"]):
        raise ValueError("Candidate embedding contract mismatch")
    table_search = config["retrieval"]["table_search"]
    if (table_search["collection_name"] != targets["qdrant_collection"]
            or table_search["baseline_collection"] != source["storage_targets"]["qdrant_collection"]
            # The candidate may have been built in another checkout: the registry
            # must be the same repository file, pinned by its hash below.
            or not Path(table_search["registry_path"]).as_posix().endswith(
                "/" + Path(source["artifacts"]["structured_tables"]["path"]).as_posix())
            or table_search["registry_sha256"] != source["artifacts"]["structured_tables"]["sha256"]):
        raise ValueError("Candidate retrieval contract mismatch")
    return {"manifest": candidate, "source": source, "chunks": chunks, "parents": parents,
            "config": config, "directory": directory}


def ensure_new_targets(prepared: dict, qdrant, database) -> None:
    targets = prepared["manifest"]["storage_targets"]
    if qdrant.collection_exists(targets["qdrant_collection"]):
        raise FileExistsError("Qdrant candidate already exists; no overwrite permitted")
    if targets["mongo_parent_collection"] in database.list_collection_names():
        raise FileExistsError("MongoDB candidate already exists; no overwrite permitted")


def validate_vectors(vectors, count: int, dimension: int) -> np.ndarray:
    array = np.asarray(vectors, dtype=np.float32)
    if array.shape != (count, dimension) or not np.isfinite(array).all():
        raise ValueError("Invalid embedding count, dimension or nonfinite vector")
    if not np.allclose(np.linalg.norm(array, axis=1), 1.0, atol=1e-4, rtol=0):
        raise ValueError("Vectors must be nonzero and normalized")
    return array


def baseline_counts(prepared: dict, qdrant, database) -> dict:
    targets = prepared["source"]["storage_targets"]
    return {"qdrant": qdrant.count(targets["qdrant_collection"], exact=True).count,
            "mongo": database[targets["mongo_parent_collection"]].count_documents({})}


def verify_stores(prepared: dict, qdrant, database, vectors: np.ndarray) -> dict:
    targets = prepared["manifest"]["storage_targets"]
    expected = {string_to_uuid(c["_id"]): (i, {**c["metadata"], "chunk_id": c["_id"], "content": c["content"]})
                for i, c in enumerate(prepared["chunks"])}
    seen, offset = set(), None
    with tqdm(total=len(expected), desc="Verify Qdrant", unit="vector") as progress:
        while True:
            records, offset = qdrant.scroll(targets["qdrant_collection"], limit=64, offset=offset,
                                            with_payload=True, with_vectors=True)
            for point in records:
                key = str(point.id)
                if key not in expected or key in seen:
                    raise ValueError("Unexpected/duplicate remote point")
                index, payload = expected[key]
                if point.payload != payload:
                    raise ValueError("Remote payload mismatch")
                remote = validate_vectors([point.vector], 1, vectors.shape[1])[0]
                if not np.allclose(remote, vectors[index], atol=2e-6, rtol=0):
                    raise ValueError("Remote vector mismatch")
                seen.add(key)
            progress.update(len(records))
            if offset is None:
                break
    if seen != set(expected):
        raise ValueError("Missing remote points")
    parents = {p["_id"]: p for p in prepared["parents"]}
    actual = {p["_id"]: p for p in database[targets["mongo_parent_collection"]].find({})}
    if actual != parents:
        raise ValueError("Remote parent data mismatch")
    info = qdrant.get_collection(targets["qdrant_collection"])
    config = info.config.params.vectors
    if config.size != vectors.shape[1] or config.distance != Distance.COSINE:
        raise ValueError("Remote vector configuration mismatch")
    return {"verified_vectors": len(seen), "verified_parents": len(actual),
            "payload_mismatches": 0, "vector_mismatches": 0, "parent_mismatches": 0,
            "dimension": vectors.shape[1], "distance": "Cosine",
            "chunk_cohorts": dict(Counter(c["metadata"]["cohort"] for c in prepared["chunks"]))}


def publish_candidate(prepared: dict, qdrant, database, embedder, report: dict) -> dict:
    """One publish operation: preflight → embeddings → new stores → exact verification."""
    directory = prepared["directory"]
    vector_path = directory / "embeddings_full.npy"
    if vector_path.exists():
        raise FileExistsError("Saved vectors already exist; preserve them and do not pay twice")
    report["stage"] = "preflight"
    ensure_new_targets(prepared, qdrant, database)
    before = baseline_counts(prepared, qdrant, database)
    report["baseline_before"] = before
    report["stage"] = "embedding"
    started = time.perf_counter()
    vectors = validate_vectors(embedder.embed_documents([c["content"] for c in prepared["chunks"]]),
        len(prepared["chunks"]), prepared["manifest"]["embedding"]["dimension"])
    report["embedding_seconds"] = time.perf_counter() - started
    with vector_path.open("xb") as stream:
        np.save(stream, vectors, allow_pickle=False)
    report["vector_artifact"] = {"path": str(vector_path), "sha256": hashlib.sha256(vector_path.read_bytes()).hexdigest(),
                                 "shape": list(vectors.shape)}
    # Recheck after paid work; concurrent writers cannot authorize an overwrite.
    report["stage"] = "target_recheck"
    ensure_new_targets(prepared, qdrant, database)
    targets = prepared["manifest"]["storage_targets"]
    report["stage"] = "creating_collections"
    qdrant.create_collection(targets["qdrant_collection"],
        vectors_config=VectorParams(size=vectors.shape[1], distance=Distance.COSINE))
    create_payload_indexes(qdrant, targets["qdrant_collection"])
    collection = database.create_collection(targets["mongo_parent_collection"])
    report["stage"] = "uploading"
    for start in tqdm(range(0, len(prepared["parents"]), 100), desc="Upload MongoDB"):
        collection.insert_many(prepared["parents"][start:start + 100], ordered=True)
    for start in tqdm(range(0, len(prepared["chunks"]), 64), desc="Upload Qdrant"):
        points = [PointStruct(id=string_to_uuid(c["_id"]), vector=vectors[i].tolist(),
                              payload={**c["metadata"], "chunk_id": c["_id"], "content": c["content"]})
                  for i, c in enumerate(prepared["chunks"][start:start + 64], start)]
        qdrant.upsert(targets["qdrant_collection"], points=points, wait=True)
    report["stage"] = "verification"
    report["verification"] = verify_stores(prepared, qdrant, database, vectors)
    after = baseline_counts(prepared, qdrant, database)
    report["baseline_after"] = after
    if before != after:
        raise ValueError("Baseline counts changed during experiment")
    report.update(stage="complete", completed=True, production_activated=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=32)
    args = parser.parse_args()
    if not 1 <= args.workers <= 64:
        raise ValueError("Workers must be between 1 and 64")
    prepared = prepare_candidate(ROOT, args.candidate)
    path = prepared["directory"] / "publication_report.json"
    if path.exists():
        raise FileExistsError("Preserve existing publication report")
    load_dotenv(args.env_file, override=False)
    report = {"completed": False, "embedding_policy": {"mode": "reembed_all", "batch_size": 64,
        "workers": args.workers, "retry_per_batch": 1}, "requested_embedding_inputs": len(prepared["chunks"]),
        "storage_targets": prepared["manifest"]["storage_targets"], "api_requests": 0, "embedding_input_tokens": 0,
        "model": prepared["manifest"]["embedding"]["model"], "production_activated": False}
    lock = threading.Lock()
    completed_inputs = 0
    def counted_post(*positional, **kwargs):
        nonlocal completed_inputs
        with lock:
            report["api_requests"] += 1
        response = requests.post(*positional, **kwargs)
        if response.ok:
            body = response.json()
            with lock:
                report["embedding_input_tokens"] += int((body.get("usage") or {}).get("prompt_tokens") or 0)
                completed_inputs += len(kwargs["json"]["input"])
                if completed_inputs % 512 == 0 or completed_inputs >= len(prepared["chunks"]):
                    print(f"Embedding API returned {completed_inputs}/{len(prepared['chunks'])} inputs", flush=True)
        return response
    embedding_config = {**prepared["config"]["embedding"], "document_batch_size": 64,
                        "document_concurrency": args.workers, "document_retries": 1}
    qdrant, mongo = None, None
    report["stage"] = "initializing_clients"
    try:
        embedder = EmbeddingClient(embedding_config, post=counted_post)
        qdrant = QdrantClient(url=os.environ["QDRANT_URL"], api_key=os.environ["QDRANT_API_KEY"],
                              timeout=90, check_compatibility=False)
        mongo = MongoClient(os.environ["MONGODB_URL"], serverSelectionTimeoutMS=30000,
                            connectTimeoutMS=30000, socketTimeoutMS=30000)
        db = mongo[os.environ.get("MONGODB_DB_NAME") or "chatbotHCMUE"]
        publish_candidate(prepared, qdrant, db, embedder, report)
    except Exception as exc:
        report.update(error_type=type(exc).__name__, details="Connection/credential values omitted")
    finally:
        if qdrant is not None:
            qdrant.close()
        if mongo is not None:
            mongo.close()
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["completed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
