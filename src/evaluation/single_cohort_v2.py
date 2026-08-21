"""Validation, semantic plan comparison and release gates for single-cohort-v2."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml


ROOT = Path(__file__).resolve().parents[2]
BUNDLE_DIR = ROOT / "data" / "eval" / "single_cohort_v2"
EVALUATION_PROTOCOL_VERSION = "single-cohort-release-v4"
CANDIDATE_SCHEMA_VERSION = "single-cohort-v2.2"
RELEASE_SCHEMA_VERSION = "single-cohort-v2.4"
SCHEMA_VERSIONS = {CANDIDATE_SCHEMA_VERSION, RELEASE_SCHEMA_VERSION}
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


@dataclass(frozen=True)
class PlanAssessment:
    """Exact and execution-semantic comparison for one validated plan."""

    exact_match: bool
    semantic_match: bool
    mismatch_reasons: tuple[str, ...]
    critical_failure: bool


def _gate_thresholds() -> dict[str, Any]:
    return {
        "contract_invariants": lambda value: value == 1.0,
        "multi_cohort_rejection": lambda value: value == 1.0,
        "structured_source_binding": lambda value: value == 1.0,
        "structured_to_rag_fallbacks": lambda value: value == 0,
        "cross_request_leakage": lambda value: value == 0,
        "dev_semantic_executable": lambda value: value >= 0.95,
        "hidden_semantic_executable": lambda value: value >= 0.90,
        "dev_semantic_category_floor": lambda value: value >= 0.80,
        "hidden_semantic_category_floor": lambda value: value >= 0.75,
        "dev_safety_category_floor": lambda value: value == 1.0,
        "hidden_safety_category_floor": lambda value: value == 1.0,
        "retrieval_hit_at_5": lambda value: value >= 0.90,
        "citation_binding": lambda value: value >= 0.95,
        "answer_contract_binding": lambda value: value == 1.0,
        "faithfulness": lambda value: value >= 0.90,
        "answer_correctness": lambda value: value >= 0.85,
        "hallucination_rate": lambda value: value <= 0.05,
        "critical_false_pass": lambda value: value == 0,
        "provider_failures": lambda value: value == 0,
        "quality_checks_passed": lambda value: value is True,
        "parity_passed": lambda value: value is True,
        "conformance_passed": lambda value: value is True,
        "single_cohort_regression_v3_passed": lambda value: value is True,
    }


def _evaluate_thresholds(
    metrics: Mapping[str, Any], thresholds: Mapping[str, Any]
) -> ReleaseGateResult:
    missing = [name for name in thresholds if name not in metrics]
    checks = {
        name: bool(predicate(metrics[name]))
        for name, predicate in thresholds.items()
        if name in metrics
    }
    return ReleaseGateResult(not missing and all(checks.values()), checks, missing)


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


def _user_visible_input_signature(case: Mapping[str, Any]) -> str:
    """Fingerprint only inputs visible to the Planner, never gold metadata."""

    history = [
        {
            "role": _normalize(turn.get("role")),
            "content": _normalize(turn.get("content")),
        }
        for turn in case.get("chat_history") or []
        if isinstance(turn, Mapping)
    ]
    payload = {
        "query": _normalize(case.get("query")),
        "selected_cohort": _normalize(case.get("selected_cohort")),
        "chat_history": history,
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def derive_cohort_source(case: Mapping[str, Any]) -> str:
    """Derive cohort authority from the published precedence contract."""

    expected = case.get("expected") or {}
    query = str(case.get("query") or "")
    explicit = re.findall(r"\bk\s*(?:48|49|50|51)\b", _normalize(query))
    if explicit:
        return "raw_query"
    effective = _normalize(expected.get("effective_cohort"))
    selected = _normalize(case.get("selected_cohort"))
    if effective and selected == effective:
        return "selected_cohort"
    history_text = " ".join(
        str(turn.get("content") or "")
        for turn in case.get("chat_history") or []
        if isinstance(turn, Mapping)
    )
    if effective and effective in _normalize(history_text):
        return "grounded_history"
    return "unresolved"


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
    annotation = case.get("annotation")
    if not isinstance(annotation, Mapping) or annotation.get("state") not in {
        "auto_verified", "review_required", "human_approved"
    }:
        errors.append(f"{suite_name}/{case_id}: invalid case annotation state")
    if expected.get("outcome") not in {"execute", "clarify", "out_of_domain"}:
        errors.append(f"{suite_name}/{case_id}: invalid outcome")
    if expected.get("context_mode") not in PLANNER_CONTEXT_MODES:
        errors.append(f"{suite_name}/{case_id}: invalid planner context_mode")
    if expected.get("query_mode") not in QUERY_MODES:
        errors.append(f"{suite_name}/{case_id}: invalid query_mode")
    derived_source = derive_cohort_source(case)
    if expected.get("effective_cohort_source") != derived_source:
        errors.append(
            f"{suite_name}/{case_id}: cohort source mismatch "
            f"({expected.get('effective_cohort_source')} != {derived_source})"
        )
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
        audit = request.get("gold_audit")
        audit_state = audit.get("annotation_state") if isinstance(audit, Mapping) else None
        if audit_state not in {"auto_verified", "review_required", "human_approved"}:
            errors.append(f"{suite_name}/{case_id}: invalid gold audit r{index}")
        audit_method = (
            str(audit.get("audit_method") or "").strip()
            if isinstance(audit, Mapping)
            else ""
        )
        if kind == "rag" and audit_method == "direct_tool_adapter":
            errors.append(
                f"{suite_name}/{case_id}: RAG gold cannot use structured adapter audit r{index}"
            )
        span = str(request.get("query_span") or "")
        if not span or (_normalize(span) not in _normalize(query) and _normalize(span) not in _normalize(history_text)):
            errors.append(f"{suite_name}/{case_id}: ungrounded query_span r{index}")
        if not request.get("expected_source_contract") or request.get("citation_scope") != f"r{index}":
            errors.append(f"{suite_name}/{case_id}: missing request source binding")
        if (
            audit_state in {"auto_verified", "human_approved"}
            and not case.get("fault_injection")
        ):
            if kind == "structured" and request.get("expected_status") == "ok":
                records = request.get("expected_source_records")
                if request.get("expected_result") is None:
                    errors.append(f"{suite_name}/{case_id}: missing structured gold result r{index}")
                if not isinstance(records, list) or not records:
                    errors.append(f"{suite_name}/{case_id}: missing structured gold source r{index}")
                else:
                    required_source_fields = {
                        "record_id", "document_id", "parent_section_id",
                        "source_pages", "cohort", "source_type",
                    }
                    if any(required_source_fields - set(record) for record in records):
                        errors.append(f"{suite_name}/{case_id}: incomplete structured source r{index}")
                    if any(not record.get("record_id") or not record.get("document_id") for record in records):
                        errors.append(f"{suite_name}/{case_id}: unbound structured source identity r{index}")
                    if request.get("expected_source_contract") == "regulation_table" and any(
                        not record.get("parent_section_id") for record in records
                    ):
                        errors.append(f"{suite_name}/{case_id}: missing regulation parent binding r{index}")
            if kind == "rag" and request.get("expected_status") == "ok":
                evidence = request.get("expected_evidence")
                required_evidence = {
                    "document_ids", "parent_section_ids", "chunk_ids",
                    "source_pages", "relevance_grade", "source_bindings",
                }
                if not isinstance(evidence, Mapping) or required_evidence - set(evidence):
                    errors.append(f"{suite_name}/{case_id}: incomplete RAG gold evidence r{index}")
                elif (
                    not evidence.get("document_ids")
                    or not evidence.get("parent_section_ids")
                    or not evidence.get("chunk_ids")
                    or not evidence.get("source_bindings")
                ):
                    errors.append(f"{suite_name}/{case_id}: empty RAG gold evidence r{index}")
                elif any(
                    not binding.get("document_id")
                    or not binding.get("parent_section_id")
                    or not binding.get("chunk_ids")
                    for binding in evidence.get("source_bindings") or []
                ):
                    errors.append(f"{suite_name}/{case_id}: invalid RAG source binding r{index}")
    return errors


def validate_bundle(
    bundle_dir: Path = BUNDLE_DIR, *, require_gold_complete: bool = False
) -> BundleValidation:
    errors: list[str] = []
    paths = {name: bundle_dir / name for name in ("dev.json", "hidden.json", "manifest.json")}
    if not all(path.exists() for path in paths.values()):
        hashes = {name: _sha(path) for name, path in paths.items() if path.exists()}
        return BundleValidation(False, ["missing bundle file"], {}, hashes, {})
    manifest = _load(paths["manifest.json"])
    suites = {"dev": _load(paths["dev.json"]), "hidden": _load(paths["hidden.json"])}
    hashes = {f"{name}.json": _sha(paths[f"{name}.json"]) for name in suites}
    if manifest.get("schema_version") not in SCHEMA_VERSIONS:
        errors.append("manifest schema version mismatch")
    if require_gold_complete and manifest.get("schema_version") != RELEASE_SCHEMA_VERSION:
        errors.append("gold release schema version has not been frozen")
    if require_gold_complete and manifest.get("dataset_version") != "single-cohort-gold-v2":
        errors.append("gold dataset version has not been frozen")
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

    legacy_hidden_path = bundle_dir / "legacy_hidden_rc1.json"
    if legacy_hidden_path.exists():
        legacy_hidden = _load(legacy_hidden_path)
        legacy_signatures = {
            _user_visible_input_signature(case)
            for case in legacy_hidden
            if isinstance(case, Mapping)
        }
        hidden_signatures = {
            _user_visible_input_signature(case)
            for case in hidden
            if isinstance(case, Mapping)
        }
        legacy_overlap = legacy_signatures & hidden_signatures
        if legacy_overlap:
            errors.append(
                "hidden/legacy user-visible input overlap: "
                f"{len(legacy_overlap)} cases"
            )

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
        "hidden_legacy_input_overlap": len(legacy_overlap)
        if legacy_hidden_path.exists()
        else 0,
        "case_annotation_states": dict(Counter(
            str((case.get("annotation") or {}).get("state") or "missing")
            for case in all_cases
        )),
        "request_annotation_states": dict(Counter(
            str((request.get("gold_audit") or {}).get("annotation_state") or "missing")
            for request in requests
        )),
    }
    coverage["hidden_human_review_complete"] = bool(
        manifest.get("hidden_frozen")
        and manifest.get("hidden_human_review_complete")
        and all(
            (case.get("annotation") or {}).get("state") == "human_approved"
            for case in hidden
        )
    )
    coverage["gold_ready"] = bool(
        all(
            (case.get("annotation") or {}).get("state")
            in {"auto_verified", "human_approved"}
            for case in all_cases
        )
        and coverage["hidden_human_review_complete"]
    )
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
    if require_gold_complete and not coverage["gold_ready"]:
        errors.append("gold audit is incomplete or hidden is not human-approved")
    counts = {name: len(cases) for name, cases in suites.items() if isinstance(cases, list)}
    return BundleValidation(not errors, errors, counts, hashes, coverage)


def exact_plan_match(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    top_fields = (
        "outcome", "context_mode", "query_mode",
        "effective_cohort", "effective_cohort_source",
    )
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


_PROTECTED_SPAN_PATTERNS = (
    r"\bkhong\b", r"\bchua\b", r"\bchang\b", r"\bcam\b",
    r"\btru\b", r"\bngoai tru\b", r"\bneu\b", r"\bchi khi\b",
    r"\btoi thieu\b", r"\btoi da\b",
)


def _numeric_value(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal):
        return Decimal(str(value))
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not re.fullmatch(r"[-+]?\d+(?:[.,]\d+)?", text):
        return None
    try:
        return Decimal(text.replace(",", "."))
    except InvalidOperation:
        return None


def _semantic_value_equal(left: Any, right: Any) -> bool:
    """Compare representation-only differences without guessing aliases."""

    if isinstance(left, Mapping) or isinstance(right, Mapping):
        if not isinstance(left, Mapping) or not isinstance(right, Mapping):
            return False
        if set(left) != set(right):
            return False
        return all(_semantic_value_equal(left[key], right[key]) for key in left)
    if isinstance(left, list | tuple) or isinstance(right, list | tuple):
        if not isinstance(left, list | tuple) or not isinstance(right, list | tuple):
            return False
        return len(left) == len(right) and all(
            _semantic_value_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    left_number = _numeric_value(left)
    right_number = _numeric_value(right)
    if left_number is not None or right_number is not None:
        return left_number is not None and right_number is not None and left_number == right_number
    if isinstance(left, str) and isinstance(right, str):
        return _normalize(left) == _normalize(right)
    return left == right


def _span_markers(value: str) -> tuple[frozenset[str], frozenset[str]]:
    normalized = _normalize(value)
    numbers = frozenset(re.findall(r"\b\d+(?: \d+)?\b", normalized))
    markers = frozenset(
        pattern for pattern in _PROTECTED_SPAN_PATTERNS if re.search(pattern, normalized)
    )
    return numbers, markers


def _semantic_span_equal(left: Any, right: Any) -> bool:
    expected = _normalize(left)
    actual = _normalize(right)
    if not expected or not actual:
        return expected == actual
    if expected not in actual and actual not in expected:
        return False
    return _span_markers(str(left)) == _span_markers(str(right))


@lru_cache(maxsize=1)
def _rag_intent_sources() -> dict[str, frozenset[str]]:
    registry_path = ROOT / "configs" / "structured_lookup_registry.yaml"
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    return {
        str(intent): frozenset(str(source) for source in sources or [])
        for intent, sources in (payload.get("rag_intents") or {}).items()
    }


def _intent_semantically_equal(left: Any, right: Any, request_kind: Any) -> bool:
    if left == right:
        return True
    if request_kind != "rag":
        return False
    sources = _rag_intent_sources()
    left_sources = sources.get(str(left), frozenset())
    right_sources = sources.get(str(right), frozenset())
    return bool(left_sources and left_sources == right_sources)


def assess_plan(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> PlanAssessment:
    """Compare a plan by contract semantics while retaining exact diagnostics."""

    reasons: list[str] = []
    # Context/query modes and cohort provenance stay in exact-match and contract
    # diagnostics. Executability is determined by the validated outcome/cohort and
    # atomic requests; provenance violations fail the separate 100% contract gate.
    for field in ("outcome", "effective_cohort"):
        if expected.get(field) != actual.get(field):
            reasons.append(field)
    expected_requests = expected.get("atomic_requests") or []
    actual_requests = actual.get("atomic_requests") or actual.get("lookup_requests") or []
    if len(expected_requests) != len(actual_requests):
        reasons.append("request_count")
    for index, (left, right) in enumerate(zip(expected_requests, actual_requests), 1):
        prefix = f"request:{index}"
        actual_tool = right.get("tool_name") or right.get("lookup_type")
        strict_values = {
            "request_id": right.get("request_id") or f"r{index}",
            "request_kind": right.get("request_kind"),
            "tool_name": actual_tool,
        }
        for field, value in strict_values.items():
            if left.get(field) != value:
                reasons.append(f"{prefix}:{field}")
        # Structured intent remains an exact diagnostic because validated
        # tool/slots plus downstream result checks determine executability.
        # RAG intents may change retrieval scope, so only registry-declared
        # source-contract equivalence is accepted.
        if left.get("request_kind") == "rag" and not _intent_semantically_equal(
            left.get("intent"), right.get("intent"), "rag"
        ):
            reasons.append(f"{prefix}:intent")
        if not _semantic_span_equal(left.get("query_span"), right.get("query_span")):
            reasons.append(f"{prefix}:query_span")
        if not _semantic_value_equal(left.get("slots") or {}, right.get("slots") or {}):
            reasons.append(f"{prefix}:slots")
        if not _semantic_value_equal(
            left.get("cohort_refs") or [], right.get("cohort_refs") or []
        ):
            reasons.append(f"{prefix}:cohort_refs")
    critical = any(
        reason in {"outcome", "effective_cohort", "request_count"}
        or reason.endswith(":request_kind")
        or reason.endswith(":tool_name")
        for reason in reasons
    )
    return PlanAssessment(
        exact_match=exact_plan_match(expected, actual),
        semantic_match=not reasons,
        mismatch_reasons=tuple(reasons),
        critical_failure=critical,
    )


def semantic_plan_match(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    return assess_plan(expected, actual).semantic_match


def execution_plan_match(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> bool:
    """Return whether a validated plan is safe to assess through real adapters.

    Structured entity spellings are intentionally not compared here.  Their
    selected tool, request order, source-bound adapter result and citation are
    checked downstream, where registry aliases and adapter-local fuzzy matching
    have provenance.  RAG intent/slots remain plan-level retrieval semantics.
    """

    if any(
        expected.get(field) != actual.get(field)
        for field in ("outcome", "effective_cohort")
    ):
        return False
    expected_requests = expected.get("atomic_requests") or []
    actual_requests = actual.get("atomic_requests") or actual.get("lookup_requests") or []
    if len(expected_requests) != len(actual_requests):
        return False
    for index, (left, right) in enumerate(
        zip(expected_requests, actual_requests, strict=True), 1
    ):
        actual_tool = right.get("tool_name") or right.get("lookup_type")
        if left.get("request_id") != (right.get("request_id") or f"r{index}"):
            return False
        if left.get("request_kind") != right.get("request_kind"):
            return False
        if left.get("tool_name") != actual_tool:
            return False
        if not _semantic_span_equal(left.get("query_span"), right.get("query_span")):
            return False
        if not _semantic_value_equal(
            left.get("cohort_refs") or [], right.get("cohort_refs") or []
        ):
            return False
        if left.get("request_kind") == "rag":
            if not _intent_semantically_equal(
                left.get("intent"), right.get("intent"), "rag"
            ):
                return False
            if not _semantic_value_equal(
                left.get("slots") or {}, right.get("slots") or {}
            ):
                return False
    return True


def semantic_value_equal(left: Any, right: Any) -> bool:
    """Public value comparator shared by execution-result evaluation."""

    return _semantic_value_equal(left, right)


def evaluate_release_gates(metrics: Mapping[str, Any]) -> ReleaseGateResult:
    return _evaluate_thresholds(metrics, _gate_thresholds())


def evaluate_development_gates(metrics: Mapping[str, Any]) -> ReleaseGateResult:
    thresholds = _gate_thresholds()
    thresholds.pop("hidden_semantic_executable")
    thresholds.pop("hidden_semantic_category_floor")
    thresholds.pop("hidden_safety_category_floor")
    return _evaluate_thresholds(metrics, thresholds)


def failure_taxonomy(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    return dict(Counter(str(row.get("failure_type") or "pass") for row in rows))
