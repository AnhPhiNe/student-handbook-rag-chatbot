"""Production suite: send the official requests to a deployed API and check
transport, cache behaviour and latency."""

from __future__ import annotations

import json
import time
from uuid import NAMESPACE_URL, uuid5
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request
from tqdm import tqdm

from .metrics import (
    safe_mean,
)
from .shared import (
    case_history_kwargs,
    eval_checkpoint_identity,
    latency_summary,
    load_eval_checkpoint,
    save_eval_checkpoint,
)


def _expected_response_status(case: dict[str, Any]) -> str:
    expected_path = case.get("expected_path")
    expected_behavior = case.get("expected_answer_behavior")
    if expected_path == "clarify" and expected_behavior == "abstain":
        return "answered_or_guardrail"
    if expected_path == "clarify":
        return "needs_clarification"
    if expected_path == "out_of_domain":
        return "out_of_domain"
    return "answered"


def _response_status_matches_expected(
    response_status: str,
    expected_status: str,
) -> bool:
    if expected_status == "answered_or_guardrail":
        return response_status in {
            "answered",
            "needs_clarification",
            "out_of_domain",
        }
    return response_status == expected_status


def _summarize_production_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    streaming_rows = [row for row in rows if row.get("scenario") == "streaming"]
    cold_rows = [row for row in rows if row.get("scenario") == "cold_rag"]
    warm_rows = [row for row in rows if row.get("scenario") == "warm_cache"]
    cold_regulation_rows = [
        row for row in cold_rows if row.get("expected_path") == "regulation_rag"
    ]

    cold_cache_observed = [
        row for row in cold_rows if row.get("used_cache") is not None
    ]
    warm_cache_observed = [
        row for row in warm_rows if row.get("used_cache") is not None
    ]
    cold_cache_hit_rate = safe_mean(
        [float(bool(row.get("used_cache"))) for row in cold_cache_observed]
    )
    warm_cache_hit_rate = safe_mean(
        [float(bool(row.get("used_cache"))) for row in warm_cache_observed]
    )
    cold_cache_coverage = (
        len(cold_cache_observed) / len(cold_rows) if cold_rows else 0.0
    )
    warm_cache_coverage = (
        len(warm_cache_observed) / len(warm_rows) if warm_rows else 0.0
    )
    streaming_ttft_coverage = (
        len([row for row in streaming_rows if row.get("ttft_ms") is not None])
        / len(streaming_rows)
        if streaming_rows
        else 0.0
    )

    summary: dict[str, Any] = {
        "n": len(rows),
        "success_rate": safe_mean([float(row["success"]) for row in rows]),
        "transport_success_rate": safe_mean(
            [float(bool(row.get("transport_success"))) for row in rows]
        ),
        "payload_success_rate": safe_mean(
            [float(bool(row.get("payload_success"))) for row in rows]
        ),
        "response_status_accuracy": safe_mean(
            [
                float(bool(row.get("expected_status_match")))
                for row in rows
                if row.get("expected_path")
            ]
        ),
        "error_rate": safe_mean([float(not row["success"]) for row in rows]),
        "http_429_rate": safe_mean(
            [float(row.get("status_code") == 429) for row in rows]
        ),
        "timeout_rate": safe_mean(
            [float("timed out" in str(row.get("error") or "").lower()) for row in rows]
        ),
        "latency_ms": latency_summary([row["latency_ms"] for row in rows]),
        "streaming_ttft_ms": latency_summary(
            [row["ttft_ms"] for row in streaming_rows if row.get("ttft_ms") is not None]
        ),
        "streaming_ttft_coverage": streaming_ttft_coverage,
        "cold_regulation_rag_latency_ms": latency_summary(
            [row["latency_ms"] for row in cold_regulation_rows]
        ),
        "cache_hit_rate": safe_mean(
            [float(bool(row.get("used_cache"))) for row in rows]
        ),
        "cold_cache_hit_rate": cold_cache_hit_rate,
        "warm_cache_hit_rate": warm_cache_hit_rate,
        "cold_cache_status_coverage": cold_cache_coverage,
        "warm_cache_status_coverage": warm_cache_coverage,
        "cache_protocol_valid": (
            cold_cache_coverage == 1.0
            and warm_cache_coverage == 1.0
            and cold_cache_hit_rate == 0.0
            and warm_cache_hit_rate is not None
            and warm_cache_hit_rate >= 0.90
        ),
        "source_count_mean": safe_mean(
            [float(row.get("source_count", 0)) for row in rows]
        ),
        "context_chars_mean": safe_mean(
            [float(row.get("context_chars", 0)) for row in rows]
        ),
        "answer_chars_mean": safe_mean(
            [float(row.get("answer_chars", 0)) for row in rows]
        ),
        "source_utilization": safe_mean(
            [min(1.0, float(row.get("source_count", 0)) / 5.0) for row in rows]
        ),
        "telemetry_coverage": safe_mean(
            [
                float(bool(row.get("telemetry")))
                for row in rows
                if row.get("scenario") != "streaming"
            ]
        ),
        "key_distribution": dict(
            Counter(
                row.get("key_fingerprint") for row in rows if row.get("key_fingerprint")
            )
        ),
        "retry_count": sum(int(row.get("retry_count") or 0) for row in rows),
        "cooldown_events": sum(int(row.get("cooldown_events") or 0) for row in rows),
        "realistic_score": safe_mean(
            [
                float(row["success"])
                for row in rows
                if row.get("eval_split") == "realistic"
            ]
        ),
        "stress_score": safe_mean(
            [float(row["success"]) for row in rows if row.get("eval_split") == "stress"]
        ),
        "by_scenario": {},
        "by_expected_path": {},
    }
    for scenario in sorted({str(row["scenario"]) for row in rows}):
        group = [row for row in rows if row["scenario"] == scenario]
        summary["by_scenario"][scenario] = {
            "n": len(group),
            "success_rate": safe_mean([float(row["success"]) for row in group]),
            "latency_ms": latency_summary([row["latency_ms"] for row in group]),
        }
    for expected_path in sorted(
        {str(row["expected_path"]) for row in rows if row.get("expected_path")}
    ):
        group = [row for row in rows if row.get("expected_path") == expected_path]
        summary["by_expected_path"][expected_path] = {
            "n": len(group),
            "success_rate": safe_mean([float(row["success"]) for row in group]),
            "status_accuracy": safe_mean(
                [float(bool(row.get("expected_status_match"))) for row in group]
            ),
            "latency_ms": latency_summary([row["latency_ms"] for row in group]),
        }
    return summary


