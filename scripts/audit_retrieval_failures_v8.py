"""Audit retrieval misses without mutating the frozen holdout dataset.

The audit separates annotation/design issues from genuine retrieval misses so
we do not tune the system directly against a frozen headline set.
"""

from __future__ import annotations

import argparse
import json
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = (
    ROOT
    / "data"
    / "eval"
    / "reports"
    / "v8_3_holdout"
    / "retrieval_qdrant_vector_primary_graph_supplement_full.json"
)
DEFAULT_DOCSTORE = ROOT / "data" / "processed" / "chunks" / "all_docstore_items.json"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "eval" / "reports" / "v8_3_holdout"

SUPPLEMENT_MARKERS = ("_Supplement_", "Supplement_")
STRUCTURED_OR_DIRECTORY_TOPICS = {
    "phong_ban",
    "bieu_mau",
    "nganh_hoc",
}
AMBIGUOUS_SECTION_TITLES = (
    "giai thich tu ngu",
    "pham vi dieu chinh",
    "doi tuong ap dung",
    "noi dung chinh",
    "to chuc thuc hien",
    "trach nhiem thi hanh",
    "hieu luc thi hanh",
    "cac don vi",
    "cac khoa",
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.lower())
    ascii_text = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return " ".join(ascii_text.split())


def _docstore_index(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(item.get("_id")): item for item in items if item.get("_id")}


def _expected_ids(case: dict[str, Any]) -> list[str]:
    return [
        str(judgment.get("parent_section_id"))
        for judgment in case.get("relevance_judgments", [])
        if judgment.get("parent_section_id")
    ]


def _source_type(docstore: dict[str, dict[str, Any]], source_id: str) -> str:
    item = docstore.get(source_id) or {}
    metadata = item.get("metadata") or {}
    return str(metadata.get("source_type") or metadata.get("content_type") or "")


def _is_supplement_expected(case: dict[str, Any], docstore: dict[str, dict[str, Any]]) -> bool:
    for source_id in _expected_ids(case):
        if any(marker in source_id for marker in SUPPLEMENT_MARKERS):
            return True
        if _source_type(docstore, source_id) == "supplemental_regulation":
            return True
    return False


def _is_structured_or_directory_case(case: dict[str, Any]) -> bool:
    topic = str(case.get("topic") or "")
    expected_path = str(case.get("expected_path") or "")
    expected_types = set(case.get("expected_content_types") or [])
    if topic in STRUCTURED_OR_DIRECTORY_TOPICS:
        return True
    if expected_path in {"structured", "mixed", "direct_lookup", "structured_reasoning"}:
        return True
    return any(
        content_type != "regulation_text"
        for content_type in expected_types
        if content_type
    )


def _is_broad_or_low_specificity(case: dict[str, Any]) -> bool:
    if case.get("question_specificity") == "broad":
        return True
    normalized_query = _normalize(str(case.get("query") or ""))
    return any(title in normalized_query for title in AMBIGUOUS_SECTION_TITLES)


def _recommendation(category: str) -> str:
    if category == "expected_supplemental_source":
        return (
            "Exclude from regulation headline or remap to an approved regulation parent/catalog; "
            "production filters supplemental_regulation sources."
        )
    if category == "structured_or_directory_case":
        return (
            "Move to structured/mixed evaluation or add directory/table source judgments; "
            "do not score it as pure regulation retrieval."
        )
    if category == "broad_or_under_anchored_query":
        return (
            "Add a document/topic anchor, allow multiple valid primary sources, or mark as clarify; "
            "single-parent Hit@5 is too brittle for this query."
        )
    if category == "empty_retrieval":
        return "Keep as retrieval development target if the expected source is production-valid."
    return "Keep as genuine retrieval miss for development; do not patch by case-specific keywords."


def _classify(case: dict[str, Any], docstore: dict[str, dict[str, Any]]) -> str:
    if _is_supplement_expected(case, docstore):
        return "expected_supplemental_source"
    if _is_structured_or_directory_case(case):
        return "structured_or_directory_case"
    if _is_broad_or_low_specificity(case):
        return "broad_or_under_anchored_query"
    if case.get("empty_retrieval"):
        return "empty_retrieval"
    return "true_retrieval_miss"


