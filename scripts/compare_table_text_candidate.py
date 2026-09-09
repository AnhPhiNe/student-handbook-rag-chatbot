"""Offline BM25 sensitivity check; not a hybrid, Planner or answer-quality eval."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.retrieval.core.bm25_retriever import BM25Retriever  # noqa: E402


def retrieve(index, query, cohort):
    hits = index.sparse_search(query, cohort=cohort, top_k=24)
    parents = list(dict.fromkeys(h["metadata"]["parent_section_id"] for h in hits))[:5]
    return parents


def compare(baseline, candidate, cases):
    indexes = []
    for corpus in (baseline, candidate):
        index = BM25Retriever()
        index.build_bm25_index(corpus)
        indexes.append(index)
    units = []
    for case in cases:
        targets = case.get("relevance_judgments", [])
        cohorts = sorted({t["cohort"] for t in targets if t.get("grade", 0) >= 2})
        for cohort in cohorts:
            expected = {t["parent_section_id"] for t in targets
                        if t["cohort"] == cohort and t.get("grade", 0) >= 2}
            results = [retrieve(i, case["query"], cohort) for i in indexes]
            units.append({
                "id": case["id"], "cohort": cohort, "expected": sorted(expected),
                "baseline": results[0], "candidate": results[1],
                "baseline_hit": bool(expected.intersection(results[0])),
                "candidate_hit": bool(expected.intersection(results[1])),
                "baseline_recall": len(expected.intersection(results[0])) / len(expected),
                "candidate_recall": len(expected.intersection(results[1])) / len(expected),
            })
    return {
        "method": "Production BM25 tokenizer/scoring, 24 filtered children -> first 5 unique parents; original queries, gold cohorts, no Planner, dense search, RRF or Composer.",
        "purpose": "Corpus sensitivity diagnostic only; not comparable to published end-to-end Hit@5.",
        "case_count": len(cases), "execution_units": len(units),
        "baseline_hit_units": sum(u["baseline_hit"] for u in units),
        "candidate_hit_units": sum(u["candidate_hit"] for u in units),
        "lost_hits": [u for u in units if u["baseline_hit"] and not u["candidate_hit"]],
        "gained_hits": [u for u in units if u["candidate_hit"] and not u["baseline_hit"]],
        "recall_decreases": [u for u in units if u["candidate_recall"] < u["baseline_recall"]],
        "units": units,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument(
        "--cases",
        type=Path,
        default=ROOT / "data/eval/official_v1/retrieval_cases.json",
    )
    args = parser.parse_args()
    directory = args.candidate_dir.resolve()
    if not directory.is_relative_to((ROOT / "work").resolve()):
        parser.error("Use an isolated candidate directory under work/.")
    output = directory / f"bm25_{args.cases.stem}.json"
    if output.exists():
        parser.error("Comparison already exists; keep it and use another candidate build.")
    paths = {
        "baseline": ROOT / "data/processed/chunks/child_parent_chunks.json",
        "candidate": directory / "child_parent_chunks.json",
        "cases": args.cases,
    }
    data = {key: json.loads(path.read_text(encoding="utf-8")) for key, path in paths.items()}
    report = compare(**data)
    report["input_sha256"] = {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in paths.items()}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "units"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
