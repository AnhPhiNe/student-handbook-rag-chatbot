from __future__ import annotations

from typing import Any

# Release thresholds for the deployed service (the official_v1 production suite).
PRODUCTION_MINIMUMS = {
    "success_rate": 0.98,
    "telemetry_coverage": 1.0,
    "warm_cache_hit_rate": 0.90,
    "cold_cache_status_coverage": 1.0,
    "warm_cache_status_coverage": 1.0,
    "streaming_ttft_coverage": 1.0,
}
PRODUCTION_MAXIMUMS = {
    "http_429_rate": 0.0,
    "cold_cache_hit_rate": 0.0,
}
PRODUCTION_P95_LIMITS_MS = {
    "deterministic_p95_ms": 3_000.0,
    "warm_cache_p95_ms": 2_000.0,
    "rag_p95_ms": 45_000.0,
    "streaming_ttft_p95_ms": 10_000.0,
}


def _check(actual: Any, operator: str, threshold: float) -> dict[str, Any]:
    applicable = actual is not None
    if not applicable:
        passed = None
    elif operator == ">=":
        passed = float(actual) >= threshold
    else:
        passed = float(actual) <= threshold
    return {
        "actual": actual,
        "operator": operator,
        "threshold": threshold,
        "applicable": applicable,
        "passed": passed,
    }


def production_gates(summary: dict[str, Any]) -> dict[str, Any]:
    """Check a production-suite summary against the release thresholds."""

    checks = {name: _check(summary.get(name), ">=", t) for name, t in PRODUCTION_MINIMUMS.items()}
    checks.update(
        {name: _check(summary.get(name), "<=", t) for name, t in PRODUCTION_MAXIMUMS.items()}
    )
    scenario = summary.get("by_scenario") or {}
    p95 = {
        "deterministic_p95_ms": ((scenario.get("deterministic") or {}).get("latency_ms") or {}).get("p95"),
        "warm_cache_p95_ms": ((scenario.get("warm_cache") or {}).get("latency_ms") or {}).get("p95"),
        "rag_p95_ms": (summary.get("cold_regulation_rag_latency_ms") or {}).get("p95"),
        "streaming_ttft_p95_ms": (summary.get("streaming_ttft_ms") or {}).get("p95"),
    }
    checks.update(
        {name: _check(p95[name], "<=", t) for name, t in PRODUCTION_P95_LIMITS_MS.items()}
    )
    applicable = [check for check in checks.values() if check["applicable"]]
    return {
        "passed": bool(applicable) and all(check["passed"] is True for check in applicable),
        "checks": checks,
    }