def _make_case_audit(case: dict[str, Any], docstore: dict[str, dict[str, Any]]) -> dict[str, Any]:
    category = _classify(case, docstore)
    expected = _expected_ids(case)
    ranked = [str(source_id) for source_id in case.get("ranked_parent_ids", [])]
    return {
        "id": case.get("id"),
        "audit_category": category,
        "recommendation": _recommendation(category),
        "query": case.get("query"),
        "cohort": case.get("cohort"),
        "topic": case.get("topic"),
        "question_style": case.get("question_style") or case.get("query_style"),
        "question_specificity": case.get("question_specificity"),
        "expected_path": case.get("expected_path"),
        "expected_answer_behavior": case.get("expected_answer_behavior"),
        "expected_parent_ids": expected,
        "expected_source_types": {
            source_id: _source_type(docstore, source_id) for source_id in expected
        },
        "ranked_parent_ids": ranked,
        "empty_retrieval": bool(case.get("empty_retrieval")),
        "cohort_match": bool(case.get("cohort_match")),
        "content_type_match": bool(case.get("content_type_match")),
        "synthetic_leak": bool(case.get("synthetic_leak")),
        "latency_ms": case.get("latency_ms"),
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# V8.3 Retrieval Failure Audit",
        "",
        "This audit reviews missed Hit@5 cases without changing the frozen holdout.",
        "",
        "## Summary",
        "",
        f"- Total cases: {report['summary']['total_cases']}",
        f"- Miss@5 cases: {report['summary']['miss_at_5_cases']}",
    ]
    for category, count in report["summary"]["categories"].items():
        lines.append(f"- {category}: {count}")

    estimate = report["filtered_estimate_excluding_non_headline_cases"]
    lines.extend(
        [
            "",
            "## Filtered Estimate",
            "",
            "If non-headline cases are excluded or moved to the right suite, the current retrieval run becomes:",
            "",
            f"- N: {estimate['n']}",
            f"- Hit@1: {estimate['hit_at_1']:.2%}",
            f"- Hit@3: {estimate['hit_at_3']:.2%}",
            f"- Hit@5: {estimate['hit_at_5']:.2%}",
            f"- MRR: {estimate['mrr']:.2%}",
            f"- nDCG@5: {estimate['ndcg_at_5']:.2%}",
        ]
    )

    lines.extend(
        [
            "",
            "## Recommended V8.4 Cleanup",
            "",
            "- Remove or remap expected `Supplement_*` sources from the pure regulation headline.",
            "- Move directory/table/program questions to structured or mixed eval instead of true-RAG retrieval.",
            "- Rewrite broad section-title questions with a document/topic anchor, or mark them as clarify/multi-source.",
            "- Keep only `true_retrieval_miss` cases as retrieval development targets.",
            "",
            "## Missed Cases",
            "",
            "| ID | Category | Cohort | Topic | Specificity | Recommendation |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for case in report["cases"]:
        lines.append(
            "| {id} | {category} | {cohort} | {topic} | {specificity} | {recommendation} |".format(
                id=case["id"],
                category=case["audit_category"],
                cohort=case.get("cohort") or "",
                topic=case.get("topic") or "",
                specificity=case.get("question_specificity") or "",
                recommendation=case["recommendation"],
            )
        )
    return "\n".join(lines) + "\n"


def build_audit(report_path: Path, docstore_path: Path) -> dict[str, Any]:
    retrieval_report = _load_json(report_path)
    docstore = _docstore_index(_load_json(docstore_path))
    cases = retrieval_report.get("cases") or []
    misses = [case for case in cases if not case.get("hit_at_5")]
    audited_cases = [_make_case_audit(case, docstore) for case in misses]
    categories = Counter(case["audit_category"] for case in audited_cases)
    excluded_ids = {
        str(case["id"])
        for case in audited_cases
        if case["audit_category"] != "true_retrieval_miss"
    }
    filtered_cases = [case for case in cases if str(case.get("id")) not in excluded_ids]
    return {
        "source_report": str(report_path.relative_to(ROOT)),
        "docstore": str(docstore_path.relative_to(ROOT)),
        "summary": {
            "total_cases": len(cases),
            "miss_at_5_cases": len(misses),
            "categories": dict(sorted(categories.items())),
        },
        "filtered_estimate_excluding_non_headline_cases": _metric_estimate(filtered_cases),
        "cases": audited_cases,
    }


def _metric_estimate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    if not cases:
        return {"n": 0}
    metric_keys = ("hit_at_1", "hit_at_3", "hit_at_5", "mrr", "ndcg_at_5")
    estimate: dict[str, Any] = {"n": len(cases)}
    for key in metric_keys:
        estimate[key] = sum(float(case.get(key) or 0.0) for case in cases) / len(cases)
    estimate["remaining_miss_at_5_ids"] = [
        str(case.get("id")) for case in cases if not case.get("hit_at_5")
    ]
    return estimate


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit V8 retrieval misses.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--docstore", type=Path, default=DEFAULT_DOCSTORE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    audit = build_audit(args.report, args.docstore)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "retrieval_v8_3_failure_audit.json"
    md_path = args.output_dir / "retrieval_v8_3_failure_audit.md"
    json_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(_markdown(audit), encoding="utf-8")
    print(json.dumps(audit["summary"], ensure_ascii=True, indent=2))
    print(json_path)
    print(md_path)


if __name__ == "__main__":
    main()
