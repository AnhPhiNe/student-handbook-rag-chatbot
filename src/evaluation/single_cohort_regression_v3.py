"""Current-contract regression bundle built from the frozen v9 holdout archive.

The frozen archive is evidence, not a mutable evaluation target.  This module
provides fail-closed validation for a separately versioned migration bundle.
It intentionally does not call the Planner or use runtime outputs to create
gold annotations.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml


ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_DIR = ROOT / "data" / "eval" / "final_holdout"
BUNDLE_DIR = ROOT / "data" / "eval" / "single_cohort_regression_v3"
SCHEMA_VERSION = "single-cohort-regression-v3.0"
REVIEW_DATASET_VERSION = "single-cohort-regression-v3-review"
FROZEN_DATASET_VERSION = "single-cohort-regression-v3-gold-v1"

SUITE_FILES = {
    "deterministic": "deterministic_cases.json",
    "retrieval": "retrieval_cases.json",
    "answers": "answer_cases.json",
    "production": "production_cases.json",
}
ARCHIVE_FILES = {
    "deterministic": "deterministic_tool_cases.json",
    "retrieval": "retrieval_cases.json",
    "answers": "generated_answer_cases.json",
    "production": "production_cases.json",
}
EXPECTED_COUNTS = {
    "deterministic": 120,
    "retrieval": 180,
    "answers": 100,
    "production": 60,
}
LIFECYCLE_STATES = {
    "active",
    "deferred_multi_cohort",
    "retired_invalid_gold",
}
ANNOTATION_STATES = {"auto_verified", "review_required", "human_approved"}
OUTCOMES = {"execute", "clarify", "out_of_domain"}
REQUEST_KINDS = {"structured", "rag"}
RETRIEVAL_POLICIES = {"required", "forbidden", "not_applicable"}


@dataclass(frozen=True)
class RegressionBundleValidation:
    valid: bool
    errors: tuple[str, ...]
    counts: dict[str, int]
    lifecycle_counts: dict[str, int]
    annotation_counts: dict[str, int]
    archive_preserved: bool
    release_ready: bool


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stable_json_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def archive_integrity(root: Path = ROOT) -> dict[str, Any]:
    archive_dir = root / "data" / "eval" / "final_holdout"
    manifest = load_json(archive_dir / "manifest.json")
    declared = manifest.get("dataset_hashes") or {}
    actual = {
        suite: stable_json_hash(load_json(archive_dir / filename))
        for suite, filename in ARCHIVE_FILES.items()
    }
    return {
        "preserved": actual == declared,
        "declared": declared,
        "actual": actual,
        "archive_commit": manifest.get("git_commit"),
        "archive_version": manifest.get("version"),
    }


def _registry(root: Path) -> dict[str, Any]:
    path = root / "configs" / "structured_lookup_registry.yaml"
    value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(value.get("tools"), Mapping):
        raise ValueError("Structured registry does not define tools.")
    return value


def _source_ids(root: Path) -> set[str]:
    path = root / "data" / "processed" / "chunks" / "all_docstore_items.json"
    values = load_json(path)
    result: set[str] = set()
    for item in values:
        if not isinstance(item, Mapping):
            continue
        metadata = item.get("metadata") or {}
        source_id = str(
            item.get("_id")
            or metadata.get("parent_section_id")
            or item.get("parent_section_id")
            or ""
        ).strip()
        if source_id:
            result.add(source_id)
    return result


def _iter_cases(bundle_dir: Path) -> Iterable[tuple[str, Mapping[str, Any]]]:
    for suite, filename in SUITE_FILES.items():
        path = bundle_dir / filename
        if not path.exists():
            continue
        values = load_json(path)
        if not isinstance(values, list):
            continue
        for case in values:
            if isinstance(case, Mapping):
                yield suite, case


def metric_cases(
    cases: Iterable[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    """Return only active cases; deferred/retired rows never inflate metrics."""

    return [case for case in cases if case.get("lifecycle") == "active"]


def _validate_case(
    suite: str,
    case: Mapping[str, Any],
    *,
    tools: Mapping[str, Any],
    source_ids: set[str],
) -> list[str]:
    case_id = str(case.get("id") or "missing-id")
    prefix = f"{suite}/{case_id}"
    errors: list[str] = []
    required = {
        "id",
        "suite",
        "query",
        "selected_cohort",
        "origin",
        "lifecycle",
        "expected_contract",
        "annotation",
        "legacy_annotation",
    }
    missing = required - set(case)
    if missing:
        return [f"{prefix}: missing fields {sorted(missing)}"]
    if case.get("suite") != suite:
        errors.append(f"{prefix}: suite mismatch")

    origin = case.get("origin") or {}
    if not isinstance(origin, Mapping) or not all(
        origin.get(field)
        for field in ("bundle", "commit", "case_id", "source_file", "source_hash")
    ):
        errors.append(f"{prefix}: incomplete origin provenance")
    elif origin.get("case_id") != case_id:
        errors.append(f"{prefix}: origin case id mismatch")

    lifecycle = case.get("lifecycle")
    if lifecycle not in LIFECYCLE_STATES:
        errors.append(f"{prefix}: invalid lifecycle")
    annotation = case.get("annotation") or {}
    if not isinstance(annotation, Mapping) or annotation.get("state") not in ANNOTATION_STATES:
        errors.append(f"{prefix}: invalid annotation state")
    if lifecycle == "retired_invalid_gold" and not case.get("retirement_reason"):
        errors.append(f"{prefix}: retired case missing retirement reason")

    contract = case.get("expected_contract") or {}
    if not isinstance(contract, Mapping):
        return [*errors, f"{prefix}: expected_contract must be object"]
    outcome = contract.get("outcome")
    retrieval_policy = contract.get("retrieval_policy")
    if outcome not in OUTCOMES:
        errors.append(f"{prefix}: invalid outcome")
    if retrieval_policy not in RETRIEVAL_POLICIES:
        errors.append(f"{prefix}: invalid retrieval policy")
    requests = contract.get("atomic_requests") or []
    if not isinstance(requests, list) or len(requests) > 6:
        errors.append(f"{prefix}: invalid atomic request list")
        requests = []
    if outcome != "execute" and requests:
        errors.append(f"{prefix}: non-execute case contains requests")
    if outcome != "execute" and retrieval_policy != "forbidden":
        errors.append(f"{prefix}: non-execute case must forbid retrieval")
    if lifecycle == "deferred_multi_cohort" and (
        outcome != "clarify" or retrieval_policy != "forbidden"
    ):
        errors.append(f"{prefix}: deferred multi-cohort must clarify without retrieval")

    has_rag = False
    for index, request in enumerate(requests, 1):
        request_prefix = f"{prefix}/r{index}"
        if request.get("request_id") != f"r{index}":
            errors.append(f"{request_prefix}: unstable request id")
        kind = request.get("request_kind")
        if kind not in REQUEST_KINDS:
            errors.append(f"{request_prefix}: invalid request kind")
            continue
        tool_name = request.get("tool_name")
        if kind == "structured":
            spec = tools.get(tool_name)
            if not isinstance(spec, Mapping):
                errors.append(f"{request_prefix}: unknown structured tool {tool_name!r}")
            elif request.get("source_contract") != spec.get("source_contract"):
                errors.append(f"{request_prefix}: registry source contract mismatch")
            if request.get("evidence_sources"):
                errors.append(f"{request_prefix}: structured request declares RAG evidence")
            expected_status = request.get("expected_status")
            if expected_status not in {"ok", "no_match", "invalid", "unresolved", "error"}:
                errors.append(f"{request_prefix}: invalid structured expected status")
            records = request.get("expected_source_records") or []
            strict_gold = annotation.get("state") in {"auto_verified", "human_approved"}
            if strict_gold and expected_status == "ok":
                if not records:
                    errors.append(f"{request_prefix}: approved structured gold lacks source records")
                required_record_fields = {
                    "record_id",
                    "document_id",
                    "parent_section_id",
                    "source_pages",
                    "cohort",
                    "source_type",
                }
                for record in records:
                    if required_record_fields - set(record):
                        errors.append(f"{request_prefix}: incomplete structured source record")
            if expected_status == "no_match" and records:
                errors.append(f"{request_prefix}: no_match structured request has source records")
        else:
            has_rag = True
            if tool_name is not None:
                errors.append(f"{request_prefix}: RAG request declares tool")
            evidence = request.get("evidence_sources") or []
            expected_status = request.get("expected_status")
            if expected_status not in {"ok", "no_match"}:
                errors.append(f"{request_prefix}: invalid RAG expected status")
            if expected_status == "ok" and not evidence:
                errors.append(f"{request_prefix}: RAG execute request lacks gold evidence")
            if expected_status == "no_match" and evidence:
                errors.append(f"{request_prefix}: no_match request declares gold evidence")
            for source in evidence:
                source_id = str(source.get("parent_section_id") or "")
                if not source_id or source_id not in source_ids:
                    errors.append(f"{request_prefix}: unknown source {source_id!r}")
                if source.get("cohort") != contract.get("effective_cohort"):
                    errors.append(f"{request_prefix}: evidence cohort mismatch")
                if not source.get("document_id") or not source.get("source_pages"):
                    errors.append(f"{request_prefix}: incomplete evidence binding")

    if outcome == "execute":
        expected_policy = "required" if has_rag else "not_applicable"
        if retrieval_policy != expected_policy:
            errors.append(
                f"{prefix}: retrieval policy {retrieval_policy!r} != {expected_policy!r}"
            )
    return errors


def validate_bundle(
    bundle_dir: Path = BUNDLE_DIR,
    *,
    root: Path = ROOT,
    require_frozen: bool = False,
) -> RegressionBundleValidation:
    errors: list[str] = []
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        return RegressionBundleValidation(
            False,
            ("manifest.json is missing",),
            {},
            {},
            {},
            False,
            False,
        )
    manifest = load_json(manifest_path)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        errors.append("manifest schema version mismatch")
    archive = archive_integrity(root)
    if not archive["preserved"]:
        errors.append("frozen final_holdout archive hash mismatch")
    if manifest.get("source_archive", {}).get("dataset_hashes") != archive["declared"]:
        errors.append("manifest source archive hashes mismatch")

    tools = _registry(root)["tools"]
    source_ids = _source_ids(root)
    counts: dict[str, int] = {}
    lifecycle_counts: Counter[str] = Counter()
    annotation_counts: Counter[str] = Counter()
    case_ids: set[str] = set()
    for suite, filename in SUITE_FILES.items():
        path = bundle_dir / filename
        if not path.exists():
            errors.append(f"missing suite file {filename}")
            continue
        values = load_json(path)
        if not isinstance(values, list):
            errors.append(f"{filename} must contain an array")
            continue
        counts[suite] = len(values)
        if len(values) != EXPECTED_COUNTS[suite]:
            errors.append(
                f"{suite}: expected {EXPECTED_COUNTS[suite]} cases, got {len(values)}"
            )
        declared_hash = manifest.get("dataset_hashes", {}).get(suite)
        if declared_hash != file_sha256(path):
            errors.append(f"{suite}: dataset hash mismatch")
        for case in values:
            if not isinstance(case, Mapping):
                errors.append(f"{suite}: non-object case")
                continue
            case_id = str(case.get("id") or "")
            if not case_id or case_id in case_ids:
                errors.append(f"{suite}: missing or duplicate id {case_id!r}")
            case_ids.add(case_id)
            lifecycle_counts[str(case.get("lifecycle"))] += 1
            annotation = case.get("annotation") or {}
            annotation_counts[str(annotation.get("state"))] += 1
            errors.extend(
                _validate_case(
                    suite,
                    case,
                    tools=tools,
                    source_ids=source_ids,
                )
            )

    frozen = manifest.get("frozen") is True
    unresolved_reviews = annotation_counts.get("review_required", 0)
    if frozen and unresolved_reviews:
        errors.append("frozen bundle contains unresolved review proposals")
    if require_frozen and not frozen:
        errors.append("release evaluation requires a frozen bundle")
    if require_frozen and manifest.get("dataset_version") != FROZEN_DATASET_VERSION:
        errors.append("release evaluation requires the gold dataset version")
    release_ready = frozen and not unresolved_reviews and not errors
    return RegressionBundleValidation(
        valid=not errors,
        errors=tuple(errors),
        counts=counts,
        lifecycle_counts=dict(lifecycle_counts),
        annotation_counts=dict(annotation_counts),
        archive_preserved=bool(archive["preserved"]),
        release_ready=release_ready,
    )
