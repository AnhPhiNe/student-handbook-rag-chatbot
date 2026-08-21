from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .answer_guardrails import build_deterministic_answer
from .claim_verification import (
    AnswerClaim,
    ClaimContractError,
    ClaimVerificationResult,
    RequestAnswerDraft,
    VerifiedAnswerBatch,
    merge_usage,
    parse_request_draft,
    parse_verification_results,
    render_verified_answer,
)
from .gemini_client import GeminiClient
from .prompt_builder import build_claim_verifier_prompt, build_request_claim_prompt


class RequestAnswerOrchestrator:
    """Compose and verify atomic requests without leaking sibling evidence."""

    def __init__(
        self,
        *,
        config: Mapping[str, Any],
        client_provider: Callable[[], Any],
    ) -> None:
        self._config = config
        self._client_provider = client_provider

    @staticmethod
    def _request_scope_id(value: Mapping[str, Any]) -> str:
        metadata = value.get("metadata")
        metadata = metadata if isinstance(metadata, Mapping) else {}
        return str(value.get("request_id") or metadata.get("request_id") or "").strip()

    @classmethod
    def _scoped_values(
        cls,
        values: Any,
        *,
        request_id: str,
    ) -> list[dict[str, Any]]:
        return [
            dict(value)
            for value in values or []
            if isinstance(value, Mapping)
            and cls._request_scope_id(value) == request_id
        ]

    @classmethod
    def _scoped_structured_result(
        cls,
        value: Any,
        *,
        request_id: str,
    ) -> dict[str, Any] | None:
        if not isinstance(value, Mapping):
            return None
        if cls._request_scope_id(value) == request_id:
            return dict(value)

        candidates = value.get("sub_results")
        if not isinstance(candidates, list):
            candidates = (
                value.get("result") if isinstance(value.get("result"), list) else []
            )
        for candidate in candidates:
            if not isinstance(candidate, Mapping):
                continue
            nested = candidate.get("result")
            nested = nested if isinstance(nested, Mapping) else candidate
            if cls._request_scope_id(candidate) == request_id or cls._request_scope_id(
                nested
            ) == request_id:
                return dict(nested)
        return None

    @classmethod
    def _request_scoped_retrieval_result(
        cls,
        retrieval_result: Mapping[str, Any],
        *,
        request_id: str,
    ) -> dict[str, Any]:
        scoped = dict(retrieval_result)
        for key in (
            "request_results",
            "request_execution_contexts",
            "retrieved_items",
            "citations",
            "unresolved_lookup_requests",
        ):
            scoped[key] = cls._scoped_values(
                retrieval_result.get(key), request_id=request_id
            )
        scoped["structured_result"] = cls._scoped_structured_result(
            retrieval_result.get("structured_result"), request_id=request_id
        )
        scoped["related_items"] = []
        scoped["related_references"] = []
        return scoped

    def _evidence_catalog(
        self,
        *,
        retrieval_result: Mapping[str, Any],
        selected_citations: list[dict[str, Any]],
        request_id: str,
        expected_cohort: str | None,
    ) -> list[dict[str, Any]]:
        verifier_config = self._config.get("claim_verifier") or {}
        max_chars = max(
            500, int(verifier_config.get("max_chars_per_evidence", 5000))
        )
        scoped_items = self._scoped_values(
            retrieval_result.get("retrieved_items"), request_id=request_id
        )
        item_by_chunk: dict[str, dict[str, Any]] = {}
        for item in scoped_items:
            metadata = item.get("metadata")
            metadata = metadata if isinstance(metadata, Mapping) else {}
            chunk_id = str(item.get("chunk_id") or metadata.get("chunk_id") or "").strip()
            if chunk_id:
                item_by_chunk[chunk_id] = item

        catalog: list[dict[str, Any]] = []
        seen: set[str] = set()
        for citation in self._scoped_values(
            selected_citations, request_id=request_id
        ):
            metadata = citation.get("metadata")
            metadata = metadata if isinstance(metadata, Mapping) else {}
            evidence_id = str(
                citation.get("chunk_id")
                or metadata.get("chunk_id")
                or citation.get("source_record_id")
                or ""
            ).strip()
            if not evidence_id or evidence_id in seen:
                continue
            matching_item = item_by_chunk.get(evidence_id) or {}
            item_metadata = matching_item.get("metadata")
            item_metadata = (
                item_metadata if isinstance(item_metadata, Mapping) else {}
            )
            content = str(
                citation.get("content")
                or citation.get("text")
                or matching_item.get("content")
                or matching_item.get("text")
                or matching_item.get("page_content")
                or ""
            ).strip()
            source_cohort = str(
                citation.get("request_cohort")
                or citation.get("cohort")
                or metadata.get("cohort")
                or matching_item.get("request_cohort")
                or matching_item.get("cohort")
                or item_metadata.get("cohort")
                or ""
            ).strip()
            document_id = citation.get("document_id") or metadata.get(
                "document_id"
            ) or matching_item.get("document_id") or item_metadata.get(
                "document_id"
            )
            parent_section_id = citation.get("parent_section_id") or metadata.get(
                "parent_section_id"
            ) or matching_item.get("parent_section_id") or item_metadata.get(
                "parent_section_id"
            )
            source_pages = citation.get("source_pages") or metadata.get(
                "source_pages"
            ) or matching_item.get("source_pages") or item_metadata.get(
                "source_pages"
            )
            if (
                not content
                or not document_id
                or not parent_section_id
                or not source_pages
                or (expected_cohort and source_cohort != expected_cohort)
            ):
                continue
            seen.add(evidence_id)
            catalog.append(
                {
                    "evidence_id": evidence_id,
                    "request_id": request_id,
                    "document_id": document_id,
                    "parent_section_id": parent_section_id,
                    "source_pages": source_pages,
                    "cohort": source_cohort,
                    "title": citation.get("title") or matching_item.get("title"),
                    "content": content[:max_chars],
                }
            )
        return catalog

    @classmethod
    def _structured_draft(
        cls,
        *,
        retrieval_result: Mapping[str, Any],
        request: Mapping[str, Any],
    ) -> RequestAnswerDraft:
        request_id = str(request.get("request_id") or "").strip()
        request_index = int(request.get("request_index") or 0)
        query_span = str(request.get("query_span") or "").strip()
        scoped = cls._request_scoped_retrieval_result(
            retrieval_result, request_id=request_id
        )
        text = build_deterministic_answer(query_span, scoped).strip()
        return RequestAnswerDraft(
            request_id=request_id,
            request_index=request_index,
            request_kind="structured",
            query_span=query_span,
            claims=(
                AnswerClaim(
                    claim_id=f"{request_id}.c1",
                    text=text,
                    citation_ids=tuple(
                        str(citation.get("chunk_id") or "").strip()
                        for citation in scoped.get("citations") or []
                        if str(citation.get("chunk_id") or "").strip()
                    ),
                ),
            ),
        )

    @staticmethod
    def _failed_draft(
        request: Mapping[str, Any],
        *,
        error_type: str,
    ) -> RequestAnswerDraft:
        return RequestAnswerDraft(
            request_id=str(request.get("request_id") or "").strip(),
            request_index=int(request.get("request_index") or 0),
            request_kind=str(request.get("request_kind") or "rag"),
            query_span=str(request.get("query_span") or "").strip(),
            abstention_reason=error_type,
            error_type=error_type,
        )

    def generate(
        self,
        *,
        retrieval_result: dict[str, Any],
        selected_citations: list[dict[str, Any]],
        cohort: str | None,
    ) -> VerifiedAnswerBatch | None:
        requests = [
            dict(item)
            for item in retrieval_result.get("request_results") or []
            if isinstance(item, Mapping)
            and item.get("request_kind") in {"structured", "rag"}
            and str(item.get("request_id") or "").strip()
        ]
        if not requests:
            return None
        requests.sort(key=lambda item: int(item.get("request_index") or 0))

        drafts: list[RequestAnswerDraft] = []
        rag_jobs: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        for request in requests:
            status = str(request.get("status") or "error")
            request_kind = str(request.get("request_kind") or "")
            if request_kind == "structured" and status == "ok" and bool(
                (request.get("provenance") or {}).get("source_bound")
            ):
                scoped_result = self._scoped_structured_result(
                    retrieval_result.get("structured_result"),
                    request_id=str(request.get("request_id")),
                )
                if scoped_result is not None:
                    drafts.append(
                        self._structured_draft(
                            retrieval_result=retrieval_result,
                            request=request,
                        )
                    )
                    continue
            if request_kind == "rag" and status == "ok" and bool(
                (request.get("provenance") or {}).get("qualified")
            ):
                evidence = self._evidence_catalog(
                    retrieval_result=retrieval_result,
                    selected_citations=selected_citations,
                    request_id=str(request.get("request_id")),
                    expected_cohort=str(
                        request.get("cohort") or cohort or ""
                    ).strip()
                    or None,
                )
                if evidence:
                    rag_jobs.append((request, evidence))
                    continue
                drafts.append(
                    self._failed_draft(
                        request, error_type="missing_request_evidence"
                    )
                )
                continue
            drafts.append(
                self._failed_draft(request, error_type=f"request_{status}")
            )

        llm_results: list[Mapping[str, Any]] = []
        provider_failures = 0
        model_used: str | None = None
        composition_started = time.monotonic()
        llm_client: Any | None = None
        if rag_jobs:
            try:
                llm_client = self._client_provider()
            except Exception:
                provider_failures += len(rag_jobs)
                drafts.extend(
                    self._failed_draft(request, error_type="composer_client_error")
                    for request, _ in rag_jobs
                )
                rag_jobs = []

        def compose_one(
            request: dict[str, Any], evidence: list[dict[str, Any]]
        ) -> Mapping[str, Any]:
            prompt = build_request_claim_prompt(
                request_id=str(request.get("request_id")),
                query_span=str(request.get("query_span") or ""),
                cohort=str(request.get("cohort") or cohort or "").strip() or None,
                evidence_catalog=evidence,
            )
            assert llm_client is not None
            return llm_client.generate(prompt)

        if rag_jobs:
            composition_config = self._config.get("request_composition") or {}
            configured_workers = int(composition_config.get("max_concurrency", 3))
            max_workers = max(1, min(3, configured_workers, len(rag_jobs)))
            future_metadata: dict[
                Any, tuple[dict[str, Any], list[dict[str, Any]]]
            ] = {}
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for request, evidence in rag_jobs:
                    future = executor.submit(compose_one, request, evidence)
                    future_metadata[future] = (request, evidence)
                for future in as_completed(future_metadata):
                    request, evidence = future_metadata[future]
                    try:
                        result = future.result()
                    except Exception:
                        provider_failures += 1
                        drafts.append(
                            self._failed_draft(
                                request, error_type="composer_exception"
                            )
                        )
                        continue
                    llm_results.append(result)
                    if not result.get("ok"):
                        provider_failures += 1
                        drafts.append(
                            self._failed_draft(
                                request,
                                error_type=str(
                                    result.get("error_type")
                                    or "composer_provider_error"
                                ),
                            )
                        )
                        continue
                    model_used = (
                        str(result.get("model_used") or model_used or "") or None
                    )
                    try:
                        drafts.append(
                            parse_request_draft(
                                result.get("text"),
                                request_id=str(request.get("request_id")),
                                request_index=int(request.get("request_index") or 0),
                                query_span=str(request.get("query_span") or ""),
                                allowed_evidence_ids={
                                    str(item.get("evidence_id"))
                                    for item in evidence
                                },
                            )
                        )
                    except ClaimContractError:
                        drafts.append(
                            self._failed_draft(
                                request, error_type="composer_contract_error"
                            )
                        )
        composition_ms = (time.monotonic() - composition_started) * 1000

        drafts.sort(key=lambda draft: draft.request_index)
        rag_drafts = [
            draft for draft in drafts if draft.request_kind == "rag" and draft.claims
        ]
        evidence_by_request = {
            str(request.get("request_id")): evidence for request, evidence in rag_jobs
        }
        verifier_config = self._config.get("claim_verifier") or {}
        verifier_enabled = bool(verifier_config.get("enabled", True))
        verification_results: list[ClaimVerificationResult] = []
        verifier_call_count = 0
        verification_executed = False
        verification_status = "not_applicable"
        verification_started = time.monotonic()
        verifier_error: str | None = None
        configured_verifier_model = str(
            verifier_config.get("model_name") or ""
        ).strip()
        active_model = str(getattr(llm_client, "model_name", "") or "").strip()
        model_mismatch = bool(
            configured_verifier_model
            and active_model
            and configured_verifier_model != active_model
        )

        if (
            rag_drafts
            and verifier_enabled
            and llm_client is not None
            and not model_mismatch
        ):
            verification_executed = True
            verifier_call_count = 1
            verifier_prompt = build_claim_verifier_prompt(
                drafts=rag_drafts,
                evidence_by_request={
                    request_id: evidence_by_request[request_id]
                    for request_id in {draft.request_id for draft in rag_drafts}
                },
            )
            try:
                if isinstance(llm_client, GeminiClient):
                    verifier_result = llm_client.generate(
                        verifier_prompt,
                        temperature=float(verifier_config.get("temperature", 0.0)),
                        max_output_tokens=int(
                            verifier_config.get("max_output_tokens", 2048)
                        ),
                    )
                else:
                    verifier_result = llm_client.generate(verifier_prompt)
                llm_results.append(verifier_result)
                model_used = (
                    str(verifier_result.get("model_used") or model_used or "") or None
                )
                if not verifier_result.get("ok"):
                    provider_failures += 1
                    verification_status = "provider_error"
                    verifier_error = str(
                        verifier_result.get("error_type")
                        or "verifier_provider_error"
                    )
                else:
                    verification_results = parse_verification_results(
                        verifier_result.get("text"), drafts=rag_drafts
                    )
                    verification_status = "passed"
            except ClaimContractError as exc:
                verification_status = "contract_error"
                verifier_error = str(exc)
            except Exception as exc:
                provider_failures += 1
                verification_status = "provider_error"
                verifier_error = type(exc).__name__
        elif rag_drafts and verifier_enabled and model_mismatch:
            verification_status = "config_error"
            verifier_error = "verifier_model_mismatch"
        elif rag_drafts and not verifier_enabled:
            verification_status = "disabled"
        elif any(draft.request_kind == "rag" for draft in drafts):
            verification_status = "no_claims"

        verification_ms = (time.monotonic() - verification_started) * 1000
        answer, request_debug = render_verified_answer(
            drafts,
            verification_results,
            accept_unverified_rag=not verifier_enabled,
        )
        supported_parts = sum(
            int(item.get("supported_claim_count") or 0) for item in request_debug
        )
        has_structured = any(
            draft.request_kind == "structured" and draft.claims for draft in drafts
        )
        contract_failure = any(
            draft.error_type == "composer_contract_error" for draft in drafts
        )
        generation_failure = bool(verifier_error or provider_failures or contract_failure)
        if generation_failure and not has_structured and supported_parts == 0:
            status = "api_error"
            error_type = (
                verifier_error
                or ("composer_contract_error" if contract_failure else None)
                or "composer_provider_error"
            )
        else:
            status = "answered"
            error_type = (
                "partial_answer_generation_error"
                if generation_failure
                else None
            )

        supporting_evidence_ids: list[str] = []
        for draft in drafts:
            if draft.request_kind == "structured" or not verifier_enabled:
                evidence_ids = [
                    evidence_id
                    for claim in draft.claims
                    for evidence_id in claim.citation_ids
                ]
            else:
                evidence_ids = [
                    evidence_id
                    for result in verification_results
                    if result.request_id == draft.request_id
                    and result.verdict == "supported"
                    for evidence_id in result.supporting_evidence_ids
                ]
            for evidence_id in evidence_ids:
                if evidence_id not in supporting_evidence_ids:
                    supporting_evidence_ids.append(evidence_id)

        return VerifiedAnswerBatch(
            answer=answer,
            drafts=drafts,
            verification_results=verification_results,
            verification_executed=verification_executed,
            verification_status=verification_status,
            composer_call_count=len(rag_jobs),
            verifier_call_count=verifier_call_count,
            provider_failures=provider_failures,
            model_used=model_used,
            usage=merge_usage(llm_results),
            request_debug=request_debug,
            status=status,
            error_type=error_type,
            error_message=verifier_error,
            composition_ms=composition_ms,
            verification_ms=verification_ms,
            supporting_evidence_ids=tuple(supporting_evidence_ids),
        )
