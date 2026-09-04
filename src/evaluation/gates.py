from __future__ import annotations

from typing import Any


def evaluate_gates(suite: str, summary: dict[str, Any]) -> dict[str, Any]:
    """Evaluate metric thresholds and return pass/fail gate details."""

    checks: dict[str, dict[str, Any]] = {}

    def minimum(name: str, threshold: float) -> None:
        actual = summary.get(name)
        applicable = actual is not None
        checks[name] = {
            "actual": actual,
            "operator": ">=",
            "threshold": threshold,
            "applicable": applicable,
            "passed": float(actual) >= threshold if applicable else None,
        }

    def maximum(name: str, threshold: float) -> None:
        actual = summary.get(name)
        applicable = actual is not None
        checks[name] = {
            "actual": actual,
            "operator": "<=",
            "threshold": threshold,
            "applicable": applicable,
            "passed": float(actual) <= threshold if applicable else None,
        }

    if suite == "deterministic":
        minimum("precision", 0.98)
        minimum("recall", 0.95)
        maximum("false_positive_rate", 0.02)
        minimum("citation_metadata_accuracy", 1.0)
        maximum("cross_cohort_leak", 0.0)
    elif suite == "retrieval":
        minimum("hit_at_3", 0.80)
        minimum("hit_at_5", 0.90)
        minimum("mrr", 0.70)
        minimum("ndcg_at_5", 0.75)
        minimum("content_type_match", 0.98)
        maximum("cohort_leak_rate", 0.0)
    elif suite == "judge":
        minimum("faithfulness", 0.90)
        minimum("answer_correctness", 0.82)
        minimum("citation_correctness", 0.90)
        minimum("numeric_accuracy", 0.95)
        maximum("hallucination_rate", 0.05)
        minimum("abstention_correct", 0.90)
        maximum("critical_false_passes", 1.0)
    elif suite == "production":
        minimum("success_rate", 0.98)
        maximum("http_429_rate", 0.0)
        minimum("telemetry_coverage", 1.0)
        maximum("cold_cache_hit_rate", 0.0)
        minimum("warm_cache_hit_rate", 0.90)
        minimum("cold_cache_status_coverage", 1.0)
        minimum("warm_cache_status_coverage", 1.0)
        minimum("streaming_ttft_coverage", 1.0)
        scenario = summary.get("by_scenario") or {}
        derived = {
            "deterministic_p95_ms": (
                (scenario.get("deterministic") or {}).get("latency_ms") or {}
            ).get("p95"),
            "warm_cache_p95_ms": (
                (scenario.get("warm_cache") or {}).get("latency_ms") or {}
            ).get("p95"),
            "rag_p95_ms": (summary.get("cold_regulation_rag_latency_ms") or {}).get(
                "p95"
            ),
            "streaming_ttft_p95_ms": (summary.get("streaming_ttft_ms") or {}).get(
                "p95"
            ),
        }
        for name, threshold in (
            ("deterministic_p95_ms", 3_000.0),
            ("warm_cache_p95_ms", 2_000.0),
            ("rag_p95_ms", 45_000.0),
            ("streaming_ttft_p95_ms", 10_000.0),
        ):
            actual = derived[name]
            checks[name] = {
                "actual": actual,
                "operator": "<=",
                "threshold": threshold,
                "applicable": actual is not None,
                "passed": float(actual) <= threshold if actual is not None else None,
            }
    elif suite == "faults":
        minimum("pass_rate", 1.0)

    applicable_checks = [
        check for check in checks.values() if check.get("applicable", True)
    ]
    return {
        "passed": bool(applicable_checks)
        and all(check.get("passed") is True for check in applicable_checks),
        "checks": checks,
    }
