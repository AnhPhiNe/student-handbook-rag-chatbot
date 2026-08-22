"""Pre-registered, human-adjudicated material-hallucination protocol."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from typing import Any


MATERIAL_AUDIT_SCHEMA_VERSION = "single-cohort-material-audit-v1"
MATERIALITY_DIMENSIONS = {
    "right_or_obligation",
    "prohibition_or_eligibility",
    "scope_or_subject",
    "number_threshold_deadline_formula",
    "procedure_document_or_responsible_unit",
    "direct_answer_conclusion",
}
FINAL_VERDICTS = {
    "supported",
    "judge_false_positive",
    "non_material_unsupported",
    "material_unsupported",
    "insufficient_evidence",
}


def deterministic_control_ids(
    answer_ids: Iterable[str],
    flagged_ids: set[str],
    *,
    count: int = 10,
) -> list[str]:
    """Choose stable controls without looking at answer quality or content."""

    candidates = sorted({str(case_id) for case_id in answer_ids} - flagged_ids)
    return sorted(
        candidates,
        key=lambda case_id: hashlib.sha256(case_id.encode("utf-8")).hexdigest(),
    )[: min(count, len(candidates))]


def _request_scoped_sources(answer_row: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Expose only request-scoped evidence, never the judge verdict, to auditors."""

    sources: dict[str, list[dict[str, Any]]] = {}
    for citation in answer_row.get("citations") or []:
        if not isinstance(citation, Mapping):
            continue
        request_id = str(citation.get("request_id") or "").strip()
        if not request_id:
            continue
        metadata = citation.get("metadata") or {}
        sources.setdefault(request_id, []).append(
            {
                "citation_id": str(
                    citation.get("citation_id")
                    or citation.get("chunk_id")
                    or citation.get("_id")
                    or ""
                ),
                "document_id": citation.get("document_id")
                or (metadata.get("document_id") if isinstance(metadata, Mapping) else None),
                "parent_section_id": citation.get("parent_section_id")
                or (metadata.get("parent_section_id") if isinstance(metadata, Mapping) else None),
                "source_pages": citation.get("source_pages")
                or (metadata.get("source_pages") if isinstance(metadata, Mapping) else None),
                "cohort": citation.get("cohort")
                or (metadata.get("cohort") if isinstance(metadata, Mapping) else None),
                "content": citation.get("content")
                or (metadata.get("content") if isinstance(metadata, Mapping) else None),
            }
        )

    context = str(answer_row.get("context_used") or "")
    for block in re.split(r"\n\s*---\s*\n", context):
        match = re.search(r"^Request ID:\s*(\S+)\s*$", block, re.MULTILINE)
        if not match:
            continue
        request_id = match.group(1)
        sources.setdefault(request_id, []).append(
            {"citation_id": None, "context_block": block.strip()}
        )
    return sources


def build_material_audit_packet(
    cases: Iterable[Mapping[str, Any]],
    answer_rows: Iterable[Mapping[str, Any]],
    judge_rows: Iterable[Mapping[str, Any]],
    *,
    answers_report_hash: str,
    commit: str,
    control_count: int = 10,
) -> dict[str, Any]:
    """Build a blinded packet: no judge verdicts are included in entries."""

    cases_by_id = {str(case.get("id")): case for case in cases}
    answers_by_id = {str(row.get("id")): row for row in answer_rows}
    flagged_ids = {
        str(row.get("id"))
        for row in judge_rows
        if bool(row.get("hallucination")) and str(row.get("id")) in answers_by_id
    }
    controls = deterministic_control_ids(
        answers_by_id,
        flagged_ids,
        count=control_count,
    )
    selected_ids = sorted(flagged_ids) + controls
    entries: list[dict[str, Any]] = []
    for case_id in selected_ids:
        case = cases_by_id.get(case_id)
        answer = answers_by_id.get(case_id)
        if not case or not answer:
            continue
        expected = case.get("expected") or {}
        entries.append(
            {
                "id": case_id,
                "query": case.get("query"),
                "selected_cohort": case.get("selected_cohort"),
                "atomic_requests": expected.get("atomic_requests") or [],
                "answer": answer.get("answer"),
                "request_scoped_sources": _request_scoped_sources(answer),
            }
        )
    return {
        "schema_version": MATERIAL_AUDIT_SCHEMA_VERSION,
        "commit": commit,
        "answers_report_hash": answers_report_hash,
        "materiality_dimensions": sorted(MATERIALITY_DIMENSIONS),
        "audit_packet": {"entries": entries},
        "audit_manifest": {
            "required_judge_flag_ids": sorted(flagged_ids),
            "required_control_ids": controls,
            "decisions": [
                {
                    "id": entry["id"],
                    "final_verdict": None,
                    "claims": [],
                    "approved_by": None,
                    "approved_at": None,
                }
                for entry in entries
            ],
        },
    }


