from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

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
DEFAULT_GOLDEN_PATH = Path("data/eval/final_true_rag_holdout_v7.json")
DEFAULT_OUTPUT_PATH = Path("data/processed/metadata/true_rag_retrieval_eval_report.json")
REGULATION_SCOPE_TYPES = {"regulation", "regulation_sections", "regulation_text"}
REGULATION_COMPATIBLE_STRATEGIES = {
    "semantic",
    "semantic_filtered",
    "semantic_filtered_rerank",
    "hybrid",
}


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


def normalize_content_type(value: Any) -> str:
    aliases = {
        "faculty": "faculty_directory",
        "form": "form_templates",
        "office": "office_directory",
        "procedure": "procedures",
        "program": "program_directory",
        "regulation": "regulation_sections",
    }
    text = str(value or "").strip()
    return aliases.get(text, text)


def normalize_chunk_type(value: Any) -> str:
    aliases = {
        "faculty": "faculty_directory",
        "form_templates": "form",
        "office": "office_directory",
        "procedures": "procedure",
        "program": "program_directory",
        "regulation_text": "regulation",
        "regulation_sections": "regulation",
    }
    text = str(value or "").strip()
    return aliases.get(text, text)


def metadata_value(item: dict[str, Any], key: str) -> Any:
    metadata = item.get("metadata") or {}
    if key in metadata and metadata.get(key) is not None:
        return metadata.get(key)
    return item.get(key)


def item_identity_values(item: dict[str, Any]) -> set[str]:
    values = {
        item.get("chunk_id"),
        item.get("parent_section_id"),
        item.get("parent_chunk_id"),
        metadata_value(item, "chunk_id"),
        metadata_value(item, "parent_section_id"),
        metadata_value(item, "parent_chunk_id"),
    }
    return {str(value).strip() for value in values if str(value or "").strip()}


def item_chunk_type(item: dict[str, Any]) -> str:
    return normalize_chunk_type(
        metadata_value(item, "chunk_type")
        or metadata_value(item, "content_type")
    )


def has_retrieval_expectation(case: dict[str, Any]) -> bool:
    if str(case.get("eval_type") or "").strip() == "structured":
        return False
    return any(
        case.get(key)
        for key in (
            "expected_chunk_ids",
            "expected_parent_section_ids",
            "expected_content_types",
            "expected_document_id",
            "expected_source_sections",
            "expected_source_pages",
        )
    )


def case_matches_scope(case: dict[str, Any], scope: str) -> bool:
    if scope == "all":
        return True
    if scope != "regulation-v7":
        raise ValueError(f"Unsupported evaluation scope: {scope}")

    content_types = set()
    if case.get("content_type"):
        content_types.add(normalize_content_type(case.get("content_type")))
    content_types.update(
        normalize_content_type(value)
        for value in expected_list(case, "expected_content_types")
    )
    content_types.update(
        normalize_chunk_type(value)
        for value in expected_list(case, "expected_content_types")
    )
    return bool(content_types & REGULATION_SCOPE_TYPES)


def cohort_arg(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"all", "general"}:
        return None
    return text


def metadata_relevance(item: dict[str, Any], case: dict[str, Any]) -> bool:
    expected_ids = set(expected_list(case, "expected_chunk_ids"))
    item_ids = item_identity_values(item)
    if expected_ids and item_ids & expected_ids:
        return True

    expected_parent_ids = set(expected_list(case, "expected_parent_section_ids"))
    if expected_parent_ids and item_ids & expected_parent_ids:
        return True

    checks: list[bool] = []

    expected_content_types = {
        normalize_chunk_type(item)
        for item in expected_list(case, "expected_content_types")
    }
    if expected_content_types:
        checks.append(item_chunk_type(item) in expected_content_types)

    expected_cohort = str(case.get("expected_cohort") or case.get("cohort") or "").strip()
    if expected_cohort and expected_cohort.lower() not in {"all", "general"}:
        checks.append(str(metadata_value(item, "cohort")) == expected_cohort)

    expected_document_id = str(case.get("expected_document_id") or "").strip()
    if expected_document_id:
        checks.append(str(metadata_value(item, "document_id")) == expected_document_id)

    expected_sections = set(expected_list(case, "expected_source_sections"))
    if expected_sections:
        actual_section = str(metadata_value(item, "source_section") or "").strip()
        if actual_section:
            checks.append(actual_section in expected_sections)
        else:
            actual_identity = " ".join(item_ids)
            checks.append(section_identity_matches(actual_identity, expected_sections))

    expected_pages = set(parse_source_pages(case.get("expected_source_pages")))
    if expected_pages:
        actual_pages = set(parse_source_pages(metadata_value(item, "source_pages")))
        checks.append(bool(expected_pages & actual_pages))

    return bool(checks) and all(checks)


