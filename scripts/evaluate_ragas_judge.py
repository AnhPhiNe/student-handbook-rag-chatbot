from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_API_KEY"] = ""
os.environ["LANGCHAIN_API_KEY"] = ""
os.environ["MONGODB_PARENT_LOOKUP_ENABLED"] = "false"
os.environ["STUDENT_RAG_DISABLE_AI_ROUTER"] = "1"


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
from src.generation.gemini_client import GeminiClient


DEFAULT_CASES_PATH = Path("data/eval/ragas_judge_cases.json")
DEFAULT_OUTPUT_PATH = Path("data/processed/metadata/ragas_judge_report.json")
DEFAULT_ANSWER_CACHE_PATH = Path("data/processed/metadata/ragas_answer_cache.json")
DEFAULT_JUDGE_MODEL = "gemini-3.5-flash"
STRUCTURED_TOOL_CONTENT_TYPES = {
    "form_templates",
    "formula_rules",
    "program_directory",
    "scoring_tables",
    "threshold_rules",
}

JUDGE_PROMPT_TEMPLATE = """Bạn là giám khảo đánh giá hệ thống RAG cho Sổ tay sinh viên HCMUE.

Hãy chấm điểm từ 0.0 đến 1.0 theo phong cách RAGAS. Chỉ dựa vào dữ liệu dưới đây.
LƯU Ý CỰC KỲ QUAN TRỌNG: Bạn CHỈ ĐƯỢC PHÉP trả về duy nhất một đối tượng JSON hợp lệ. Tuyệt đối không in ra bất kỳ văn bản, lời chào, định dạng markdown hay giải thích nào nằm ngoài khối JSON. Nếu có giải thích, hãy đặt toàn bộ vào trường "rationale".

[CÂU HỎI]
{query}

[KHÓA/PHẠM VI]
{cohort}

[CONTEXT HỆ THỐNG ĐÃ DÙNG]
{context}

[CITATION/METADATA]
{citations}

[CÂU TRẢ LỜI CỦA HỆ THỐNG]
{answer}

[ĐÁP ÁN CHUẨN / GROUND TRUTH]
{ground_truth}

Tiêu chí:
- faithfulness: câu trả lời có bám context không, có bịa ngoài nguồn không.
- answer_relevancy: câu trả lời có đúng trọng tâm câu hỏi không.
- context_precision: context/citation được đưa vào có đúng trọng tâm không.
- context_recall: context có đủ thông tin cần thiết để trả lời không.
- answer_correctness: câu trả lời có đúng với đáp án chuẩn không.
- citation_correctness: citation có đúng khóa, loại nội dung, trang/section nếu có không.

Trả về JSON hợp lệ duy nhất, không markdown:
{{
  "faithfulness": 0.0,
  "answer_relevancy": 0.0,
  "context_precision": 0.0,
  "context_recall": 0.0,
  "answer_correctness": 0.0,
  "citation_correctness": 0.0,
  "rationale": "một câu ngắn"
}}
"""


class MockJudgeClient:
    def generate(self, prompt: str) -> dict[str, Any]:
        return {
            "ok": True,
            "text": json.dumps(
                {
                    "faithfulness": 1.0,
                    "answer_relevancy": 1.0,
                    "context_precision": 1.0,
                    "context_recall": 1.0,
                    "answer_correctness": 1.0,
                    "citation_correctness": 1.0,
                    "rationale": "Mock judge dùng để kiểm tra luồng eval.",
                },
                ensure_ascii=False,
            ),
            "model_used": "mock-judge",
        }


class MockAnswerClient:
    def generate(self, prompt: str) -> dict[str, Any]:
        return {
            "ok": True,
            "text": (
                "Theo nguồn được truy xuất từ Sổ tay sinh viên, câu trả lời cần "
                "được đối chiếu với phần nguồn đi kèm trong hệ thống."
            ),
            "model_used": "mock-answer",
        }


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        f.write("\n")


