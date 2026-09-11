"""Evaluate Cohere Rerank on a previously captured RRF candidate pool.

This is an offline retrieval-layer experiment: it reuses saved child candidates
and never calls the application Planner, retriever, Composer, or Judge. Results
are checkpointed after every Cohere response so an interrupted trial-key run can
resume without repeating successful requests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT))

from src.common.io import sha256_file

DEFAULT_CASES = ROOT / "data/eval/official_v1/retrieval_cases.json"
DEFAULT_CAPTURE = ROOT / (
    "data/eval/reports/official_v1_retrieval_layer_bge_top12_"
    "20260908T180300_escalated/candidates.jsonl"
)
EXPECTED_CASES_SHA256 = "8b0f474d1036fb9fa25f1e901e4562ff8c067f82384959d078747a0a08171026"
EXPECTED_CAPTURE_SHA256 = "1d882f3ddb6be48579babc99cba668af8aa60e844e6a4f3190adca66decb07c5"
MODEL = "rerank-v4.0-fast"
CANDIDATE_COUNT = 16
FINAL_K = 5
EXPECTED_CASE_COUNT = 155
EXPECTED_EVENT_COUNT = 157


class EvaluationError(RuntimeError):
    """Raised when experiment identity or output invariants do not hold."""


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def git_head() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def effective_cohort(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return None if normalized.lower() in {"", "general", "all", "shared", "*"} else normalized


def event_cohorts(case: dict[str, Any]) -> list[str | None]:
    direct = effective_cohort(case.get("cohort"))
    if direct is not None:
        return [direct]
    requested = case.get("requested_cohorts")
    values = (
        [effective_cohort(item) for item in requested]
        if isinstance(requested, list)
        else []
    )
    if not values:
        values = [
            effective_cohort(item.get("cohort"))
            for item in (case.get("relevance_judgments") or [])
            if isinstance(item, dict)
        ]
    result: list[str | None] = []
    for value in values:
        if value is not None and value not in result:
            result.append(value)
    return result or [None]


def child_id(child: dict[str, Any]) -> str:
    return str(child.get("child_id") or child.get("chunk_id") or child.get("_id") or "")


def parent_id(child: dict[str, Any]) -> str:
    metadata = child.get("metadata") or {}
    return str(
        child.get("parent_id")
        or metadata.get("parent_section_id")
        or metadata.get("source_parent_id")
        or ""
    )


def group_parent_ids(
    ranked_children: list[tuple[float, dict[str, Any]]],
    available_parent_ids: set[str],
) -> list[str]:
    best_scores: dict[str, float] = {}
    for score, child in ranked_children:
        parent = parent_id(child)
        if not parent or parent not in available_parent_ids:
            continue
        best_scores[parent] = max(float(score), best_scores.get(parent, float("-inf")))
    return sorted(best_scores, key=best_scores.__getitem__, reverse=True)[:FINAL_K]


def event_metrics(
    case: dict[str, Any], cohort: str | None, ranked_parent_ids: list[str]
) -> dict[str, float]:
    from src.evaluation.suites import _retrieval_metrics_for_execution_units

    grades: dict[str, int] = {}
    for judgment in case.get("relevance_judgments") or []:
        if not isinstance(judgment, dict):
            continue
        if cohort is not None and effective_cohort(judgment.get("cohort")) != cohort:
            continue
        parent = str(judgment.get("parent_section_id") or "")
        if parent:
            grades[parent] = max(grades.get(parent, 0), int(judgment.get("grade") or 0))
    metrics, _ = _retrieval_metrics_for_execution_units(
        case=case,
        ranked_ids=ranked_parent_ids,
        grade_by_id=grades,
        scope="pure",
    )
    return {
        "hit_at_5": float(metrics["hit_at_5"]),
        "mrr": float(metrics["reciprocal_rank"]),
        "ndcg_at_5": float(metrics["ndcg_at_5"]),
        "required_source_recall_at_5": float(
            metrics["required_source_recall_at_5"]
        ),
    }


def load_events(cases_path: Path, capture_path: Path) -> list[dict[str, Any]]:
    if sha256_file(cases_path) != EXPECTED_CASES_SHA256:
        raise EvaluationError("official retrieval dataset hash does not match")
    if sha256_file(capture_path) != EXPECTED_CAPTURE_SHA256:
        raise EvaluationError("saved candidate capture hash does not match")
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    capture = read_jsonl(capture_path)
    if len(cases) != EXPECTED_CASE_COUNT or len(capture) != EXPECTED_CASE_COUNT:
        raise EvaluationError("expected exactly 155 cases and capture records")
    case_by_id = {str(case["id"]): case for case in cases}
    if len(case_by_id) != EXPECTED_CASE_COUNT:
        raise EvaluationError("case IDs are missing or duplicated")

    events: list[dict[str, Any]] = []
    for record in capture:
        case_id = str(record.get("case_id") or "")
        case = case_by_id.get(case_id)
        if case is None or record.get("status") != "ok":
            raise EvaluationError(f"invalid capture record: {case_id!r}")
        query = str(record.get("normalized_query") or "")
        if record.get("query_sha256") != sha256_text(str(case.get("query") or "")):
            raise EvaluationError(f"query identity mismatch: {case_id}")
        if record.get("event_cohorts") != event_cohorts(case):
            raise EvaluationError(f"cohort expansion mismatch: {case_id}")
        for event_index, event in enumerate(record.get("events") or []):
            children = list(event.get("children") or [])
            if len(children) != 24 or len({child_id(child) for child in children}) != 24:
                raise EvaluationError(f"candidate pool mismatch: {case_id}:{event_index}")
            for child in children:
                content = str(child.get("content") or "")
                if child.get("content_sha256") != sha256_text(content):
                    raise EvaluationError(f"candidate content mismatch: {case_id}:{event_index}")
            rrf_scores = [float(score) for score in event.get("rrf_scores") or []]
            if len(rrf_scores) != 24:
                raise EvaluationError(f"RRF score mismatch: {case_id}:{event_index}")
            available = set(event.get("available_parent_ids") or [])
            baseline_parents = group_parent_ids(list(zip(rrf_scores, children)), available)
            if baseline_parents != list(event.get("baseline_parent_ids") or []):
                raise EvaluationError(f"baseline grouping mismatch: {case_id}:{event_index}")
            cohort = event.get("cohort")
            events.append(
                {
                    "event_key": f"{case_id}:{event_index}:{cohort or 'general'}",
                    "case_id": case_id,
                    "event_index": event_index,
                    "cohort": cohort,
                    "query": query,
                    "children": children[:CANDIDATE_COUNT],
                    "available_parent_ids": sorted(available),
                    "baseline_parent_ids": baseline_parents,
                    "baseline": event_metrics(case, cohort, baseline_parents),
                    "case": case,
                }
            )
    if len(events) != EXPECTED_EVENT_COUNT:
        raise EvaluationError(f"expected 157 events, got {len(events)}")
    return events


def call_cohere(
    api_key: str,
    query: str,
    documents: list[str],
    *,
    timeout_seconds: float,
    max_attempts: int = 5,
) -> tuple[dict[str, Any], float]:
    payload = {
        "model": MODEL,
        "query": query,
        "documents": documents,
        "top_n": len(documents),
        "max_tokens_per_doc": 4096,
    }
    for attempt in range(max_attempts):
        started = time.perf_counter()
        try:
            response = requests.post(
                "https://api.cohere.com/v2/rerank",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout_seconds,
            )
        except requests.RequestException as exc:
            if attempt == max_attempts - 1:
                raise EvaluationError("Cohere request failed after retries") from exc
            time.sleep(min(60.0, 8.0 * (attempt + 1)))
            continue
        latency_ms = (time.perf_counter() - started) * 1000.0
        if response.status_code == 200:
            return response.json(), latency_ms
        if response.status_code not in {429, 500, 503, 504} or attempt == max_attempts - 1:
            raise EvaluationError(f"Cohere API returned HTTP {response.status_code}")
        retry_after = response.headers.get("Retry-After")
        delay = float(retry_after) if retry_after else min(60.0, 8.0 * (attempt + 1))
        time.sleep(max(1.0, delay))
    raise EvaluationError("Cohere request exhausted retries")


def validate_response(response: dict[str, Any], candidate_count: int) -> list[tuple[int, float]]:
    ranked = [
        (int(item["index"]), float(item["relevance_score"]))
        for item in response.get("results") or []
    ]
    indices = [index for index, _ in ranked]
    if len(ranked) != candidate_count or set(indices) != set(range(candidate_count)):
        raise EvaluationError("Cohere response changed or omitted candidate indices")
    if any(not math.isfinite(score) or not 0.0 <= score <= 1.0 for _, score in ranked):
        raise EvaluationError("Cohere returned an invalid relevance score")
    return ranked


def validate_checkpoint_row(row: dict[str, Any], event: dict[str, Any]) -> None:
    """Reject checkpoint rows that do not belong to the exact live event."""

    children = list(event["children"])
    candidate_ids = [child_id(child) for child in children]
    content_hashes = [
        sha256_text(str(child.get("content") or "")) for child in children
    ]
    expected = {
        "event_key": event["event_key"],
        "case_id": event["case_id"],
        "event_index": event["event_index"],
        "cohort": event["cohort"],
        "query_sha256": sha256_text(event["query"]),
        "candidate_child_ids": candidate_ids,
        "candidate_content_sha256": content_hashes,
        "model": MODEL,
        "candidate_count": CANDIDATE_COUNT,
    }
    for field, value in expected.items():
        if row.get(field) != value:
            raise EvaluationError(
                f"checkpoint identity mismatch for {event['event_key']}: {field}"
            )
    ranked_ids = list(row.get("cohere_ranked_child_ids") or [])
    scores = [float(score) for score in row.get("cohere_scores") or []]
    if len(ranked_ids) != len(candidate_ids) or set(ranked_ids) != set(candidate_ids):
        raise EvaluationError(
            f"checkpoint ranking mismatch for {event['event_key']}"
        )
    if len(scores) != len(candidate_ids) or any(
        not math.isfinite(score) or not 0.0 <= score <= 1.0 for score in scores
    ):
        raise EvaluationError(f"checkpoint score mismatch for {event['event_key']}")


def mean(rows: list[dict[str, Any]], arm: str, metric: str) -> float:
    return sum(float(row[arm][metric]) for row in rows) / len(rows)


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def build_report(
    rows: list[dict[str, Any]], cases_path: Path, capture_path: Path
) -> dict[str, Any]:
    metrics = ("hit_at_5", "mrr", "ndcg_at_5", "required_source_recall_at_5")
    baseline = {metric: mean(rows, "baseline", metric) for metric in metrics}
    cohere = {metric: mean(rows, "cohere", metric) for metric in metrics}
    latency = [float(row["cohere_latency_ms"]) for row in rows]
    better = sum(row["cohere"]["ndcg_at_5"] > row["baseline"]["ndcg_at_5"] for row in rows)
    worse = sum(row["cohere"]["ndcg_at_5"] < row["baseline"]["ndcg_at_5"] for row in rows)
    return {
        "status": "complete",
        "artifact_type": "cohere_saved_candidate_retrieval_benchmark",
        "git_head": git_head(),
        "runner": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
        },
        "dataset": {"path": str(cases_path), "sha256": sha256_file(cases_path)},
        "source_capture": {"path": str(capture_path), "sha256": sha256_file(capture_path)},
        "scope": {
            "saved_capture_reused": True,
            "retrieval_called": False,
            "planner_called": False,
            "composer_called": False,
            "judge_called": False,
            "end_to_end_claim": False,
        },
        "model": MODEL,
        "candidate_count": CANDIDATE_COUNT,
        "final_parent_count": FINAL_K,
        "event_count": len(rows),
        "baseline": baseline,
        "cohere": cohere,
        "delta": {metric: cohere[metric] - baseline[metric] for metric in metrics},
        "paired_ndcg": {"better": better, "equal": len(rows) - better - worse, "worse": worse},
        "latency_ms": {
            "mean": sum(latency) / len(latency),
            "p50": percentile(latency, 0.5),
            "p95": percentile(latency, 0.95),
            "max": max(latency),
        },
        "successful_response_search_units": sum(
            int(row.get("billed_search_units") or 0) for row in rows
        ),
        "event_rows": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--capture", type=Path, default=DEFAULT_CAPTURE)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--min-interval-seconds", type=float, default=6.2)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    api_key = os.getenv("COHERE_API_KEY", "").strip()
    events = load_events(args.cases.resolve(), args.capture.resolve())
    baseline = {
        metric: sum(event["baseline"][metric] for event in events) / len(events)
        for metric in ("hit_at_5", "mrr", "ndcg_at_5", "required_source_recall_at_5")
    }
    print(f"Validated {len(events)} events; baseline={json.dumps(baseline, sort_keys=True)}", flush=True)
    if args.validate_only:
        return 0
    if not api_key:
        raise EvaluationError("COHERE_API_KEY is required")

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "checkpoint.jsonl"
    checkpoint_rows = read_jsonl(checkpoint_path)
    existing = {row["event_key"]: row for row in checkpoint_rows}
    if len(existing) != len(checkpoint_rows):
        raise EvaluationError("checkpoint contains duplicate event keys")

    previous_request_at = 0.0
    for position, event in enumerate(events, start=1):
        key = event["event_key"]
        if key in existing:
            validate_checkpoint_row(existing[key], event)
            continue
        elapsed = time.monotonic() - previous_request_at
        if elapsed < args.min_interval_seconds:
            time.sleep(args.min_interval_seconds - elapsed)
        response, latency_ms = call_cohere(
            api_key,
            event["query"],
            [str(child.get("content") or "") for child in event["children"]],
            timeout_seconds=args.timeout_seconds,
        )
        previous_request_at = time.monotonic()
        ranking = validate_response(response, len(event["children"]))
        ranked_children = [(score, event["children"][index]) for index, score in ranking]
        parents = group_parent_ids(ranked_children, set(event["available_parent_ids"]))
        result = {
            "event_key": key,
            "case_id": event["case_id"],
            "event_index": event["event_index"],
            "cohort": event["cohort"],
            "query_sha256": sha256_text(event["query"]),
            "candidate_child_ids": [child_id(child) for child in event["children"]],
            "candidate_content_sha256": [sha256_text(str(child.get("content") or "")) for child in event["children"]],
            "model": MODEL,
            "candidate_count": CANDIDATE_COUNT,
            "cohere_ranked_child_ids": [child_id(event["children"][index]) for index, _ in ranking],
            "cohere_scores": [score for _, score in ranking],
            "cohere_parent_ids": parents,
            "baseline_parent_ids": event["baseline_parent_ids"],
            "baseline": event["baseline"],
            "cohere": event_metrics(event["case"], event["cohort"], parents),
            "cohere_latency_ms": latency_ms,
            "cohere_response_id": response.get("id"),
            "billed_search_units": int(
                (((response.get("meta") or {}).get("billed_units") or {}).get("search_units") or 0)
            ),
        }
        append_jsonl(checkpoint_path, result)
        existing[key] = result
        print(f"[{len(existing)}/{len(events)}] {key} {latency_ms:.0f} ms", flush=True)

    rows = [existing[event["event_key"]] for event in events]
    report = build_report(rows, args.cases.resolve(), args.capture.resolve())
    report_path = output_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "baseline",
                    "cohere",
                    "delta",
                    "paired_ndcg",
                    "latency_ms",
                    "successful_response_search_units",
                )
            },
            indent=2,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
