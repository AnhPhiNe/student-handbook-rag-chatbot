from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_API_KEY"] = ""
os.environ["LANGCHAIN_API_KEY"] = ""
os.environ["MONGODB_PARENT_LOOKUP_ENABLED"] = "false"
os.environ["STUDENT_RAG_DISABLE_AI_ROUTER"] = "1"
os.environ["STUDENT_RAG_OFFLINE_EVAL"] = "1"


def _disable_langsmith_tracing() -> None:
    try:
        import langsmith
    except Exception:
        return

    def no_op_traceable(*args: Any, **kwargs: Any) -> Any:
        if args and callable(args[0]) and len(args) == 1 and not kwargs:
            return args[0]

        def decorator(func: Any) -> Any:
            return func

        return decorator

    langsmith.traceable = no_op_traceable


_disable_langsmith_tracing()

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


def top_retrieved_items(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in result.get("retrieved_items", [])
        if isinstance(item, dict)
    ]


def parse_source_pages(value: Any) -> list[int]:
    if value is None:
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, list):
        pages: list[int] = []
        for item in value:
            pages.extend(parse_source_pages(item))
        return pages
    if isinstance(value, str):
        pages: list[int] = []
        for item in value.split(","):
            item = item.strip()
            if item.isdigit():
                pages.append(int(item))
        return pages
    return []


def expected_list(case: dict[str, Any], key: str) -> list[str]:
    value = case.get(key)
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def has_retrieval_expectation(case: dict[str, Any]) -> bool:
    return any(
        case.get(key)
        for key in (
            "expected_chunk_ids",
            "expected_content_types",
            "expected_document_id",
            "expected_source_sections",
            "expected_source_pages",
        )
    )


