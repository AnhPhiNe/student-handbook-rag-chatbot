"""Frozen single-cohort-v2 evaluation bundle and deterministic contract checks."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
BUNDLE_DIR = ROOT / "data" / "eval" / "single_cohort_v2"
SCHEMA_VERSION = "single-cohort-v2.0"
EXPECTED_COUNTS = {
    "single_structured": (10, 4), "single_rag": (10, 4),
    "multi_entity": (15, 6), "two_structured": (18, 7),
    "mixed": (20, 8), "two_regulations": (15, 6),
    "three_to_six_requests": (12, 5), "robustness": (14, 6),
    "follow_up": (15, 6), "cohort_resolution": (11, 4),
    "failure_isolation": (10, 4),
}


@dataclass(frozen=True)
class BundleValidation:
    valid: bool
    errors: list[str]
    counts: dict[str, int]
    hashes: dict[str, str]


def _load(name: str) -> list[dict[str, Any]]:
    with (BUNDLE_DIR / name).open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, list):
        raise ValueError(f"{name} must contain a JSON list")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_bundle(bundle_dir: Path = BUNDLE_DIR) -> BundleValidation:
    errors: list[str] = []
    paths = {name: bundle_dir / name for name in ("dev.json", "hidden.json", "manifest.json")}
    hashes = {name: _sha(path) for name, path in paths.items() if path.exists()}
    if len(hashes) != len(paths):
        return BundleValidation(False, ["missing bundle file"], {}, hashes)
    suites: dict[str, list[dict[str, Any]]] = {}
    for name in ("dev.json", "hidden.json"):
        with paths[name].open(encoding="utf-8") as handle:
            value = json.load(handle)
        if not isinstance(value, list):
            errors.append(f"{name}: expected list")
            continue
        suites[name] = value
    expected_total = {"dev.json": 150, "hidden.json": 60}
    for name, cases in suites.items():
        if len(cases) != expected_total[name]:
            errors.append(f"{name}: expected {expected_total[name]}, got {len(cases)}")
        ids: set[str] = set()
        for case in cases:
            case_id = str(case.get("id") or "")
            if not case_id or case_id in ids:
                errors.append(f"{name}: duplicate/missing id {case_id}")
            ids.add(case_id)
            required = {"query", "selected_cohort", "chat_history", "expected", "category"}
            missing = required - set(case)
            if missing:
                errors.append(f"{case_id}: missing {sorted(missing)}")
                continue
            expected = case["expected"]
            if expected.get("outcome") not in {"execute", "clarify", "out_of_domain"}:
                errors.append(f"{case_id}: invalid outcome")
            if expected.get("context_mode") not in {"validated", "raw"}:
                errors.append(f"{case_id}: invalid context mode")
            requests = expected.get("atomic_requests") or []
            if len(requests) > 6:
                errors.append(f"{case_id}: more than six requests")
            for index, request in enumerate(requests, 1):
                if request.get("request_id") != f"r{index}":
                    errors.append(f"{case_id}: unstable request id")
                if request.get("request_kind") not in {"structured", "rag"}:
                    errors.append(f"{case_id}: invalid request kind")
                if not request.get("query_span"):
                    errors.append(f"{case_id}: missing query span")
            if expected.get("outcome") != "execute" and requests:
                errors.append(f"{case_id}: non-execute has requests")
    if suites:
        for category, (dev_count, hidden_count) in EXPECTED_COUNTS.items():
            if sum(case.get("category") == category for case in suites.get("dev.json", [])) != dev_count:
                errors.append(f"dev count mismatch: {category}")
            if sum(case.get("category") == category for case in suites.get("hidden.json", [])) != hidden_count:
                errors.append(f"hidden count mismatch: {category}")
        dev_queries = {str(case.get("query") or "").casefold() for case in suites.get("dev.json", [])}
        hidden_queries = {str(case.get("query") or "").casefold() for case in suites.get("hidden.json", [])}
        if dev_queries & hidden_queries:
            errors.append("dev/hidden query overlap")
    counts = {name: len(cases) for name, cases in suites.items()}
    return BundleValidation(not errors, errors, counts, hashes)


def exact_plan_match(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    """Strict planner comparison: order, tool, spans, slots, cohorts all bind."""
    keys = ("outcome", "context_mode", "effective_cohort", "effective_cohort_source")
    if any(expected.get(key) != actual.get(key) for key in keys):
        return False
    wanted = expected.get("atomic_requests") or []
    actual_requests = actual.get("atomic_requests") or actual.get("lookup_requests") or []
    if len(wanted) != len(actual_requests):
        return False
    for left, right in zip(wanted, actual_requests, strict=True):
        fields = ("request_id", "request_kind", "lookup_type", "intent", "query_span", "slots", "cohort_refs")
        if any(left.get(field) != right.get(field) for field in fields):
            return False
    return True


def failure_taxonomy(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(str(row.get("failure_type") or "pass") for row in rows))