def section_identity_matches(actual_identity: str, expected_sections: set[str]) -> bool:
    actual = normalize_for_section_match(actual_identity)
    if not actual:
        return False
    for expected in expected_sections:
        expected_normalized = normalize_for_section_match(expected)
        marker = extract_article_marker(expected_normalized)
        if marker and marker in actual:
            return True
    return False


def normalize_for_section_match(value: Any) -> str:
    text = str(value or "").lower()
    text = (
        text.replace("đ", "d")
        .replace("Đ", "d")
        .replace("_", " ")
        .replace("-", " ")
    )
    return re.sub(r"[^a-z0-9]+", "", text)


def extract_article_marker(normalized_text: str) -> str:
    match = re.search(r"dieu0*(\d+)", normalized_text)
    if not match:
        return ""
    return f"dieu{match.group(1)}"


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
        "id": case.get("id"),
        "tags": expected_list(case, "tags"),
        "eval_type": case.get("eval_type") or (
            "true_rag" if has_retrieval_expectation(case) else "structured"
        ),
        "content_type": case.get("content_type"),
        "cohort": case.get("cohort"),
        "expected_intent": case.get("expected_intent"),
        "actual_intent": result.get("intent"),
        "intent_match": result.get("intent") == case.get("expected_intent"),
        "expected_strategy": case.get("expected_strategy"),
        "actual_strategy": result.get("strategy"),
        "strategy_match": strategy_matches(case, result),
        "expected_chunk_ids": expected_ids,
        "expected_parent_section_ids": expected_list(case, "expected_parent_section_ids"),
        "expected_content_types": expected_list(case, "expected_content_types"),
        "expected_cohort": case.get("expected_cohort") or case.get("cohort"),
        "expected_document_id": case.get("expected_document_id"),
        "expected_source_sections": expected_list(case, "expected_source_sections"),
        "expected_source_pages": parse_source_pages(case.get("expected_source_pages")),
        "top_chunk_ids": actual_ids[:5],
        "top_metadata": [
            {
                "chunk_type": metadata_value(item, "chunk_type"),
                "content_type": metadata_value(item, "content_type"),
                "normalized_type": item_chunk_type(item),
                "cohort": metadata_value(item, "cohort"),
                "document_id": metadata_value(item, "document_id"),
                "chunk_id": item.get("chunk_id") or metadata_value(item, "chunk_id"),
                "parent_section_id": metadata_value(item, "parent_section_id"),
                "parent_chunk_id": metadata_value(item, "parent_chunk_id"),
                "source_section": metadata_value(item, "source_section"),
                "source_pages": parse_source_pages(metadata_value(item, "source_pages")),
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
    true_rag_cases = [
        item for item in case_results if item.get("eval_type") == "true_rag"
    ]
    structured_tool_cases = [
        item for item in case_results if item.get("eval_type") == "structured"
    ]
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
        "true_rag_cases": len(true_rag_cases),
        "structured_tool_cases": len(structured_tool_cases),
        "retrieval_cases": len(retrieval_cases),
        "intent_accuracy": _mean_bool(case_results, "intent_match"),
        "strategy_accuracy": _mean_bool(case_results, "strategy_match"),
        "true_rag_summary": _retrieval_metric_summary(retrieval_cases),
        "structured_tool_summary": _structured_tool_summary(structured_tool_cases),
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
        "tag_breakdown": _tag_breakdown(retrieval_cases),
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
        "true_rag_cases": sum(
            1 for item in case_results if item.get("eval_type") == "true_rag"
        ),
        "structured_tool_cases": sum(
            1 for item in case_results if item.get("eval_type") == "structured"
        ),
        "intent_accuracy": _mean_bool(case_results, "intent_match"),
        "strategy_accuracy": _mean_bool(case_results, "strategy_match"),
        "hit_at_3": _mean_bool(retrieval_cases, "hit_at_3"),
        "mrr": _mean_float(retrieval_cases, "reciprocal_rank"),
        "ndcg_at_5": _mean_float(retrieval_cases, "ndcg_at_5"),
        "lookup_accuracy": _mean_bool(lookup_cases, "lookup_match"),
        "tool_accuracy": _mean_bool(tool_cases, "tool_match"),
    }


def _retrieval_metric_summary(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "cases": len(case_results),
        "hit_at_1": _mean_bool(case_results, "hit_at_1"),
        "hit_at_3": _mean_bool(case_results, "hit_at_3"),
        "hit_at_5": _mean_bool(case_results, "hit_at_5"),
        "mrr": _mean_float(case_results, "reciprocal_rank"),
        "ndcg_at_5": _mean_float(case_results, "ndcg_at_5"),
    }


def _structured_tool_summary(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    lookup_cases = [
        item for item in case_results if item.get("expected_lookup_type")
    ]
    tool_cases = [
        item for item in case_results if item.get("expected_tool_name")
    ]
    return {
        "cases": len(case_results),
        "lookup_cases": len(lookup_cases),
        "tool_cases": len(tool_cases),
        "lookup_accuracy": _mean_bool(lookup_cases, "lookup_match"),
        "tool_accuracy": _mean_bool(tool_cases, "tool_match"),
    }


def _content_type_breakdown(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in case_results:
        content_types = item.get("expected_content_types") or [
            item.get("content_type") or "unknown"
        ]
        for content_type in content_types:
            groups[_normalize_report_content_type(str(content_type))].append(item)

    return {
        content_type: {
            "total_cases": len(items),
            "hit_at_3": _mean_bool(items, "hit_at_3"),
            "mrr": _mean_float(items, "reciprocal_rank"),
            "ndcg_at_5": _mean_float(items, "ndcg_at_5"),
        }
        for content_type, items in sorted(groups.items())
    }


def _normalize_report_content_type(content_type: str) -> str:
    aliases = {
        "faculty": "faculty_directory",
        "form": "form_templates",
        "office": "office_directory",
        "procedure": "procedures",
        "program": "program_directory",
        "regulation": "regulation_sections",
        "scoring_table": "scoring_tables",
    }
    return aliases.get(content_type, content_type)


def _tag_breakdown(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in case_results:
        tags = item.get("tags") or []
        for tag in tags:
            groups[str(tag)].append(item)

    return {
        tag: {
            "total_cases": len(items),
            "hit_at_3": _mean_bool(items, "hit_at_3"),
            "mrr": _mean_float(items, "reciprocal_rank"),
            "ndcg_at_5": _mean_float(items, "ndcg_at_5"),
        }
        for tag, items in sorted(groups.items())
    }


def run_evaluation(config_path: Path, golden_path: Path, scope: str = "all") -> dict[str, Any]:
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
    from src.retrieval.core.hybrid_pipeline import run_hybrid_retrieval_pipeline as run_retrieval_pipeline
    from src.retrieval.core.vector_retriever import (
        get_chroma_collection,
        load_embedding_model,
    )

    config = load_yaml(config_path)
    all_cases = load_json(golden_path)
    cases = [case for case in all_cases if case_matches_scope(case, scope)]

    scoring_tables = load_project_json(Path(config["input"]["scoring_tables"]))
    formula_rules = load_project_json(Path(config["input"]["formula_rules"]))
    form_templates = load_project_json(Path(config["input"]["form_templates"]))
    program_directory = load_project_json(Path(config["input"]["program_directory"]))
    entity_registry = load_project_json(Path(config["input"]["entity_registry"]))
    expansion_rules = load_project_json(Path(config["input"]["query_expansion_rules"]))

    model = None
    collection = None

    from tqdm import tqdm
    case_results = []
    for index, case in enumerate(tqdm(cases, desc="Evaluating True RAG", unit="case"), start=1):
        query = str(case["query"])
        # Bỏ print cũ để TQDM tự hiển thị thanh tiến độ mượt mà
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
            candidate_multiplier=config["retrieval"].get("candidate_multiplier", 5),
            min_candidates=config["retrieval"].get("min_candidates", 25),
        )
        case_results.append(evaluate_case(case, result))

    return {
        "evaluation": "golden_retrieval_eval",
        "scope": scope,
        "config_path": str(config_path),
        "golden_path": str(golden_path),
        "total_cases_before_scope_filter": len(all_cases),
        "summary": build_summary(case_results),
        "cases": case_results,
    }


def main() -> None:
    configure_utf8_stdio()

    parser = argparse.ArgumentParser(description="Evaluate retrieval against golden queries.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--golden", default=str(DEFAULT_GOLDEN_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument(
        "--scope",
        choices=["all", "regulation-v7"],
        default="all",
        help="Use regulation-v7 to keep only regulation_text/regulation_sections cases in the headline retrieval report.",
    )
    parser.add_argument("--fail-under-hit3", type=float, default=None)
    args = parser.parse_args()

    report = run_evaluation(
        config_path=Path(args.config),
        golden_path=Path(args.golden),
        scope=args.scope,
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


def strategy_matches(case: dict[str, Any], result: dict[str, Any]) -> bool:
    expected = case.get("expected_strategy")
    actual = result.get("strategy")
    if expected == actual:
        return True

    content_types = set()
    if case.get("content_type"):
        content_types.add(normalize_content_type(case.get("content_type")))
    content_types.update(
        normalize_content_type(value)
        for value in expected_list(case, "expected_content_types")
    )
    content_types.update(
        normalize_chunk_type(value)
        for value in expected_list(case, "expected_content_types")
    )
    is_regulation_case = bool(content_types & REGULATION_SCOPE_TYPES)
    return (
        is_regulation_case
        and actual == "hybrid_graph_retrieval"
        and str(expected or "") in REGULATION_COMPATIBLE_STRATEGIES
    )


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
