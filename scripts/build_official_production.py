"""Author 60 HF transport/cache requests without sending any HTTP request."""
from __future__ import annotations

import json
from collections import Counter

import yaml

from scripts.build_official_answers import BUNDLE, COHORTS


def build():
    authored = yaml.safe_load((BUNDLE / "production_authoring.yaml").read_text(encoding="utf-8"))
    assert {k: len(v) for k, v in authored.items()} == {"cold_rag": 20, "structured": 10, "burst": 10}
    cases = []

    def add(query, scenario, *, stress=False, repeat=None, pair=None, concurrency=1):
        index = len(cases) + 1
        cohort = COHORTS[(index - 1) % 3]
        path = "structured" if scenario == "deterministic" else "regulation_rag"
        style = "stress" if stress else "realistic"
        cases.append({
            "id": f"official_prod_{index:03d}", "suite": "production",
            "query": query, "cohort": cohort, "history": [], "scenario": scenario,
            "expected_path": path, "expected_intent": "regulation_query",
            "expected_strategy": "deterministic_lookup" if path == "structured" else "hybrid_graph_retrieval",
            "concurrency": concurrency, "stream": scenario == "streaming",
            "repeat_of": repeat, "paired_sync_id": pair, "timeout_seconds": 90,
            "topic": "khac", "question_style": style, "eval_split": style,
            "tags": ["official_v1", "production", scenario, style],
            "cohort_sensitivity": "single_cohort", "question_specificity": "specific",
            "expected_answer_behavior": "direct_answer",
            "frozen": False, "review_method": "AI-assisted; not independent human review",
            "cache_expectation": "hit" if scenario == "warm_cache" else "observe" if pair else "miss",
            "na_assertions": {
                "answer_correctness": "N/A: operational suite; audit content separately",
                "fallback_exercised": "N/A unless fallback actually occurs; no HF fault injection",
                "ttft": "measured" if scenario == "streaming" else "N/A: non-stream response",
            },
        })

    for i, query in enumerate(authored["cold_rag"], 1):
        add(query, "cold_rag", stress=i in {5, 16, 18, 20})
    for i, query in enumerate(authored["structured"], 1):
        add(query, "deterministic", stress=i in {4, 9})
    # Reuse the source client's UUID via repeat_of, as supported by the evaluator.
    for source in cases[:10]:
        add(source["query"], "warm_cache", stress=source["eval_split"] == "stress", repeat=source["id"])
        assert cases[-1]["cohort"] == source["cohort"]
    for i, source in enumerate(cases[1:11], 1):
        add(source["query"], "streaming", pair=source["id"],
            stress=source["eval_split"] == "stress" or i in {9, 10})
        assert cases[-1]["cohort"] == source["cohort"]
    for i, query in enumerate(authored["burst"], 1):
        add(query, "burst", stress=i in {4, 9}, concurrency=3 if i <= 5 else 5)
    assert len(cases) == 60
    assert Counter(c["cohort"] for c in cases) == {c: 20 for c in COHORTS}
    assert Counter(c["eval_split"] for c in cases) == {"realistic": 48, "stress": 12}
    return cases


if __name__ == "__main__":
    assert not (BUNDLE / "manifest.json").exists(), "Do not overwrite a frozen bundle"
    cases = build()
    (BUNDLE / "production_cases.json").write_text(
        json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Compiled 60 production drafts. No HTTP requests or freeze.")
