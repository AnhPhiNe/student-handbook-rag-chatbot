"""Compare rerankers on official_v1 retrieval questions with identical candidates.

A side measurement: it does not change the system or its configuration.

    python -m scripts.compare_rerankers --candidates            # build the 24 RRF candidates once
    python -m scripts.compare_rerankers --reranker rrf          # no rerank (baseline)
    python -m scripts.compare_rerankers --reranker deepinfra:Qwen/Qwen3-Reranker-4B
    python -m scripts.compare_rerankers --reranker voyage:rerank-3

Every reranker scores the same candidate children. Children are grouped into
parents by their best score, as the pipeline does; a question counts as top-5
when a gold parent (grade 2) is among the first five parents, and as first when
the first parent is gold. Latency is one call per question, run one at a time.
"""
import argparse
import json
import os
import time
from pathlib import Path

import requests
import yaml

ROOT = Path.cwd()
OUT = Path(os.environ.get("RERANKER_COMPARE_OUT") or ROOT / "data/eval/reports/reranker_compare_v1")
CASES = ROOT / "data/eval/official_v1/retrieval_cases.json"
TIMEOUT_SECONDS = 60


def build_candidates() -> None:
    from src.evaluation.shared import wait_for_bm25_ready
    from src.retrieval.core.hybrid_pipeline import initialize_hybrid_retriever, reciprocal_rank_fusion

    retriever = initialize_hybrid_retriever()
    wait_for_bm25_ready()
    limit = retriever.candidate_children
    rows = []
    for case in json.loads(CASES.read_text(encoding="utf-8")):
        dense = retriever._dense_candidates(case["query"], cohort=case["cohort"], limit=limit)
        lexical = retriever._bm25_candidates(case["query"], cohort=case["cohort"], limit=limit)
        fused = reciprocal_rank_fusion(dense, lexical)[:limit]
        rows.append({
            "id": case["id"], "query": case["query"], "cohort": case["cohort"],
            "gold": [j["parent_section_id"] for j in case["relevance_judgments"] if j.get("grade") == 2],
            "candidates": [{"parent": (chunk.get("metadata") or {}).get("parent_section_id"),
                            "content": str(chunk.get("content") or "")} for _, chunk in fused],
        })
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "candidates.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"{len(rows)} questions, {limit} candidates each -> {OUT / 'candidates.json'}")


def _post_scores(url: str, key_env: str, payload: dict, parse) -> tuple[list[float] | None, float, str | None]:
    """One timed call; a 429 waits and retries, and the wait is not counted."""
    for _ in range(6):
        started = time.perf_counter()
        try:
            response = requests.post(url, headers={"Authorization": f"Bearer {os.environ[key_env]}"},
                                     json=payload, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            return None, time.perf_counter() - started, type(exc).__name__
        seconds = time.perf_counter() - started
        if response.status_code == 429:
            time.sleep(21)
            continue
        if response.status_code != 200:
            return None, seconds, f"http_{response.status_code}"
        return parse(response.json()), seconds, None
    return None, 0.0, "rate_limited"


def scorer(name: str):
    if name == "rrf":
        return lambda query, docs: ([float(len(docs) - i) for i in range(len(docs))], 0.0, None)
    provider, model = name.split(":", 1)
    if provider == "deepinfra":
        config = yaml.safe_load((ROOT / "configs/retrieval.yaml").read_text(encoding="utf-8"))["reranker"]
        return lambda query, docs: _post_scores(
            f"{config['api_url']}/{model}", config["api_key_env_var"],
            {"queries": [query], "documents": docs, "instruction": config["instruction"]},
            lambda body: [float(score) for score in body["scores"]])
    if provider == "voyage":
        def parse(body):
            scores = [0.0] * len(body["data"])
            for item in body["data"]:
                scores[item["index"]] = float(item["relevance_score"])
            return scores
        # Keys issued by MongoDB Atlas ("al-...") are served by ai.mongodb.com, Voyage's own by api.voyageai.com.
        atlas_key = os.environ.get("VOYAGE_API_KEY", "").startswith("al-")
        url = "https://ai.mongodb.com/v1/rerank" if atlas_key else "https://api.voyageai.com/v1/rerank"
        return lambda query, docs: _post_scores(
            url, "VOYAGE_API_KEY",
            {"query": query, "documents": docs, "model": model, "truncation": True}, parse)
    raise SystemExit(f"Unknown reranker: {name}")


def run(name: str) -> None:
    from src.common.env_loader import load_project_env
    load_project_env()
    score = scorer(name)
    rows, latencies = [], []
    for row in json.loads((OUT / "candidates.json").read_text(encoding="utf-8")):
        docs = [candidate["content"] for candidate in row["candidates"]]
        scores, seconds, error = score(row["query"], docs)
        if scores is None or len(scores) != len(docs):
            rows.append({"id": row["id"], "error": error or "invalid_response", "seconds": seconds})
            continue
        latencies.append(seconds)
        order = sorted(range(len(scores)), key=lambda index: (-scores[index], index))
        parents = list(dict.fromkeys(row["candidates"][index]["parent"] for index in order))[:5]
        rows.append({"id": row["id"], "seconds": seconds, "top5": bool(set(row["gold"]) & set(parents)),
                     "first": bool(parents) and parents[0] in row["gold"], "parents": parents})
    scored = [r for r in rows if "error" not in r]
    latencies.sort()
    summary = {
        "reranker": name, "questions": len(rows), "scored": len(scored),
        "errors": sorted({r["error"] for r in rows if "error" in r}),
        "top5": sum(r["top5"] for r in scored), "first": round(sum(r["first"] for r in scored) / max(1, len(scored)), 3),
        "latency_s": {"p50": round(latencies[len(latencies) // 2], 2), "p90": round(latencies[int(len(latencies) * 0.9)], 2),
                      "max": round(latencies[-1], 2)} if latencies else None,
    }
    (OUT / f"result_{name.replace(':', '_').replace('/', '_')}.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", action="store_true")
    parser.add_argument("--reranker")
    args = parser.parse_args()
    if args.candidates:
        build_candidates()
    if args.reranker:
        run(args.reranker)


if __name__ == "__main__":
    main()
