from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
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
os.environ["EVAL_VECTORDB_PROVIDER"] = "chroma"
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
from src.retrieval.core.io_utils import load_json, load_yaml, save_json
from src.retrieval.core.retrieval_pipeline import run_retrieval_pipeline
from src.retrieval.core.vector_retriever import get_chroma_collection, load_embedding_model


DEFAULT_CONFIG_PATH = Path("configs/retrieval.yaml")
DEFAULT_CHUNKS_PATH = Path("data/processed/chunks/semantic_chunks.json")
DEFAULT_OUTPUT_PATH = Path("data/processed/metadata/retrieval_debug_failed_cases.json")

DEBUG_CASES = [
    {
        "id": "gen_case_018",
        "query": (
            "Trường mình có chương trình liên kết đào tạo không? "
            "Nó áp dụng cho hình thức vừa làm vừa học như thế nào?"
        ),
        "cohort": "general",
        "expected_terms": ["liên kết đào tạo", "vừa làm vừa học"],
    },
    {
        "id": "gen_case_009",
        "query": "Ai là người chịu trách nhiệm thi hành quyết định của trường?",
        "cohort": "general",
        "expected_terms": ["chịu trách nhiệm", "thi hành quyết định"],
        "note": "Câu có thể mơ hồ vì nhiều quyết định đều có mục thi hành.",
    },
    {
        "id": "gen_case_020",
        "query": "Em bị kỷ luật oan, trường mình có quy định nào về việc khiếu nại không?",
        "cohort": "general",
        "expected_terms": ["kỷ luật", "khiếu nại"],
    },
]


def normalize_text(value: Any) -> str:
    text = str(value or "").lower()
    text = text.replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^\w\s+-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def text_blob(item: dict[str, Any]) -> str:
    metadata = item.get("metadata") or {}
    fields = [
        item.get("chunk_id"),
        item.get("chunk_type"),
        item.get("content"),
        item.get("text"),
        metadata.get("chunk_type"),
        metadata.get("content_type"),
        metadata.get("title"),
        metadata.get("document_title"),
        metadata.get("chapter"),
        metadata.get("article"),
        metadata.get("source_section"),
        metadata.get("unit_name"),
        metadata.get("faculty_or_unit_name"),
        metadata.get("procedure_name"),
        metadata.get("form_name"),
    ]
    return " ".join(str(field) for field in fields if field)


def term_match_flags(item: dict[str, Any], expected_terms: list[str]) -> dict[str, bool]:
    blob = normalize_text(text_blob(item))
    return {term: normalize_text(term) in blob for term in expected_terms}


def has_all_terms(item: dict[str, Any], expected_terms: list[str]) -> bool:
    flags = term_match_flags(item, expected_terms)
    return bool(flags) and all(flags.values())


def summarize_item(
    item: dict[str, Any],
    *,
    expected_terms: list[str],
    rank: int | None = None,
) -> dict[str, Any]:
    metadata = item.get("metadata") or {}
    content = str(item.get("content") or item.get("text") or "")
    summary: dict[str, Any] = {
        "rank": rank,
        "chunk_id": item.get("chunk_id"),
        "chunk_type": item.get("chunk_type") or metadata.get("chunk_type"),
        "content_type": metadata.get("content_type"),
        "cohort": metadata.get("cohort"),
        "document_id": metadata.get("document_id"),
        "source_section": metadata.get("source_section"),
        "source_pages": metadata.get("source_pages"),
        "title": (
            metadata.get("title")
            or metadata.get("article")
            or metadata.get("procedure_name")
            or metadata.get("unit_name")
            or metadata.get("faculty_or_unit_name")
            or metadata.get("form_name")
        ),
        "distance": item.get("distance"),
        "retrieval_purpose": item.get("retrieval_purpose"),
        "rerank": item.get("rerank"),
        "term_matches": term_match_flags(item, expected_terms),
        "preview": content[:550],
    }
    return summary


