"""Compile retrieval drafts from explicit source anchors; no inference or freeze."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "data/eval/official_v1"
COHORTS = ("K48-K49", "K50", "K51")


def validate_relevance(case):
    """Reject inconsistent authored judgments before any model call."""
    judgments = case["relevance_judgments"]
    by_id = {j["parent_section_id"]: j for j in judgments}
    assert len(by_id) == len(judgments), "Duplicate source judgment"
    assert any(j["grade"] == 2 for j in judgments), "No required source"
    assert all(j["grade"] in (0, 1, 2) for j in judgments)
    assert {e["source_id"] for e in case["gold_evidence"]} == set(by_id)
    assert len(case["gold_evidence"]) == len(judgments)
    requested = set(case.get("requested_cohorts", [case["cohort"]]))
    assert {j["cohort"] for j in judgments} <= requested
    seen = set()
    for group in case.get("equivalent_source_groups", []):
        assert len(group) >= 2 and len(set(group)) == len(group), "Invalid equivalent group"
        assert set(group) <= set(by_id), "Unknown equivalent source"
        assert not seen.intersection(group), "Overlapping equivalent groups"
        assert len({by_id[source]["cohort"] for source in group}) == 1, "Cross-cohort equivalence"
        assert all(by_id[source]["grade"] == 2 for source in group), "Equivalent source must answer the requirement"
        seen.update(group)


def judgment(parent, cohort, grade=2):
    """Relevance judgment for one regulation parent."""
    return {"parent_section_id": parent["_id"], "grade": grade, "cohort": cohort,
            "document_id": parent["document_id"], "content_type": "regulation_text",
            "source_section": parent["metadata"]["title"],
            "source_pages": parent["metadata"]["source_pages"]}


def evidence(parent, anchor):
    """Gold evidence: the anchor quote with some surrounding article text."""
    content = " ".join(parent["content"].split())
    assert anchor in content, (parent["_id"], anchor)
    position = content.index(anchor)
    return {"source_id": parent["_id"], "anchor": anchor,
            "context": content[max(0, position - 200):position + len(anchor) + 600],
            "content_sha256": hashlib.sha256(parent["content"].encode()).hexdigest()}


def build():
    definitions = yaml.safe_load((BUNDLE / "retrieval_authoring.yaml").read_text(encoding="utf-8"))
    groups = definitions["groups"]
    parents = json.loads((ROOT / "data/processed/chunks/all_docstore_items.json").read_text(encoding="utf-8"))
    cases = []
    for group in groups:
        assert len(group["cases"]) == 5
        for offset, (query, anchor) in enumerate(group["cases"]):
            index = len(cases) + 1
            cohort = COHORTS[(index - 1) % 3]
            suffix = group.get("source_by_cohort", {}).get(cohort, group["source"])
            matches = [p for p in parents if p["cohort"] == cohort and p["_id"].endswith(suffix)]
            assert len(matches) == 1, (index, cohort, suffix)
            parent = matches[0]
            style = "stress" if offset == 4 else "realistic"
            cases.append({
                "id": f"official_ret_{index:03d}", "suite": "retrieval",
                "query": query, "cohort": cohort, "history": [],
                "topic": group["topic"], "tags": ["official_v1", "true_rag", style],
                "question_style": style, "eval_split": style,
                "expected_intent": "regulation_query",
                "expected_strategy": "hybrid_graph_retrieval",
                "expected_path": "regulation_rag",
                "expected_content_types": ["regulation_text"],
                "case_type": "regulation_true_rag",
                "cohort_sensitivity": "single_cohort", "question_specificity": "specific",
                "expected_answer_behavior": "scoped_summary",
                "relevance_judgments": [judgment(parent, cohort)],
                "gold_evidence": [evidence(parent, anchor)],
                "annotation_status": "draft_source_anchored",
                "review_status": "pending_equivalent_sources_and_context_review",
                "frozen": False, "independent_holdout": False,
                "na_assertions": {"final_answer": "N/A: retrieval-only suite",
                    "fact_lock": "N/A: narrative evidence retrieval"},
            })
    for index, replacement in definitions.get("replacements", {}).items():
        case = cases[index - 1]
        case["query"] = replacement["query"]
        case["coverage_features"] = replacement["features"]
        case["relevance_judgments"] = []
        case["gold_evidence"] = []
        for source_index, (suffix, anchor, *explicit_cohort) in enumerate(replacement["sources"]):
            cohort = explicit_cohort[0] if explicit_cohort else case["cohort"]
            matches = [p for p in parents if p["cohort"] == cohort and p["_id"].endswith(suffix)]
            assert len(matches) == 1, (index, cohort, suffix)
            grade = replacement.get("source_grades", [2] * len(replacement["sources"]))[source_index]
            case["relevance_judgments"].append(judgment(matches[0], cohort, grade))
            case["gold_evidence"].append(evidence(matches[0], anchor))
        case["requested_cohorts"] = sorted({j["cohort"] for j in case["relevance_judgments"]})
        if replacement.get("review_note"):
            case["gold_rationale"] = replacement["review_note"]
        if len(case["requested_cohorts"]) > 1:
            case["allocation_cohort"] = case["cohort"]
            case["cohort"] = "general"
            case["cohort_sensitivity"] = "multi_cohort_risk"
    for index, (suffix, anchor) in definitions.get("equivalent_sources", {}).items():
        case = cases[index - 1]
        matches = [p for p in parents if p["cohort"] == case["cohort"] and p["_id"].endswith(suffix)]
        assert len(matches) == 1
        parent = matches[0]
        assert len(case["relevance_judgments"]) == 1
        case["equivalent_source_groups"] = [[case["relevance_judgments"][0]["parent_section_id"], parent["_id"]]]
        case["relevance_judgments"].append(judgment(parent, case["cohort"]))
        case["gold_evidence"].append(evidence(parent, anchor))
    assert len(cases) == 155
    assert Counter(c.get("allocation_cohort", c["cohort"]) for c in cases) == {"K48-K49": 52, "K50": 52, "K51": 51}
    assert Counter(c["question_style"] for c in cases) == {"realistic": 124, "stress": 31}
    for case in cases:
        validate_relevance(case)
    return cases


if __name__ == "__main__":
    if (BUNDLE / "manifest.json").exists():
        raise RuntimeError("Bundle manifest exists; refusing to overwrite reviewed data")
    cases = build()
    (BUNDLE / "retrieval_cases.json").write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Compiled {len(cases)} retrieval drafts with source anchors. No inference or freeze.")
