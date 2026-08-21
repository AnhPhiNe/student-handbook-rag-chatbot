from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.prepare_single_cohort_dev_answer_audit import (
    ALLOWED_LABELS,
    ALLOWED_SEVERITIES,
)


ALLOWED_LAYERS = {
    "none",
    "judge_packet",
    "structured_guardrail",
    "composer_context",
    "composer_prompt",
    "retrieval",
    "validator",
    "source_binding",
}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _index_by_id(rows: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or not row.get("id"):
            continue
        indexed[str(row["id"])] = dict(row)
    return indexed


def _identity_matches(
    expected: Mapping[str, Any],
    actual: Mapping[str, Any],
    *,
    request_id: str | None,
) -> bool:
    if request_id and str(actual.get("request_id") or "") != request_id:
        return False
    expected_parent = str(
        expected.get("parent_section_id") or expected.get("source_parent_id") or ""
    )
    actual_parent = str(
        actual.get("parent_section_id") or actual.get("source_parent_id") or ""
    )
    fields = (
        ("document_id", str(expected.get("document_id") or ""), str(actual.get("document_id") or "")),
        ("parent_section_id", expected_parent, actual_parent),
        ("chunk_id", str(expected.get("chunk_id") or ""), str(actual.get("chunk_id") or "")),
    )
    constrained = False
    for _field, expected_value, actual_value in fields:
        if not expected_value:
            continue
        constrained = True
        if expected_value != actual_value:
            return False
    return constrained


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def validate_external_audit(
    external: Mapping[str, Any],
    queue: list[dict[str, Any]],
    *,
    expected_commit: str,
    expected_queue_sha256: str,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    source = external.get("source") or {}
    if source.get("commit") != expected_commit:
        errors.append("source.commit does not match the frozen run")
    if source.get("queue_sha256") != expected_queue_sha256:
        errors.append("source.queue_sha256 does not match the frozen queue")
    if source.get("hidden_included") is not False:
        errors.append("hidden_included must be false")
    if (external.get("human_review") or {}).get("human_approved") is not False:
        errors.append("external model must not self-approve human review")

    queue_by_id = _index_by_id(queue)
    cases = external.get("cases") or []
    if not isinstance(cases, list):
        errors.append("cases must be a list")
        cases = []
    case_ids = [str(case.get("id") or "") for case in cases if isinstance(case, Mapping)]
    duplicate_ids = sorted(
        case_id for case_id, count in Counter(case_ids).items() if count > 1
    )
    if duplicate_ids:
        errors.append(f"duplicate case ids: {duplicate_ids}")
    missing_ids = sorted(set(queue_by_id) - set(case_ids))
    extra_ids = sorted(set(case_ids) - set(queue_by_id))
    if missing_ids:
        errors.append(f"missing case ids: {missing_ids}")
    if extra_ids:
        errors.append(f"unexpected case ids: {extra_ids}")

    labels: Counter[str] = Counter()
    citation_checks = 0
    quote_checks = 0
    for case in cases:
        if not isinstance(case, Mapping):
            errors.append("case row is not an object")
            continue
        case_id = str(case.get("id") or "")
        queue_case = queue_by_id.get(case_id)
        if queue_case is None:
            continue
        final = case.get("final_decision") or {}
        label = str(final.get("label") or "")
        severity = str(final.get("severity") or "")
        layer = str(final.get("recommended_layer") or "")
        labels[label] += 1
        if label not in ALLOWED_LABELS:
            errors.append(f"{case_id}: invalid label {label!r}")
        if severity not in ALLOWED_SEVERITIES:
            errors.append(f"{case_id}: invalid severity {severity!r}")
        if layer not in ALLOWED_LAYERS:
            errors.append(f"{case_id}: invalid recommended_layer {layer!r}")
        if not isinstance(final.get("answers_user_need"), bool):
            errors.append(f"{case_id}: answers_user_need must be boolean")
        if not str(final.get("production_impact") or "").strip():
            errors.append(f"{case_id}: production_impact is required")

        valid_request_ids = {
            str(request.get("request_id") or "")
            for request in queue_case.get("expected_requests") or []
            if isinstance(request, Mapping)
        }
        runtime_citations = [
            citation
            for citation in (queue_case.get("answer") or {}).get("citations") or []
            if isinstance(citation, Mapping)
        ]
        omitted_citations = [
            citation
            for citation in (queue_case.get("judge") or {}).get("omitted_citations") or []
            if isinstance(citation, Mapping)
        ]

        for claim in (case.get("blind_audit") or {}).get("claim_audit") or []:
            if not isinstance(claim, Mapping):
                errors.append(f"{case_id}: claim audit row is not an object")
                continue
            request_id = claim.get("request_id")
            if request_id is not None and str(request_id) not in valid_request_ids:
                errors.append(
                    f"{case_id}/{claim.get('claim_id')}: invalid request_id {request_id!r}"
                )
            for cited in claim.get("supporting_citations") or []:
                if not isinstance(cited, Mapping):
                    errors.append(
                        f"{case_id}/{claim.get('claim_id')}: citation is not an object"
                    )
                    continue
                matches = [
                    citation
                    for citation in runtime_citations
                    if _identity_matches(cited, citation, request_id=str(request_id))
                ]
                citation_checks += 1
                if not matches:
                    errors.append(
                        f"{case_id}/{claim.get('claim_id')}: supporting citation identity not found in the same request"
                    )
                    continue
                quote = _normalize_text(claim.get("evidence_quote"))
                if quote:
                    quote_checks += 1
                    if not any(
                        quote in _normalize_text(citation.get("content"))
                        for citation in matches
                    ):
                        warnings.append(
                            f"{case_id}/{claim.get('claim_id')}: evidence quote is not an exact normalized substring"
                        )

        for omitted in (case.get("reconciliation") or {}).get(
            "supported_but_omitted_claims"
        ) or []:
            if not isinstance(omitted, Mapping):
                errors.append(f"{case_id}: omitted-support row is not an object")
                continue
            request_id = str(omitted.get("request_id") or "")
            if request_id not in valid_request_ids:
                errors.append(
                    f"{case_id}: omitted-support request_id {request_id!r} is invalid"
                )
                continue
            if not any(
                _identity_matches(omitted, citation, request_id=request_id)
                for citation in runtime_citations
            ):
                errors.append(
                    f"{case_id}: omitted-support citation is absent from runtime citations"
                )
            if not any(
                _identity_matches(omitted, citation, request_id=request_id)
                for citation in omitted_citations
            ):
                errors.append(
                    f"{case_id}: omitted-support citation is not listed in judge.omitted_citations"
                )

    reported_summary = external.get("summary") or {}
    if int(reported_summary.get("total_cases") or -1) != len(cases):
        errors.append("summary.total_cases does not match cases")
    for label, count in labels.items():
        if int(reported_summary.get(label) or 0) != count:
            errors.append(f"summary count mismatch for {label}")

    return {
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "case_count": len(cases),
        "citation_identity_checks": citation_checks,
        "exact_quote_checks": quote_checks,
        "label_counts": dict(labels),
    }


def build_approved_decisions(
    external: Mapping[str, Any],
    queue: list[dict[str, Any]],
    *,
    external_sha256: str,
    reviewer: str,
    approval_statement: str,
    reviewed_at: str,
) -> dict[str, Any]:
    queue_by_id = _index_by_id(queue)
    reviews = []
    for case in external.get("cases") or []:
        case_id = str(case["id"])
        final = dict(case.get("final_decision") or {})
        reviews.append(
            {
                "id": case_id,
                "selection_group": queue_by_id[case_id].get("selection_group"),
                "label": final.get("label"),
                "severity": final.get("severity"),
                "unsupported_claims": final.get("unsupported_claims") or [],
                "supported_but_omitted_claims": final.get(
                    "supported_but_omitted_claims"
                )
                or [],
                "answers_user_need": final.get("answers_user_need"),
                "production_impact": final.get("production_impact"),
                "recommended_layer": final.get("recommended_layer"),
                "notes": final.get("notes"),
                "external_confidence": case.get("confidence"),
                "requires_human_attention": case.get("requires_human_attention"),
            }
        )
    return {
        "audit_protocol_version": "single-cohort-dev-answer-human-audit-v2",
        "status": "human_approved",
        "audit_method": "llm_assisted_human_review",
        "commit": (external.get("source") or {}).get("commit"),
        "queue_sha256": (external.get("source") or {}).get("queue_sha256"),
        "reviewer": reviewer,
        "reviewed_at": reviewed_at,
        "approval_statement": approval_statement,
        "external_audit": {
            "sha256": external_sha256,
            "protocol_version": external.get("audit_protocol_version"),
            "auditor": external.get("auditor"),
        },
        "allowed_labels": ALLOWED_LABELS,
        "allowed_severities": ALLOWED_SEVERITIES,
        "summary": external.get("summary"),
        "reviews": reviews,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate an external dev answer audit and apply explicit human approval."
    )
    parser.add_argument("--external-audit", type=Path, required=True)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--decisions-output", type=Path, required=True)
    parser.add_argument("--archive-output", type=Path, required=True)
    parser.add_argument("--validation-output", type=Path, required=True)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--approval-statement", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    external = _load_json(args.external_audit)
    queue = _load_json(args.queue)
    manifest = _load_json(args.manifest)
    if not isinstance(external, Mapping) or not isinstance(queue, list):
        raise ValueError("External audit must be an object and queue must be a list.")
    validation = validate_external_audit(
        external,
        queue,
        expected_commit=str(manifest["commit"]),
        expected_queue_sha256=str(manifest["queue_sha256"]),
    )
    validation.update(
        {
            "external_audit_sha256": _sha256(args.external_audit),
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    args.validation_output.parent.mkdir(parents=True, exist_ok=True)
    args.validation_output.write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if not validation["passed"]:
        raise ValueError(
            "External audit validation failed: " + "; ".join(validation["errors"])
        )

    reviewed_at = datetime.now(timezone.utc).isoformat()
    decisions = build_approved_decisions(
        external,
        queue,
        external_sha256=validation["external_audit_sha256"],
        reviewer=args.reviewer,
        approval_statement=args.approval_statement,
        reviewed_at=reviewed_at,
    )
    args.decisions_output.write_text(
        json.dumps(decisions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    shutil.copyfile(args.external_audit, args.archive_output)
    print(json.dumps(validation, ensure_ascii=False))


if __name__ == "__main__":
    main()
