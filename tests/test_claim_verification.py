from __future__ import annotations

import json
from typing import Any

import pytest

from src.generation.answer_pipeline import AnswerPipeline
from src.generation.claim_verification import (
    AnswerClaim,
    ClaimContractError,
    RequestAnswerDraft,
    parse_request_draft,
    parse_verification_results,
)


def _citation(request_id: str, chunk_id: str, content: str) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "request_index": int(request_id[1:]) - 1,
        "request_kind": "rag",
        "request_cohort": "K51",
        "chunk_id": chunk_id,
        "document_id": "handbook-k51",
        "parent_section_id": f"section-{chunk_id}",
        "source_pages": [10],
        "title": f"Nguồn {chunk_id}",
        "content": content,
    }


def _rag_retrieval_result() -> dict[str, Any]:
    citations = [
        _citation("r1", "evidence-r1", "Quy định riêng chỉ thuộc yêu cầu thứ nhất."),
        _citation("r2", "evidence-r2", "Quy định riêng chỉ thuộc yêu cầu thứ hai."),
    ]
    return {
        "selected_cohort": "K51",
        "citations": citations,
        "retrieved_items": [dict(item) for item in citations],
        "request_results": [
            {
                "request_id": "r1",
                "request_index": 0,
                "request_kind": "rag",
                "query_span": "quy định thứ nhất",
                "cohort": "K51",
                "status": "ok",
                "provenance": {"qualified": True},
            },
            {
                "request_id": "r2",
                "request_index": 1,
                "request_kind": "rag",
                "query_span": "quy định thứ hai",
                "cohort": "K51",
                "status": "ok",
                "provenance": {"qualified": True},
            },
        ],
    }


class _ContractClient:
    def __init__(self, *, verifier_mode: str = "pass") -> None:
        self.verifier_mode = verifier_mode
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> dict[str, Any]:
        self.prompts.append(prompt)
        if "bộ kiểm chứng claim" in prompt:
            if self.verifier_mode == "provider_error":
                return {"ok": False, "error_type": "timeout"}
            if self.verifier_mode == "forged":
                payload = {
                    "results": [
                        {
                            "request_id": "r1",
                            "claim_id": "r1.c1",
                            "verdict": "supported",
                            "supporting_evidence_ids": ["evidence-r2"],
                            "reason_code": "direct_support",
                        },
                        {
                            "request_id": "r2",
                            "claim_id": "r2.c1",
                            "verdict": "supported",
                            "supporting_evidence_ids": ["evidence-r2"],
                            "reason_code": "direct_support",
                        },
                    ]
                }
            else:
                payload = {
                    "results": [
                        {
                            "request_id": request_id,
                            "claim_id": f"{request_id}.c1",
                            "verdict": "supported",
                            "supporting_evidence_ids": [f"evidence-{request_id}"],
                            "reason_code": "direct_support",
                        }
                        for request_id in ("r1", "r2")
                    ]
                }
            return {
                "ok": True,
                "text": json.dumps(payload),
                "model_used": "deterministic-gemini",
                "usage": {"input": 1, "output": 1, "total": 2},
            }

        request_id = "r1" if "request_id=r1" in prompt else "r2"
        payload = {
            "request_id": request_id,
            "claims": [
                {
                    "text": f"Nội dung đã xác minh cho {request_id}.",
                    "citation_ids": [f"evidence-{request_id}"],
                }
            ],
            "abstention_reason": None,
        }
        return {
            "ok": True,
            "text": json.dumps(payload),
            "model_used": "deterministic-gemini",
            "usage": {"input": 1, "output": 1, "total": 2},
        }


def _pipeline(client: _ContractClient, *, verifier_enabled: bool = True) -> AnswerPipeline:
    pipeline = AnswerPipeline.__new__(AnswerPipeline)
    pipeline.config = {
        "request_composition": {"max_concurrency": 3},
        "claim_verifier": {
            "enabled": verifier_enabled,
            "max_chars_per_evidence": 5000,
        },
    }
    pipeline._get_llm_client = lambda: client
    return pipeline


def test_composer_accepts_direct_json_object_and_assigns_stable_claim_ids() -> None:
    draft = parse_request_draft(
        {
            "request_id": "r2",
            "claims": [{"text": "Có căn cứ.", "citation_ids": ["e2"]}],
            "abstention_reason": None,
        },
        request_id="r2",
        request_index=1,
        query_span="yêu cầu hai",
        allowed_evidence_ids={"e2"},
    )

    assert draft.claims[0].claim_id == "r2.c1"


def test_verifier_rejects_cross_request_evidence_id() -> None:
    drafts = [
        RequestAnswerDraft(
            request_id="r1",
            request_index=0,
            request_kind="rag",
            query_span="request one",
            claims=(AnswerClaim("r1.c1", "claim", ("e1",)),),
        )
    ]

    with pytest.raises(ClaimContractError, match="out_of_claim_scope"):
        parse_verification_results(
            {
                "results": [
                    {
                        "request_id": "r1",
                        "claim_id": "r1.c1",
                        "verdict": "supported",
                        "supporting_evidence_ids": ["e2"],
                        "reason_code": "direct_support",
                    }
                ]
            },
            drafts=drafts,
        )


