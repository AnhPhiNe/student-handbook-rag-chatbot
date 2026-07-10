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
from src.common.env_loader import load_project_env
from src.generation.answer_pipeline import DEFAULT_CONFIG_PATH, AnswerPipeline


DEFAULT_CASES_PATH = Path("data/eval/structured_eval_cases.json")
DEFAULT_OUTPUT_PATH = Path("data/processed/metadata/structured_answer_eval_report.json")


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


def evaluate_case(case: dict[str, Any], pipeline: AnswerPipeline) -> dict[str, Any]:
    cohort = case.get("cohort")
    result = pipeline.answer(
        str(case["query"]),
        cohort=_cohort_arg(cohort),
    )
    answer = str(result.get("answer") or "")
    citations_used = result.get("citations_used") or []
    structured_result = result.get("structured_result") or {}
    tool_result = result.get("tool_result") or {}

    checks = {
        "intent_match": _optional_match(case.get("expected_intent"), result.get("intent")),
        "strategy_match": _optional_match(
            case.get("expected_strategy"),
            result.get("strategy"),
        ),
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
        "answer_not_contains_match": _contains_none(
            answer,
            case.get("expected_answer_not_contains", []),
        ),
        "structured_item_count_match": _structured_item_count_match(
            structured_result,
            case,
        ),
        "structured_items_include_match": _structured_items_include_match(
            structured_result,
            case.get("expected_structured_items_include"),
        ),
        "structured_items_exclude_match": _structured_items_exclude_match(
            structured_result,
            case.get("expected_structured_items_exclude"),
        ),
        "citation_count_match": len(citations_used) >= int(case.get("min_citations", 0)),
        "citation_type_match": _citation_types_match(
            citations_used,
            case.get("expected_citation_chunk_types"),
        ),
        "citation_page_match": _citation_pages_match(
            citations_used,
            case.get("expected_citation_pages"),
        ),
        "citation_metadata_match": _citation_metadata_match(citations_used, case),
        "no_context_leak": "context_used" not in answer.lower(),
        "source_section_match": _source_section_match(answer, citations_used, case),
    }

    passed = all(value is not False for value in checks.values())

    return {
        "id": case.get("id"),
        "category": case.get("category"),
        "eval_type": case.get("eval_type") or "structured",
        "content_type": case.get("content_type"),
        "cohort": cohort,
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


def _cohort_arg(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"all", "general"}:
        return None
    return text


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_cohort: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_content_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_eval_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in results:
        by_cohort[str(item.get("cohort") or "general")].append(item)
        by_content_type[str(item.get("content_type") or "unknown")].append(item)
        by_eval_type[str(item.get("eval_type") or "unknown")].append(item)

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
        "citation_metadata_accuracy": _mean_check(
            results,
            "citation_metadata_match",
        ),
        "source_section_accuracy": _mean_check(results, "source_section_match"),
        "intent_accuracy": _mean_check(results, "intent_match"),
        "strategy_accuracy": _mean_check(results, "strategy_match"),
        "structured_item_count_accuracy": _mean_check(
            results,
            "structured_item_count_match",
        ),
        "eval_type_breakdown": {
            eval_type: _summary_for_group(items)
            for eval_type, items in sorted(by_eval_type.items())
        },
        "content_type_breakdown": {
            content_type: _summary_for_group(items)
            for content_type, items in sorted(by_content_type.items())
        },
        "cohort_breakdown": {
            cohort: _summary_for_group(items)
            for cohort, items in sorted(by_cohort.items())
        },
    }


def _summary_for_group(results: list[dict[str, Any]]) -> dict[str, Any]:
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
        "citation_metadata_accuracy": _mean_check(
            results,
            "citation_metadata_match",
        ),
        "source_section_accuracy": _mean_check(results, "source_section_match"),
        "intent_accuracy": _mean_check(results, "intent_match"),
        "strategy_accuracy": _mean_check(results, "strategy_match"),
        "structured_item_count_accuracy": _mean_check(
            results,
            "structured_item_count_match",
        ),
    }