def evaluate_production(
    cases: list[dict[str, Any]],
    *,
    base_url: str,
    limit: int | None = None,
    checkpoint_path: Path | None = None,
    resume: bool = False,
    checkpoint_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the production evaluation workflow and quality gates."""

    selected = cases[:limit]
    identity = (
        eval_checkpoint_identity(
            cases,
            suite="production",
            context=checkpoint_context,
            base_url=base_url,
        )
        if checkpoint_path
        else None
    )
    rows = load_eval_checkpoint(checkpoint_path, resume=resume, identity=identity)
    completed_ids = {row["id"] for row in rows}
    pending = [case for case in selected if case["id"] not in completed_ids]

    def run(case: dict[str, Any]) -> dict[str, Any]:
        endpoint = "/chat/stream" if case["scenario"] == "streaming" else "/chat"
        # Production browsers send an anonymous UUID used by the API's
        # per-browser rate limiter.  Reuse the originating identity for a warm
        # cache repeat; independent cases represent independent clients.  The
        # public-IP abuse guard still applies to the whole evaluation run.
        client_identity = str(case.get("repeat_of") or case["id"])
        client_id = str(uuid5(NAMESPACE_URL, f"student-rag-eval:{client_identity}"))
        payload = json.dumps(
            {
                "query": case["query"],
                "cohort": case.get("cohort"),
                "include_debug": True,
                **case_history_kwargs(case),
            }
        ).encode("utf-8")
        req = urllib_request.Request(
            base_url.rstrip("/") + endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-Client-ID": client_id,
            },
            method="POST",
        )
        started = time.perf_counter()
        ttft = None
        status_code = 0
        body = b""
        try:
            stream_done = False
            stream_error = False
            stream_token_chars = 0
            stream_metadata: dict[str, Any] = {}
            answer_parts: list[str] = []
            with urllib_request.urlopen(
                req, timeout=float(case.get("timeout_seconds", 90))
            ) as response:
                status_code = response.status
                if endpoint.endswith("/stream"):
                    chunks: list[bytes] = []
                    current_event = ""
                    for line in response:
                        chunks.append(line)
                        decoded = line.decode("utf-8", errors="replace").strip()
                        if decoded.startswith("event:"):
                            current_event = decoded.split(":", 1)[1].strip()
                            stream_done = stream_done or current_event == "done"
                            stream_error = stream_error or current_event == "error"
                        elif decoded.startswith("data:"):
                            raw_data = decoded.split(":", 1)[1].strip()
                            try:
                                event_data = json.loads(raw_data)
                            except json.JSONDecodeError:
                                event_data = {}
                            if current_event == "metadata":
                                stream_metadata = event_data
                            elif current_event == "token":
                                answer_parts.append(str(event_data.get("text") or ""))
                                stream_token_chars += len(
                                    str(event_data.get("text") or "")
                                )
                                if ttft is None:
                                    ttft = (time.perf_counter() - started) * 1000
                    body = b"".join(chunks)
                else:
                    body = response.read()
            parsed = (
                json.loads(body.decode("utf-8")) if endpoint.endswith("chat") else {}
            )
            response_payload = (
                stream_metadata if endpoint.endswith("/stream") else parsed
            )
            debug = response_payload.get("debug") or {}
            telemetry = debug.get("evaluation_telemetry") or {}
            transport_success = 200 <= status_code < 300
            if endpoint.endswith("/stream"):
                payload_success = (
                    stream_done
                    and not stream_error
                    and str(stream_metadata.get("status") or "")
                    not in {"api_error", "retrieval_error"}
                    and not stream_metadata.get("error_type")
                    and (
                        stream_token_chars > 0
                        or str(stream_metadata.get("status") or "")
                        in {
                            "needs_clarification",
                            "out_of_domain",
                        }
                    )
                )
                answer_chars = stream_token_chars
                answer_text = "".join(answer_parts)
            else:
                answer_text = str(parsed.get("answer") or "").strip()
                payload_success = bool(answer_text) and not parsed.get("error_type")
                answer_chars = len(answer_text)
            response_status = str(response_payload.get("status") or "")
            expected_status = _expected_response_status(case)
            return {
                **case,
                "success": transport_success and payload_success,
                "transport_success": transport_success,
                "payload_success": payload_success,
                "status_code": status_code,
                "latency_ms": (time.perf_counter() - started) * 1000,
                "ttft_ms": ttft,
                "answer_chars": answer_chars,
                "answer": answer_text,
                "response_payload": response_payload,
                "stream_done": stream_done if endpoint.endswith("/stream") else None,
                "stream_error": stream_error if endpoint.endswith("/stream") else None,
                "response_status": response_status,
                "response_intent": response_payload.get("intent"),
                "response_strategy": response_payload.get("strategy"),
                "response_error_type": response_payload.get("error_type"),
                "response_error_message": response_payload.get("error_message"),
                "expected_response_status": expected_status,
                "expected_status_match": _response_status_matches_expected(
                    response_status,
                    expected_status,
                ),
                "used_cache": response_payload.get("used_cache"),
                "source_count": len(
                    response_payload.get("citations_used")
                    or response_payload.get("citations")
                    or []
                ),
                "context_chars": int(
                    debug.get("context_used_length")
                    or telemetry.get("context_chars")
                    or 0
                ),
                "key_fingerprint": telemetry.get("key_fingerprint"),
                "retry_count": int(telemetry.get("retry_count") or 0),
                "cooldown_events": int(telemetry.get("cooldown_events") or 0),
                "telemetry": telemetry,
            }
        except urllib_error.HTTPError as exc:
            try:
                error_body = exc.read().decode("utf-8", errors="replace")
            except OSError:
                error_body = ""
            return {
                **case,
                "success": False,
                "transport_success": False,
                "payload_success": False,
                "status_code": int(exc.code),
                "latency_ms": (time.perf_counter() - started) * 1000,
                "ttft_ms": ttft,
                "expected_response_status": _expected_response_status(case),
                "expected_status_match": False,
                "error": f"HTTP {exc.code}: {error_body or exc.reason}",
            }
        except Exception as exc:
            return {
                **case,
                "success": False,
                "status_code": status_code,
                "latency_ms": (time.perf_counter() - started) * 1000,
                "ttft_ms": ttft,
                "expected_response_status": _expected_response_status(case),
                "expected_status_match": False,
                "error": str(exc),
            }

    sequential = [case for case in pending if case["scenario"] != "burst"]
    sequential_progress = tqdm(
        sequential,
        desc="Production Eval",
        unit="req",
        dynamic_ncols=True,
    )
    for case in sequential_progress:
        sequential_progress.set_postfix_str(str(case.get("id") or "unknown"))
        row = run(case)
        rows.append(row)
        save_eval_checkpoint(checkpoint_path, rows, identity=identity)
        sequential_progress.set_postfix(
            {
                "case": case.get("id"),
                "ok": int(bool(row.get("success"))),
                "ms": int(float(row.get("latency_ms") or 0)),
            },
            refresh=False,
        )
    bursts = [case for case in pending if case["scenario"] == "burst"]
    by_concurrency: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for case in bursts:
        by_concurrency[int(case.get("concurrency", 3))].append(case)
    for concurrency, group in by_concurrency.items():
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {executor.submit(run, case): case for case in group}
            burst_progress = tqdm(
                as_completed(futures),
                total=len(futures),
                desc=f"Production Burst c={concurrency}",
                unit="req",
                dynamic_ncols=True,
            )
            for future in burst_progress:
                case = futures[future]
                row = future.result()
                rows.append(row)
                save_eval_checkpoint(checkpoint_path, rows, identity=identity)
                burst_progress.set_postfix(
                    {
                        "case": case.get("id"),
                        "ok": int(bool(row.get("success"))),
                        "ms": int(float(row.get("latency_ms") or 0)),
                    },
                    refresh=False,
                )

    by_id = {row["id"]: row for row in rows}
    rows = [by_id[case["id"]] for case in selected if case["id"] in by_id]
    summary = _summarize_production_rows(rows)
    return {
        "suite": "production",
        "base_url": base_url,
        "summary": summary,
        "cases": rows,
    }
