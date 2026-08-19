"""Validation, exact-plan comparison and release gates for single-cohort-v2."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
BUNDLE_DIR = ROOT / "data" / "eval" / "single_cohort_v2"
SCHEMA_VERSION = "single-cohort-v2.1"
EXPECTED_COUNTS = {
    "single_structured": (10, 4), "single_rag": (10, 4),
    "multi_entity": (15, 6), "two_structured": (18, 7),
    "mixed": (20, 8), "two_regulations": (15, 6),
    "three_to_six_requests": (12, 5), "robustness": (14, 6),
    "follow_up": (15, 6), "cohort_resolution": (11, 4),
    "failure_isolation": (10, 4),
}
PLANNER_CONTEXT_MODES = {"standalone", "follow_up", "ambiguous"}
QUERY_MODES = {"validated", "raw"}
REQUEST_STATUSES = {"ok", "no_match", "invalid", "unresolved", "error"}
REQUIRED_TOOLS = {
    "foreign_language", "study_duration", "scholarship_classification",
    "scoring", "student_service", "office", "faculty", "program", "formula",
}


@dataclass(frozen=True)
class BundleValidation:
    valid: bool
    errors: list[str]
    counts: dict[str, int]
    hashes: dict[str, str]
    coverage: dict[str, Any]


@dataclass(frozen=True)
class ReleaseGateResult:
    passed: bool
    checks: dict[str, bool]
    missing_metrics: list[str]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").casefold()).replace("đ", "d")
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def _template_signature(query: str) -> str:
    normalized = _normalize(query)
    normalized = re.sub(r"\bk(?:48|49|50|51)\b", "<cohort>", normalized)
    normalized = re.sub(r"\b\d+(?:\s+\d+)?\b", "<number>", normalized)
    return normalized


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _case_errors(case: Mapping[str, Any], suite_name: str) -> list[str]:
    errors: list[str] = []
    case_id = str(case.get("id") or "missing-id")
    required = {
        "id", "category", "template_id", "entity_signature",
        "conversation_pattern", "query", "selected_cohort", "chat_history", "expected",
    }
    missing = required - set(case)
    if missing:
        return [f"{suite_name}/{case_id}: missing {sorted(missing)}"]
    expected = case.get("expected")
    if not isinstance(expected, Mapping):
        return [f"{suite_name}/{case_id}: expected must be object"]
    if expected.get("outcome") not in {"execute", "clarify", "out_of_domain"}:
        errors.append(f"{suite_name}/{case_id}: invalid outcome")
    if expected.get("context_mode") not in PLANNER_CONTEXT_MODES:
        errors.append(f"{suite_name}/{case_id}: invalid planner context_mode")
    if expected.get("query_mode") not in QUERY_MODES:
        errors.append(f"{suite_name}/{case_id}: invalid query_mode")
    requests = expected.get("atomic_requests") or []
    if not isinstance(requests, list) or len(requests) > 6:
        errors.append(f"{suite_name}/{case_id}: invalid request list")
        return errors
    if expected.get("outcome") != "execute" and requests:
        errors.append(f"{suite_name}/{case_id}: non-execute contains requests")
    if bool(expected.get("retrieval_executed")) != bool(
        expected.get("outcome") == "execute" and requests
    ):
        errors.append(f"{suite_name}/{case_id}: retrieval invariant mismatch")
    query = str(case.get("query") or "")
    history_text = " ".join(str(item.get("content") or "") for item in case.get("chat_history") or [] if isinstance(item, Mapping))
    for index, request in enumerate(requests, 1):
        if request.get("request_id") != f"r{index}":
            errors.append(f"{suite_name}/{case_id}: unstable request id")
        kind = request.get("request_kind")
        if kind not in {"structured", "rag"}:
            errors.append(f"{suite_name}/{case_id}: invalid request kind")
        if kind == "structured" and not request.get("tool_name"):
            errors.append(f"{suite_name}/{case_id}: structured request missing tool_name")
        if kind == "rag" and request.get("tool_name") is not None:
            errors.append(f"{suite_name}/{case_id}: RAG request declares tool_name")
        if request.get("expected_status") not in REQUEST_STATUSES:
            errors.append(f"{suite_name}/{case_id}: invalid expected status")
        span = str(request.get("query_span") or "")
        if not span or (_normalize(span) not in _normalize(query) and _normalize(span) not in _normalize(history_text)):
            errors.append(f"{suite_name}/{case_id}: ungrounded query_span r{index}")
        if not request.get("expected_source_contract") or request.get("citation_scope") != f"r{index}":
            errors.append(f"{suite_name}/{case_id}: missing request source binding")
    return errors


def validate_bundle(bundle_dir: Path = BUNDLE_DIR) -> BundleValidation:
    errors: list[str] = []
    paths = {name: bundle_dir / name for name in ("dev.json", "hidden.json", "manifest.json")}
    if not all(path.exists() for path in paths.values()):
        hashes = {name: _sha(path) for name, path in paths.items() if path.exists()}
        return BundleValidation(False, ["missing bundle file"], {}, hashes, {})
    manifest = _load(paths["manifest.json"])
    suites = {"dev": _load(paths["dev.json"]), "hidden": _load(paths["hidden.json"])}
    hashes = {f"{name}.json": _sha(paths[f"{name}.json"]) for name in suites}
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append("manifest schema version mismatch")
    for filename, digest in hashes.items():
        if manifest.get("files", {}).get(filename) != digest:
            errors.append(f"frozen hash mismatch: {filename}")
    for suite_name, cases in suites.items():
        expected_total = 150 if suite_name == "dev" else 60
        if not isinstance(cases, list) or len(cases) != expected_total:
            errors.append(f"{suite_name}: expected {expected_total} cases")
            continue
        ids = [str(case.get("id") or "") for case in cases]
        if len(ids) != len(set(ids)):
            errors.append(f"{suite_name}: duplicate ids")
        queries = [_normalize(case.get("query")) for case in cases]
        if len(queries) != len(set(queries)):
            errors.append(f"{suite_name}: duplicate normalized queries")
        for case in cases:
            errors.extend(_case_errors(case, suite_name))
        for category, pair in EXPECTED_COUNTS.items():
            expected_count = pair[0 if suite_name == "dev" else 1]
            actual = sum(case.get("category") == category for case in cases)
            if actual != expected_count:
                errors.append(f"{suite_name}: {category} expected {expected_count}, got {actual}")

    dev, hidden = suites.get("dev", []), suites.get("hidden", [])
    for field in ("template_id", "entity_signature", "conversation_pattern"):
        if {case.get(field) for case in dev} & {case.get(field) for case in hidden}:
            errors.append(f"dev/hidden overlap: {field}")
    dev_templates = {_template_signature(case.get("query") or "") for case in dev}
    hidden_templates = {_template_signature(case.get("query") or "") for case in hidden}
    if dev_templates & hidden_templates:
        errors.append("dev/hidden normalized template overlap")

    all_cases = dev + hidden
    requests = [request for case in all_cases for request in case.get("expected", {}).get("atomic_requests") or []]
    tools = {request.get("tool_name") for request in requests if request.get("tool_name")}
    statuses = {request.get("expected_status") for request in requests}
    request_counts = {len(case.get("expected", {}).get("atomic_requests") or []) for case in all_cases}
    two_structured = [case for case in all_cases if case.get("category") == "two_structured"]
    same_tool = any(len({request.get("tool_name") for request in case["expected"]["atomic_requests"]}) == 1 for case in two_structured)
    different_tool = any(len({request.get("tool_name") for request in case["expected"]["atomic_requests"]}) > 1 for case in two_structured)
    coverage = {
        "tools": sorted(tools),
        "statuses": sorted(statuses),
        "request_counts": sorted(request_counts),
        "same_tool_pair": same_tool,
        "different_tool_pair": different_tool,
        "tampering_cases": sum(bool(case.get("fault_injection", {}).get("type") == "plan_tampering") for case in all_cases if isinstance(case.get("fault_injection"), Mapping)),
    }
    if not REQUIRED_TOOLS.issubset(tools):
        errors.append(f"missing tool coverage: {sorted(REQUIRED_TOOLS - tools)}")
    if not REQUEST_STATUSES.issubset(statuses):
        errors.append(f"missing status coverage: {sorted(REQUEST_STATUSES - statuses)}")
    if not {3, 4, 5, 6}.issubset(request_counts):
        errors.append("missing 3-6 request coverage")
    if not same_tool or not different_tool:
        errors.append("missing same/different tool pair coverage")
    if coverage["tampering_cases"] < 2:
        errors.append("missing plan tampering coverage")
    counts = {name: len(cases) for name, cases in suites.items() if isinstance(cases, list)}
    return BundleValidation(not errors, errors, counts, hashes, coverage)


def exact_plan_match(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    top_fields = ("outcome", "context_mode", "effective_cohort", "effective_cohort_source")
    if any(expected.get(field) != actual.get(field) for field in top_fields):
        return False
    expected_requests = expected.get("atomic_requests") or []
    actual_requests = actual.get("atomic_requests") or actual.get("lookup_requests") or []
    if len(expected_requests) != len(actual_requests):
        return False
    for index, (left, right) in enumerate(zip(expected_requests, actual_requests, strict=True), 1):
        actual_tool = right.get("tool_name") or right.get("lookup_type")
        comparisons = {
            "request_id": right.get("request_id") or f"r{index}",
            "request_kind": right.get("request_kind"),
            "tool_name": actual_tool,
            "intent": right.get("intent"),
            "query_span": right.get("query_span"),
            "slots": right.get("slots") or {},
            "cohort_refs": right.get("cohort_refs") or [],
        }
        if any(left.get(field) != value for field, value in comparisons.items()):
            return False
    return True


def evaluate_release_gates(metrics: Mapping[str, Any]) -> ReleaseGateResult:
    thresholds = {
        "contract_invariants": lambda value: value == 1.0,
        "multi_cohort_rejection": lambda value: value == 1.0,
        "structured_source_binding": lambda value: value == 1.0,
        "structured_to_rag_fallbacks": lambda value: value == 0,
        "cross_request_leakage": lambda value: value == 0,
        "dev_exact_plan": lambda value: value >= 0.95,
        "hidden_exact_plan": lambda value: value >= 0.90,
        "retrieval_hit_at_5": lambda value: value >= 0.90,
        "citation_binding": lambda value: value >= 0.95,
        "faithfulness": lambda value: value >= 0.90,
        "answer_correctness": lambda value: value >= 0.85,
        "hallucination_rate": lambda value: value <= 0.05,
        "critical_false_pass": lambda value: value == 0,
        "provider_failures": lambda value: value == 0,
        "quality_checks_passed": lambda value: value is True,
        "parity_passed": lambda value: value is True,
    }
    missing = [name for name in thresholds if name not in metrics]
    checks = {
        name: bool(predicate(metrics[name]))
        for name, predicate in thresholds.items()
        if name in metrics
    }
    return ReleaseGateResult(not missing and all(checks.values()), checks, missing)


def failure_taxonomy(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    return dict(Counter(str(row.get("failure_type") or "pass") for row in rows))
