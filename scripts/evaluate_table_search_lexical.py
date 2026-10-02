"""Offline BM25 source-coverage comparison; no inference/embedding/remote stores."""
import argparse
import hashlib
import json
from pathlib import Path

from scripts.build_table_search_candidate import ROOT, assert_separate_output
from src.retrieval.core.bm25_retriever import BM25Retriever
from src.retrieval.core.table_search import build_table_descriptions


def evaluate() -> dict:
    cases_path = ROOT / "tests/fixtures/table_search_development.json"
    frozen = json.loads(cases_path.read_text(encoding="utf-8"))
    def read(path):
        return json.loads((ROOT / path).read_text(encoding="utf-8"))
    manifest = read("data/processed/metadata/build_manifest.json")
    if manifest["build_id"] != frozen["source_build_id"]:
        raise ValueError("Development fixtures require the frozen source build")
    parents = read("data/processed/chunks/all_docstore_items.json")
    children = read("data/processed/chunks/child_parent_chunks.json")
    tables = read("data/processed/tables/structured_tables_registry.json")
    index = {}
    for name, corpus in (("baseline", children), ("candidate", children + build_table_descriptions(tables, parents))):
        index[name] = BM25Retriever()
        index[name].build_bm25_index(corpus)
    rows = []
    for case in frozen["cases"]:
        expected = {t["source_parent_id"] for t in tables if t["cohort"] == case["source_cohort"]
                    and t["table_subtype"] == case["table_subtype"]}
        if not expected:
            raise ValueError("Missing expected source for frozen probe")
        row = {"id": case["id"], "query": case["query"], "cohort": case["cohort"]}
        for name, retriever in index.items():
            chunks = retriever.sparse_search(case["query"], top_k=24, cohort=case["cohort"],
                                             chunk_types=["regulation"], content_types=["regulation_text"])
            parent_ids = list(dict.fromkeys(c["metadata"]["parent_section_id"] for c in chunks))[:5]
            row[name] = {"parent_hit_at_5": bool(expected.intersection(parent_ids)), "parent_ids": parent_ids}
        rows.append(row)
    return {"suite": "table-search-development-bm25-only", "model_calls": 0,
            "dense_rerank_answer_quality_measured": False, "fixture_sha256": hashlib.sha256(cases_path.read_bytes()).hexdigest(),
            "n": len(rows), "baseline_parent_hits_at_5": sum(r["baseline"]["parent_hit_at_5"] for r in rows),
            "candidate_parent_hits_at_5": sum(r["candidate"]["parent_hit_at_5"] for r in rows), "cases": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert_separate_output(ROOT, args.output)
    if args.output.suffix.casefold() != ".json":
        raise ValueError("Development report must be a separate JSON file")
    report = evaluate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, ensure_ascii=False, indent=2))
