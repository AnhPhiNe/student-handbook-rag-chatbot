from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Mapping


REQUEST_COMPOSER_PROMPT_VERSION = "single-cohort-request-composer-v3"


class RequestContractError(ValueError):
    """Raised when a request composer violates its typed source contract."""


@dataclass(frozen=True)
class AnswerClaim:
    claim_id: str
    text: str
    citation_ids: tuple[str, ...]
    fact_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class RequestAnswerDraft:
    request_id: str
    request_index: int
    request_kind: str
    query_span: str
    grounded_request_query: str
    claims: tuple[AnswerClaim, ...] = ()
    abstention_reason: str | None = None
    error_type: str | None = None
    used_fallback: bool = False


@dataclass
class RequestAnswerBatch:
    answer: str
    drafts: list[RequestAnswerDraft]
    composer_call_count: int
    provider_failures: int = 0
    contract_passed: bool = True
    final_contract_passed: bool = True
    model_used: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    request_debug: list[dict[str, Any]] = field(default_factory=list)
    status: str = "answered"
    error_type: str | None = None
    error_message: str | None = None
    composition_ms: float = 0.0
    request_composition_ms: dict[str, float] = field(default_factory=dict)
    supporting_evidence_ids: tuple[str, ...] = ()


def parse_json_object(payload: Any) -> dict[str, Any]:
    """Parse a JSON object without coercing malformed model values."""

    if isinstance(payload, Mapping):
        return dict(payload)
    if not isinstance(payload, str):
        raise RequestContractError("model_output_not_object_or_string")

    text = payload.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RequestContractError("model_output_invalid_json") from exc
    if not isinstance(parsed, dict):
        raise RequestContractError("model_output_not_json_object")
    return parsed