def test_verifier_rejects_missing_claim_verdict() -> None:
    drafts = [
        RequestAnswerDraft(
            request_id="r1",
            request_index=0,
            request_kind="rag",
            query_span="request one",
            claims=(
                AnswerClaim("r1.c1", "claim one", ("e1",)),
                AnswerClaim("r1.c2", "claim two", ("e1",)),
            ),
        )
    ]

    with pytest.raises(ClaimContractError, match="missing_claim_verdict"):
        parse_verification_results(
            {
                "results": [
                    {
                        "request_id": "r1",
                        "claim_id": "r1.c1",
                        "verdict": "supported",
                        "supporting_evidence_ids": ["e1"],
                        "reason_code": "direct_support",
                    }
                ]
            },
            drafts=drafts,
        )


def test_composer_rejects_malformed_json_without_coercion() -> None:
    with pytest.raises(ClaimContractError, match="invalid_json"):
        parse_request_draft(
            "{not-json}",
            request_id="r1",
            request_index=0,
            query_span="request one",
            allowed_evidence_ids={"e1"},
        )


def test_request_composers_receive_only_their_own_evidence_and_batch_verify() -> None:
    client = _ContractClient()
    pipeline = _pipeline(client)
    retrieval_result = _rag_retrieval_result()

    batch = pipeline._generate_request_isolated_answer(
        retrieval_result=retrieval_result,
        selected_citations=retrieval_result["citations"],
        cohort="K51",
    )

    assert batch is not None
    assert batch.verification_status == "passed"
    assert batch.composer_call_count == 2
    assert batch.verifier_call_count == 1
    assert "Nội dung đã xác minh cho r1" in batch.answer
    assert "Nội dung đã xác minh cho r2" in batch.answer
    composer_prompts = [
        prompt for prompt in client.prompts if "bộ kiểm chứng claim" not in prompt
    ]
    r1_prompt = next(prompt for prompt in composer_prompts if "request_id=r1" in prompt)
    r2_prompt = next(prompt for prompt in composer_prompts if "request_id=r2" in prompt)
    assert "evidence-r2" not in r1_prompt
    assert "evidence-r1" not in r2_prompt


def test_forged_verifier_binding_fails_closed_for_all_rag_claims() -> None:
    client = _ContractClient(verifier_mode="forged")
    pipeline = _pipeline(client)
    retrieval_result = _rag_retrieval_result()

    batch = pipeline._generate_request_isolated_answer(
        retrieval_result=retrieval_result,
        selected_citations=retrieval_result["citations"],
        cohort="K51",
    )

    assert batch is not None
    assert batch.verification_status == "contract_error"
    assert batch.status == "api_error"
    assert "Nội dung đã xác minh" not in batch.answer
    assert all(item["supported_claim_count"] == 0 for item in batch.request_debug)


def test_wrong_cohort_evidence_is_rejected_before_composer() -> None:
    client = _ContractClient()
    pipeline = _pipeline(client)
    retrieval_result = _rag_retrieval_result()
    retrieval_result["citations"][0]["request_cohort"] = "K50"
    retrieval_result["retrieved_items"][0]["request_cohort"] = "K50"

    batch = pipeline._generate_request_isolated_answer(
        retrieval_result=retrieval_result,
        selected_citations=retrieval_result["citations"],
        cohort="K51",
    )

    assert batch is not None
    r1 = next(item for item in batch.request_debug if item["request_id"] == "r1")
    assert r1["supported_claim_count"] == 0
    assert r1["abstention_reason"] == "missing_request_evidence"
    assert not any("request_id=r1" in prompt for prompt in client.prompts)


def test_verifier_disabled_supports_ablation_without_extra_call() -> None:
    client = _ContractClient()
    pipeline = _pipeline(client, verifier_enabled=False)
    retrieval_result = _rag_retrieval_result()

    batch = pipeline._generate_request_isolated_answer(
        retrieval_result=retrieval_result,
        selected_citations=retrieval_result["citations"],
        cohort="K51",
    )

    assert batch is not None
    assert batch.verification_status == "disabled"
    assert batch.verifier_call_count == 0
    assert len(client.prompts) == 2
    assert "Nội dung đã xác minh cho r1" in batch.answer


def test_mixed_verifier_failure_keeps_source_bound_structured_part() -> None:
    client = _ContractClient(verifier_mode="provider_error")
    pipeline = _pipeline(client)
    retrieval_result = _rag_retrieval_result()
    retrieval_result["request_results"][0] = {
        "request_id": "r1",
        "request_index": 0,
        "request_kind": "structured",
        "query_span": "điểm chữ A quy đổi thế nào",
        "cohort": "K51",
        "status": "ok",
        "provenance": {"source_bound": True},
    }
    retrieval_result["structured_result"] = {
        "request_id": "r1",
        "request_index": 0,
        "lookup_type": "grade_10_to_letter",
        "input_value": 8.5,
        "result": [
            {
                "row": {
                    "letter_grade": "A",
                    "score_10_range": "8,5–10,0",
                    "status": "Đạt",
                },
                "applicability": "hệ chính quy",
            }
        ],
    }
    retrieval_result["citations"][0]["request_kind"] = "structured"

    batch = pipeline._generate_request_isolated_answer(
        retrieval_result=retrieval_result,
        selected_citations=retrieval_result["citations"],
        cohort="K51",
    )

    assert batch is not None
    assert batch.status == "answered"
    assert batch.verification_status == "provider_error"
    assert "điểm 8.5 tương ứng" in batch.answer
    assert "Nội dung đã xác minh cho r2" not in batch.answer
    assert "chưa tìm thấy thông tin đủ rõ" in batch.answer
