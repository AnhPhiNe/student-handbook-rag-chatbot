from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
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

from src.common.console import configure_utf8_stdio
from src.generation.context_allocation import (
    ContextAllocationConfig,
    build_context_for_prompt,
)
from src.generation.evidence_selection import (
    format_evidence_for_prompt,
    select_evidence_blocks,
)
from src.generation.io_utils import load_yaml
from src.retrieval.core.hybrid_pipeline import (
    run_hybrid_retrieval_pipeline as run_retrieval_pipeline,
)


DEFAULT_CASES_PATH = Path("data/eval/evidence_regression_cases.json")
DEFAULT_CONFIG_PATH = Path("configs/answer_generation.yaml")
DEFAULT_OUTPUT_PATH = Path("data/processed/metadata/evidence_selection_eval_report.json")
EVIDENCE_MARKERS = (
    "THÔNG TIN TRỌNG TÂM TỪ NGUỒN",
    "ĐIỀU KIỆN / TRƯỜNG HỢP / MỐC SỐ LIỆU",
    "BẢNG/DÒNG ĐÃ GOM TỪ NGUỒN",
)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        f.write("\n")


def normalize_text(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return " ".join(text.lower().split())


def contains_all(text: str, facts: list[str]) -> bool:
    normalized = normalize_text(text)
    return all(normalize_text(fact) in normalized for fact in facts)


def contains_any(text: str, values: list[str]) -> bool:
    normalized = normalize_text(text)
    return any(normalize_text(value) in normalized for value in values if value)


def cohort_arg(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or text.lower() in {"all", "general"}:
        return None
    return text


def _context_config(config: dict[str, Any], *, evidence_enabled: bool) -> ContextAllocationConfig:
    context_config = dict(config.get("context_allocation") or {})
    evidence_config = dict(context_config.get("evidence_selection") or {})
    evidence_config["enabled"] = bool(evidence_enabled)
    context_config["evidence_selection"] = evidence_config
    return ContextAllocationConfig.from_config(context_config)


def _selected_evidence(
    retrieval_result: dict[str, Any],
    query: str,
    evidence_config: dict[str, Any],
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in retrieval_result.get("retrieved_items") or []:
        if not isinstance(item, dict):
            continue
        for block in select_evidence_blocks(
            item=item,
            query=query,
            config=evidence_config,
        ):
            evidence_id = str(block.get("evidence_id") or "")
            if evidence_id and evidence_id in seen:
                continue
            if evidence_id:
                seen.add(evidence_id)
            blocks.append(block)
    return blocks


def _citation_text(retrieval_result: dict[str, Any]) -> str:
    return json.dumps(
        retrieval_result.get("citations") or [],
        ensure_ascii=False,
        default=str,
    )


def _retrieved_text(retrieval_result: dict[str, Any]) -> str:
    return "\n\n".join(
        str(item.get("content") or "")
        for item in retrieval_result.get("retrieved_items") or []
        if isinstance(item, dict)
    )


def _source_blob(source: dict[str, Any]) -> str:
    metadata = source.get("metadata") or {}
    keys = (
        "chunk_id",
        "_id",
        "document_id",
        "cohort",
        "parent_section_id",
        "source_section",
        "section_title",
        "title",
        "source_label",
        "chunk_type",
        "content_type",
        "content",
        "document",
        "text",
    )
    values: list[str] = []
    for key in keys:
        values.append(str(source.get(key) or ""))
        values.append(str(metadata.get(key) or ""))
    return " ".join(values)


def _sources_correct(sources: list[dict[str, Any]], case: dict[str, Any]) -> bool | None:
    expected_keywords = [str(item) for item in case.get("expected_source_keywords") or []]
    expected_document_id = str(case.get("expected_document_id") or "").strip()
    expected_cohort = str(case.get("expected_cohort") or case.get("cohort") or "").strip()
    if not expected_keywords and not expected_document_id and not expected_cohort:
        return None
    for source in sources:
        if not isinstance(source, dict):
            continue
        metadata = source.get("metadata") or {}
        source_blob = _source_blob(source)
        if expected_document_id and expected_document_id not in source_blob:
            continue
        if expected_cohort and expected_cohort.lower() not in {"all", "general"}:
            source_cohort = str(source.get("cohort") or metadata.get("cohort") or "")
            if source_cohort != expected_cohort:
                continue
        if expected_keywords and not contains_any(source_blob, expected_keywords):
            continue
        return True
    return False


def evaluate_case(case: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    query = str(case["query"])
    required_facts = [str(item) for item in case.get("required_facts") or []]
    top_k = int((config.get("citations") or {}).get("max_sources") or 4)
    max_context_chars = int((config.get("llm") or {}).get("max_context_chars") or 10000)
    retrieval_result = run_retrieval_pipeline(
        query,
        top_k=top_k,
        cohort=cohort_arg(case.get("cohort")),
    )

    off_context = build_context_for_prompt(
        retrieval_result,
        query=query,
        max_context_chars=max_context_chars,
        allocation_config=_context_config(config, evidence_enabled=False),
    )
    on_config = _context_config(config, evidence_enabled=True)
    on_context = build_context_for_prompt(
        retrieval_result,
        query=query,
        max_context_chars=max_context_chars,
        allocation_config=on_config,
    )
    evidence_config = dict(on_config.evidence_selection or {})
    selected_blocks = _selected_evidence(retrieval_result, query, evidence_config)
    evidence_text = format_evidence_for_prompt(selected_blocks)
    citations_text = _citation_text(retrieval_result)
    retrieved_text = _retrieved_text(retrieval_result)

    off_fact_hit = contains_all(off_context, required_facts)
    on_fact_hit = contains_all(on_context, required_facts)
    evidence_fact_hit = contains_all(evidence_text, required_facts)
    retrieval_fact_available = contains_all(retrieved_text, required_facts)
    evidence_context_present = EVIDENCE_MARKERS[0] in on_context
    no_marker_leakage = not any(marker in citations_text for marker in EVIDENCE_MARKERS)
    retrieved_items = [
        item for item in retrieval_result.get("retrieved_items") or [] if isinstance(item, dict)
    ]
    citations = [
        item for item in retrieval_result.get("citations") or [] if isinstance(item, dict)
    ]
    retrieval_source_correct = _sources_correct(retrieved_items, case)
    citation_binding_correct = _sources_correct(citations, case)
    evidence_parent_source_match = _sources_correct(selected_blocks, case)
    context_uses_evidence = evidence_context_present and on_fact_hit

    return {
        "id": case.get("id"),
        "query": query,
        "cohort": case.get("cohort"),
        "tags": case.get("tags") or [],
        "required_facts": required_facts,
        "retrieved_count": len(retrieval_result.get("retrieved_items") or []),
        "retrieval_strategy": retrieval_result.get("strategy"),
        "retrieval_fact_available": retrieval_fact_available,
        "evidence_context_present": evidence_context_present,
        "required_fact_hit_off": off_fact_hit,
        "required_fact_hit_on": on_fact_hit,
        "required_fact_improved": (not off_fact_hit) and on_fact_hit,
        "required_fact_regressed": off_fact_hit and (not on_fact_hit),
        "evidence_fact_hit": evidence_fact_hit,
        "context_uses_evidence": context_uses_evidence,
        "answer_uses_evidence": context_uses_evidence,
        "retrieval_source_correctness": retrieval_source_correct,
        "citation_binding_correctness": citation_binding_correct,
        "evidence_parent_source_match": evidence_parent_source_match,
        "evidence_source_correctness": evidence_parent_source_match,
        "no_marker_leakage": no_marker_leakage,
        "selected_evidence_count": len(selected_blocks),
        "selected_evidence_preview": [
            {
                "evidence_id": block.get("evidence_id"),
                "cohort": block.get("cohort"),
                "document_id": block.get("document_id"),
                "parent_section_id": block.get("parent_section_id"),
                "source_section": block.get("source_section"),
                "section_title": block.get("section_title"),
                "block_type": block.get("block_type"),
                "text": str(block.get("text") or "")[:350],
            }
            for block in selected_blocks[:5]
        ],
        "top_citations": [
            {
                "chunk_id": item.get("chunk_id"),
                "cohort": item.get("cohort"),
                "document_id": item.get("document_id"),
                "source_section": item.get("source_section"),
                "title": item.get("title"),
            }
            for item in citations[:4]
            if isinstance(item, dict)
        ],
        "top_sources": [
            {
                "chunk_id": item.get("chunk_id") or item.get("_id"),
                "cohort": item.get("cohort") or (item.get("metadata") or {}).get("cohort"),
                "document_id": item.get("document_id") or (item.get("metadata") or {}).get("document_id"),
                "source_section": item.get("source_section") or (item.get("metadata") or {}).get("source_section"),
                "title": (item.get("metadata") or {}).get("title"),
                "rerank_score": item.get("rerank_score"),
            }
            for item in (retrieval_result.get("retrieved_items") or [])[:4]
            if isinstance(item, dict)
        ],
    }


def _mean_bool(items: list[dict[str, Any]], key: str) -> float:
    values = [item.get(key) for item in items if item.get(key) is not None]
    if not values:
        return 0.0
    return sum(1 for value in values if value is True) / len(values)


def _summary_for_group(items: list[dict[str, Any]]) -> dict[str, Any]:
    retrieval_available_items = [
        item for item in items if item.get("retrieval_fact_available") is True
    ]
    return {
        "total_cases": len(items),
        "retrieval_fact_availability": _mean_bool(items, "retrieval_fact_available"),
        "evidence_context_present": _mean_bool(items, "evidence_context_present"),
        "required_fact_hit_off": _mean_bool(items, "required_fact_hit_off"),
        "required_fact_hit_on": _mean_bool(items, "required_fact_hit_on"),
        "retrieval_source_correctness": _mean_bool(items, "retrieval_source_correctness"),
        "evidence_fact_hit": _mean_bool(items, "evidence_fact_hit"),
        "answer_uses_evidence": _mean_bool(items, "answer_uses_evidence"),
        "citation_binding_correctness": _mean_bool(items, "citation_binding_correctness"),
        "evidence_parent_source_match": _mean_bool(items, "evidence_parent_source_match"),
        "no_marker_leakage": _mean_bool(items, "no_marker_leakage"),
        "improved_cases": sum(1 for item in items if item.get("required_fact_improved")),
        "regressed_cases": sum(1 for item in items if item.get("required_fact_regressed")),
        "retrieval_available_cases": len(retrieval_available_items),
        "available_required_fact_hit_off": _mean_bool(
            retrieval_available_items,
            "required_fact_hit_off",
        ),
        "available_required_fact_hit_on": _mean_bool(
            retrieval_available_items,
            "required_fact_hit_on",
        ),
        "available_evidence_fact_hit": _mean_bool(
            retrieval_available_items,
            "evidence_fact_hit",
        ),
        "available_answer_uses_evidence": _mean_bool(
            retrieval_available_items,
            "answer_uses_evidence",
        ),
        "available_retrieval_source_correctness": _mean_bool(
            retrieval_available_items,
            "retrieval_source_correctness",
        ),
        "available_citation_binding_correctness": _mean_bool(
            retrieval_available_items,
            "citation_binding_correctness",
        ),
        "available_evidence_parent_source_match": _mean_bool(
            retrieval_available_items,
            "evidence_parent_source_match",
        ),
        "available_improved_cases": sum(
            1 for item in retrieval_available_items if item.get("required_fact_improved")
        ),
        "available_regressed_cases": sum(
            1 for item in retrieval_available_items if item.get("required_fact_regressed")
        ),
    }


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_cohort: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_tag: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in results:
        by_cohort[str(item.get("cohort") or "general")].append(item)
        for tag in item.get("tags") or ["untagged"]:
            by_tag[str(tag)].append(item)
    return {
        **_summary_for_group(results),
        "cohort_breakdown": {
            key: _summary_for_group(value)
            for key, value in sorted(by_cohort.items())
        },
        "tag_breakdown": {
            key: _summary_for_group(value)
            for key, value in sorted(by_tag.items())
        },
    }


def run_eval(cases_path: Path, config_path: Path, output_path: Path, limit: int | None) -> dict[str, Any]:
    configure_utf8_stdio()
    cases = load_json(cases_path)
    if limit is not None:
        cases = cases[: max(0, limit)]
    config = load_yaml(config_path)
    results = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] evidence: {case['query'][:90]}")
        results.append(evaluate_case(case, config))
    report = {
        "evaluation": "evidence_selection_regression",
        "cases_path": str(cases_path),
        "config_path": str(config_path),
        "summary": build_summary(results),
        "results": results,
    }
    save_json(report, output_path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate evidence selection A/B after V6 retrieval.")
    parser.add_argument("--cases", default=str(DEFAULT_CASES_PATH))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    report = run_eval(
        cases_path=Path(args.cases),
        config_path=Path(args.config),
        output_path=Path(args.output),
        limit=args.limit,
    )
    print("\nEvidence selection evaluation")
    for key, value in report["summary"].items():
        if key.endswith("_breakdown"):
            continue
        print(f"{key}: {value}")
    print(f"Saved report: {args.output}")


if __name__ == "__main__":
    main()
