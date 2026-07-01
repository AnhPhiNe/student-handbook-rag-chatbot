from __future__ import annotations

import argparse
import json
import unicodedata
from pathlib import Path
from typing import Any


DEFAULT_GOLDEN_PATH = Path("data/eval/golden_queries.json")
DEFAULT_ANSWER_PATH = Path("data/eval/answer_eval_cases.json")
DEFAULT_GENERATION_PATH = Path("data/eval/generation_eval_cases.json")
DEFAULT_OUTPUT_DIR = Path("data/eval")

STRUCTURED_TARGET = 70
TRUE_RAG_TARGET = 80
JUDGE_TARGET = 100

STRUCTURED_CONTENT_BY_LOOKUP = {
    "academic_classification": "scoring_tables",
    "conduct_classification": "scoring_tables",
    "form_template": "form_templates",
    "grade_10_to_letter": "threshold_rules",
    "letter_to_grade_4": "scoring_tables",
    "program_directory": "program_directory",
}

STRUCTURED_CONTENT_BY_TOOL = {
    "calculate_scholarship_score": "formula_rules",
}

RAG_CONTENT_ALIASES = {
    "faculty": "faculty_directory",
    "form": "form_templates",
    "office": "office_directory",
    "procedure": "procedures",
    "program": "program_directory",
    "regulation": "regulation_sections",
    "scoring_table": "scoring_tables",
    "structured_lookup": "structured_lookup",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        f.write("\n")


def normalize_cohort(value: Any) -> str:
    text = str(value or "general").strip()
    if not text or text.lower() == "all":
        return "general"
    return text


def strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or "").lower())
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return normalized.replace("đ", "d")


def is_program_lookup_query(case: dict[str, Any]) -> bool:
    query = strip_accents(case.get("query") or "")
    if "nganh" not in query and "chuyen nganh" not in query:
        return False
    list_signals = [
        "co nganh nao",
        "co nhung nganh",
        "co cac nganh",
        "dao tao nhung nganh",
        "dao tao nganh nao",
        "nganh nao",
        "nganh gi",
        "danh sach nganh",
        "liet ke nganh",
    ]
    resolve_signals = [
        "thuoc khoa",
        "khoa nao",
        "khoa phu trach",
        "phu trach nganh",
    ]
    return any(signal in query for signal in list_signals + resolve_signals)


def infer_structured_content_type(case: dict[str, Any]) -> str:
    if is_program_lookup_query(case):
        return "program_directory"
    lookup_type = str(case.get("expected_lookup_type") or "")
    tool_name = str(case.get("expected_tool_name") or "")
    if lookup_type in STRUCTURED_CONTENT_BY_LOOKUP:
        return STRUCTURED_CONTENT_BY_LOOKUP[lookup_type]
    if tool_name in STRUCTURED_CONTENT_BY_TOOL:
        return STRUCTURED_CONTENT_BY_TOOL[tool_name]
    category = str(case.get("category") or "")
    if "office" in category:
        return "office_directory"
    if "form" in category:
        return "form_templates"
    if "program" in category:
        return "program_directory"
    if "score" in category:
        return "scoring_tables"
    if "guard" in category:
        return "guardrail"
    return "structured_or_guardrail"


def normalize_rag_content_type(case: dict[str, Any]) -> str:
    content_types = case.get("expected_content_types") or []
    if not content_types:
        return "regulation_sections"
    first = str(content_types[0])
    return RAG_CONTENT_ALIASES.get(first, first)


def is_structured_case(case: dict[str, Any]) -> bool:
    return bool(
        case.get("expected_lookup_type")
        or case.get("expected_tool_name")
        or str(case.get("category") or "").startswith("guard")
        or is_program_lookup_query(case)
    )


def is_true_rag_case(case: dict[str, Any]) -> bool:
    if case.get("expected_lookup_type") or case.get("expected_tool_name"):
        return False
    if is_program_lookup_query(case):
        return False
    strategy = str(case.get("expected_strategy") or "")
    content_types = {str(item) for item in case.get("expected_content_types") or []}
    if "form" in content_types:
        return False
    return strategy.startswith("semantic") or bool(content_types)


