from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping


REQUEST_COMPOSER_PROMPT_VERSION = "single-cohort-request-composer-v1"
CLAIM_VERIFIER_PROMPT_VERSION = "single-cohort-claim-verifier-v1"


class ClaimContractError(ValueError):
    """Raised when model output violates the request/claim evidence contract."""


@dataclass(frozen=True)
class AnswerClaim:
    claim_id: str
    text: str
    citation_ids: tuple[str, ...]


@dataclass(frozen=True)
class RequestAnswerDraft:
    request_id: str
    request_index: int
    request_kind: str
    query_span: str
    claims: tuple[AnswerClaim, ...] = ()
    abstention_reason: str | None = None
    error_type: str | None = None


@dataclass(frozen=True)
class ClaimVerificationResult:
    request_id: str
    claim_id: str
    verdict: str
    supporting_evidence_ids: tuple[str, ...]
    reason_code: str


@dataclass
class VerifiedAnswerBatch:
    answer: str
    drafts: list[RequestAnswerDraft]
    verification_results: list[ClaimVerificationResult]
    verification_executed: bool
    verification_status: str
    composer_call_count: int
    verifier_call_count: int
    provider_failures: int = 0
    model_used: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    request_debug: list[dict[str, Any]] = field(default_factory=list)
    status: str = "answered"
    error_type: str | None = None
    error_message: str | None = None
    composition_ms: float = 0.0
    verification_ms: float = 0.0
    supporting_evidence_ids: tuple[str, ...] = ()


def parse_json_object(payload: Any) -> dict[str, Any]:
    """Parse a JSON object without coercing malformed model values to strings."""

    if isinstance(payload, Mapping):
        return dict(payload)
    if not isinstance(payload, str):
        raise ClaimContractError("model_output_not_object_or_string")

    text = payload.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ClaimContractError("model_output_invalid_json") from exc
    if not isinstance(parsed, dict):
        raise ClaimContractError("model_output_not_json_object")
    return parsed


def parse_request_draft(
    payload: Any,
    *,
    request_id: str,
    request_index: int,
    query_span: str,
    allowed_evidence_ids: set[str],
) -> RequestAnswerDraft:
    data = parse_json_object(payload)
    if data.get("request_id") != request_id:
        raise ClaimContractError("composer_request_id_mismatch")

    raw_claims = data.get("claims")
    if not isinstance(raw_claims, list):
        raise ClaimContractError("composer_claims_not_list")
    if len(raw_claims) > 6:
        raise ClaimContractError("composer_too_many_claims")

    claims: list[AnswerClaim] = []
    for offset, raw_claim in enumerate(raw_claims, start=1):
        if not isinstance(raw_claim, Mapping):
            raise ClaimContractError("composer_claim_not_object")
        text = str(raw_claim.get("text") or "").strip()
        if not text:
            raise ClaimContractError("composer_claim_text_empty")
        raw_citations = raw_claim.get("citation_ids")
        if not isinstance(raw_citations, list) or not raw_citations:
            raise ClaimContractError("composer_claim_missing_citations")
        citation_ids: list[str] = []
        for raw_citation_id in raw_citations:
            if not isinstance(raw_citation_id, str):
                raise ClaimContractError("composer_citation_id_not_string")
            citation_id = raw_citation_id.strip()
            if not citation_id or citation_id not in allowed_evidence_ids:
                raise ClaimContractError("composer_citation_out_of_scope")
            if citation_id not in citation_ids:
                citation_ids.append(citation_id)
        claims.append(
            AnswerClaim(
                claim_id=f"{request_id}.c{offset}",
                text=text,
                citation_ids=tuple(citation_ids),
            )
        )

    abstention_reason = data.get("abstention_reason")
    if abstention_reason is not None and not isinstance(abstention_reason, str):
        raise ClaimContractError("composer_abstention_reason_not_string")
    abstention_reason = str(abstention_reason or "").strip() or None
    if claims and abstention_reason:
        raise ClaimContractError("composer_claims_and_abstention_conflict")
    if not claims and not abstention_reason:
        raise ClaimContractError("composer_empty_without_abstention")

    return RequestAnswerDraft(
        request_id=request_id,
        request_index=request_index,
        request_kind="rag",
        query_span=query_span,
        claims=tuple(claims),
        abstention_reason=abstention_reason,
    )