def run_evaluation(config_path: Path, cases_path: Path) -> dict[str, Any]:
    os.environ["EVAL_VECTORDB_PROVIDER"] = "chroma"
    os.environ["STUDENT_RAG_DISABLE_REDIS"] = "1"
    os.environ["QUERY_REWRITER_ENABLED"] = "false"
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    load_project_env(override=False)
    os.environ["EVAL_VECTORDB_PROVIDER"] = "chroma"
    os.environ["STUDENT_RAG_DISABLE_REDIS"] = "1"
    os.environ["QUERY_REWRITER_ENABLED"] = "false"
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGSMITH_API_KEY"] = ""
    os.environ["LANGCHAIN_API_KEY"] = ""
    os.environ["MONGODB_PARENT_LOOKUP_ENABLED"] = "false"
    os.environ["STUDENT_RAG_DISABLE_AI_ROUTER"] = "1"
    os.environ["STUDENT_RAG_OFFLINE_EVAL"] = "1"
    pipeline = AnswerPipeline(config_path=config_path, llm_client=OfflineLlmClient())
    pipeline.response_cache.enabled = False
    pipeline.query_rewriter.enabled = False
    pipeline.semantic_cache.enabled = False

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
    normalized = _normalize_for_eval(text)
    return all(_normalize_for_eval(item) in normalized for item in expected_items)


def _contains_none(text: str, unexpected_items: list[str]) -> bool | None:
    if not unexpected_items:
        return None
    normalized = _normalize_for_eval(text)
    return all(_normalize_for_eval(item) not in normalized for item in unexpected_items)


def _structured_item_count_match(
    structured_result: dict[str, Any],
    case: dict[str, Any],
) -> bool | None:
    min_items = case.get("min_structured_items")
    max_items = case.get("max_structured_items")
    if min_items is None and max_items is None:
        return None

    items = _structured_items(structured_result)
    if min_items is not None and len(items) < int(min_items):
        return False
    if max_items is not None and len(items) > int(max_items):
        return False
    return True


def _structured_items_include_match(
    structured_result: dict[str, Any],
    expected_items: list[str] | None,
) -> bool | None:
    if expected_items is None:
        return None
    haystack = _structured_items_text(structured_result)
    return all(_normalize_for_eval(item) in haystack for item in expected_items)


def _structured_items_exclude_match(
    structured_result: dict[str, Any],
    unexpected_items: list[str] | None,
) -> bool | None:
    if unexpected_items is None:
        return None
    haystack = _structured_items_text(structured_result)
    return all(_normalize_for_eval(item) not in haystack for item in unexpected_items)


def _structured_items_text(structured_result: dict[str, Any]) -> str:
    return _normalize_for_eval(
        json.dumps(_structured_items(structured_result), ensure_ascii=False)
    )


def _structured_items(structured_result: dict[str, Any]) -> list[dict[str, Any]]:
    result = structured_result.get("result")
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    if isinstance(result, dict):
        return [result]
    return []


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


def _citation_metadata_match(
    citations: list[dict[str, Any]],
    case: dict[str, Any],
) -> bool | None:
    expected = {
        "cohort": _expected_values(case, "expected_citation_cohort"),
        "document_id": _expected_values(case, "expected_citation_document_id"),
        "chunk_type": _expected_values(case, "expected_citation_content_types")
        or _expected_values(case, "expected_citation_chunk_types"),
        "source_section": _expected_values(case, "expected_citation_source_sections"),
    }
    expected_pages = set(_parse_pages(case.get("expected_citation_pages")))
    has_expectation = any(expected.values()) or bool(expected_pages)
    if not has_expectation:
        return None

    for citation in citations:
        checks: list[bool] = []
        for key, values in expected.items():
            if values:
                checks.append(str(citation.get(key) or "") in values)
        if expected_pages:
            actual_pages = set(_parse_pages(citation.get("source_pages")))
            checks.append(bool(actual_pages & expected_pages))
        if checks and all(checks):
            return True
    return False


def _expected_values(case: dict[str, Any], key: str) -> set[str]:
    value = case.get(key)
    if value is None:
        return set()
    if isinstance(value, list):
        return {str(item) for item in value if str(item).strip()}
    text = str(value).strip()
    return {text} if text else set()


def _parse_pages(value: Any) -> list[int]:
    if value is None:
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, list):
        pages: list[int] = []
        for item in value:
            pages.extend(_parse_pages(item))
        return pages
    if isinstance(value, str):
        pages: list[int] = []
        for item in value.split(","):
            item = item.strip()
            if item.isdigit():
                pages.append(int(item))
        return pages
    return []


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


def _normalize_for_eval(value: Any) -> str:
    text = str(value or "").lower()
    text = text.replace("đ", "d").replace("Đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return " ".join(text.split())


if __name__ == "__main__":
    main()