def scan_corpus_for_terms(
    chunks: list[dict[str, Any]],
    expected_terms: list[str],
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    matches = []
    normalized_terms = [normalize_text(term) for term in expected_terms]
    for item in chunks:
        blob = normalize_text(text_blob(item))
        matched_count = sum(1 for term in normalized_terms if term in blob)
        if matched_count <= 0:
            continue
        matches.append((matched_count, len(blob), item))

    matches.sort(key=lambda row: (-row[0], row[1]))
    return [
        summarize_item(item, expected_terms=expected_terms, rank=index)
        for index, (_, _, item) in enumerate(matches[:limit], start=1)
    ]


def diagnose_case(
    result: dict[str, Any],
    expected_terms: list[str],
    corpus_matches: list[dict[str, Any]],
) -> dict[str, Any]:
    top_items = [
        item
        for item in result.get("retrieved_items", [])
        if isinstance(item, dict)
    ][:5]
    top_has_all = [
        item
        for item in top_items
        if has_all_terms(item, expected_terms)
    ]
    corpus_has_all = [
        item
        for item in corpus_matches
        if all((item.get("term_matches") or {}).values())
    ]
    routing_types = set(result.get("target_chunk_types") or [])

    if not top_items:
        root = "retrieval_empty"
    elif top_has_all:
        root = "answer_or_prompt_layer"
    elif corpus_has_all:
        root = "retrieval_or_rerank_missed_specific_source"
    elif not routing_types:
        root = "router_no_target_chunk_type"
    else:
        root = "ambiguous_or_missing_source_terms"

    return {
        "root_cause_hint": root,
        "correct_like_source_in_top5": bool(top_has_all),
        "correct_like_source_in_corpus_scan": bool(corpus_has_all),
        "top5_chunk_ids": [item.get("chunk_id") for item in top_items],
    }


def debug_case(
    case: dict[str, Any],
    *,
    model: Any,
    collection: Any,
    config: dict[str, Any],
    scoring_tables: list[dict[str, Any]],
    formula_rules: list[dict[str, Any]],
    form_templates: list[dict[str, Any]],
    program_directory: list[dict[str, Any]],
    entity_registry: list[dict[str, Any]],
    expansion_rules: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
) -> dict[str, Any]:
    expected_terms = [str(term) for term in case.get("expected_terms") or []]
    result = run_retrieval_pipeline(
        query=str(case["query"]),
        model=model,
        collection=collection,
        scoring_tables=scoring_tables,
        formula_rules=formula_rules,
        form_templates=form_templates,
        program_directory=program_directory,
        top_k=config["retrieval"]["default_top_k"],
        batch_size=config["embedding"]["batch_size"],
        entity_registry=entity_registry,
        expansion_rules=expansion_rules,
        normalize_embeddings=config["embedding"]["normalize_embeddings"],
        cohort=None if case.get("cohort") == "general" else case.get("cohort"),
        candidate_multiplier=config["retrieval"].get("candidate_multiplier", 5),
        min_candidates=config["retrieval"].get("min_candidates", 25),
    )

    top_items = [
        summarize_item(item, expected_terms=expected_terms, rank=index)
        for index, item in enumerate(result.get("retrieved_items", [])[:5], start=1)
    ]
    corpus_matches = scan_corpus_for_terms(chunks, expected_terms)

    return {
        "id": case.get("id"),
        "query": case.get("query"),
        "cohort": case.get("cohort"),
        "note": case.get("note"),
        "expected_terms": expected_terms,
        "router": {
            "router_mode": "rule_based_offline",
            "intent": result.get("intent"),
            "strategy": result.get("strategy"),
            "target_chunk_types": result.get("target_chunk_types"),
            "needs_clarification": result.get("needs_clarification"),
            "clarification_question": result.get("clarification_question"),
        },
        "retrieval_query": result.get("retrieval_query"),
        "detected_entities": result.get("detected_entities"),
        "retrieval_plan": result.get("retrieval_plan"),
        "diagnosis": diagnose_case(result, expected_terms, corpus_matches),
        "top_items_after_rerank": top_items,
        "corpus_term_scan": corpus_matches,
        "citations": result.get("citations", [])[:5],
    }


def load_cases(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return DEBUG_CASES
    data = load_json(path)
    if not isinstance(data, list):
        raise ValueError("Case file must contain a JSON list.")
    return data


def main() -> None:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="Debug router/retrieval/rerank for known failed Judge cases."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--cases", type=Path, default=None)
    parser.add_argument("--chunks", type=Path, default=DEFAULT_CHUNKS_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    config = load_yaml(args.config)
    cases = load_cases(args.cases)
    chunks = load_json(args.chunks)

    entity_registry = load_json(Path(config["input"]["entity_registry"]))
    expansion_rules = load_json(Path(config["input"]["query_expansion_rules"]))
    scoring_tables = load_json(Path(config["input"]["scoring_tables"]))
    formula_rules = load_json(Path(config["input"]["formula_rules"]))
    form_templates = load_json(Path(config["input"]["form_templates"]))
    program_directory = load_json(Path(config["input"]["program_directory"]))

    model = load_embedding_model(config["embedding"]["model_name"])
    collection = get_chroma_collection(
        persist_dir=config["vectorstore"]["persist_dir"],
        collection_name=config["vectorstore"]["collection_name"],
    )

    results = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case.get('id')}: {case.get('query')}")
        report = debug_case(
            case,
            model=model,
            collection=collection,
            config=config,
            scoring_tables=scoring_tables,
            formula_rules=formula_rules,
            form_templates=form_templates,
            program_directory=program_directory,
            entity_registry=entity_registry,
            expansion_rules=expansion_rules,
            chunks=chunks,
        )
        diagnosis = report["diagnosis"]
        print(
            "  ",
            report["router"]["intent"],
            report["router"]["strategy"],
            diagnosis["root_cause_hint"],
        )
        results.append(report)

    save_json(
        {
            "case_count": len(results),
            "router_mode": "rule_based_offline",
            "ai_router_disabled": True,
            "output": [item["id"] for item in results],
            "cases": results,
        },
        args.output,
    )
    print(f"Saved debug report: {args.output}")


if __name__ == "__main__":
    main()
