from __future__ import annotations

import argparse
import json
import os
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.env_loader import load_project_env
from src.generation.answer_pipeline import AnswerPipeline


DEFAULT_INPUT = Path(
    "data/eval/reports/router_holdout_v8_2/deterministic_full.json"
)
DEFAULT_OUTPUT = Path(
    "data/eval/reports/router_holdout_v8_2/fallback_answer_diagnostic.json"
)


def _normalize(value: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or "").lower())
    return " ".join(
        "".join(char for char in decomposed if not unicodedata.combining(char)).split()
    )


def _citation_cohort(citation: dict[str, Any]) -> str | None:
    metadata = citation.get("metadata") or {}
    return citation.get("cohort") or metadata.get("cohort")


def _citation_content_type(citation: dict[str, Any]) -> str | None:
    metadata = citation.get("metadata") or {}
    return (
        citation.get("content_type")
        or citation.get("chunk_type")
        or metadata.get("content_type")
        or metadata.get("chunk_type")
    )


def _save(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Diagnose end-to-end answers for positive router holdout fallbacks."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    load_project_env()
    os.environ["STUDENT_RAG_QUALITY_EVAL"] = "1"
    os.environ["STUDENT_RAG_DISABLE_ROUTER_CACHE"] = "1"
    os.environ["STUDENT_RAG_ROUTER_WAIT_WHEN_LIMITED"] = "1"
    os.environ["STUDENT_RAG_EVAL_TELEMETRY"] = "1"
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    source_report = json.loads(args.input.read_text(encoding="utf-8"))
    cases = [
        case
        for case in source_report.get("cases", [])
        if case.get("case_type") == "positive"
        and not case.get("passed")
        and case.get("actual_group") == "rag"
    ]
    pipeline = AnswerPipeline()
    rows: list[dict[str, Any]] = []

    for index, case in enumerate(cases, start=1):
        started = time.monotonic()
        try:
            result = pipeline.answer(case["query"], cohort=case.get("cohort"))
            unhandled_error = None
        except Exception as exc:  # pragma: no cover - diagnostic containment
            result = {}
            unhandled_error = f"{type(exc).__name__}: {exc}"

        answer = str(result.get("answer") or "")
        expected_facts = list(case.get("expected_contains_any") or [])
        normalized_answer = _normalize(answer)
        fact_hit = bool(expected_facts) and any(
            _normalize(fact) in normalized_answer for fact in expected_facts
        )
        citations = list(result.get("citations_used") or result.get("citations") or [])
        citation_cohorts = sorted(
            {value for item in citations if (value := _citation_cohort(item))}
        )
        citation_content_types = sorted(
            {
                value
                for item in citations
                if (value := _citation_content_type(item))
            }
        )
        expected_cohort = case.get("cohort")
        cohort_ok = not citation_cohorts or all(
            value in {expected_cohort, "general"} for value in citation_cohorts
        )
        expected_content_type = case.get("expected_citation_content_type")
        content_type_match = (
            expected_content_type in citation_content_types
            if expected_content_type
            else True
        )
        telemetry = result.get("evaluation_telemetry") or {}
        row = {
            "id": case.get("id"),
            "lookup_group": case.get("lookup_group"),
            "query": case.get("query"),
            "cohort": expected_cohort,
            "expected_facts": expected_facts,
            "status": result.get("status"),
            "intent": result.get("intent"),
            "strategy": result.get("strategy"),
            "llm_called": bool(result.get("llm_called")),
            "model_used": result.get("model_used"),
            "used_cache": bool(result.get("used_cache")),
            "answer": answer,
            "expected_fact_hit": fact_hit,
            "citation_cohorts": citation_cohorts,
            "citation_content_types": citation_content_types,
            "citation_cohort_ok": cohort_ok,
            "citation_content_type_match": content_type_match,
            "citations_used": citations,
            "context_chars": int(telemetry.get("context_chars") or 0),
            "source_count": int(telemetry.get("source_count") or 0),
            "latency_ms": float(
                telemetry.get("total_ms") or (time.monotonic() - started) * 1000
            ),
            "unhandled_error": unhandled_error,
        }
        rows.append(row)
        _save(
            args.output,
            {
                "diagnostic_only": True,
                "source_report": str(args.input),
                "completed": len(rows),
                "expected": len(cases),
                "cases": rows,
            },
        )
        print(
            f"[{index}/{len(cases)}] {case.get('id')} "
            f"status={row['status']} llm={row['llm_called']} "
            f"fact_hit={row['expected_fact_hit']} latency_ms={row['latency_ms']:.0f}"
        )

    latencies = sorted(row["latency_ms"] for row in rows)
    summary = {
        "n": len(rows),
        "answered": sum(row["status"] == "answered" for row in rows),
        "llm_called": sum(row["llm_called"] for row in rows),
        "expected_fact_hits": sum(row["expected_fact_hit"] for row in rows),
        "citation_cohort_ok": sum(row["citation_cohort_ok"] for row in rows),
        "citation_content_type_match": sum(
            row["citation_content_type_match"] for row in rows
        ),
        "cache_hits": sum(row["used_cache"] for row in rows),
        "unhandled_errors": sum(bool(row["unhandled_error"]) for row in rows),
        "latency_ms": {
            "mean": sum(latencies) / len(latencies) if latencies else 0.0,
            "p50": latencies[len(latencies) // 2] if latencies else 0.0,
            "max": max(latencies, default=0.0),
        },
    }
    _save(
        args.output,
        {
            "diagnostic_only": True,
            "source_report": str(args.input),
            "completed": len(rows),
            "expected": len(cases),
            "summary": summary,
            "cases": rows,
        },
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
