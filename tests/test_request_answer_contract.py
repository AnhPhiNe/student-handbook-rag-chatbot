from __future__ import annotations

import pytest

from src.generation.request_answer_contract import (
    REQUEST_COMPOSER_PROMPT_VERSION,
    RequestContractError,
    build_fact_catalog,
    build_structured_fallback,
    parse_json_object,
    parse_request_draft,
    render_request_answers,
)
from src.generation.request_answer_orchestrator import RequestAnswerOrchestrator
from src.generation.prompt_builder import build_request_claim_prompt


def test_request_composer_prompt_preserves_source_applicability() -> None:
    prompt = build_request_claim_prompt(
        request_id="r1",
        request_kind="rag",
        query_span="Nội dung đó có ngoại lệ nào?",
        grounded_request_query="quy định cảnh báo học vụ có ngoại lệ nào",
        cohort="K51",
        evidence_catalog=[
            {
                "evidence_id": "source-a",
                "title": "Nguồn A",
                "content": "Quy định áp dụng cho phạm vi A.",
            },
            {
                "evidence_id": "source-b",
                "title": "Nguồn B",
                "content": "Quy định áp dụng cho phạm vi B.",
            },
        ],
        fact_catalog=[],
    )

    assert REQUEST_COMPOSER_PROMPT_VERSION in prompt
    assert "phải nêu tách" in prompt
    assert "không được trình bày một phạm vi" in prompt
    assert "dev-follow_up-04" not in prompt
    assert "Điều 12" not in prompt
    assert "Điều 13" not in prompt


def test_parse_json_object_accepts_direct_provider_object() -> None:
    assert parse_json_object({"request_id": "r1"}) == {"request_id": "r1"}


def test_rag_draft_rejects_cross_request_citation() -> None:
    with pytest.raises(RequestContractError, match="citation_out_of_scope"):
        parse_request_draft(
            {
                "request_id": "r1",
                "claims": [
                    {
                        "text": "Nội dung nguồn.",
                        "citation_ids": ["chunk-r2"],
                        "fact_refs": [],
                    }
                ],
                "abstention_reason": None,
            },
            request_id="r1",
            request_index=0,
            request_kind="rag",
            query_span="quy định",
            grounded_request_query="quy định K51",
            allowed_evidence_ids={"chunk-r1"},
            fact_catalog=[],
        )


def test_structured_draft_requires_valid_fact_refs() -> None:
    facts = build_fact_catalog(
        {"formula_text": "A = Σ(ai × ni) / Σ(ni)", "source_article": "Điều 11"}
    )
    with pytest.raises(RequestContractError, match="fact_ref_out_of_scope"):
        parse_request_draft(
            {
                "request_id": "r1",
                "claims": [
                    {
                        "text": "Theo Điều 11, dùng công thức đã tra cứu.",
                        "citation_ids": ["formula-r1"],
                        "fact_refs": ["result.unknown"],
                    }
                ],
                "abstention_reason": None,
            },
            request_id="r1",
            request_index=0,
            request_kind="structured",
            query_span="công thức điểm trung bình",
            grounded_request_query="K51 công thức điểm trung bình",
            allowed_evidence_ids={"formula-r1"},
            fact_catalog=facts,
        )


def test_structured_draft_rejects_ungrounded_number() -> None:
    facts = build_fact_catalog({"minimum_score": 3.2, "classification": "Giỏi"})
    with pytest.raises(RequestContractError, match="literal_not_grounded"):
        parse_request_draft(
            {
                "request_id": "r1",
                "claims": [
                    {
                        "text": "Mức Giỏi bắt đầu từ 3.6.",
                        "citation_ids": ["row-r1"],
                        "fact_refs": ["result.minimum_score", "result.classification"],
                    }
                ],
                "abstention_reason": None,
            },
            request_id="r1",
            request_index=0,
            request_kind="structured",
            query_span="mức Giỏi",
            grounded_request_query="mức Giỏi K51",
            allowed_evidence_ids={"row-r1"},
            fact_catalog=facts,
        )


def test_structured_fallback_is_generic_and_source_bound() -> None:
    facts = build_fact_catalog(
        {"formula_text": "A = Σ(ai × ni) / Σ(ni)", "source_article": "Điều 11"}
    )
    draft = build_structured_fallback(
        request_id="r1",
        request_index=0,
        query_span="công thức điểm trung bình",
        grounded_request_query="K51 công thức điểm trung bình",
        fact_catalog=facts,
        citation_ids=["formula-r1"],
        error_type="composer_provider_error",
    )
    answer, debug = render_request_answers([draft])

    assert "A = Σ(ai × ni) / Σ(ni)" in answer
    assert "Điều 11" in answer
    assert draft.claims[0].citation_ids == ("formula-r1",)
    assert debug[0]["used_fallback"] is True
    assert debug[0]["contract_passed"] is False
    assert debug[0]["final_contract_passed"] is True


def test_shared_structured_catalog_accepts_record_identity_without_pages() -> None:
    citation = {
        "request_id": "r1",
        "chunk_id": "structured:office:student-services",
        "document_id": "shared-directory",
        "source_record_id": "student-services",
        "cohort": None,
        "source_pages": [],
    }
    catalog = RequestAnswerOrchestrator._evidence_catalog(
        retrieval_result={"citations": [citation], "retrieved_items": []},
        selected_citations=[],
        request_id="r1",
        expected_cohort="K51",
        require_content=False,
        max_chars=5000,
    )

    assert catalog[0]["source_record_id"] == "student-services"
    assert catalog[0]["cohort"] == ""