def parse_verification_results(
    payload: Any,
    *,
    drafts: list[RequestAnswerDraft],
) -> list[ClaimVerificationResult]:
    data = parse_json_object(payload)
    raw_results = data.get("results")
    if not isinstance(raw_results, list):
        raise ClaimContractError("verifier_results_not_list")

    expected: dict[tuple[str, str], AnswerClaim] = {
        (draft.request_id, claim.claim_id): claim
        for draft in drafts
        if draft.request_kind == "rag"
        for claim in draft.claims
    }
    seen: set[tuple[str, str]] = set()
    results: list[ClaimVerificationResult] = []
    for raw_result in raw_results:
        if not isinstance(raw_result, Mapping):
            raise ClaimContractError("verifier_result_not_object")
        request_id = raw_result.get("request_id")
        claim_id = raw_result.get("claim_id")
        if not isinstance(request_id, str) or not isinstance(claim_id, str):
            raise ClaimContractError("verifier_ids_not_strings")
        key = (request_id.strip(), claim_id.strip())
        claim = expected.get(key)
        if claim is None or key in seen:
            raise ClaimContractError("verifier_unknown_or_duplicate_claim")

        verdict = raw_result.get("verdict")
        if verdict not in {"supported", "unsupported", "insufficient"}:
            raise ClaimContractError("verifier_invalid_verdict")
        raw_evidence_ids = raw_result.get("supporting_evidence_ids")
        if not isinstance(raw_evidence_ids, list):
            raise ClaimContractError("verifier_evidence_ids_not_list")
        evidence_ids: list[str] = []
        for raw_evidence_id in raw_evidence_ids:
            if not isinstance(raw_evidence_id, str):
                raise ClaimContractError("verifier_evidence_id_not_string")
            evidence_id = raw_evidence_id.strip()
            if not evidence_id or evidence_id not in claim.citation_ids:
                raise ClaimContractError("verifier_evidence_out_of_claim_scope")
            if evidence_id not in evidence_ids:
                evidence_ids.append(evidence_id)
        if verdict == "supported" and not evidence_ids:
            raise ClaimContractError("supported_claim_without_evidence")

        reason_code = raw_result.get("reason_code")
        if reason_code not in {
            "direct_support",
            "scope_mismatch",
            "missing_support",
            "contradiction",
        }:
            raise ClaimContractError("verifier_reason_code_missing")
        seen.add(key)
        results.append(
            ClaimVerificationResult(
                request_id=key[0],
                claim_id=key[1],
                verdict=verdict,
                supporting_evidence_ids=tuple(evidence_ids),
                reason_code=reason_code,
            )
        )

    if seen != set(expected):
        raise ClaimContractError("verifier_missing_claim_verdict")
    return results


def render_verified_answer(
    drafts: list[RequestAnswerDraft],
    verification_results: list[ClaimVerificationResult],
    *,
    accept_unverified_rag: bool = False,
) -> tuple[str, list[dict[str, Any]]]:
    verdicts = {
        (result.request_id, result.claim_id): result
        for result in verification_results
    }
    ordered = sorted(drafts, key=lambda draft: draft.request_index)
    multi_request = len(ordered) > 1
    sections: list[str] = []
    request_debug: list[dict[str, Any]] = []

    for position, draft in enumerate(ordered, start=1):
        accepted: list[AnswerClaim] = []
        rejected = 0
        for claim in draft.claims:
            if draft.request_kind == "structured":
                accepted.append(claim)
                continue
            if accept_unverified_rag:
                accepted.append(claim)
                continue
            result = verdicts.get((draft.request_id, claim.claim_id))
            if result is not None and result.verdict == "supported":
                accepted.append(claim)
            else:
                rejected += 1

        if accepted:
            body = "\n\n".join(claim.text for claim in accepted)
            abstention_reason = None
        else:
            body = (
                "Mình chưa tìm thấy thông tin đủ rõ trong Sổ tay sinh viên "
                "để xác nhận phần này."
            )
            abstention_reason = draft.abstention_reason or draft.error_type or (
                "all_claims_rejected" if draft.claims else "no_supported_claim"
            )

        if multi_request:
            title = draft.query_span.strip() or f"Yêu cầu {position}"
            sections.append(f"{position}. **{title}**\n\n{body}")
        else:
            sections.append(body)
        request_debug.append(
            {
                "request_id": draft.request_id,
                "request_kind": draft.request_kind,
                "proposed_claim_count": len(draft.claims),
                "supported_claim_count": len(accepted),
                "rejected_claim_count": rejected,
                "abstention_reason": abstention_reason,
            }
        )

    return "\n\n".join(sections).strip(), request_debug


def merge_usage(results: list[Mapping[str, Any]]) -> dict[str, int]:
    totals = {"input": 0, "output": 0, "total": 0}
    for result in results:
        usage = result.get("usage")
        if not isinstance(usage, Mapping):
            continue
        for key in totals:
            value = usage.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                totals[key] += value
    return totals