def structured_from_answer(case: dict[str, Any], index: int) -> dict[str, Any]:
    item = dict(case)
    item.setdefault("id", f"structured_answer_{index:03d}")
    item["eval_type"] = "structured"
    item["content_type"] = infer_structured_content_type(case)
    item["cohort"] = normalize_cohort(item.get("cohort"))
    item["source_eval_file"] = "answer_eval_cases.json"
    return item


def structured_from_golden(case: dict[str, Any], index: int) -> dict[str, Any]:
    item = dict(case)
    item.setdefault("id", f"structured_golden_{index:03d}")
    item["eval_type"] = "structured"
    item["content_type"] = infer_structured_content_type(case)
    if is_program_lookup_query(case):
        item["expected_intent"] = "faculty_query"
        item["expected_strategy"] = "program_lookup"
        item["expected_lookup_type"] = "program_directory"
        item["expected_content_types"] = []
        item["expected_chunk_ids"] = []
    item["cohort"] = normalize_cohort(item.get("cohort"))
    item["source_eval_file"] = "golden_queries.json"
    return item


def form_structured_from_golden(case: dict[str, Any], index: int) -> dict[str, Any]:
    item = dict(case)
    item.setdefault("id", f"structured_form_{index:03d}")
    item["eval_type"] = "structured"
    item["content_type"] = "form_templates"
    item["expected_intent"] = "form_query"
    item["expected_strategy"] = "form_lookup"
    item["expected_lookup_type"] = "form_template"
    item["cohort"] = normalize_cohort(item.get("cohort"))
    item["source_eval_file"] = "golden_queries.json"
    return item


def true_rag_from_golden(case: dict[str, Any], index: int) -> dict[str, Any]:
    item = dict(case)
    item.setdefault("id", f"true_rag_{index:03d}")
    item["eval_type"] = "true_rag"
    item["content_type"] = normalize_rag_content_type(case)
    item["cohort"] = normalize_cohort(item.get("cohort"))
    if item["cohort"] == "general":
        item["expected_cohort"] = "general"
    item["source_eval_file"] = "golden_queries.json"
    return item


def true_rag_from_generation(case: dict[str, Any], index: int) -> dict[str, Any]:
    item = {
        "id": case.get("id") or f"true_rag_generation_{index:03d}",
        "query": case["query"],
        "eval_type": "true_rag",
        "content_type": _judge_content_type(case),
        "cohort": normalize_cohort(case.get("cohort")),
        "expected_intent": case.get("expected_intent") or "regulation_query",
        "expected_strategy": "semantic_filtered",
        "expected_chunk_ids": [case["chunk_id"]] if case.get("chunk_id") else [],
        "ground_truth": case.get("ground_truth"),
        "source_eval_file": "generation_eval_cases.json",
    }
    if item["content_type"] == "regulation_sections":
        item["expected_content_types"] = ["regulation"]
    elif item["content_type"] == "procedures":
        item["expected_content_types"] = ["procedure"]
    elif item["content_type"] == "office_directory":
        item["expected_content_types"] = ["office"]
    elif item["content_type"] == "faculty_directory":
        item["expected_content_types"] = ["faculty"]
    return item


def judge_from_generation(case: dict[str, Any], index: int) -> dict[str, Any]:
    item = dict(case)
    item.setdefault("id", f"judge_{index:03d}")
    item["eval_type"] = "true_rag" if not is_structured_case(item) else "structured"
    item["content_type"] = _judge_content_type(item)
    item["cohort"] = normalize_cohort(item.get("cohort"))
    item["judge_metrics"] = [
        "faithfulness",
        "answer_relevancy",
        "context_precision",
        "context_recall",
        "answer_correctness",
        "citation_correctness",
    ]
    item["source_eval_file"] = "generation_eval_cases.json"
    return item


