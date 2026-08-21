"""Build review proposals for the current-contract regression bundle.

The builder reads the frozen v9 holdout but never edits it.  Gold proposals are
derived from archive annotations, the current tool registry and source files;
runtime Planner/executor outputs are deliberately not inputs.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import unicodedata
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Mapping

import yaml

from src.evaluation.single_cohort_regression_v3 import (
    ARCHIVE_FILES,
    BUNDLE_DIR,
    EXPECTED_COUNTS,
    REVIEW_DATASET_VERSION,
    ROOT,
    SCHEMA_VERSION,
    SUITE_FILES,
    archive_integrity,
    file_sha256,
    load_json,
    validate_bundle,
    write_json,
)


TOOL_BY_LEGACY_GROUP = {
    "foreign_language": "foreign_language",
    "study_duration": "study_duration",
    "scholarship": "scholarship_classification",
    "scoring": "scoring",
    "conduct": "scoring",
    "service": "student_service",
    "office": "office",
    "faculty": "faculty",
    "program": "program",
    "formula": "formula",
}


def _normalize(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").casefold()).replace("đ", "d")
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text)).strip()


def _commit(root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()


def _registry(root: Path) -> dict[str, Any]:
    return yaml.safe_load(
        (root / "configs/structured_lookup_registry.yaml").read_text(encoding="utf-8")
    )


def _source_catalog(root: Path) -> dict[str, dict[str, Any]]:
    values = load_json(root / "data/processed/chunks/all_docstore_items.json")
    result: dict[str, dict[str, Any]] = {}
    for item in values:
        metadata = item.get("metadata") or {}
        source_id = str(
            item.get("_id")
            or metadata.get("parent_section_id")
            or item.get("parent_section_id")
            or ""
        ).strip()
        if source_id:
            result[source_id] = dict(metadata)
    return result


def _evidence(
    judgments: list[Mapping[str, Any]],
    *,
    effective_cohort: str | None,
    source_catalog: Mapping[str, Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    result: list[dict[str, Any]] = []
    reasons: list[str] = []
    for value in judgments:
        parent_id = str(value.get("parent_section_id") or "").strip()
        if not parent_id:
            continue
        metadata = source_catalog.get(parent_id)
        if not metadata:
            reasons.append("gold_parent_missing_from_current_docstore")
            continue
        source_cohort = str(metadata.get("cohort") or value.get("cohort") or "")
        if effective_cohort and source_cohort != effective_cohort:
            reasons.append("gold_source_not_applicable_to_effective_cohort")
            continue
        result.append(
            {
                "parent_section_id": parent_id,
                "document_id": str(
                    metadata.get("document_id") or value.get("document_id") or ""
                ).strip(),
                "source_pages": list(
                    metadata.get("source_pages") or value.get("source_pages") or []
                ),
                "cohort": source_cohort,
                "content_type": metadata.get("content_type") or value.get("content_type"),
                "source_section": (
                    metadata.get("title")
                    or metadata.get("section_title")
                    or value.get("source_section")
                ),
                "relevance_grade": int(value.get("grade") or 0),
            }
        )
    return result, list(dict.fromkeys(reasons))


def _request(
    *,
    request_id: str,
    kind: str,
    query: str,
    cohort: str | None,
    registry: Mapping[str, Any],
    tool_name: str | None = None,
    evidence_sources: list[dict[str, Any]] | None = None,
    slots: Mapping[str, Any] | None = None,
    expected_status: str = "ok",
) -> dict[str, Any]:
    spec = registry.get("tools", {}).get(tool_name) if tool_name else None
    return {
        "request_id": request_id,
        "request_kind": kind,
        "query_span": query,
        "effective_cohort": cohort,
        "tool_name": tool_name,
        "typed_slots": dict(slots or {}),
        "expected_status": expected_status,
        "source_contract": (
            spec.get("source_contract") if isinstance(spec, Mapping) else "regulation_text"
        ),
        "evidence_sources": list(evidence_sources or []),
        "expected_source_records": [],
    }


def _structured_requests(
    case: Mapping[str, Any],
    *,
    registry: Mapping[str, Any],
    start_index: int = 1,
) -> tuple[list[dict[str, Any]], list[str]]:
    group = str(case.get("lookup_group") or "").strip()
    tool = TOOL_BY_LEGACY_GROUP.get(group)
    reasons: list[str] = []
    if group == "faculty" and "nganh" in _normalize(case.get("query")):
        # The v4 registry separates faculty contact from program listings.
        tool = "program"
        reasons.append("registry_v4_faculty_listing_maps_to_program")
    if not tool:
        return [], ["structured_tool_requires_human_mapping"]

    query = str(case.get("query") or "")
    cohort = None if case.get("cohort") == "general" else case.get("cohort")
    normalized = _normalize(query)
    formula_slots: dict[str, Any] = {}
    if tool == "formula":
        if "hoc bong" in normalized:
            formula_slots = {"formula_type": "scholarship_score"}
        elif "gpa" in normalized or "trung binh" in normalized:
            formula_slots = {"formula_type": "gpa_weighted_average"}
    if tool == "formula" and "gpa" in normalized and "hoc bong" in normalized:
        requests = [
            _request(
                request_id=f"r{start_index}",
                kind="structured",
                query=query,
                cohort=cohort,
                registry=registry,
                tool_name=tool,
                slots={"formula_type": "gpa_weighted_average"},
            ),
            _request(
                request_id=f"r{start_index + 1}",
                kind="structured",
                query=query,
                cohort=cohort,
                registry=registry,
                tool_name=tool,
                slots={"formula_type": "scholarship_score"},
            ),
        ]
        reasons.append("multi_operand_formula_decomposed")
        return requests, reasons
    return [
        _request(
            request_id=f"r{start_index}",
            kind="structured",
            query=query,
            cohort=cohort,
            registry=registry,
            tool_name=tool,
            slots=formula_slots,
        )
    ], reasons


def _contract(
    case: Mapping[str, Any],
    *,
    registry: Mapping[str, Any],
    source_catalog: Mapping[str, Mapping[str, Any]],
) -> tuple[str, dict[str, Any], list[str]]:
    cohort = None if case.get("cohort") == "general" else case.get("cohort")
    old_path = str(case.get("expected_path") or "")
    reasons = ["migrated_from_frozen_archive_to_current_query_contract"]
    if case.get("cohort") == "general":
        return (
            "deferred_multi_cohort",
            {
                "outcome": "clarify",
                "effective_cohort": None,
                "retrieval_policy": "forbidden",
                "atomic_requests": [],
            },
            [*reasons, "general_scope_deferred_until_multi_cohort"],
        )
    if old_path == "out_of_domain":
        return (
            "active",
            {
                "outcome": "out_of_domain",
                "effective_cohort": None,
                "retrieval_policy": "forbidden",
                "atomic_requests": [],
            },
            reasons,
        )
    if old_path == "clarify" or case.get("answerability") == "unanswerable":
        return (
            "active",
            {
                "outcome": "clarify",
                "effective_cohort": cohort,
                "retrieval_policy": "forbidden",
                "atomic_requests": [],
            },
            reasons,
        )

    requests: list[dict[str, Any]] = []
    if old_path in {"structured", "mixed"}:
        structured, structured_reasons = _structured_requests(case, registry=registry)
        requests.extend(structured)
        reasons.extend(structured_reasons)
    if old_path in {"regulation_rag", "mixed"}:
        archived_sources = list(
            case.get("expected_citations")
            or case.get("relevance_judgments")
            or []
        )
        sources, source_reasons = _evidence(
            archived_sources,
            effective_cohort=cohort,
            source_catalog=source_catalog,
        )
        reasons.extend(source_reasons)
        if not sources:
            reasons.append("rag_gold_requires_source_review")
        requests.append(
            _request(
                request_id=f"r{len(requests) + 1}",
                kind="rag",
                query=str(case.get("query") or ""),
                cohort=cohort,
                registry=registry,
                evidence_sources=sources,
                expected_status="ok" if sources else "no_match",
            )
        )
    if not requests:
        return (
            "active",
            {
                "outcome": "clarify",
                "effective_cohort": cohort,
                "retrieval_policy": "forbidden",
                "atomic_requests": [],
            },
            [*reasons, "archive_path_not_executable_under_current_contract"],
        )
    has_rag = any(request["request_kind"] == "rag" for request in requests)
    return (
        "active",
        {
            "outcome": "execute",
            "effective_cohort": cohort,
            "retrieval_policy": "required" if has_rag else "not_applicable",
            "atomic_requests": requests,
        },
        reasons,
    )


def _doc_title_collisions(root: Path) -> dict[tuple[str, str], set[str]]:
    values = load_json(root / "data/processed/chunks/all_docstore_items.json")
    groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    for item in values:
        metadata = item.get("metadata") or {}
        cohort = str(metadata.get("cohort") or "")
        title = _normalize(
            metadata.get("section_title")
            or metadata.get("source_section")
            or metadata.get("title")
        )
        document_id = str(metadata.get("document_id") or "")
        if cohort and title and document_id:
            groups[(cohort, title)].add(document_id)
    return groups


def _decorate_reasons(
    case: Mapping[str, Any],
    contract: Mapping[str, Any],
    reasons: list[str],
    *,
    collisions: Mapping[tuple[str, str], set[str]],
) -> list[str]:
    query = _normalize(case.get("query"))
    for request in contract.get("atomic_requests") or []:
        for source in request.get("evidence_sources") or []:
            title = _normalize(source.get("source_section"))
            key = (str(source.get("cohort") or ""), title)
            if title and len(collisions.get(key, set())) > 1 and title not in query:
                reasons.append("ambiguous_duplicate_source_title_requires_review")
                return list(dict.fromkeys(reasons))
    return list(dict.fromkeys(reasons))


def _migrate_case(
    case: Mapping[str, Any],
    *,
    suite: str,
    source_file: str,
    source_hash: str,
    archive_commit: str,
    registry: Mapping[str, Any],
    source_catalog: Mapping[str, Mapping[str, Any]],
    collisions: Mapping[tuple[str, str], set[str]],
) -> dict[str, Any]:
    lifecycle, contract, reasons = _contract(
        case,
        registry=registry,
        source_catalog=source_catalog,
    )
    reasons = _decorate_reasons(case, contract, reasons, collisions=collisions)
    return {
        "id": case["id"],
        "suite": suite,
        "query": case.get("query"),
        "selected_cohort": None if case.get("cohort") == "general" else case.get("cohort"),
        "origin": {
            "bundle": "final_holdout",
            "commit": archive_commit,
            "case_id": case["id"],
            "source_file": source_file,
            "source_hash": source_hash,
        },
        "lifecycle": lifecycle,
        "expected_contract": contract,
        "annotation": {
            "state": "review_required",
            "proposal_method": "source_registry_contract_migration",
            "reason_codes": reasons,
        },
        "legacy_annotation": dict(case),
    }


def _inherit_duplicate_contracts(
    migrated: dict[str, list[dict[str, Any]]],
) -> None:
    canonical: dict[tuple[str, str], tuple[dict[str, Any], str]] = {}
    for suite in ("deterministic", "retrieval", "answers"):
        for case in migrated[suite]:
            contract = case["expected_contract"]
            if contract.get("outcome") == "execute" and all(
                request.get("request_kind") != "rag"
                or request.get("evidence_sources")
                or request.get("expected_status") == "no_match"
                for request in contract.get("atomic_requests") or []
            ):
                canonical[("query", _normalize(case["query"]))] = (contract, case["id"])
                duplicate_group = str(
                    case.get("legacy_annotation", {}).get("duplicate_group") or ""
                )
                if duplicate_group:
                    canonical[("duplicate_group", duplicate_group)] = (
                        contract,
                        case["id"],
                    )
    for case in migrated["production"]:
        duplicate_group = str(
            case.get("legacy_annotation", {}).get("duplicate_group") or ""
        )
        match = canonical.get(("query", _normalize(case["query"])))
        if not match and duplicate_group:
            match = canonical.get(("duplicate_group", duplicate_group))
        if not match:
            continue
        contract, source_case_id = match
        case["expected_contract"] = json.loads(json.dumps(contract, ensure_ascii=False))
        obsolete = {
            "structured_tool_requires_human_mapping",
            "rag_source_binding_requires_linked_case_review",
            "rag_gold_requires_source_review",
            "archive_path_not_executable_under_current_contract",
        }
        existing = [
            value
            for value in case["annotation"]["reason_codes"]
            if value not in obsolete
        ]
        case["annotation"]["reason_codes"] = list(
            dict.fromkeys([*existing, "contract_inherited_from_archived_duplicate"])
        )
        case["annotation"]["linked_contract_case_id"] = source_case_id


def _structured_record_from_formula(rule: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "record_id": str(rule.get("record_id") or rule.get("rule_id") or ""),
        "document_id": str(rule.get("document_id") or ""),
        "parent_section_id": str(
            rule.get("source_parent_id") or rule.get("source_section_id") or ""
        ),
        "source_pages": list(rule.get("source_pages") or []),
        "cohort": rule.get("cohort"),
        "source_type": rule.get("content_type") or "structured_lookup",
    }


def _audit_structured_source_proposals(
    migrated: Mapping[str, list[dict[str, Any]]],
    *,
    root: Path,
) -> None:
    formula_rows = load_json(root / "data/processed/tables/formula_rules.json")
    formula_by_key = {
        (str(row.get("cohort") or ""), str(row.get("rule_id") or "")): row
        for row in formula_rows
    }
    for cases in migrated.values():
        for case in cases:
            reasons = case["annotation"]["reason_codes"]
            for request in case["expected_contract"].get("atomic_requests") or []:
                if request.get("request_kind") != "structured":
                    continue
                if request.get("tool_name") != "formula":
                    reasons.append("structured_source_binding_requires_adapter_audit")
                    continue
                formula_type = str(
                    (request.get("typed_slots") or {}).get("formula_type") or ""
                )
                if not formula_type:
                    reasons.append("formula_type_requires_human_annotation")
                    continue
                rule = formula_by_key.get(
                    (str(request.get("effective_cohort") or ""), formula_type)
                )
                if not rule:
                    request["expected_status"] = "no_match"
                    reasons.append("formula_source_missing")
                    continue
                if rule.get("disabled") or str(rule.get("review_status") or "").startswith(
                    "rejected"
                ):
                    request["expected_status"] = "no_match"
                    request["expected_source_records"] = []
                    reasons.append("formula_source_disabled_or_rejected")
                    continue
                request["expected_source_records"] = [
                    _structured_record_from_formula(rule)
                ]
                request["expected_result"] = {
                    "rule_id": rule.get("rule_id"),
                    "formula_text": rule.get("formula_text"),
                }
                reasons.append("formula_source_bound_from_current_data")
            case["annotation"]["reason_codes"] = list(dict.fromkeys(reasons))


def build_bundle(*, root: Path = ROOT, output: Path = BUNDLE_DIR) -> dict[str, Any]:
    archive = archive_integrity(root)
    if not archive["preserved"]:
        raise RuntimeError("Refusing migration: frozen final_holdout hashes changed.")
    registry = _registry(root)
    source_catalog = _source_catalog(root)
    collisions = _doc_title_collisions(root)
    migrated: dict[str, list[dict[str, Any]]] = {}
    for suite, source_file in ARCHIVE_FILES.items():
        values = load_json(root / "data/eval/final_holdout" / source_file)
        migrated[suite] = [
            _migrate_case(
                case,
                suite=suite,
                source_file=source_file,
                source_hash=archive["declared"][suite],
                archive_commit=str(archive["archive_commit"]),
                registry=registry,
                source_catalog=source_catalog,
                collisions=collisions,
            )
            for case in values
        ]
    _inherit_duplicate_contracts(migrated)
    _audit_structured_source_proposals(migrated, root=root)

    output.mkdir(parents=True, exist_ok=True)
    for suite, filename in SUITE_FILES.items():
        write_json(output / filename, migrated[suite])

    review_rows = [
        {
            "case_id": case["id"],
            "suite": suite,
            "query": case["query"],
            "lifecycle_proposal": case["lifecycle"],
            "expected_contract_proposal": case["expected_contract"],
            "reason_codes": case["annotation"]["reason_codes"],
            "review_decision": None,
            "reviewer": None,
            "reviewed_at": None,
            "review_notes": None,
        }
        for suite in SUITE_FILES
        for case in migrated[suite]
    ]
    write_json(output / "review_queue.json", review_rows)

    lifecycle_counts = Counter(case["lifecycle"] for cases in migrated.values() for case in cases)
    reason_counts = Counter(
        reason
        for cases in migrated.values()
        for case in cases
        for reason in case["annotation"]["reason_codes"]
    )
    report = {
        "schema_version": SCHEMA_VERSION,
        "dataset_version": REVIEW_DATASET_VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "generated_from_commit": _commit(root),
        "source_archive_preserved": True,
        "counts": {suite: len(cases) for suite, cases in migrated.items()},
        "lifecycle_counts": dict(lifecycle_counts),
        "review_required": len(review_rows),
        "reason_counts": dict(reason_counts),
        "gold_policy": "source_and_contract_proposals_only_no_runtime_output_as_gold",
        "approval_policy": "human_approval_required_before_freeze",
    }
    write_json(output / "migration_report.json", report)

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "dataset_version": REVIEW_DATASET_VERSION,
        "frozen": False,
        "created_at": report["generated_at"],
        "generated_from_commit": report["generated_from_commit"],
        "counts": EXPECTED_COUNTS,
        "dataset_hashes": {
            suite: file_sha256(output / filename)
            for suite, filename in SUITE_FILES.items()
        },
        "source_archive": {
            "path": "data/eval/final_holdout",
            "version": archive["archive_version"],
            "commit": archive["archive_commit"],
            "dataset_hashes": archive["declared"],
            "preserved": True,
            "policy": "read_only_archive_not_a_release_gate",
        },
        "contract_assets": {
            "structured_registry": file_sha256(
                root / "configs/structured_lookup_registry.yaml"
            ),
            "docstore": file_sha256(
                root / "data/processed/chunks/all_docstore_items.json"
            ),
            "formula_rules": file_sha256(
                root / "data/processed/tables/formula_rules.json"
            ),
        },
        "lifecycle_policy": {
            "active": "counted only after approval",
            "deferred_multi_cohort": "clarify and forbid retrieval in single-cohort",
            "retired_invalid_gold": "reported separately and excluded from metrics",
        },
        "annotation_policy": "all migration proposals require explicit human approval",
        "hidden_suite_touched": False,
    }
    write_json(output / "manifest.json", manifest)
    validation = validate_bundle(output, root=root)
    if not validation.valid:
        raise RuntimeError("Generated bundle is invalid:\n" + "\n".join(validation.errors))
    report["validation"] = {
        "valid": validation.valid,
        "release_ready": validation.release_ready,
        "archive_preserved": validation.archive_preserved,
        "annotation_counts": validation.annotation_counts,
    }
    write_json(output / "migration_report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=BUNDLE_DIR)
    args = parser.parse_args()
    report = build_bundle(output=args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
