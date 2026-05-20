from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from src.common.console import configure_utf8_stdio
from src.common.env_loader import load_project_env
from src.generation.phase8_pipeline import DEFAULT_CONFIG_PATH, Phase8AnswerPipeline


DEFAULT_CASES_PATH = Path("data/eval/answer_eval_cases.json")
DEFAULT_OUTPUT_PATH = Path("data/processed/metadata/answer_eval_report.json")


class OfflineLlmClient:
    def generate(self, prompt: str) -> dict[str, Any]:
        return {
            "ok": True,
            "text": (
                "Theo các nguồn được truy xuất từ Sổ tay sinh viên, nội dung trả lời "
                "cần được đối chiếu với phần nguồn bên dưới."
            ),
        }


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        f.write("\n")


def evaluate_case(case: dict[str, Any], pipeline: Phase8AnswerPipeline) -> dict[str, Any]:
    result = pipeline.answer(str(case["query"]))
    answer = str(result.get("answer") or "")
    citations_used = result.get("citations_used") or []
    structured_result = result.get("structured_result") or {}
    tool_result = result.get("tool_result") or {}

    checks = {
        "status_match": _optional_match(case.get("expected_status"), result.get("status")),
        "llm_called_match": _optional_match(case.get("expected_llm_called"), result.get("llm_called")),
        "lookup_type_match": _optional_match(
            case.get("expected_lookup_type"),
            structured_result.get("lookup_type"),
        ),
        "tool_name_match": _optional_match(
            case.get("expected_tool_name"),
            tool_result.get("tool_name"),
        ),
        "answer_contains_match": _contains_all(answer, case.get("expected_answer_contains", [])),
        "citation_count_match": len(citations_used) >= int(case.get("min_citations", 0)),
        "citation_type_match": _citation_types_match(
            citations_used,
            case.get("expected_citation_chunk_types"),
        ),
        "citation_page_match": _citation_pages_match(
            citations_used,
            case.get("expected_citation_pages"),
        ),
        "no_context_leak": "context_used" not in answer.lower(),
        "source_section_match": _source_section_match(answer, citations_used, case),
    }

    passed = all(value is not False for value in checks.values())

    return {
        "id": case.get("id"),
        "category": case.get("category"),
        "query": case["query"],
        "passed": passed,
        "checks": checks,
        "actual_status": result.get("status"),
        "actual_intent": result.get("intent"),
        "actual_strategy": result.get("strategy"),
        "actual_lookup_type": structured_result.get("lookup_type"),
        "actual_tool_name": tool_result.get("tool_name"),
        "actual_llm_called": result.get("llm_called"),
        "citations_used": citations_used,
        "answer_preview": answer[:500],
    }


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_cases": len(results),
        "pass_rate": _mean_bool(results, "passed"),
        "passed_cases": sum(1 for item in results if item.get("passed") is True),
        "failed_cases": sum(1 for item in results if item.get("passed") is False),
        "status_accuracy": _mean_check(results, "status_match"),
        "deterministic_exactness": _mean_check(results, "answer_contains_match"),
        "citation_count_accuracy": _mean_check(results, "citation_count_match"),
        "citation_type_accuracy": _mean_check(results, "citation_type_match"),
        "citation_page_accuracy": _mean_check(results, "citation_page_match"),
        "source_section_accuracy": _mean_check(results, "source_section_match"),
    }


def run_evaluation(config_path: Path, cases_path: Path) -> dict[str, Any]:
    load_project_env()
    pipeline = Phase8AnswerPipeline(config_path=config_path, llm_client=OfflineLlmClient())
    pipeline.response_cache.enabled = False

    cases = load_json(cases_path)
    results = [evaluate_case(case, pipeline) for case in cases]
    return {
        "evaluation": "answer_eval_offline",
        "config_path": str(config_path),
        "cases_path": str(cases_path),
        "llm_provider": "offline_mock",
        "summary": build_summary(results),
        "cases": results,
    }


def main() -> None:
    configure_utf8_stdio()

    parser = argparse.ArgumentParser(description="Evaluate answer behavior without calling Gemini.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--cases", default=str(DEFAULT_CASES_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--fail-under-pass-rate", type=float, default=None)
    args = parser.parse_args()

    report = run_evaluation(Path(args.config), Path(args.cases))
    save_json(report, Path(args.output))

    summary = report["summary"]
    print("\nOffline answer evaluation")
    for key, value in summary.items():
        print(f"{key}: {value}")
    print(f"Saved report: {args.output}")

    if args.fail_under_pass_rate is not None and summary["pass_rate"] < args.fail_under_pass_rate:
        sys.exit(1)


def _optional_match(expected: Any, actual: Any) -> bool | None:
    if expected is None:
        return None
    return actual == expected


def _contains_all(text: str, expected_items: list[str]) -> bool | None:
    if not expected_items:
        return None
    normalized = text.lower()
    return all(str(item).lower() in normalized for item in expected_items)


def _citation_types_match(
    citations: list[dict[str, Any]],
    expected_types: list[str] | None,
) -> bool | None:
    if expected_types is None:
        return None
    actual_types = [str(item.get("chunk_type") or "") for item in citations]
    return all(expected in actual_types for expected in expected_types)


def _citation_pages_match(
    citations: list[dict[str, Any]],
    expected_pages: list[int] | None,
) -> bool | None:
    if expected_pages is None:
        return None
    actual_pages: set[int] = set()
    for citation in citations:
        for page in citation.get("source_pages") or []:
            if isinstance(page, int):
                actual_pages.add(page)
    return all(page in actual_pages for page in expected_pages)


def _source_section_match(
    answer: str,
    citations: list[dict[str, Any]],
    case: dict[str, Any],
) -> bool | None:
    if not case.get("expect_sources_section"):
        return None
    return bool(citations) and "Nguồn:" in answer


def _mean_bool(items: list[dict[str, Any]], field: str) -> float | None:
    values = [item.get(field) for item in items if item.get(field) is not None]
    if not values:
        return None
    return round(sum(1 for value in values if value is True) / len(values), 4)


def _mean_check(items: list[dict[str, Any]], check_name: str) -> float | None:
    values = [
        item.get("checks", {}).get(check_name)
        for item in items
        if item.get("checks", {}).get(check_name) is not None
    ]
    if not values:
        return None
    return round(sum(1 for value in values if value is True) / len(values), 4)


if __name__ == "__main__":
    main()