def cohort_arg(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "all":
        return None
    return text


def metadata_relevance(item: dict[str, Any], case: dict[str, Any]) -> bool:
    metadata = item.get("metadata") or {}

    expected_ids = set(expected_list(case, "expected_chunk_ids"))
    if expected_ids and str(item.get("chunk_id")) in expected_ids:
        return True

    checks: list[bool] = []

    expected_content_types = set(expected_list(case, "expected_content_types"))
    if expected_content_types:
        checks.append(str(metadata.get("chunk_type")) in expected_content_types)

    expected_cohort = str(case.get("expected_cohort") or case.get("cohort") or "").strip()
    if expected_cohort and expected_cohort.lower() != "all":
        checks.append(str(metadata.get("cohort")) == expected_cohort)

    expected_document_id = str(case.get("expected_document_id") or "").strip()
    if expected_document_id:
        checks.append(str(metadata.get("document_id")) == expected_document_id)

    expected_sections = set(expected_list(case, "expected_source_sections"))
    if expected_sections:
        checks.append(str(metadata.get("source_section")) in expected_sections)

    expected_pages = set(parse_source_pages(case.get("expected_source_pages")))
    if expected_pages:
        actual_pages = set(parse_source_pages(metadata.get("source_pages")))
        checks.append(bool(expected_pages & actual_pages))

    return bool(checks) and all(checks)


def relevance_flags(items: list[dict[str, Any]], case: dict[str, Any]) -> list[bool]:
    return [metadata_relevance(item, case) for item in items]


def reciprocal_rank(flags: list[bool]) -> float:
    if not flags:
        return 0.0

    for index, is_relevant in enumerate(flags, start=1):
        if is_relevant:
            return 1.0 / index
    return 0.0


def ndcg_at_k(flags: list[bool], k: int) -> float:
    if not flags:
        return 0.0

    dcg = 0.0
    for index, is_relevant in enumerate(flags[:k], start=1):
        if is_relevant:
            dcg += 1.0 / math.log2(index + 1)

    ideal_hits = min(sum(1 for flag in flags if flag), k)
    idcg = sum(1.0 / math.log2(index + 1) for index in range(1, ideal_hits + 1))
    if idcg == 0:
        return 0.0
    return round(dcg / idcg, 4)


def has_hit_at_k(flags: list[bool], k: int) -> bool:
    return any(flags[:k])


def evaluate_case(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    actual_ids = top_chunk_ids(result)
    expected_ids = [str(item) for item in case.get("expected_chunk_ids", [])]
    retrieved_items = top_retrieved_items(result)
    flags = relevance_flags(retrieved_items, case)
    retrieval_case = has_retrieval_expectation(case)

    structured_result = result.get("structured_result") or {}
    tool_result = result.get("tool_result") or {}

    return {
        "query": case["query"],
        "cohort": case.get("cohort"),
        "expected_intent": case.get("expected_intent"),
        "actual_intent": result.get("intent"),
        "intent_match": result.get("intent") == case.get("expected_intent"),
        "expected_strategy": case.get("expected_strategy"),
        "actual_strategy": result.get("strategy"),
        "strategy_match": result.get("strategy") == case.get("expected_strategy"),
        "expected_chunk_ids": expected_ids,
        "expected_content_types": expected_list(case, "expected_content_types"),
        "expected_cohort": case.get("expected_cohort") or case.get("cohort"),
        "expected_document_id": case.get("expected_document_id"),
        "expected_source_sections": expected_list(case, "expected_source_sections"),
        "expected_source_pages": parse_source_pages(case.get("expected_source_pages")),
        "top_chunk_ids": actual_ids[:5],
        "top_metadata": [
            {
                "chunk_type": (item.get("metadata") or {}).get("chunk_type"),
                "cohort": (item.get("metadata") or {}).get("cohort"),
                "document_id": (item.get("metadata") or {}).get("document_id"),
                "source_section": (item.get("metadata") or {}).get("source_section"),
                "source_pages": parse_source_pages(
                    (item.get("metadata") or {}).get("source_pages")
                ),
            }
            for item in retrieved_items[:5]
        ],
        "is_retrieval_case": retrieval_case,
        "hit_at_1": has_hit_at_k(flags, 1) if retrieval_case else None,
        "hit_at_3": has_hit_at_k(flags, 3) if retrieval_case else None,
        "hit_at_5": has_hit_at_k(flags, 5) if retrieval_case else None,
        "reciprocal_rank": reciprocal_rank(flags) if retrieval_case else None,
        "ndcg_at_5": ndcg_at_k(flags, 5) if retrieval_case else None,
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
        item for item in case_results if item.get("is_retrieval_case")
    ]
    lookup_cases = [
        item for item in case_results if item.get("expected_lookup_type")
    ]
    tool_cases = [
        item for item in case_results if item.get("expected_tool_name")
    ]
    by_cohort: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in case_results:
        by_cohort[str(item.get("cohort") or "all")].append(item)

    return {
        "total_cases": len(case_results),
        "retrieval_cases": len(retrieval_cases),
        "intent_accuracy": _mean_bool(case_results, "intent_match"),
        "strategy_accuracy": _mean_bool(case_results, "strategy_match"),
        "hit_at_1": _mean_bool(retrieval_cases, "hit_at_1"),
        "hit_at_3": _mean_bool(retrieval_cases, "hit_at_3"),
        "hit_at_5": _mean_bool(retrieval_cases, "hit_at_5"),
        "mrr": _mean_float(retrieval_cases, "reciprocal_rank"),
        "ndcg_at_5": _mean_float(retrieval_cases, "ndcg_at_5"),
        "lookup_accuracy": _mean_bool(lookup_cases, "lookup_match"),
        "tool_accuracy": _mean_bool(tool_cases, "tool_match"),
        "cohort_breakdown": {
            cohort: _summary_for_group(items)
            for cohort, items in sorted(by_cohort.items())
        },
        "content_type_breakdown": _content_type_breakdown(retrieval_cases),
    }


def _summary_for_group(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    retrieval_cases = [
        item for item in case_results if item.get("is_retrieval_case")
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
        "hit_at_3": _mean_bool(retrieval_cases, "hit_at_3"),
        "mrr": _mean_float(retrieval_cases, "reciprocal_rank"),
        "ndcg_at_5": _mean_float(retrieval_cases, "ndcg_at_5"),
        "lookup_accuracy": _mean_bool(lookup_cases, "lookup_match"),
        "tool_accuracy": _mean_bool(tool_cases, "tool_match"),
    }


def _content_type_breakdown(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in case_results:
        content_types = item.get("expected_content_types") or ["unknown"]
        for content_type in content_types:
            groups[str(content_type)].append(item)

    return {
        content_type: {
            "total_cases": len(items),
            "hit_at_3": _mean_bool(items, "hit_at_3"),
            "mrr": _mean_float(items, "reciprocal_rank"),
            "ndcg_at_5": _mean_float(items, "ndcg_at_5"),
        }
        for content_type, items in sorted(groups.items())
    }


def run_evaluation(config_path: Path, golden_path: Path) -> dict[str, Any]:
    os.environ["EVAL_VECTORDB_PROVIDER"] = "chroma"
    os.environ["STUDENT_RAG_DISABLE_REDIS"] = "1"
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGSMITH_API_KEY"] = ""
    os.environ["LANGCHAIN_API_KEY"] = ""
    os.environ["MONGODB_PARENT_LOOKUP_ENABLED"] = "false"
    os.environ["STUDENT_RAG_DISABLE_AI_ROUTER"] = "1"
    os.environ["STUDENT_RAG_OFFLINE_EVAL"] = "1"

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
    form_templates = load_project_json(Path(config["input"]["form_templates"]))
    program_directory = load_project_json(Path(config["input"]["program_directory"]))
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
        cohort = case.get("cohort")
        result = run_retrieval_pipeline(
            query=query,
            model=model,
            collection=collection,
            scoring_tables=scoring_tables,
            formula_rules=formula_rules,
            form_templates=form_templates,
            program_directory=program_directory,
            entity_registry=entity_registry,
            expansion_rules=expansion_rules,
            top_k=config["retrieval"]["default_top_k"],
            batch_size=config["embedding"]["batch_size"],
            normalize_embeddings=config["embedding"]["normalize_embeddings"],
        cohort=cohort_arg(cohort),
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