def _judge_content_type(case: dict[str, Any]) -> str:
    intent = str(case.get("expected_intent") or "")
    if "program" in intent or "faculty" in intent:
        return "program_directory" if "program" in intent else "faculty_directory"
    if "score" in intent or "scoring" in intent:
        return "scoring_tables"
    if "form" in intent:
        return "form_templates"
    if "office" in intent or "reference" in intent:
        return "office_directory"
    if "procedure" in intent:
        return "procedures"
    if "mixed" in intent or "clarification" in intent:
        return "mixed_or_guardrail"
    return "regulation_sections"


def dedupe_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    unique: list[dict[str, Any]] = []
    for case in cases:
        key = (
            str(case.get("query") or "").strip().lower(),
            str(case.get("cohort") or "general"),
            str(case.get("eval_type") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(case)
    return unique


def build_sets(
    golden_cases: list[dict[str, Any]],
    answer_cases: list[dict[str, Any]],
    generation_cases: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    structured_candidates = [
        structured_from_answer(case, index)
        for index, case in enumerate(answer_cases, start=1)
        if is_structured_case(case)
    ]
    structured_candidates.extend(
        structured_from_golden(case, index)
        for index, case in enumerate(golden_cases, start=1)
        if is_structured_case(case)
    )
    structured_candidates.extend(
        form_structured_from_golden(case, index)
        for index, case in enumerate(golden_cases, start=1)
        if case.get("expected_intent") == "form_query"
    )
    structured_cases = dedupe_cases(structured_candidates)[:STRUCTURED_TARGET]

    true_rag_candidates = [
        true_rag_from_golden(case, index)
        for index, case in enumerate(golden_cases, start=1)
        if is_true_rag_case(case)
    ]
    true_rag_candidates.extend(
        true_rag_from_generation(case, index)
        for index, case in enumerate(generation_cases, start=1)
        if case.get("chunk_id") and _judge_content_type(case) not in {
            "form_templates",
            "program_directory",
            "scoring_tables",
        }
    )
    true_rag_cases = dedupe_cases(true_rag_candidates)[:TRUE_RAG_TARGET]

    judge_candidates = [
        judge_from_generation(case, index)
        for index, case in enumerate(generation_cases, start=1)
        if case.get("ground_truth")
    ]
    judge_cases = dedupe_cases(judge_candidates)[:JUDGE_TARGET]

    return {
        "structured": structured_cases,
        "true_rag": true_rag_cases,
        "beta": structured_cases + true_rag_cases,
        "judge": judge_cases,
    }


def build_manifest(sets: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {
        "description": (
            "Bộ eval beta tách structured/tool khỏi true RAG để tránh chấm sai bản chất "
            "của từng nhóm năng lực."
        ),
        "targets": {
            "structured_cases": STRUCTURED_TARGET,
            "true_rag_cases": TRUE_RAG_TARGET,
            "ragas_judge_cases": JUDGE_TARGET,
        },
        "actual_counts": {name: len(cases) for name, cases in sets.items()},
        "files": {
            "structured": "data/eval/structured_eval_cases.json",
            "true_rag": "data/eval/true_rag_eval_cases.json",
            "beta": "data/eval/beta_eval_cases.json",
            "judge": "data/eval/ragas_judge_cases.json",
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build beta eval sets.")
    parser.add_argument("--golden", default=str(DEFAULT_GOLDEN_PATH))
    parser.add_argument("--answers", default=str(DEFAULT_ANSWER_PATH))
    parser.add_argument("--generation", default=str(DEFAULT_GENERATION_PATH))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    args = parser.parse_args()

    sets = build_sets(
        golden_cases=load_json(Path(args.golden)),
        answer_cases=load_json(Path(args.answers)),
        generation_cases=load_json(Path(args.generation)),
    )
    output_dir = Path(args.output_dir)
    save_json(sets["structured"], output_dir / "structured_eval_cases.json")
    save_json(sets["true_rag"], output_dir / "true_rag_eval_cases.json")
    save_json(sets["beta"], output_dir / "beta_eval_cases.json")
    save_json(sets["judge"], output_dir / "ragas_judge_cases.json")
    save_json(build_manifest(sets), output_dir / "beta_eval_manifest.json")

    print("Built beta eval sets")
    for name, cases in sets.items():
        print(f"{name}: {len(cases)}")


if __name__ == "__main__":
    main()
