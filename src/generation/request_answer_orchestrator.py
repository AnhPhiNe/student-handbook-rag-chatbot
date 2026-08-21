from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .prompt_builder import build_request_claim_prompt
from .request_answer_contract import (
    RequestAnswerBatch,
    RequestAnswerDraft,
    RequestContractError,
    build_fact_catalog,
    build_structured_fallback,
    merge_usage,
    parse_request_draft,
    render_request_answers,
)


class RequestAnswerOrchestrator:
    """Compose atomic requests independently and merge only validated drafts."""

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
        cls, values: Any, *, request_id: str
    ) -> list[dict[str, Any]]:
        return [
            dict(value)
            for value in values or []
            if isinstance(value, Mapping)
            and cls._request_scope_id(value) == request_id
        ]

    @classmethod
    def _scoped_structured_result(
        cls, value: Any, *, request_id: str
    ) -> dict[str, Any] | None:
        if not isinstance(value, Mapping):
            return None
        if cls._request_scope_id(value) == request_id:
            return dict(value)
        candidates = value.get("sub_results")
        if not isinstance(candidates, list):
            candidates = value.get("result") if isinstance(value.get("result"), list) else []
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
    def _execution_contexts(
        cls, retrieval_result: Mapping[str, Any]
    ) -> dict[str, dict[str, Any]]:
        contexts: dict[str, dict[str, Any]] = {}
        for value in retrieval_result.get("request_execution_contexts") or []:
            if not isinstance(value, Mapping):
                continue
            request_id = cls._request_scope_id(value)
            if request_id:
                contexts[request_id] = dict(value)
        return contexts

    @classmethod
    def _grounded_request_query(
        cls,
        request: Mapping[str, Any],
        contexts: Mapping[str, Mapping[str, Any]],
    ) -> str:
        request_id = cls._request_scope_id(request)
        context = contexts.get(request_id) or {}
        retrieval_query = context.get("retrieval_query")
        if isinstance(retrieval_query, str) and retrieval_query.strip():
            return retrieval_query.strip()
        return str(request.get("query_span") or "").strip()

    @classmethod
    def _evidence_catalog(
        cls,
        *,
        retrieval_result: Mapping[str, Any],
        selected_citations: list[dict[str, Any]],
        request_id: str,
        expected_cohort: str | None,
        require_content: bool,
        max_chars: int,
    ) -> list[dict[str, Any]]:
        scoped_items = cls._scoped_values(
            retrieval_result.get("retrieved_items"), request_id=request_id
        )
        item_by_chunk: dict[str, dict[str, Any]] = {}
        for item in scoped_items:
            metadata = item.get("metadata")
            metadata = metadata if isinstance(metadata, Mapping) else {}
            chunk_id = str(item.get("chunk_id") or metadata.get("chunk_id") or "").strip()
            if chunk_id:
                item_by_chunk[chunk_id] = item

        all_citations = [
            *list(retrieval_result.get("citations") or []),
            *selected_citations,
        ]
        catalog: list[dict[str, Any]] = []
        seen: set[str] = set()
        for citation in cls._scoped_values(all_citations, request_id=request_id):
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
            item_metadata = item_metadata if isinstance(item_metadata, Mapping) else {}
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
            document_id = (
                citation.get("document_id")
                or metadata.get("document_id")
                or matching_item.get("document_id")
                or item_metadata.get("document_id")
            )
            parent_section_id = (
                citation.get("parent_section_id")
                or metadata.get("parent_section_id")
                or matching_item.get("parent_section_id")
                or item_metadata.get("parent_section_id")
            )
            source_record_id = (
                citation.get("source_record_id")
                or metadata.get("source_record_id")
                or matching_item.get("source_record_id")
                or item_metadata.get("source_record_id")
            )
            table_id = (
                citation.get("table_id")
                or metadata.get("table_id")
                or matching_item.get("table_id")
                or item_metadata.get("table_id")
            )
            source_url = citation.get("source_url") or metadata.get("source_url")
            source_pages = (
                citation.get("source_pages")
                or metadata.get("source_pages")
                or matching_item.get("source_pages")
                or item_metadata.get("source_pages")
                or []
            )
            source_identity = parent_section_id or source_record_id or table_id or source_url
            wrong_cohort = bool(
                expected_cohort
                and (
                    (require_content and source_cohort != expected_cohort)
                    or (not require_content and source_cohort and source_cohort != expected_cohort)
                )
            )
            if not document_id or not source_identity or wrong_cohort:
                continue
            if require_content and (
                not parent_section_id or not content or not source_pages
            ):
                continue
            seen.add(evidence_id)
            catalog.append(
                {
                    "evidence_id": evidence_id,
                    "request_id": request_id,
                    "document_id": document_id,
                    "parent_section_id": parent_section_id,
                    "source_record_id": source_record_id,
                    "table_id": table_id,
                    "source_url": source_url,
                    "source_pages": source_pages,
                    "cohort": source_cohort,
                    "title": citation.get("title") or matching_item.get("title"),
                    "content": content[:max_chars],
                }
            )
        return catalog

    @staticmethod
    def _failed_draft(
        request: Mapping[str, Any],
        *,
        grounded_request_query: str,
        error_type: str,
    ) -> RequestAnswerDraft:
        return RequestAnswerDraft(
            request_id=str(request.get("request_id") or "").strip(),
            request_index=int(request.get("request_index") or 0),
            request_kind=str(request.get("request_kind") or "rag"),
            query_span=str(request.get("query_span") or "").strip(),
            grounded_request_query=grounded_request_query,
            abstention_reason=error_type,
            error_type=error_type,
        )

    def generate(
        self,
        *,
        retrieval_result: dict[str, Any],
        selected_citations: list[dict[str, Any]],
        cohort: str | None,
    ) -> RequestAnswerBatch | None:
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

        contexts = self._execution_contexts(retrieval_result)
        max_chars = max(
            500,
            int(
                (self._config.get("request_composition") or {}).get(
                    "max_chars_per_evidence", 5000
                )
            ),
        )
        drafts: list[RequestAnswerDraft] = []
        jobs: list[
            tuple[
                dict[str, Any],
                str,
                list[dict[str, Any]],
                list[dict[str, Any]],
            ]
        ] = []
        for request in requests:
            request_id = str(request.get("request_id") or "").strip()
            request_kind = str(request.get("request_kind") or "")
            status = str(request.get("status") or "error")
            grounded_query = self._grounded_request_query(request, contexts)
            if status != "ok":
                drafts.append(
                    self._failed_draft(
                        request,
                        grounded_request_query=grounded_query,
                        error_type=f"request_{status}",
                    )
                )
                continue

            expected_cohort = str(request.get("cohort") or cohort or "").strip() or None
            evidence = self._evidence_catalog(
                retrieval_result=retrieval_result,
                selected_citations=selected_citations,
                request_id=request_id,
                expected_cohort=expected_cohort,
                require_content=request_kind == "rag",
                max_chars=max_chars,
            )
            if request_kind == "structured":
                if not bool((request.get("provenance") or {}).get("source_bound")):
                    drafts.append(
                        self._failed_draft(
                            request,
                            grounded_request_query=grounded_query,
                            error_type="structured_source_unbound",
                        )
                    )
                    continue
                structured_result = self._scoped_structured_result(
                    retrieval_result.get("structured_result"), request_id=request_id
                )
                facts = build_fact_catalog(structured_result)
                if not structured_result or not facts or not evidence:
                    drafts.append(
                        self._failed_draft(
                            request,
                            grounded_request_query=grounded_query,
                            error_type="missing_structured_contract",
                        )
                    )
                    continue
                jobs.append((request, grounded_query, evidence, facts))
                continue
            if request_kind == "rag":
                if not bool((request.get("provenance") or {}).get("qualified")) or not evidence:
                    drafts.append(
                        self._failed_draft(
                            request,
                            grounded_request_query=grounded_query,
                            error_type="missing_request_evidence",
                        )
                    )
                    continue
                jobs.append((request, grounded_query, evidence, []))

        llm_results: list[Mapping[str, Any]] = []
        provider_failures = 0
        composer_call_count = 0
        model_used: str | None = None
        request_composition_ms: dict[str, float] = {}
        request_provider_telemetry: dict[str, dict[str, Any]] = {}
        composition_started = time.monotonic()
        llm_client: Any | None = None
        if jobs:
            try:
                llm_client = self._client_provider()
            except Exception:
                provider_failures += len(jobs)
                for request, grounded_query, evidence, facts in jobs:
                    drafts.append(
                        self._fallback_or_failure(
                            request=request,
                            grounded_query=grounded_query,
                            evidence=evidence,
                            facts=facts,
                            error_type="composer_client_error",
                        )
                    )
                jobs = []

        def compose_one(
            request: dict[str, Any],
            grounded_query: str,
            evidence: list[dict[str, Any]],
            facts: list[dict[str, Any]],
        ) -> tuple[Mapping[str, Any], float, int]:
            prompt = build_request_claim_prompt(
                request_id=str(request.get("request_id")),
                request_kind=str(request.get("request_kind")),
                query_span=str(request.get("query_span") or ""),
                grounded_request_query=grounded_query,
                cohort=str(request.get("cohort") or cohort or "").strip() or None,
                evidence_catalog=evidence,
                fact_catalog=facts,
            )
            assert llm_client is not None
            started = time.monotonic()
            result = llm_client.generate(prompt)
            return result, (time.monotonic() - started) * 1000, len(prompt)

        if jobs:
            configured_workers = int(
                (self._config.get("request_composition") or {}).get(
                    "max_concurrency", 3
                )
            )
            max_workers = max(1, min(3, configured_workers, len(jobs)))
            composer_call_count = len(jobs)
            future_metadata: dict[
                Any,
                tuple[
                    dict[str, Any],
                    str,
                    list[dict[str, Any]],
                    list[dict[str, Any]],
                ],
            ] = {}
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                for job in jobs:
                    future_metadata[executor.submit(compose_one, *job)] = job
                for future in as_completed(future_metadata):
                    request, grounded_query, evidence, facts = future_metadata[future]
                    try:
                        result, request_ms, prompt_chars = future.result()
                    except Exception:
                        provider_failures += 1
                        drafts.append(
                            self._fallback_or_failure(
                                request=request,
                                grounded_query=grounded_query,
                                evidence=evidence,
                                facts=facts,
                                error_type="composer_exception",
                            )
                        )
                        continue
                    request_composition_ms[str(request.get("request_id"))] = request_ms
                    request_provider_telemetry[str(request.get("request_id"))] = {
                        "attempts": int(result.get("attempts") or 0),
                        "key_fingerprint": result.get("key_fingerprint"),
                        "model_used": result.get("model_used"),
                        "prompt_chars": prompt_chars,
                        "usage": dict(result.get("usage") or {}),
                    }
                    llm_results.append(result)
                    if not result.get("ok"):
                        provider_failures += 1
                        drafts.append(
                            self._fallback_or_failure(
                                request=request,
                                grounded_query=grounded_query,
                                evidence=evidence,
                                facts=facts,
                                error_type=str(
                                    result.get("error_type") or "composer_provider_error"
                                ),
                            )
                        )
                        continue
                    model_used = str(result.get("model_used") or model_used or "") or None
                    try:
                        drafts.append(
                            parse_request_draft(
                                result.get("text"),
                                request_id=str(request.get("request_id")),
                                request_index=int(request.get("request_index") or 0),
                                request_kind=str(request.get("request_kind")),
                                query_span=str(request.get("query_span") or ""),
                                grounded_request_query=grounded_query,
                                allowed_evidence_ids={
                                    str(item.get("evidence_id")) for item in evidence
                                },
                                fact_catalog=facts,
                            )
                        )
                    except RequestContractError:
                        drafts.append(
                            self._fallback_or_failure(
                                request=request,
                                grounded_query=grounded_query,
                                evidence=evidence,
                                facts=facts,
                                error_type="composer_contract_error",
                            )
                        )

        composition_ms = (time.monotonic() - composition_started) * 1000
        drafts.sort(key=lambda draft: draft.request_index)
        answer, request_debug = render_request_answers(drafts)
        for row in request_debug:
            request_id = str(row.get("request_id"))
            row["composition_ms"] = request_composition_ms.get(request_id, 0.0)
            row["provider"] = request_provider_telemetry.get(request_id)
        supported_parts = sum(bool(draft.claims) for draft in drafts)
        contract_passed = all(not draft.error_type for draft in drafts)
        final_contract_passed = all(
            not draft.error_type
            or (
                draft.request_kind == "structured"
                and draft.used_fallback
                and bool(draft.claims)
            )
            for draft in drafts
        )
        generation_failure = provider_failures > 0 or not contract_passed
        if generation_failure and supported_parts == 0:
            status = "api_error"
            error_type = "request_composition_error"
        else:
            status = "answered"
            error_type = "partial_answer_generation_error" if generation_failure else None

        supporting_evidence_ids: list[str] = []
        for draft in drafts:
            for claim in draft.claims:
                for evidence_id in claim.citation_ids:
                    if evidence_id not in supporting_evidence_ids:
                        supporting_evidence_ids.append(evidence_id)
        return RequestAnswerBatch(
            answer=answer,
            drafts=drafts,
            composer_call_count=composer_call_count,
            provider_failures=provider_failures,
            contract_passed=contract_passed,
            final_contract_passed=final_contract_passed,
            model_used=model_used,
            usage=merge_usage(llm_results),
            request_debug=request_debug,
            status=status,
            error_type=error_type,
            composition_ms=composition_ms,
            request_composition_ms=request_composition_ms,
            supporting_evidence_ids=tuple(supporting_evidence_ids),
        )

    def _fallback_or_failure(
        self,
        *,
        request: Mapping[str, Any],
        grounded_query: str,
        evidence: list[dict[str, Any]],
        facts: list[dict[str, Any]],
        error_type: str,
    ) -> RequestAnswerDraft:
        if str(request.get("request_kind")) == "structured":
            return build_structured_fallback(
                request_id=str(request.get("request_id") or ""),
                request_index=int(request.get("request_index") or 0),
                query_span=str(request.get("query_span") or ""),
                grounded_request_query=grounded_query,
                fact_catalog=facts,
                citation_ids=[str(item.get("evidence_id")) for item in evidence],
                error_type=error_type,
            )
        return self._failed_draft(
            request,
            grounded_request_query=grounded_query,
            error_type=error_type,
        )