def parse_judge_result(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    try:
        data = json.loads(cleaned.strip())
    except Exception as exc:
        return {
            "parse_error": str(exc),
            "raw_output": text,
            **_zero_metrics(),
        }

    metrics = _zero_metrics()
    for key in metrics:
        try:
            metrics[key] = max(0.0, min(1.0, float(data.get(key, 0.0))))
        except Exception:
            metrics[key] = 0.0
    metrics["rationale"] = str(data.get("rationale") or "")
    return metrics


def _zero_metrics() -> dict[str, float]:
    return {
        "faithfulness": 0.0,
        "answer_relevancy": 0.0,
        "context_precision": 0.0,
        "context_recall": 0.0,
        "answer_correctness": 0.0,
        "citation_correctness": 0.0,
    }


def format_context(citations: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for index, citation in enumerate(citations, start=1):
        content = str(citation.get("content") or citation.get("text") or "").strip()
        if not content:
            continue
        parts.append(f"[{index}] {content[:2000]}")
    return "\n\n".join(parts) if parts else "(không có context)"


def format_citations(citations: list[dict[str, Any]]) -> str:
    rows = []
    for citation in citations:
        rows.append(
            {
                "chunk_id": citation.get("chunk_id"),
                "cohort": citation.get("cohort"),
                "document_id": citation.get("document_id"),
                "content_type": citation.get("chunk_type") or citation.get("content_type"),
                "source_section": citation.get("source_section"),
                "source_pages": citation.get("source_pages"),
            }
        )
    return json.dumps(rows, ensure_ascii=False, indent=2)


def cohort_arg(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or text.lower() in {"all", "general"}:
        return None
    return text


def eval_bucket(eval_type: Any, content_type: Any) -> str:
    eval_type_text = str(eval_type or "").strip()
    content_type_text = str(content_type or "").strip()
    if eval_type_text in {"structured", "tool", "structured_tool"}:
        return "structured_tool"
    if content_type_text in STRUCTURED_TOOL_CONTENT_TYPES:
        return "structured_tool"
    return "true_rag"


def case_cache_key(case: dict[str, Any], index: int) -> str:
    return str(case.get("id") or f"case_{index:03d}")


def filter_by_eval_bucket(
    items: list[dict[str, Any]],
    bucket: str | None,
) -> list[dict[str, Any]]:
    if not bucket:
        return items
    return [
        item
        for item in items
        if str(
            item.get("eval_bucket")
            or eval_bucket(item.get("eval_type"), item.get("content_type"))
        )
        == bucket
    ]


def load_answer_cache(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    data = load_json(path)
    if isinstance(data, dict) and isinstance(data.get("answers"), list):
        return {
            str(item.get("cache_key") or item.get("id")): item
            for item in data["answers"]
            if item.get("cache_key") or item.get("id")
        }
    if isinstance(data, list):
        return {
            str(item.get("cache_key") or item.get("id")): item
            for item in data
            if item.get("cache_key") or item.get("id")
        }
    return {}


def save_answer_cache(cache: dict[str, dict[str, Any]], path: Path) -> None:
    answers = list(cache.values())
    save_json(
        {
            "total_cases": len(answers),
            "ready_cases": sum(1 for item in answers if item.get("answer_ready")),
            "pending_cases": sum(1 for item in answers if not item.get("answer_ready")),
            "answers": answers,
        },
        path,
    )


def answer_record_from_case(
    case: dict[str, Any],
    index: int,
    pipeline: AnswerPipeline,
) -> dict[str, Any]:
    query = str(case["query"])
    cohort = case.get("cohort")
    result = pipeline.answer(query, cohort=cohort_arg(cohort))
    answer = str(result.get("answer") or "").strip()
    citations = result.get("citations_used") or []
    status = result.get("status")
    error_type = result.get("error_type")
    answer_ready = status == "answered" and bool(answer)

    return {
        "cache_key": case_cache_key(case, index),
        "id": case.get("id"),
        "query": query,
        "cohort": cohort,
        "eval_type": case.get("eval_type"),
        "eval_bucket": eval_bucket(case.get("eval_type"), case.get("content_type")),
        "content_type": case.get("content_type"),
        "ground_truth": case.get("ground_truth", ""),
        "status": status,
        "error_type": error_type,
        "error_message": result.get("error_message"),
        "intent": result.get("intent"),
        "strategy": result.get("strategy"),
        "llm_called": result.get("llm_called"),
        "model_used": result.get("model_used"),
        "citation_count": len(citations),
        "citations": citations,
        "context": format_context(citations),
        "answer": answer,
        "answer_preview": answer[:700],
        "answer_ready": answer_ready,
    }


def generate_answer_cache(
    config_path: Path,
    cases_path: Path,
    cache_path: Path,
    limit: int | None,
    resume: bool,
    mock_answers: bool,
    stop_on_failure: bool,
    disable_answer_fallback: bool,
    answer_model: str | None,
    max_context_chars: int | None,
    max_output_tokens: int | None,
    eval_bucket_filter: str | None,
) -> dict[str, Any]:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["EVAL_VECTORDB_PROVIDER"] = "qdrant"
    os.environ["STUDENT_RAG_DISABLE_REDIS"] = "1"
    os.environ["QUERY_REWRITER_ENABLED"] = "false"
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGSMITH_API_KEY"] = ""
    os.environ["LANGCHAIN_API_KEY"] = ""
    os.environ["MONGODB_PARENT_LOOKUP_ENABLED"] = "false"
    os.environ["STUDENT_RAG_DISABLE_AI_ROUTER"] = "1"
    if disable_answer_fallback:
        os.environ["STUDENT_RAG_DISABLE_GROQ_FALLBACK"] = "1"
    if mock_answers:
        os.environ["STUDENT_RAG_OFFLINE_EVAL"] = "1"

    load_project_env()
    cases = load_json(cases_path)
    cases = filter_by_eval_bucket(cases, eval_bucket_filter)
    if limit is not None:
        cases = cases[:limit]

    cache = load_answer_cache(cache_path) if resume else {}
    pipeline = AnswerPipeline(
        config_path=config_path,
        llm_client=MockAnswerClient() if mock_answers else None,
    )
    if answer_model and not mock_answers:
        pipeline.config.setdefault("llm", {})["model_name"] = answer_model
    if max_context_chars is not None:
        pipeline.config.setdefault("llm", {})["max_context_chars"] = max_context_chars
        pipeline.max_context_chars = max_context_chars
    if max_output_tokens is not None:
        pipeline.config.setdefault("llm", {})["max_output_tokens"] = max_output_tokens
    pipeline.response_cache.enabled = False
    pipeline.semantic_cache.enabled = False
    pipeline.query_rewriter.enabled = False

    generated = 0
    skipped = 0
    failed = 0

    for index, case in enumerate(cases, start=1):
        key = case_cache_key(case, index)
        existing = cache.get(key)
        if resume and existing and existing.get("answer_ready"):
            skipped += 1
            print(f"[{index}/{len(cases)}] skip cached: {case['query'][:80]}")
            continue

        print(f"[{index}/{len(cases)}] generate: {case['query'][:90]}")
        record = answer_record_from_case(case, index, pipeline)
        cache[key] = record
        save_answer_cache(cache, cache_path)
        if record.get("answer_ready"):
            generated += 1
            print("   -> ready")
        else:
            failed += 1
            print(
                "   -> pending "
                f"status={record.get('status')} error={record.get('error_type')}"
            )
            if stop_on_failure:
                break

    report = {
        "evaluation": "ragas_answer_cache_generation",
        "config_path": str(config_path),
        "cases_path": str(cases_path),
        "cache_path": str(cache_path),
        "total_cases": len(cases),
        "ready_cases": sum(1 for item in cache.values() if item.get("answer_ready")),
        "pending_cases": sum(1 for item in cache.values() if not item.get("answer_ready")),
        "generated_this_run": generated,
        "skipped_cached": skipped,
        "failed_this_run": failed,
        "answer_model": "mock" if mock_answers else pipeline.config.get("llm", {}).get("model_name"),
        "max_context_chars": pipeline.config.get("llm", {}).get("max_context_chars"),
        "max_output_tokens": pipeline.config.get("llm", {}).get("max_output_tokens"),
        "disable_answer_fallback": disable_answer_fallback,
        "eval_bucket_filter": eval_bucket_filter,
    }
    return report


def judge_cached_case(
    record: dict[str, Any],
    judge: GeminiClient | MockJudgeClient,
) -> dict[str, Any]:
    answer = str(record.get("answer") or "")
    citations = record.get("citations") or []
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        query=record.get("query"),
        cohort=record.get("cohort") or "general",
        context=record.get("context") or format_context(citations),
        citations=format_citations(citations),
        answer=answer,
        ground_truth=record.get("ground_truth", ""),
    )
    judge_result = judge.generate(prompt)
    if not judge_result.get("ok"):
        metrics = {
            **_zero_metrics(),
            "judge_error_type": judge_result.get("error_type"),
            "judge_error_message": judge_result.get("error_message"),
        }
        raw_output = str(judge_result.get("error_message") or "")
    else:
        raw_output = str(judge_result.get("text") or "")
        metrics = parse_judge_result(raw_output)

    return {
        "id": record.get("id"),
        "query": record.get("query"),
        "cohort": record.get("cohort"),
        "eval_type": record.get("eval_type"),
        "eval_bucket": record.get("eval_bucket")
        or eval_bucket(record.get("eval_type"), record.get("content_type")),
        "content_type": record.get("content_type"),
        "status": record.get("status"),
        "intent": record.get("intent"),
        "strategy": record.get("strategy"),
        "llm_called": record.get("llm_called"),
        "model_used": record.get("model_used"),
        "citation_count": record.get("citation_count"),
        "metrics": metrics,
        "answer_preview": str(record.get("answer") or "")[:700],
        "judge_raw_output": raw_output,
    }


def judge_from_answer_cache(
    cache_path: Path,
    output_path: Path,
    judge_model: str,
    sleep_seconds: float,
    limit: int | None,
    mock_judge: bool,
    eval_bucket_filter: str | None,
) -> dict[str, Any]:
    load_project_env()
    cache = load_answer_cache(cache_path)
    ready_records = [item for item in cache.values() if item.get("answer_ready")]
    ready_records = filter_by_eval_bucket(ready_records, eval_bucket_filter)
    if limit is not None:
        ready_records = ready_records[:limit]

    judge: GeminiClient | MockJudgeClient
    if mock_judge:
        judge = MockJudgeClient()
    else:
        judge = GeminiClient(
            model_name=judge_model,
            temperature=0.0,
            max_output_tokens=4096,
            max_retries=4,
            retry_base_delay_seconds=5,
            retry_max_delay_seconds=60,
            request_timeout_seconds=90,
        )

    results = []
    for index, record in enumerate(ready_records, start=1):
        print(f"[{index}/{len(ready_records)}] judge: {str(record.get('query'))[:90]}")
        result = judge_cached_case(record, judge)
        results.append(result)
        metrics = result.get("metrics", {})
        print(
            "   -> "
            f"F:{float(metrics.get('faithfulness', 0.0)):.2f} "
            f"Rel:{float(metrics.get('answer_relevancy', 0.0)):.2f} "
            f"Corr:{float(metrics.get('answer_correctness', 0.0)):.2f}"
        )
        partial_report = {
            "evaluation": "ragas_style_gemini_judge_from_answer_cache",
            "cache_path": str(cache_path),
            "judge_model": "mock" if mock_judge else judge_model,
            "sleep_seconds": sleep_seconds,
            "ragas_package_available": ragas_package_available(),
            "summary": build_summary(results),
            "cases": results,
        }
        save_json(partial_report, output_path)
        if metrics.get("judge_error_type") and not mock_judge:
            print("   -> Judge API failed (Rate Limit/Error). Stopping evaluation early to prevent empty reports.")
            break
        
        if not mock_judge and index < len(ready_records):
            time.sleep(max(0.0, sleep_seconds))

    return {
        "evaluation": "ragas_style_gemini_judge_from_answer_cache",
        "cache_path": str(cache_path),
        "judge_model": "mock" if mock_judge else judge_model,
        "sleep_seconds": sleep_seconds,
        "eval_bucket_filter": eval_bucket_filter,
        "ragas_package_available": ragas_package_available(),
        "summary": build_summary(results),
        "cases": results,
    }


def evaluate_case(
    case: dict[str, Any],
    pipeline: AnswerPipeline,
    judge: GeminiClient | MockJudgeClient,
) -> dict[str, Any]:
    query = str(case["query"])
    cohort = case.get("cohort")
    result = pipeline.answer(query, cohort=cohort_arg(cohort))
    answer = str(result.get("answer") or "")
    citations = result.get("citations_used") or []
    context = format_context(citations)

    if not answer:
        return {
            "id": case.get("id"),
            "query": query,
            "cohort": cohort,
            "eval_type": case.get("eval_type"),
            "eval_bucket": eval_bucket(case.get("eval_type"), case.get("content_type")),
            "content_type": case.get("content_type"),
            "status": result.get("status"),
            "intent": result.get("intent"),
            "strategy": result.get("strategy"),
            "llm_called": result.get("llm_called"),
            "model_used": result.get("model_used"),
            "metrics": _zero_metrics(),
            "judge_raw_output": "empty answer",
        }

    prompt = JUDGE_PROMPT_TEMPLATE.format(
        query=query,
        cohort=cohort or "general",
        context=context,
        citations=format_citations(citations),
        answer=answer,
        ground_truth=case.get("ground_truth", ""),
    )
    judge_result = judge.generate(prompt)
    if not judge_result.get("ok"):
        metrics = {
            **_zero_metrics(),
            "judge_error_type": judge_result.get("error_type"),
            "judge_error_message": judge_result.get("error_message"),
        }
        raw_output = str(judge_result.get("error_message") or "")
    else:
        raw_output = str(judge_result.get("text") or "")
        metrics = parse_judge_result(raw_output)

    return {
        "id": case.get("id"),
        "query": query,
        "cohort": cohort,
        "eval_type": case.get("eval_type"),
        "eval_bucket": eval_bucket(case.get("eval_type"), case.get("content_type")),
        "content_type": case.get("content_type"),
        "status": result.get("status"),
        "intent": result.get("intent"),
        "strategy": result.get("strategy"),
        "llm_called": result.get("llm_called"),
        "model_used": result.get("model_used"),
        "citation_count": len(citations),
        "metrics": metrics,
        "answer_preview": answer[:700],
        "judge_raw_output": raw_output,
    }


def build_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    by_cohort: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_eval_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_eval_bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_content_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_model_used: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in results:
        by_cohort[str(item.get("cohort") or "general")].append(item)
        by_eval_type[str(item.get("eval_type") or "unknown")].append(item)
        bucket = str(
            item.get("eval_bucket")
            or eval_bucket(item.get("eval_type"), item.get("content_type"))
        )
        by_eval_bucket[bucket].append(item)
        by_content_type[str(item.get("content_type") or "unknown")].append(item)
        by_model_used[str(item.get("model_used") or "unknown")].append(item)

    primary_ragas_results = _primary_ragas_results(results)
    structured_secondary_results = by_eval_bucket.get("structured_tool", [])

    return {
        "total_cases": len(results),
        "answered_cases": sum(1 for item in results if item.get("status") == "answered"),
        **_metric_means(results),
        "headline_metric_note": (
            "Use primary_ragas_summary for CV/report RAGAS headline. "
            "Overall metrics include structured/deterministic cases and are for debug only."
        ),
        "overall_summary": _metric_group_summary(results),
        "primary_ragas_summary": _metric_group_summary(primary_ragas_results),
        "structured_secondary_summary": _metric_group_summary(
            structured_secondary_results
        ),
        "cohort_breakdown": {
            cohort: _metric_group_summary(items)
            for cohort, items in sorted(by_cohort.items())
        },
        "eval_type_breakdown": {
            eval_type: _metric_group_summary(items)
            for eval_type, items in sorted(by_eval_type.items())
        },
        "eval_bucket_breakdown": {
            eval_bucket_name: _metric_group_summary(items)
            for eval_bucket_name, items in sorted(by_eval_bucket.items())
        },
        "content_type_breakdown": {
            content_type: _metric_group_summary(items)
            for content_type, items in sorted(by_content_type.items())
        },
        "model_used_breakdown": {
            model_used: _metric_group_summary(items)
            for model_used, items in sorted(by_model_used.items())
        },
        "true_rag_summary": _metric_group_summary(by_eval_bucket.get("true_rag", [])),
        "structured_tool_summary": _metric_group_summary(
            structured_secondary_results
        ),
        "lowest_scored_cases": _lowest_scored_cases(results, limit=15),
        "primary_lowest_scored_cases": _lowest_scored_cases(
            primary_ragas_results,
            limit=15,
        ),
    }


def _primary_ragas_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in results:
        bucket = str(
            item.get("eval_bucket")
            or eval_bucket(item.get("eval_type"), item.get("content_type"))
        )
        model_used = str(item.get("model_used") or "").strip().lower()
        if bucket != "true_rag":
            continue
        if model_used in {"", "deterministic", "mock-answer"}:
            continue
        output.append(item)
    return output


def _metric_group_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "cases": len(results),
        "answered_cases": sum(1 for item in results if item.get("status") == "answered"),
        **_metric_means(results),
    }


def _metric_means(results: list[dict[str, Any]]) -> dict[str, float | None]:
    metric_names = list(_zero_metrics().keys())
    output: dict[str, float | None] = {}
    for metric_name in metric_names:
        values = [
            float(item.get("metrics", {}).get(metric_name))
            for item in results
            if isinstance(item.get("metrics", {}).get(metric_name), int | float)
        ]
        output[metric_name] = round(sum(values) / len(values), 4) if values else None
    return output


def _lowest_scored_cases(
    results: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    scored = sorted(results, key=_case_quality_score)
    return [
        {
            "id": item.get("id"),
            "query": item.get("query"),
            "cohort": item.get("cohort"),
            "eval_type": item.get("eval_type"),
            "eval_bucket": item.get("eval_bucket")
            or eval_bucket(item.get("eval_type"), item.get("content_type")),
            "content_type": item.get("content_type"),
            "model_used": item.get("model_used"),
            "score": round(_case_quality_score(item), 4),
            "metrics": item.get("metrics"),
        }
        for item in scored[:limit]
    ]


def _case_quality_score(item: dict[str, Any]) -> float:
    metrics = item.get("metrics") or {}
    values = [
        float(metrics.get(metric_name))
        for metric_name in _zero_metrics()
        if isinstance(metrics.get(metric_name), int | float)
    ]
    return sum(values) / len(values) if values else 0.0


def resummarize_judge_report(report_path: Path) -> dict[str, Any]:
    report = load_json(report_path)
    if not isinstance(report, dict):
        raise ValueError(f"Report must be a JSON object: {report_path}")
    cases = report.get("cases")
    if not isinstance(cases, list):
        raise ValueError(f"Report does not contain a cases list: {report_path}")
    report["summary"] = build_summary(cases)
    report["resummarized_from"] = str(report_path)
    return report


def ragas_package_available() -> bool:
    try:
        import ragas  # noqa: F401
    except Exception:
        return False
    return True


def run_evaluation(
    config_path: Path,
    cases_path: Path,
    judge_model: str,
    sleep_seconds: float,
    limit: int | None,
    mock_judge: bool,
    mock_answers: bool,
    disable_answer_fallback: bool,
    answer_model: str | None,
    max_context_chars: int | None,
    max_output_tokens: int | None,
    eval_bucket_filter: str | None,
) -> dict[str, Any]:
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["EVAL_VECTORDB_PROVIDER"] = "qdrant"
    os.environ["STUDENT_RAG_DISABLE_REDIS"] = "1"
    os.environ["QUERY_REWRITER_ENABLED"] = "false"
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGSMITH_API_KEY"] = ""
    os.environ["LANGCHAIN_API_KEY"] = ""
    os.environ["MONGODB_PARENT_LOOKUP_ENABLED"] = "false"
    os.environ["STUDENT_RAG_DISABLE_AI_ROUTER"] = "1"
    if disable_answer_fallback:
        os.environ["STUDENT_RAG_DISABLE_GROQ_FALLBACK"] = "1"
    if mock_answers:
        os.environ["STUDENT_RAG_OFFLINE_EVAL"] = "1"
    load_project_env()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["EVAL_VECTORDB_PROVIDER"] = "qdrant"
    os.environ["STUDENT_RAG_DISABLE_REDIS"] = "1"
    os.environ["QUERY_REWRITER_ENABLED"] = "false"
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGSMITH_API_KEY"] = ""
    os.environ["LANGCHAIN_API_KEY"] = ""
    os.environ["MONGODB_PARENT_LOOKUP_ENABLED"] = "false"
    os.environ["STUDENT_RAG_DISABLE_AI_ROUTER"] = "1"
    if disable_answer_fallback:
        os.environ["STUDENT_RAG_DISABLE_GROQ_FALLBACK"] = "1"
    cases = filter_by_eval_bucket(load_json(cases_path), eval_bucket_filter)
    if limit is not None:
        cases = cases[:limit]

    pipeline = AnswerPipeline(
        config_path=config_path,
        llm_client=MockAnswerClient() if mock_answers else None,
    )
    if answer_model and not mock_answers:
        pipeline.config.setdefault("llm", {})["model_name"] = answer_model
    if max_context_chars is not None:
        pipeline.config.setdefault("llm", {})["max_context_chars"] = max_context_chars
        pipeline.max_context_chars = max_context_chars
    if max_output_tokens is not None:
        pipeline.config.setdefault("llm", {})["max_output_tokens"] = max_output_tokens
    pipeline.response_cache.enabled = False
    pipeline.semantic_cache.enabled = False
    pipeline.query_rewriter.enabled = False

    judge: GeminiClient | MockJudgeClient
    if mock_judge:
        judge = MockJudgeClient()
    else:
        judge = GeminiClient(
            model_name=judge_model,
            temperature=0.0,
            max_output_tokens=4096,
            max_retries=4,
            retry_base_delay_seconds=5,
            retry_max_delay_seconds=60,
            request_timeout_seconds=90,
        )

    results = []
    for index, case in enumerate(cases, start=1):
        print(f"[{index}/{len(cases)}] {case['query'][:90]}")
        result = evaluate_case(case, pipeline, judge)
        results.append(result)
        metrics = result.get("metrics", {})
        print(
            "   -> "
            f"F:{float(metrics.get('faithfulness', 0.0)):.2f} "
            f"Rel:{float(metrics.get('answer_relevancy', 0.0)):.2f} "
            f"Corr:{float(metrics.get('answer_correctness', 0.0)):.2f}"
        )
        
        if result.get("status") == "api_error" or metrics.get("judge_error_type"):
            print("   -> API Error (Generation or Judge). Stopping evaluation early to prevent empty reports.")
            break
            
        if not mock_judge and index < len(cases):
            time.sleep(max(0.0, sleep_seconds))

    return {
        "evaluation": "ragas_style_gemini_judge",
        "note": (
            "Report dùng rubric RAGAS-style qua Gemini. Nếu cài package ragas, "
            "trường ragas_package_available sẽ xác nhận môi trường có thể chạy RAGAS thật."
        ),
        "config_path": str(config_path),
        "cases_path": str(cases_path),
        "judge_model": "mock" if mock_judge else judge_model,
        "answer_model": "mock" if mock_answers else pipeline.config.get("llm", {}).get("model_name"),
        "max_context_chars": pipeline.config.get("llm", {}).get("max_context_chars"),
        "max_output_tokens": pipeline.config.get("llm", {}).get("max_output_tokens"),
        "disable_answer_fallback": disable_answer_fallback,
        "eval_bucket_filter": eval_bucket_filter,
        "sleep_seconds": sleep_seconds,
        "ragas_package_available": ragas_package_available(),
        "summary": build_summary(results),
        "cases": results,
    }


def main() -> None:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Evaluate answers with RAGAS-style Gemini Judge.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--cases", default=str(DEFAULT_CASES_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--answer-cache", default=str(DEFAULT_ANSWER_CACHE_PATH))
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--sleep-seconds", type=float, default=5.0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--eval-bucket",
        choices=("true_rag", "structured_tool"),
        default=None,
        help="Filter cases/answer cache records by eval bucket before limit is applied.",
    )
    parser.add_argument("--mock-judge", action="store_true")
    parser.add_argument("--mock-answers", action="store_true")
    parser.add_argument("--generate-answer-cache", action="store_true")
    parser.add_argument("--judge-from-cache", action="store_true")
    parser.add_argument(
        "--resummarize-report",
        default=None,
        help="Rebuild summary from an existing Judge report without calling any model.",
    )
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--stop-on-generation-failure", action="store_true")
    parser.add_argument(
        "--disable-answer-fallback",
        action="store_true",
        help="Use only the configured answer model while generating answers.",
    )
    parser.add_argument(
        "--answer-model",
        default=None,
        help="Override llm.model_name for this eval run without editing production config.",
    )
    parser.add_argument(
        "--max-context-chars",
        type=int,
        default=None,
        help="Override llm.max_context_chars for this eval run.",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=None,
        help="Override llm.max_output_tokens for this eval run.",
    )
    parser.add_argument("--fail-under-faithfulness", type=float, default=None)
    args = parser.parse_args()

    if args.resummarize_report:
        report = resummarize_judge_report(Path(args.resummarize_report))
        save_json(report, Path(args.output))
        print("\nRAGAS-style Gemini Judge report resummarized")
        for key, value in report["summary"].items():
            print(f"{key}: {value}")
        print(f"Saved report: {args.output}")
        return

    if args.generate_answer_cache:
        report = generate_answer_cache(
            config_path=Path(args.config),
            cases_path=Path(args.cases),
            cache_path=Path(args.answer_cache),
            limit=args.limit,
            resume=not args.no_resume,
            mock_answers=args.mock_answers,
            stop_on_failure=args.stop_on_generation_failure,
            disable_answer_fallback=args.disable_answer_fallback,
            answer_model=args.answer_model,
            max_context_chars=args.max_context_chars,
            max_output_tokens=args.max_output_tokens,
            eval_bucket_filter=args.eval_bucket,
        )
        save_json(report, Path(args.output))
        print("\nRAGAS answer cache generation")
        for key, value in report.items():
            print(f"{key}: {value}")
        print(f"Saved answer cache: {args.answer_cache}")
        print(f"Saved report: {args.output}")
        return

    if args.judge_from_cache:
        report = judge_from_answer_cache(
            cache_path=Path(args.answer_cache),
            output_path=Path(args.output),
            judge_model=args.judge_model,
            sleep_seconds=args.sleep_seconds,
            limit=args.limit,
            mock_judge=args.mock_judge,
            eval_bucket_filter=args.eval_bucket,
        )
    else:
        report = run_evaluation(
            config_path=Path(args.config),
            cases_path=Path(args.cases),
            judge_model=args.judge_model,
            sleep_seconds=args.sleep_seconds,
            limit=args.limit,
            mock_judge=args.mock_judge,
            mock_answers=args.mock_answers,
            disable_answer_fallback=args.disable_answer_fallback,
            answer_model=args.answer_model,
            max_context_chars=args.max_context_chars,
            max_output_tokens=args.max_output_tokens,
            eval_bucket_filter=args.eval_bucket,
        )
    save_json(report, Path(args.output))

    summary = report["summary"]
    print("\nRAGAS-style Gemini Judge evaluation")
    for key, value in summary.items():
        print(f"{key}: {value}")
    print(f"Saved report: {args.output}")

    if args.fail_under_faithfulness is not None:
        value = summary.get("faithfulness") or 0.0
        if value < args.fail_under_faithfulness:
            sys.exit(1)


if __name__ == "__main__":
    main()
