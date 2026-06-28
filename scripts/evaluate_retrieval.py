from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from src.common.console import configure_utf8_stdio


DEFAULT_CONFIG_PATH = Path("configs/retrieval.yaml")
DEFAULT_GOLDEN_PATH = Path("data/eval/golden_queries.json")
DEFAULT_OUTPUT_PATH = Path("data/processed/metadata/golden_retrieval_eval_report.json")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def top_chunk_ids(result: dict[str, Any]) -> list[str]:
    return [
        str(item.get("chunk_id"))
        for item in result.get("retrieved_items", [])
        if item.get("chunk_id")
    ]


def reciprocal_rank(actual_ids: list[str], expected_ids: list[str]) -> float:
    expected = set(expected_ids)
    if not expected:
        return 0.0

    for index, chunk_id in enumerate(actual_ids, start=1):
        if chunk_id in expected:
            return 1.0 / index
    return 0.0


def has_hit_at_k(actual_ids: list[str], expected_ids: list[str], k: int) -> bool:
    if not expected_ids:
        return False
    return bool(set(actual_ids[:k]) & set(expected_ids))


def evaluate_case(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    actual_ids = top_chunk_ids(result)
    expected_ids = [str(item) for item in case.get("expected_chunk_ids", [])]

    structured_result = result.get("structured_result") or {}
    tool_result = result.get("tool_result") or {}

    return {
        "query": case["query"],
        "expected_intent": case.get("expected_intent"),
        "actual_intent": result.get("intent"),
        "intent_match": result.get("intent") == case.get("expected_intent"),
        "expected_strategy": case.get("expected_strategy"),
        "actual_strategy": result.get("strategy"),
        "strategy_match": result.get("strategy") == case.get("expected_strategy"),
        "expected_chunk_ids": expected_ids,
        "top_chunk_ids": actual_ids[:5],
        "hit_at_1": has_hit_at_k(actual_ids, expected_ids, 1),
        "hit_at_3": has_hit_at_k(actual_ids, expected_ids, 3),
        "hit_at_5": has_hit_at_k(actual_ids, expected_ids, 5),
        "reciprocal_rank": reciprocal_rank(actual_ids, expected_ids),
        "expected_lookup_type": case.get("expected_lookup_type"),
        "actual_lookup_type": structured_result.get("lookup_type"),
        "lookup_match": _optional_match(
            case.get("expected_lookup_type"),
            structured_result.get("lookup_type"),
        ),
        "expected_tool_name": case.get("expected_tool_name"),
        "actual_tool_name": tool_result.get("tool_name"),
        "tool_match": _optional_match(
            case.get("expected_tool_name"),
            tool_result.get("tool_name"),
        ),
    }


def build_summary(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    retrieval_cases = [
        item for item in case_results if item.get("expected_chunk_ids")
    ]
    lookup_cases = [
        item for item in case_results if item.get("expected_lookup_type")
    ]
    tool_cases = [
        item for item in case_results if item.get("expected_tool_name")
    ]

    return {
        "total_cases": len(case_results),
        "retrieval_cases": len(retrieval_cases),
        "intent_accuracy": _mean_bool(case_results, "intent_match"),
        "strategy_accuracy": _mean_bool(case_results, "strategy_match"),
        "hit_at_1": _mean_bool(retrieval_cases, "hit_at_1"),
        "hit_at_3": _mean_bool(retrieval_cases, "hit_at_3"),
        "hit_at_5": _mean_bool(retrieval_cases, "hit_at_5"),
        "mrr": _mean_float(retrieval_cases, "reciprocal_rank"),
        "lookup_accuracy": _mean_bool(lookup_cases, "lookup_match"),
        "tool_accuracy": _mean_bool(tool_cases, "tool_match"),
    }


def run_evaluation(config_path: Path, golden_path: Path) -> dict[str, Any]:
    from src.retrieval.core.io_utils import load_json as load_project_json
    from src.retrieval.core.io_utils import load_yaml
    from src.retrieval.core.retrieval_pipeline import run_retrieval_pipeline
    from src.retrieval.core.vector_retriever import (
        get_chroma_collection,
        load_embedding_model,
    )

    config = load_yaml(config_path)
    cases = load_json(golden_path)

    scoring_tables = load_project_json(Path(config["input"]["scoring_tables"]))
    formula_rules = load_project_json(Path(config["input"]["formula_rules"]))
    entity_registry = load_project_json(Path(config["input"]["entity_registry"]))
    expansion_rules = load_project_json(Path(config["input"]["query_expansion_rules"]))

    model = load_embedding_model(config["embedding"]["model_name"])
    collection = get_chroma_collection(
        persist_dir=config["vectorstore"]["persist_dir"],
        collection_name=config["vectorstore"]["collection_name"],
    )

    case_results = []
    for index, case in enumerate(cases, start=1):
        query = str(case["query"])
        print(f"[{index}/{len(cases)}] {query}")
        result = run_retrieval_pipeline(
            query=query,
            model=model,
            collection=collection,
            scoring_tables=scoring_tables,
            formula_rules=formula_rules,
            entity_registry=entity_registry,
            expansion_rules=expansion_rules,
            top_k=config["retrieval"]["default_top_k"],
            batch_size=config["embedding"]["batch_size"],
            normalize_embeddings=config["embedding"]["normalize_embeddings"],
        )
        case_results.append(evaluate_case(case, result))

    return {
        "evaluation": "golden_retrieval_eval",
        "config_path": str(config_path),
        "golden_path": str(golden_path),
        "summary": build_summary(case_results),
        "cases": case_results,
    }


def main() -> None:
    configure_utf8_stdio()

    parser = argparse.ArgumentParser(description="Evaluate retrieval against golden queries.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--golden", default=str(DEFAULT_GOLDEN_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--fail-under-hit3", type=float, default=None)
    args = parser.parse_args()

    report = run_evaluation(
        config_path=Path(args.config),
        golden_path=Path(args.golden),
    )
    save_json(report, Path(args.output))

    summary = report["summary"]
    print("\nGolden retrieval evaluation")
    for key, value in summary.items():
        print(f"{key}: {value}")
    print(f"Saved report: {args.output}")

    if args.fail_under_hit3 is not None and summary["hit_at_3"] < args.fail_under_hit3:
        sys.exit(1)


def _optional_match(expected: Any, actual: Any) -> bool | None:
    if expected is None:
        return None
    return actual == expected


def _mean_bool(items: list[dict[str, Any]], field: str) -> float | None:
    values = [item.get(field) for item in items if item.get(field) is not None]
    if not values:
        return None
    return round(sum(1 for value in values if value is True) / len(values), 4)


def _mean_float(items: list[dict[str, Any]], field: str) -> float | None:
    values = [float(item[field]) for item in items if item.get(field) is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 4)


if __name__ == "__main__":
    main()
