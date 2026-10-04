"""Compare chunkings offline with the production retriever (no remote writes).

Each variant is a set of search chunks embedded with BGE-M3 (DeepInfra) into an
in-memory Qdrant collection; BM25, RRF, the Voyage reranker, the cohort filter
and the parent grouping are the production classes, and parents come from the
local docstore (the same documents MongoDB holds). Scores use the official_v1
retrieval metrics (hit@k, MRR, nDCG, primary hit@5).

    python -m scripts.eval_chunking_offline --variants current,clause_docart --cases data/eval/official_v1/retrieval_cases.json --out <dir>

Variants:
  current            the published v35 children (child_parent_chunks.json), as served today
  clause_docart      one khoản per chunk, "document › Điều" line, scope applied
  clause_article     same, "Điều" line only
  clause_chapter     same, "document › chapter › Điều" line
  point_docart       one point per chunk carrying its lead-in, "document › Điều" line
Suffixes: "+titles" keeps the BM25 title fields, "+nocap" removes the per-article cap.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np

CACHE = Path("data/eval/reports/chunking_offline_embeddings")
CAP = 3


class LocalParents:
    def __init__(self, parents: list[dict[str, Any]]):
        self.by_id = {p["_id"]: p for p in parents}

    def get_document_by_id(self, parent_id: str) -> dict[str, Any] | None:
        return self.by_id.get(parent_id)


def variant_chunks(name: str, parents: list[dict[str, Any]], tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from scripts.structure_chunking import build_structure_chunks, load_config, load_scope

    base = name.split("+")[0]
    if base == "current":
        chunks = json.loads(Path("data/processed/chunks/child_parent_chunks.json").read_text(encoding="utf-8"))
        return [{**c, "embedding_text": c["content"]} for c in chunks]
    header, unit = {
        "clause_docart": ("document_article", "clause"),
        "clause_article": ("article", "clause"),
        "clause_chapter": ("document_chapter_article", "clause"),
        "point_docart": ("document_article", "point"),
    }[base]
    return build_structure_chunks(parents, config=load_config(), scope=load_scope(), header_mode=header,
                                  unit_mode=unit, structured_tables=tables)


def embed(texts: list[str], embedder) -> np.ndarray:
    """Embed with a content-addressed cache, so variants sharing texts embed them once."""
    CACHE.mkdir(parents=True, exist_ok=True)
    keys = [hashlib.sha256(t.encode("utf-8")).hexdigest() for t in texts]
    missing = sorted({(k, t) for k, t in zip(keys, texts) if not (CACHE / f"{k}.npy").exists()})
    for start in range(0, len(missing), 256):
        batch = missing[start:start + 256]
        vectors = embedder.embed_documents([t for _, t in batch])
        for (k, _), v in zip(batch, vectors):
            np.save(CACHE / f"{k}.npy", np.asarray(v, dtype=np.float32))
    return np.stack([np.load(CACHE / f"{k}.npy") for k in keys])


def build_retriever(chunks: list[dict[str, Any]], vectors: np.ndarray, parents, *, title_fields: bool, cap: int):
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    from src.retrieval.core import hybrid_pipeline as hp
    from src.retrieval.core.bm25_retriever import BM25Retriever
    from src.retrieval.core.embedding_model import load_embedding_client
    from src.retrieval.core.graph_traverser import NetworkXGraphTraverser
    from src.retrieval.core.reranker import Reranker
    from src.retrieval.runtime_config import load_retrieval_runtime_config

    config = load_retrieval_runtime_config()
    client = QdrantClient(":memory:")
    client.create_collection("variant", vectors_config=VectorParams(size=vectors.shape[1], distance=Distance.COSINE))
    points = []
    for chunk, vector in zip(chunks, vectors):
        payload = {**(chunk.get("metadata") or {}), "chunk_id": chunk["chunk_id"], "content": chunk["content"]}
        points.append(PointStruct(id=str(uuid.uuid5(uuid.NAMESPACE_URL, chunk["chunk_id"])), vector=vector.tolist(), payload=payload))
    for start in range(0, len(points), 512):
        client.upsert("variant", points[start:start + 512])

    r = object.__new__(hp.ChildParentHybridRetriever)
    r.runtime_config = config
    r.candidate_children = int((config.get("retrieval") or {}).get("candidate_children", 24))
    r.max_children_per_parent = cap
    r.table_search_tables = {}
    r.qdrant_client = client
    r.collection_name = "variant"
    r.embedder = load_embedding_client(config.get("embedding") or {})
    r.graph = NetworkXGraphTraverser()
    r.reranker = Reranker.from_runtime_config(config)
    r.mongo_store = LocalParents(parents)
    r.parent_cache_max_entries = 4096
    r.parent_cache = OrderedDict()
    r.bm25 = BM25Retriever()
    r.bm25.title_fields = title_fields
    r.bm25.build_bm25_index([{**c, "metadata": {**(c.get("metadata") or {}), "chunk_id": c["chunk_id"]}} for c in chunks])
    hp.set_bm25_runtime_status("ready", attempts=1)
    hp._GLOBAL_RETRIEVER = r
    return r


class ThrottledReranker:
    """Space reranker calls to stay under Voyage's per-minute token limit."""

    def __init__(self, inner, min_interval: float):
        self.inner, self.min_interval, self.last = inner, min_interval, 0.0
        self.fallbacks: list[str] = []

    def rerank(self, query, scored):
        wait = self.min_interval - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()
        ranked, telemetry = self.inner.rerank(query, scored)
        if telemetry.get("reranker_fallback_reason"):
            self.fallbacks.append(str(telemetry["reranker_fallback_reason"]))
        return ranked, telemetry

    def __getattr__(self, name):
        return getattr(self.inner, name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--variants", required=True)
    parser.add_argument("--cases", action="append", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--rerank-interval", type=float, default=2.0)
    args = parser.parse_args()

    from src.evaluation.retrieval import evaluate_retrieval
    from src.retrieval.core.embedding_model import load_embedding_client
    from src.retrieval.runtime_config import load_retrieval_runtime_config

    parents = json.loads(Path("data/processed/chunks/all_docstore_items.json").read_text(encoding="utf-8"))
    tables = json.loads(Path("data/processed/tables/structured_tables_registry.json").read_text(encoding="utf-8"))
    cases = [case for path in args.cases for case in json.loads(Path(path).read_text(encoding="utf-8"))]
    embedder = load_embedding_client(load_retrieval_runtime_config().get("embedding") or {})
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    summary = {}
    for name in args.variants.split(","):
        chunks = variant_chunks(name, parents, tables)
        vectors = embed([c["embedding_text"] for c in chunks], embedder)
        current = name.startswith("current")
        title_fields = current or "+titles" in name
        cap = 0 if (current or "+nocap" in name) else CAP
        retriever = build_retriever(chunks, vectors, parents, title_fields=title_fields, cap=cap)
        throttled = ThrottledReranker(retriever.reranker, args.rerank_interval)
        retriever.reranker = throttled
        report = evaluate_retrieval(cases, backend="qdrant", scope="pure")
        report["variant"] = {"name": name, "chunks": len(chunks), "bm25_title_fields": title_fields,
                             "max_children_per_parent": cap, "reranker_fallbacks": throttled.fallbacks}
        (out / f"{name.replace('+', '_')}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        rows = report["cases"]  # per-case metrics from the official_v1 scorer, every split
        summary[name] = {k: round(sum(float(r.get(k) or 0) for r in rows) / len(rows), 4)
                         for k in ("hit_at_1", "hit_at_5", "mrr", "ndcg_at_5", "primary_hit_at_5")}
        summary[name]["n"] = len(rows)
        summary[name]["fallbacks"] = len(throttled.fallbacks)
        print(name, json.dumps(summary[name]), flush=True)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    os.environ.setdefault("STUDENT_RAG_DISABLE_REDIS", "1")
    main()