def summarize_material_audit(
    audit_payload: Mapping[str, Any],
    judge_rows: Iterable[Mapping[str, Any]],
    *,
    answer_ids: Iterable[str],
) -> dict[str, Any]:
    """Calculate release metrics from approved human/LLM-assisted decisions."""

    answer_id_set = {str(case_id) for case_id in answer_ids}
    judge_by_id = {str(row.get("id")): row for row in judge_rows}
    raw_flagged = {
        case_id
        for case_id, row in judge_by_id.items()
        if case_id in answer_id_set and bool(row.get("hallucination"))
    }
    manifest = audit_payload.get("audit_manifest") or audit_payload
    required_flags = {
        str(value) for value in manifest.get("required_judge_flag_ids") or []
    }
    required_controls = {
        str(value) for value in manifest.get("required_control_ids") or []
    }
    decisions_by_id = {
        str(row.get("id")): row
        for row in manifest.get("decisions") or []
        if isinstance(row, Mapping) and str(row.get("id") or "")
    }
    required_ids = (required_flags | required_controls) & answer_id_set
    completed_ids = {
        case_id
        for case_id, decision in decisions_by_id.items()
        if case_id in required_ids
        and decision.get("final_verdict") in FINAL_VERDICTS
        and str(decision.get("approved_by") or "").strip()
        and str(decision.get("approved_at") or "").strip()
    }
    material_ids: set[str] = set()
    critical_claims = 0
    judge_false_positive_ids: set[str] = set()
    invalid_dimension_claims = 0
    invalid_material_decisions = 0
    for case_id in completed_ids:
        decision = decisions_by_id[case_id]
        verdict = str(decision.get("final_verdict"))
        claims = decision.get("claims") or []
        has_material_claim = False
        for claim in claims:
            if not isinstance(claim, Mapping):
                continue
            dimensions = set(claim.get("materiality_dimensions") or [])
            if not dimensions.issubset(MATERIALITY_DIMENSIONS):
                invalid_dimension_claims += 1
            if bool(claim.get("material_unsupported")):
                has_material_claim = True
                if not dimensions:
                    invalid_dimension_claims += 1
                critical_claims += int(bool(claim.get("critical")))
        if verdict == "material_unsupported" and not has_material_claim:
            invalid_material_decisions += 1
        if verdict != "material_unsupported" and has_material_claim:
            invalid_material_decisions += 1
        if has_material_claim:
            material_ids.add(case_id)
        if case_id in raw_flagged and verdict in {
            "supported",
            "judge_false_positive",
        }:
            judge_false_positive_ids.add(case_id)
    complete = (
        audit_payload.get("schema_version") == MATERIAL_AUDIT_SCHEMA_VERSION
        and required_flags == raw_flagged
        and required_ids <= completed_ids
        and invalid_dimension_claims == 0
        and invalid_material_decisions == 0
    )
    denominator = len(answer_id_set)
    return {
        "schema_version": MATERIAL_AUDIT_SCHEMA_VERSION,
        "complete": complete,
        "required_judge_flag_n": len(required_flags),
        "required_control_n": len(required_controls),
        "completed_n": len(completed_ids),
        "raw_judge_hallucination_rate": (
            len(raw_flagged) / denominator if denominator else 0.0
        ),
        "material_unsupported_answer_rate": (
            len(material_ids) / denominator if denominator else 0.0
        ),
        "material_unsupported_answer_ids": sorted(material_ids),
        "material_critical_unsupported_claims": critical_claims,
        "judge_false_positive_rate": (
            len(judge_false_positive_ids) / len(raw_flagged)
            if raw_flagged
            else 0.0
        ),
        "judge_false_positive_ids": sorted(judge_false_positive_ids),
        "invalid_materiality_dimension_claims": invalid_dimension_claims,
        "invalid_material_decisions": invalid_material_decisions,
    }