def build_fact_catalog(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Flatten typed adapter output into stable, model-addressable facts."""

    facts: list[dict[str, Any]] = []
    ignored = {
        "source_records",
        "citations",
        "parent_content",
        "content",
        "request_id",
        "request_index",
    }

    def visit(value: Any, path: str) -> None:
        if isinstance(value, Mapping):
            for key in sorted(value):
                if str(key) in ignored:
                    continue
                next_path = f"{path}.{key}" if path else str(key)
                visit(value[key], next_path)
            return
        if isinstance(value, list):
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")
            return
        if value is None or isinstance(value, (str, int, float, bool)):
            if path and value not in (None, ""):
                facts.append({"fact_ref": path, "value": value})

    visit(payload or {}, "result")
    return facts


def parse_request_draft(
    payload: Any,
    *,
    request_id: str,
    request_index: int,
    request_kind: str,
    query_span: str,
    grounded_request_query: str,
    allowed_evidence_ids: set[str],
    fact_catalog: list[dict[str, Any]],
) -> RequestAnswerDraft:
    data = parse_json_object(payload)
    if data.get("request_id") != request_id:
        raise RequestContractError("composer_request_id_mismatch")

    raw_claims = data.get("claims")
    if not isinstance(raw_claims, list):
        raise RequestContractError("composer_claims_not_list")
    if len(raw_claims) > 6:
        raise RequestContractError("composer_too_many_claims")

    allowed_fact_refs = {
        str(item.get("fact_ref"))
        for item in fact_catalog
        if str(item.get("fact_ref") or "").strip()
    }
    fact_values = {
        str(item.get("fact_ref")): item.get("value") for item in fact_catalog
    }
    claims: list[AnswerClaim] = []
    for offset, raw_claim in enumerate(raw_claims, start=1):
        if not isinstance(raw_claim, Mapping):
            raise RequestContractError("composer_claim_not_object")
        text = str(raw_claim.get("text") or "").strip()
        if not text:
            raise RequestContractError("composer_claim_text_empty")
        citation_ids = _parse_string_ids(
            raw_claim.get("citation_ids"),
            allowed=allowed_evidence_ids,
            missing_error="composer_claim_missing_citations",
            type_error="composer_citation_id_not_string",
            scope_error="composer_citation_out_of_scope",
        )
        raw_fact_refs = raw_claim.get("fact_refs", [])
        if not isinstance(raw_fact_refs, list):
            raise RequestContractError("composer_fact_refs_not_list")
        fact_refs = _parse_string_ids(
            raw_fact_refs,
            allowed=allowed_fact_refs,
            missing_error="composer_structured_claim_missing_fact_refs",
            type_error="composer_fact_ref_not_string",
            scope_error="composer_fact_ref_out_of_scope",
            allow_empty=request_kind != "structured",
        )
        if request_kind == "rag" and fact_refs:
            raise RequestContractError("composer_rag_claim_has_fact_refs")
        if request_kind == "structured":
            grounding_text = " ".join(
                str(fact_values[ref]) for ref in fact_refs if ref in fact_values
            )
            _validate_structured_literals(
                text,
                grounding_text=f"{grounding_text} {grounded_request_query} {query_span}",
            )
        claims.append(
            AnswerClaim(
                claim_id=f"{request_id}.c{offset}",
                text=text,
                citation_ids=tuple(citation_ids),
                fact_refs=tuple(fact_refs),
            )
        )

    abstention_reason = data.get("abstention_reason")
    if abstention_reason is not None and not isinstance(abstention_reason, str):
        raise RequestContractError("composer_abstention_reason_not_string")
    abstention_reason = str(abstention_reason or "").strip() or None
    if claims and abstention_reason:
        raise RequestContractError("composer_claims_and_abstention_conflict")
    if not claims and not abstention_reason:
        raise RequestContractError("composer_empty_without_abstention")

    return RequestAnswerDraft(
        request_id=request_id,
        request_index=request_index,
        request_kind=request_kind,
        query_span=query_span,
        grounded_request_query=grounded_request_query,
        claims=tuple(claims),
        abstention_reason=abstention_reason,
    )


def build_structured_fallback(
    *,
    request_id: str,
    request_index: int,
    query_span: str,
    grounded_request_query: str,
    fact_catalog: list[dict[str, Any]],
    citation_ids: list[str],
    error_type: str,
) -> RequestAnswerDraft:
    """Return an exact, generic representation without tool-specific templates."""

    visible_facts = fact_catalog[:20]
    if not visible_facts or not citation_ids:
        return RequestAnswerDraft(
            request_id=request_id,
            request_index=request_index,
            request_kind="structured",
            query_span=query_span,
            grounded_request_query=grounded_request_query,
            abstention_reason=error_type,
            error_type=error_type,
            used_fallback=True,
        )
    lines = [
        f"- {_humanize_fact_ref(str(item['fact_ref']))}: {item['value']}"
        for item in visible_facts
    ]
    return RequestAnswerDraft(
        request_id=request_id,
        request_index=request_index,
        request_kind="structured",
        query_span=query_span,
        grounded_request_query=grounded_request_query,
        claims=(
            AnswerClaim(
                claim_id=f"{request_id}.c1",
                text="Kết quả tra cứu đã được xác minh:\n" + "\n".join(lines),
                citation_ids=tuple(citation_ids),
                fact_refs=tuple(str(item["fact_ref"]) for item in visible_facts),
            ),
        ),
        error_type=error_type,
        used_fallback=True,
    )


def render_request_answers(
    drafts: list[RequestAnswerDraft],
) -> tuple[str, list[dict[str, Any]]]:
    ordered = sorted(drafts, key=lambda draft: draft.request_index)
    multi_request = len(ordered) > 1
    sections: list[str] = []
    request_debug: list[dict[str, Any]] = []
    for position, draft in enumerate(ordered, start=1):
        if draft.claims:
            body = "\n\n".join(claim.text for claim in draft.claims)
            abstention_reason = None
        else:
            body = (
                "Mình chưa tìm thấy thông tin đủ rõ trong Sổ tay sinh viên "
                "để xác nhận phần này."
            )
            abstention_reason = draft.abstention_reason or draft.error_type or "no_claim"
        if multi_request:
            title = draft.query_span.strip() or f"Yêu cầu {position}"
            sections.append(f"{position}. **{title}**\n\n{body}")
        else:
            sections.append(body)
        request_debug.append(
            {
                "request_id": draft.request_id,
                "request_kind": draft.request_kind,
                "claim_count": len(draft.claims),
                "contract_passed": not bool(draft.error_type),
                "final_contract_passed": bool(
                    not draft.error_type
                    or (
                        draft.request_kind == "structured"
                        and draft.used_fallback
                        and draft.claims
                    )
                ),
                "used_fallback": draft.used_fallback,
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


def _parse_string_ids(
    value: Any,
    *,
    allowed: set[str],
    missing_error: str,
    type_error: str,
    scope_error: str,
    allow_empty: bool = False,
) -> list[str]:
    if not isinstance(value, list) or (not value and not allow_empty):
        raise RequestContractError(missing_error)
    parsed: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise RequestContractError(type_error)
        item_id = item.strip()
        if not item_id or item_id not in allowed:
            raise RequestContractError(scope_error)
        if item_id not in parsed:
            parsed.append(item_id)
    return parsed


def _validate_structured_literals(text: str, *, grounding_text: str) -> None:
    normalized_grounding = _normalize_literal_text(grounding_text)
    for literal in re.findall(r"(?<!\w)\d+(?:[.,]\d+)*(?:\s*%)?", text):
        if _normalize_literal_text(literal) not in normalized_grounding:
            raise RequestContractError("composer_structured_literal_not_grounded")
    for code in re.findall(r"\b(?:K\d{2}|[A-Z]{2,}[A-Z0-9+./-]*)\b", text):
        if _normalize_literal_text(code) not in normalized_grounding:
            raise RequestContractError("composer_structured_code_not_grounded")


def _normalize_literal_text(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"\s+", "", text)


def _humanize_fact_ref(value: str) -> str:
    leaf = value.rsplit(".", 1)[-1]
    leaf = re.sub(r"\[\d+\]", "", leaf)
    return leaf.replace("_", " ").strip()
