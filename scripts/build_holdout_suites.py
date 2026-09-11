"""Derive a held-out bundle's answer and retrieval suites from its deterministic authoring.

A held-out bundle (official_v2) has one gold source, `deterministic_authoring.yaml`, so
the three suites cannot drift apart:

- answers: one case per authored question, with the same history and UI cohort. Structured
  tasks take their required meaning from the compiled catalog rows; each policy task
  carries an authored `fact`; clarification and out-of-domain cases get the expected
  behaviour.
- retrieval: every question without history that has a policy task, plus the extra
  questions in `retrieval_authoring.yaml`. The pure retrieval scope searches the raw
  question, so it cannot use history and has no regulation parent to rank for a
  structured task. A policy task may list `equivalent` [suffix, anchor] sources that
  answer the same requirement.

Offline only: reads source catalogs, calls no model.

    python -m scripts.build_holdout_suites --bundle official_v2
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_official_answers import (  # noqa: E402
    EVALUATION_NOTES, GPA_FORMULA_NOTE, answer_meaning, citation, structured_ref,
)
from scripts.build_official_deterministic import build as build_deterministic  # noqa: E402
from scripts.build_official_deterministic import compile_task, records  # noqa: E402
from scripts.build_official_retrieval import evidence, judgment, validate_relevance  # noqa: E402

OUT_OF_DOMAIN_FACT = "Từ chối lịch sự vì câu hỏi nằm ngoài phạm vi Sổ tay sinh viên; không bịa câu trả lời."
# Output columns a single-row scoring answer must state; the remaining columns are context.
ANSWER_FIELDS = {
    ("grade_scale", "grade_10_to_letter"): ["Thang điểm chữ"],
    ("grade_scale", "pass_threshold"): ["Loại", "Thang điểm chữ"],
    ("letter_to_grade4", "letter_to_grade_4"): ["Thang điểm chữ", "Thang điểm 4"],
}


def primary_specs(definition: dict) -> list[dict]:
    if "clarify" in definition or definition.get("out_of_domain"):
        return []
    return definition.get("tasks", [definition])


def find_parent(parents: list[dict], cohort: str, suffix: str) -> dict:
    matches = [p for p in parents if p["cohort"] == cohort and p["_id"].endswith(suffix)]
    assert len(matches) == 1, (cohort, suffix, len(matches))
    return matches[0]


def structured_fact(spec: dict, task: dict) -> str:
    table = spec.get("table") or []
    if table and table[1] != "all" and not spec.get("output_rows") and "answer_fields" not in spec:
        fields = ANSWER_FIELDS.get((table[0], table[2]))
        spec = {**spec, "answer_fields": fields} if fields else spec
    fact = answer_meaning(spec, task)
    return fact + GPA_FORMULA_NOTE if spec.get("formula") == "gpa_weighted_average" else fact


def answer_case(definition: dict, compiled: dict, catalogs: dict, bundle: str) -> dict:
    cohort = compiled["cohort"]
    facts, units, citations, structured, gold = [], [], [], [], []
    for spec in primary_specs(definition):
        target = spec.get("cohort", cohort)
        if spec.get("clarify_task"):
            fact, mode = f"Hỏi lại để bổ sung: {spec['clarify_task']}", "clarify"
        else:
            task, sources = compile_task(spec, cohort, catalogs)
            mode = task["mode"]
            if "policy" in spec:
                assert spec.get("fact"), ("Missing authored policy fact", definition["query"])
                fact = spec["fact"]
                parent = next(p for p in catalogs["parents"] if p["_id"] == sources[0]["source_id"])
                citations.append(citation(parent, target))
                gold.append({**sources[0], "content": parent["content"]})
            else:
                fact = structured_fact(spec, task)
                structured += [structured_ref(source, target) for source in sources]
                gold += [{**source, "requested_cohort": target} for source in sources]
        scoped = f"[{target}] {fact}"
        facts.append(scoped)
        units.append({"cohort": target, "required_meaning": scoped, "mode": mode})
    path = compiled["expected_path"]
    if "clarify" in definition:
        facts = [f"Hỏi lại, không tự đoán: {definition['clarify']}"]
    elif definition.get("out_of_domain"):
        facts = [OUT_OF_DOMAIN_FACT]
    targets = list(dict.fromkeys(unit["cohort"] for unit in units)) or [cohort]
    kind = ("clarification" if path == "clarify" else "out_of_domain" if path == "out_of_domain"
            else "mixed_answer" if path == "mixed" else "structured_answer" if path == "structured"
            else "regulation_true_rag")
    return {
        "id": compiled["id"].replace("_det_", "_ans_"), "suite": "answers",
        "query": definition["query"], "cohort": cohort, "history": compiled["history"],
        "slice": compiled["slice"], "topic": "khac", "case_type": kind, "expected_path": path,
        "expected_intent": "query_plan",
        "expected_strategy": "deterministic_lookup" if path == "structured" else "hybrid_graph_retrieval",
        "expected_answer_behavior": compiled["expected_answer_behavior"],
        "answerability": "unanswerable" if path == "out_of_domain" else "answerable",
        "question_style": compiled["question_style"], "eval_split": compiled["eval_split"],
        "tags": [bundle, compiled["question_style"]],
        "ground_truth": "\n".join(facts), "required_facts": facts, "forbidden_claims": [],
        "relevance_judgments": citations, "expected_citations": citations,
        "expected_structured_sources": structured, "gold_evidence": gold, "answer_units": units,
        "requested_cohorts": targets,
        "cohort_sensitivity": "multi_cohort_risk" if len(targets) > 1 else "single_cohort",
        "question_specificity": compiled["question_specificity"],
        "coverage_features": compiled["coverage_features"],
        "lexical_fact_check_applicable": False, "evaluation_notes": EVALUATION_NOTES,
        "review_status": "ai_drafted_pending_owner_review",
        "review_method": "Drafted from handbook sources; owner review pending",
        "frozen": False, "independent_holdout": compiled["independent_holdout"],
        "na_assertions": {"fact_lock": "N/A: final-answer quality, not resolver execution"},
        **{key: compiled[key] for key in ("stress_type",) if key in compiled},
    }


def retrieval_case(case_id: str, query: str, cohort: str, policies: list[dict], parents: list[dict],
                   *, slice_name: str, style: str, bundle: str, holdout: bool) -> dict:
    judgments, gold, groups = [], [], []
    for spec in policies:
        target = spec.get("cohort", cohort)
        parent = find_parent(parents, target, spec["policy"][0])
        group = [parent["_id"]]
        judgments.append(judgment(parent, target))
        gold.append(evidence(parent, spec["policy"][1]))
        for suffix, anchor in spec.get("equivalent", []):
            other = find_parent(parents, target, suffix)
            group.append(other["_id"])
            judgments.append(judgment(other, target))
            gold.append(evidence(other, anchor))
        if len(group) > 1:
            groups.append(group)
    targets = list(dict.fromkeys(j["cohort"] for j in judgments))
    case = {
        "id": case_id, "suite": "retrieval", "query": query,
        # A multi-cohort question searches every cohort, as in official_v1.
        "cohort": targets[0] if len(targets) == 1 else "general", "history": [],
        "slice": slice_name, "topic": "khac", "tags": [bundle, "true_rag", style],
        "question_style": style, "eval_split": style,
        "expected_intent": "regulation_query", "expected_strategy": "hybrid_graph_retrieval",
        "expected_path": "regulation_rag", "expected_content_types": ["regulation_text"],
        "case_type": "regulation_true_rag", "requested_cohorts": targets,
        "cohort_sensitivity": "multi_cohort_risk" if len(targets) > 1 else "single_cohort",
        "question_specificity": "specific", "expected_answer_behavior": "scoped_summary",
        "relevance_judgments": judgments, "gold_evidence": gold,
        "annotation_status": "draft_source_anchored",
        "review_status": "ai_drafted_pending_owner_review",
        "frozen": False, "independent_holdout": holdout,
        "na_assertions": {"final_answer": "N/A: retrieval-only suite",
                          "fact_lock": "N/A: narrative evidence retrieval"},
    }
    if groups:
        case["equivalent_source_groups"] = groups
    validate_relevance(case)
    return case


def build(bundle: Path) -> tuple[list[dict], list[dict]]:
    authoring = yaml.safe_load((bundle / "deterministic_authoring.yaml").read_text(encoding="utf-8"))
    compiled_cases = build_deterministic(bundle)
    catalogs = records()
    holdout = bool((authoring.get("settings") or {}).get("independent_holdout", False))
    answers, retrieval = [], []
    for definition, compiled in zip(authoring["cases"], compiled_cases):
        answers.append(answer_case(definition, compiled, catalogs, bundle.name))
        policies = [spec for spec in primary_specs(definition) if "policy" in spec]
        if policies and not definition.get("history"):
            retrieval.append(retrieval_case(
                compiled["id"].replace("_det_", "_ret_"), definition["query"], compiled["cohort"],
                policies, catalogs["parents"], slice_name=compiled["slice"],
                style=compiled["question_style"], bundle=bundle.name, holdout=holdout))
    extra_path = bundle / "retrieval_authoring.yaml"
    extras = yaml.safe_load(extra_path.read_text(encoding="utf-8"))["cases"] if extra_path.exists() else []
    for index, extra in enumerate(extras, 1):
        style = "stress" if extra.get("stress") else "realistic"
        retrieval.append(retrieval_case(
            f"{bundle.name}_ret_extra_{index:03d}", extra["query"], extra["selected_cohort"],
            extra.get("tasks", [extra]), catalogs["parents"], slice_name=extra.get("slice", "single.regulation"),
            style=style, bundle=bundle.name, holdout=holdout))
    return answers, retrieval


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bundle", default="official_v2", help="Folder under data/eval.")
    bundle = ROOT / "data/eval" / parser.parse_args().bundle
    if (bundle / "manifest.json").exists():
        raise RuntimeError("Bundle is frozen; refusing to rebuild")
    answers, retrieval = build(bundle)
    for name, cases in (("generated_answer_cases.json", answers), ("retrieval_cases.json", retrieval)):
        (bundle / name).write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Compiled {len(answers)} answer and {len(retrieval)} retrieval cases; no inference executed.")


if __name__ == "__main__":
    main()
