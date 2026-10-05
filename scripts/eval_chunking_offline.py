"""Compare chunkings offline with the production retriever (no remote writes).

Each variant is a set of search chunks embedded with BGE-M3 (DeepInfra) into an
in-memory Qdrant collection; BM25, RRF, the Voyage reranker, the cohort filter
and the parent grouping are the production classes, and parents come from the
local docstore (the same documents MongoDB holds). Scores use the official_v1
retrieval metrics (hit@k, MRR, nDCG, primary hit@5).

    python -m scripts.eval_chunking_offline --variants baseline,clause \
        --baseline-chunks <published child_chunks.json> --cases data/eval/official_v1/retrieval_cases.json --out <dir>

Variants:
  baseline  a published chunk file, embedded as published (table-search
            descriptions left out, as the clause variant has none)
  clause    the structure chunks exactly as scripts.structure_chunking publishes
            them: one khoản per chunk, scope applied, reviewed tables separated
  clause_all  the same with nothing excluded (vừa làm vừa học, cao đẳng and
            staff-only content kept)

Earlier variants (a "document › Điều" or "Điều" line, one point per chunk, a cap
per article, BM25 without titles, splitting long khoản at 1,200 or 2,500
characters or by topic) were measured on 2026-10-04 and 2026-10-05 and removed;
the results are in docs/DESIGN_DECISIONS.md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np

CACHE = Path("data/eval/reports/chunking_offline_embeddings")


class LocalParents:
    def __init__(self, parents: list[dict[str, Any]]):
        self.by_id = {p["_id"]: p for p in parents}

    def get_document_by_id(self, parent_id: str) -> dict[str, Any] | None:
        return self.by_id.get(parent_id)


def variant_chunks(name: str, parents: list[dict[str, Any]], baseline: str | None = None) -> list[dict[str, Any]]:
    from scripts.build_parent_child_artifacts import REGIONS
    from scripts.structure_chunking import build_structure_chunks, load_config, load_scope

    if name == "baseline":
        if not baseline:
            raise ValueError("--baseline-chunks is required for the baseline variant")
        chunks = json.loads(Path(baseline).read_text(encoding="utf-8"))
        return [{**c, "embedding_text": c["content"]} for c in chunks
                if (c.get("metadata") or {}).get("chunk_granularity") != "table_description"]
    if name in ("clause", "clause_all", "clause_nostaff"):
        # clause_all: nothing excluded by configs/corpus_scope.yaml; clause_nostaff:
        # the staff-only code-of-conduct articles kept, vừa làm vừa học and cao đẳng still excluded.
        reviewed = {e["parent_id"] for e in json.loads(REGIONS.read_text(encoding="utf-8"))["parents"]}
        scope = load_scope() if name != "clause_all" else {}
        if name == "clause_nostaff":
            scope = {**scope, "exclude_parents": [r for r in scope.get("exclude_parents") or []
                                                  if "QuyDinhQuyTacUngXu" not in r["id"]]}
        return build_structure_chunks(parents, config=load_config(), scope=scope, drop_table_parents=reviewed)
    raise ValueError(f"Unknown variant: {name}")


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


def build_retriever(chunks: list[dict[str, Any]], vectors: np.ndarray, parents):
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
    r.bm25.build_bm25_index([{**c, "metadata": {**(c.get("metadata") or {}), "chunk_id": c["chunk_id"]}} for c in chunks])
    hp.set_bm25_runtime_status("ready", attempts=1)
    hp._GLOBAL_RETRIEVER = r
    return r


class ThrottledReranker:
    """Space reranker calls, and retry a call Voyage refused for its rate limit.

    Production skips the reranker on a 429 so a student does not wait; an
    evaluation must not, or a busy minute lowers a variant's score. A 429 is
    retried after 5, 10, 20, 30 and 30 s; only a call that still fails counts.
    """

    BACKOFF = (5, 10, 20, 30, 30)

    def __init__(self, inner, min_interval: float):
        self.inner, self.min_interval, self.last = inner, min_interval, 0.0
        self.fallbacks: list[str] = []
        self.retries = 0

    def rerank(self, query, scored):
        wait = self.min_interval - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()
        ranked, telemetry = self.inner.rerank(query, scored)
        for pause in self.BACKOFF:
            if "429" not in str(telemetry.get("reranker_fallback_reason") or ""):
                break
            self.retries += 1
            time.sleep(pause + random.random())
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
    parser.add_argument("--baseline-chunks", help="Published child_chunks.json for the baseline variant.")
    args = parser.parse_args()

    from src.evaluation.retrieval import evaluate_retrieval
    from src.retrieval.core.embedding_model import load_embedding_client
    from src.retrieval.runtime_config import load_retrieval_runtime_config

    parents = json.loads(Path("data/processed/chunks/all_docstore_items.json").read_text(encoding="utf-8"))
    cases = [case for path in args.cases for case in json.loads(Path(path).read_text(encoding="utf-8"))]
    embedder = load_embedding_client(load_retrieval_runtime_config().get("embedding") or {})
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    summary = {}
    for name in args.variants.split(","):
        chunks = variant_chunks(name, parents, args.baseline_chunks)
        vectors = embed([c["embedding_text"] for c in chunks], embedder)
        retriever = build_retriever(chunks, vectors, parents)
        throttled = ThrottledReranker(retriever.reranker, args.rerank_interval)
        retriever.reranker = throttled
        report = evaluate_retrieval(cases, backend="qdrant", scope="pure")
        report["variant"] = {"name": name, "chunks": len(chunks), "reranker_fallbacks": throttled.fallbacks,
                             "reranker_429_retries": throttled.retries}
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
