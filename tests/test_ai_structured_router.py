from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.generation.answer_guardrails import can_answer_deterministically
from src.retrieval.core.ai_router import AIRouter, GroqRouterKeyPool
from src.retrieval.core.office_lookup import find_grounded_catalog_hint, office_lookup
from src.retrieval.core.retrieval_pipeline import run_retrieval_pipeline
from src.retrieval.core.structured_routing import (
    decision_to_legacy_routing,
    fallback_to_rag,
    load_lookup_registry,
    normalize_router_decision,
    validate_router_decision,
)


ROOT = Path(__file__).resolve().parents[1]


def _load(relative: str) -> list[dict]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _resources() -> dict:
    return {
        "scoring_tables": _load("data/processed/tables/scoring_tables.json"),
        "formula_rules": _load("data/processed/tables/formula_rules.json"),
        "entity_registry": [],
        "expansion_rules": [],
        "form_templates": _load("data/processed/forms/clean_form_templates.json"),
        "office_directory": _load(
            "data/processed/directories/student_office_profiles.json"
        ),
        "student_service_directory": _load(
            "data/processed/directories/student_service_directory.json"
        ),
        "student_faculty_profiles": _load(
            "data/processed/directories/student_faculty_profiles.json"
        ),
        "foreign_language_tables": _load(
            "data/processed/tables/foreign_language_equivalency_table.json"
        ),
        "structured_tables_registry": _load(
            "data/processed/tables/structured_tables_registry.json"
        ),
        "program_directory": _load("data/processed/directories/program_directory.json"),
    }


def _run_with_decision(query: str, decision: dict, *, cohort: str = "K50") -> dict:
    router = Mock()
    router.route.return_value = {
        "model_used": "qwen/qwen3.6-27b",
        "usage": {"prompt_tokens": 320, "completion_tokens": 48},
        **decision,
    }
    with (
        patch.dict(os.environ, {"STUDENT_RAG_DISABLE_AI_ROUTER": "0"}),
        patch(
            "src.retrieval.core.retrieval_pipeline.AIRouter.from_config",
            return_value=router,
        ),
        patch(
            "src.retrieval.core.retrieval_pipeline.retrieve_with_plan",
            return_value=[],
        ),
    ):
        return run_retrieval_pipeline(
            query=query,
            model=None,
            collection=None,
            cohort=cohort,
            **_resources(),
        )


def test_registry_covers_all_production_lookup_types() -> None:
    assert set(load_lookup_registry()["tools"]) == {
        "foreign_language",
        "study_duration",
        "scholarship_classification",
        "scoring",
        "student_service",
        "office",
        "faculty",
        "program",
        "form",
        "formula",
    }


def test_legacy_direct_lookup_payload_normalizes_to_structured() -> None:
    decision = normalize_router_decision(
        {
            "route": "deterministic",
            "execution_mode": "direct_lookup",
            "intent": "direct_value",
            "lookup_type": "scoring",
            "cohort": "K50",
        },
        query="K50 điểm B+ tương ứng hệ 4 bao nhiêu?",
    )

    assert decision["route"] == "structured"
    assert decision["execution_mode"] == "structured"


def test_structured_table_decision_sends_full_table_to_answer_llm() -> None:
    result = _run_with_decision(
        "K50 IELTS 5.5 tuong duong bac may?",
        {
            "route": "structured",
            "execution_mode": "structured",
            "intent": "direct_value",
            "lookup_type": "foreign_language",
            "cohort": "K50",
            "slots": {"certificate_or_language": "IELTS", "score_or_level": 5.5},
            "slot_spans": {"certificate_or_language": "IELTS", "score_or_level": "5.5"},
            "retrieval_query": "Quy doi IELTS 5.5 cho sinh vien K50",
            "target_chunk_types": ["structured_lookup"],
        },
    )

    assert result["strategy"] == "structured_table"
    assert result["needs_llm_answer"] is True
    assert result["structured_result"]["cohort"] == "K50"
    assert result["structured_result"]["source_lookup_type"] == "foreign_language"
    assert all(
        item["selection_method"] == "full_table"
        for item in result["structured_result"]["items"]
    )
    assert result["router_model"] == "qwen/qwen3.6-27b"
    assert result.get("deterministic_validated") is not True
    assert can_answer_deterministically(result) is False


def test_rag_form_candidate_cannot_bypass_generation() -> None:
    form_candidate = {
        "lookup_type": "form_template",
        "result": [{"form_name": "Unverified candidate"}],
        "content_type": "form_template",
        "source_pages": [1],
    }
    with patch(
        "src.retrieval.core.retrieval_pipeline.form_lookup",
        return_value=form_candidate,
    ):
        result = _run_with_decision(
            "Quy trinh nop bieu mau nay nhu the nao?",
            {
                "route": "rag",
                "intent": "mixed",
                "lookup_type": None,
                "cohort": "K50",
                "slots": {},
                "slot_spans": {},
                "retrieval_query": "Quy trinh nop bieu mau",
                "target_chunk_types": ["form", "regulation"],
            },
        )

    assert result["structured_result"] == form_candidate
    assert result.get("deterministic_validated") is not True
    assert can_answer_deterministically(result) is False


def test_mixed_mode_combines_full_table_with_regulation_path() -> None:
    result = _run_with_decision(
        "K50 điểm F là gì và có bắt buộc học lại không?",
        {
            "route": "rag",
            "execution_mode": "mixed",
            "intent": "regulation",
            "lookup_type": "scoring",
            "cohort": "K50",
            "slots": {"operation": "letter_to_grade_4"},
            "slot_spans": {},
            "retrieval_query": "K50 điểm F và quy định học lại",
            "target_chunk_types": ["regulation"],
        },
    )

    assert result["execution_mode"] == "mixed"
    assert result["needs_llm_answer"] is True
    assert result["structured_result"]["source_lookup_type"] == "scoring"
    assert all(
        item["selection_method"] == "full_table"
        for item in result["structured_result"]["items"]
    )


def test_office_lookup_requires_and_formats_requested_address() -> None:
    result = _run_with_decision(
        "Dia chi Ky tuc xa cho sinh vien K50 o dau?",
        {
            "route": "deterministic",
            "intent": "contact",
            "lookup_type": "office",
            "cohort": "K50",
            "slots": {"office": "Ky tuc xa", "requested_field": "office"},
            "slot_spans": {"office": "Ky tuc xa", "requested_field": "Dia chi"},
            "retrieval_query": "Dia chi Ky tuc xa K50",
            "target_chunk_types": ["office_directory"],
        },
    )

    structured = result["structured_result"]
    assert result["strategy"] == "office_lookup"
    assert structured["requested_field"] == "office"
    assert len(structured["result"]) == 1
    assert structured["result"][0]["office"]
    assert result["needs_llm_answer"] is True


@pytest.mark.parametrize(
    ("query", "lookup_type", "entity_slot", "entity_text", "requested_field", "unit"),
    [
        ("email pdt ở đâu?", "office", "office", "pdt", "email", "Phòng Đào tạo"),
        (
            "địa chỉ phòng y tế ở đâu?",
            "office",
            "office",
            "phòng y tế",
            "office",
            "Trạm Y tế",
        ),
        (
            "phòng cntt ở đâu?",
            "office",
            "office",
            "cntt",
            "office",
            "Phòng Công nghệ Thông tin",
        ),
        (
            "tui cần in bảng điểm thì đến phòng nào?",
            "student_service",
            "service",
            "in bảng điểm",
            "unit",
            "Phòng Khảo thí và Đảm bảo chất lượng",
        ),
    ],
)
def test_office_and_service_catalog_resolve_common_query_shapes(
    query: str,
    lookup_type: str,
    entity_slot: str,
    entity_text: str,
    requested_field: str,
    unit: str,
) -> None:
    result = _run_with_decision(
        query,
        {
            "route": "deterministic",
            "intent": "contact",
            "lookup_type": lookup_type,
            "cohort": "K50",
            "slots": {
                entity_slot: entity_text,
                "requested_field": requested_field,
            },
            "slot_spans": {
                entity_slot: entity_text,
                "requested_field": (
                    "ở đâu" if requested_field == "office" else requested_field
                ),
            },
            "retrieval_query": query,
            "target_chunk_types": ["office_directory"],
        },
    )

    assert result["needs_llm_answer"] is True
    assert result["structured_result"]["result"][0]["unit_name"] == unit
    assert result["structured_result"]["match_score"] >= 0.72


def test_tied_typed_candidates_request_clarification_instead_of_using_data_order() -> None:
    records = [
        {
            "record_id": "office-a",
            "unit_name": "Phong Alpha",
            "aliases": ["cong dich vu"],
            "cohort": "K50",
        },
        {
            "record_id": "office-b",
            "unit_name": "Phong Beta",
            "aliases": ["cong dich vu"],
            "cohort": "K50",
        },
    ]

    result = office_lookup(
        "Lien he cong dich vu",
        records,
        cohort="K50",
        candidate_text="cong dich vu",
        require_confident_match=True,
    )

    assert result is not None
    assert result["resolution_status"] == "ambiguous"
    assert result["clarification_options"] == ["Phong Alpha", "Phong Beta"]


def test_rejected_office_resolution_scopes_rag_to_contact_catalogs() -> None:
    decision = {
        "route": "deterministic",
        "intent": "contact",
        "lookup_type": "office",
        "slots": {"office": "don vi mo ho", "requested_field": "office"},
        "slot_spans": {"office": "don vi mo ho"},
        "retrieval_query": "dia chi don vi mo ho",
    }

    fallback = fallback_to_rag(decision, ["resolver_not_found"], query="don vi mo ho")
    routing = decision_to_legacy_routing(fallback)

    assert routing["target_chunk_types"] == ["office_directory"]
    assert routing["content_types"] == [
        "student_service_directory",
        "student_office_profile",
    ]


def test_exact_catalog_alias_can_repair_premature_router_clarification() -> None:
    hint = find_grounded_catalog_hint(
        "email pdt ở đâu?",
        [
            {
                "record_id": "office-training",
                "unit_name": "Phòng Đào tạo",
                "aliases": ["PĐT", "PDT"],
                "cohort": "K50",
            }
        ],
        [],
        cohort="K50",
    )

    assert hint == {
        "lookup_type": "office",
        "entity_text": "pdt",
        "unit_name": "Phòng Đào tạo",
        "match_type": "exact_catalog_span",
    }


def test_catalog_hint_does_not_choose_between_tied_entities() -> None:
    hint = find_grounded_catalog_hint(
        "email abc",
        [
            {"unit_name": "Phòng Alpha", "aliases": ["ABC"], "cohort": "K50"},
            {"unit_name": "Phòng Beta", "aliases": ["ABC"], "cohort": "K50"},
        ],
        [],
        cohort="K50",
    )

    assert hint is None


def test_office_resolver_can_use_semantic_similarity_after_lexical_ranking() -> None:
    class FakeEmbeddingModel:
        def encode(self, texts: list[str], **_: object) -> list[list[float]]:
            return [
                [1.0, 0.0]
                if "academic record" in text.lower() or "khảo thí" in text.lower()
                else [0.0, 1.0]
                for text in texts
            ]

    result = office_lookup(
        "Where can I print my academic record?",
        [
            {
                "record_id": "exam-office",
                "unit_name": "Phòng Khảo thí",
                "aliases": ["phúc khảo điểm"],
                "cohort": "K50",
            },
            {
                "record_id": "finance-office",
                "unit_name": "Phòng Kế hoạch - Tài chính",
                "aliases": ["học phí"],
                "cohort": "K50",
            },
        ],
        cohort="K50",
        candidate_text="print academic record",
        require_confident_match=True,
        model=FakeEmbeddingModel(),
    )

    assert result is not None
    assert result["result"][0]["unit_name"] == "Phòng Khảo thí"
    assert result["result"][0]["semantic_score"] == 1.0


def test_pipeline_repairs_clarify_route_with_exact_catalog_hint() -> None:
    router = Mock()
    router.route.side_effect = [
        {
            "route": "clarify",
            "intent": "open_question",
            "lookup_type": None,
            "slots": {},
            "slot_spans": {},
            "clarification_question": "PDT là đơn vị nào?",
        },
        {
            "route": "deterministic",
            "intent": "contact",
            "lookup_type": "office",
            "slots": {"office": "pdt", "requested_field": "email"},
            "slot_spans": {"office": "pdt", "requested_field": "email"},
            "retrieval_query": "email pdt",
        },
    ]
    with (
        patch.dict(os.environ, {"STUDENT_RAG_DISABLE_AI_ROUTER": "0"}),
        patch(
            "src.retrieval.core.retrieval_pipeline.AIRouter.from_config",
            return_value=router,
        ),
        patch(
            "src.retrieval.core.retrieval_pipeline.retrieve_with_plan",
            return_value=[],
        ),
    ):
        result = run_retrieval_pipeline(
            query="email pdt ở đâu?",
            model=None,
            collection=None,
            cohort="K50",
            **_resources(),
        )

    assert router.route.call_count == 2
    assert router.route.call_args_list[1].kwargs["routing_hint"]["entity_text"] == "pdt"
    assert result["strategy"] == "office_lookup"
    assert result["structured_result"]["result"][0]["unit_name"] == "Phòng Đào tạo"


def test_policy_route_skips_structured_resolver_and_uses_rag() -> None:
    result = _run_with_decision(
        "K50 chua co IELTS thi co duoc xet tot nghiep khong?",
        {
            "route": "rag",
            "intent": "policy",
            "lookup_type": None,
            "cohort": "K50",
            "slots": {},
            "slot_spans": {},
            "retrieval_query": "Dieu kien xet tot nghiep K50 khi chua dat chuan ngoai ngu",
            "target_chunk_types": ["regulation"],
        },
    )

    assert result["needs_llm_answer"] is True
    assert result.get("structured_result") is None
    assert result["retrieval_query"].startswith("Dieu kien xet tot nghiep")


def test_faculty_contact_uses_faculty_catalog_not_office_catalog() -> None:
    result = _run_with_decision(
        "email khoa CNTT ở đâu?",
        {
            "route": "deterministic",
            "intent": "contact",
            "lookup_type": "faculty",
            "cohort": "K50",
            "slots": {"faculty": "khoa CNTT", "requested_field": "email"},
            "slot_spans": {"faculty": "khoa CNTT", "requested_field": "email"},
            "retrieval_query": "email Khoa Công nghệ Thông tin K50",
            "target_chunk_types": ["faculty_program_directory"],
        },
    )

    record = result["structured_result"]["result"][0]
    assert result["strategy"] == "faculty_lookup"
    assert record["unit_name"] == "Khoa Công nghệ Thông tin"
    assert record["emails"] == ["khoacntt@hcmue.edu.vn"]
    assert result["structured_result"]["content_type"] == "student_faculty_profile"


@pytest.mark.parametrize(
    ("cohort", "expected"),
    [("K48-K49", False), ("K50", False), ("K51", True)],
)
def test_program_existence_is_resolved_within_selected_cohort(
    cohort: str, expected: bool
) -> None:
    result = _run_with_decision(
        f"{cohort} có ngành Công nghệ Giáo dục không?",
        {
            "route": "deterministic",
            "intent": "exists",
            "lookup_type": "program",
            "cohort": cohort,
            "slots": {
                "program_or_faculty": "Công nghệ Giáo dục",
                "requested_field": "exists",
            },
            "slot_spans": {"program_or_faculty": "Công nghệ Giáo dục"},
            "retrieval_query": f"ngành Công nghệ Giáo dục {cohort}",
            "target_chunk_types": ["program_directory"],
        },
        cohort=cohort,
    )

    structured = result["structured_result"]
    assert result["strategy"] == "program_lookup"
    assert structured["lookup_scope"] == "program_exists"
    assert structured["exists"] is expected
    assert structured["cohort"] == cohort
    if expected:
        assert structured["result"][0]["faculty_name"] == "Khoa Công nghệ Thông tin"
    else:
        assert structured["result"] == []


def test_student_loan_service_resolves_from_data_driven_alias() -> None:
    result = _run_with_decision(
        "Tui cần làm hồ sơ vay vốn thì đến đâu?",
        {
            "route": "deterministic",
            "intent": "contact",
            "lookup_type": "student_service",
            "cohort": "K50",
            "slots": {"service": "hồ sơ vay vốn", "requested_field": "unit"},
            "slot_spans": {"service": "hồ sơ vay vốn"},
            "retrieval_query": "đơn vị phụ trách hồ sơ vay vốn K50",
            "target_chunk_types": ["office_directory"],
        },
    )

    record = result["structured_result"]["result"][0]
    assert result["strategy"] == "student_service_lookup"
    assert record["unit_name"] == "Phòng Công tác chính trị và Học sinh, sinh viên"


def test_wifi_service_resolves_from_data_driven_alias() -> None:
    result = _run_with_decision(
        "Tui cần hỗ trợ wifi thì liên hệ phòng nào?",
        {
            "route": "deterministic",
            "intent": "contact",
            "lookup_type": "student_service",
            "cohort": "K50",
            "slots": {"service": "wifi", "requested_field": "unit"},
            "slot_spans": {"service": "wifi"},
            "retrieval_query": "đơn vị hỗ trợ wifi K50",
            "target_chunk_types": ["office_directory"],
        },
    )

    record = result["structured_result"]["result"][0]
    assert result["strategy"] == "student_service_lookup"
    assert record["unit_name"] == "Phòng Công nghệ Thông tin"


def test_faculty_program_list_accepts_colloquial_faculty_name() -> None:
    result = _run_with_decision(
        "Khoa Toán - Tin có những ngành nào?",
        {
            "route": "deterministic",
            "intent": "list_items",
            "lookup_type": "program",
            "cohort": "K51",
            "slots": {
                "program_or_faculty": "Khoa Toán - Tin",
                "requested_field": "programs",
                "scope": "faculty",
            },
            "slot_spans": {"program_or_faculty": "Khoa Toán - Tin"},
            "retrieval_query": "ngành thuộc Khoa Toán - Tin K51",
            "target_chunk_types": ["program_directory"],
        },
        cohort="K51",
    )

    programs = {
        record["program_name"] for record in result["structured_result"]["result"]
    }
    assert programs == {
        "Sư phạm Toán học (Tiếng Việt và Song ngữ Việt – Anh)",
        "Toán ứng dụng",
    }


def test_rejected_faculty_resolution_scopes_rag_to_faculty_catalogs() -> None:
    decision = {
        "route": "deterministic",
        "intent": "contact",
        "lookup_type": "faculty",
        "slots": {"faculty": "khoa mơ hồ", "requested_field": "office"},
        "slot_spans": {"faculty": "khoa mơ hồ"},
        "retrieval_query": "địa chỉ khoa mơ hồ",
    }

    fallback = fallback_to_rag(decision, ["resolver_not_found"], query="khoa mơ hồ")
    routing = decision_to_legacy_routing(fallback)

    assert routing["target_chunk_types"] == ["faculty_program_directory"]
    assert routing["content_types"] == [
        "student_faculty_profile",
        "faculty_program_directory",
    ]


def test_ungrounded_required_slot_forces_rag() -> None:
    result = _run_with_decision(
        "K50 IELTS 5.5 tuong duong bac may?",
        {
            "route": "deterministic",
            "intent": "direct_value",
            "lookup_type": "foreign_language",
            "cohort": "K50",
            "slots": {"certificate_or_language": "IELTS", "score_or_level": 6.5},
            "slot_spans": {"certificate_or_language": "IELTS", "score_or_level": "6.5"},
            "retrieval_query": "Quy doi IELTS 5.5 cho sinh vien K50",
            "target_chunk_types": ["structured_lookup"],
        },
    )

    assert result["needs_llm_answer"] is True
    assert "ungrounded_slot:score_or_level" in result["router_validation_errors"]


def test_decision_validator_rejects_cohort_conflict() -> None:
    decision = normalize_router_decision(
        {
            "route": "rag",
            "intent": "policy",
            "cohort": "K51",
            "retrieval_query": "quy dinh hoc tap K51",
        },
        query="Quy dinh hoc tap K50",
        selected_cohort="K50",
    )
    assert "cohort_conflict" in validate_router_decision(
        decision,
        query="Quy dinh hoc tap K50",
        selected_cohort="K50",
    )


def test_decision_validator_rejects_unknown_enum_and_removed_lookup() -> None:
    scoring = normalize_router_decision(
        {
            "route": "deterministic",
            "intent": "direct_value",
            "lookup_type": "scoring",
            "slots": {"operation": "invented_scale", "score_or_grade": 8.5},
            "slot_spans": {"score_or_grade": "8.5"},
        },
        query="Diem 8.5 doi sang thang tu che la gi?",
    )
    assert "invalid_slot_value:operation" in validate_router_decision(
        scoring,
        query="Diem 8.5 doi sang thang tu che la gi?",
    )

    removed_lookup = normalize_router_decision(
        {
            "route": "deterministic",
            "intent": "calculation",
            "lookup_type": "calculator",
            "slots": {
                "calculation_type": "scholarship_score",
                "operands": {"academic_score_4": 3.2},
            },
            "slot_spans": {"operands": {"academic_score_4": "3.2"}},
        },
        query="GPA 3.2 thi diem hoc bong la bao nhieu?",
    )
    assert "unknown_lookup_type" in validate_router_decision(
        removed_lookup,
        query="GPA 3.2 thi diem hoc bong la bao nhieu?",
    )


def test_structured_lookup_without_cohort_requires_clarification() -> None:
    decision = normalize_router_decision(
        {
            "route": "structured",
            "execution_mode": "structured",
            "intent": "direct_value",
            "lookup_type": "foreign_language",
            "slots": {"certificate_or_language": "IELTS", "score_or_level": 5.5},
            "slot_spans": {"certificate_or_language": "IELTS", "score_or_level": "5.5"},
        },
        query="IELTS 5.5 tương đương bậc mấy?",
    )

    assert "missing_cohort" in validate_router_decision(
        decision,
        query="IELTS 5.5 tương đương bậc mấy?",
    )


def test_structured_mode_accepts_table_lookup_without_direct_value_slots() -> None:
    decision = normalize_router_decision(
        {
            "route": "structured",
            "execution_mode": "structured",
            "intent": "compare",
            "lookup_type": "scoring",
            "slots": {"operation": "academic_classification"},
            "retrieval_query": "so sánh xếp loại học lực K50 K51",
        },
        query="So sánh bảng xếp loại học lực K50 và K51",
    )

    assert not validate_router_decision(
        decision,
        query="So sánh bảng xếp loại học lực K50 và K51",
    )


def test_structured_table_validator_ignores_empty_optional_slots() -> None:
    decision = normalize_router_decision(
        {
            "route": "structured",
            "execution_mode": "structured",
            "intent": "direct_value",
            "lookup_type": "study_duration",
            "cohort": "K48-K49",
            "slots": {"training_mode": "chinh_quy", "program_type": None},
            "slot_spans": {"training_mode": "he chinh quy"},
            "retrieval_query": "Thoi gian hoc toi da he chinh quy K48-K49",
        },
        query="Theo bang danh cho K48-K49, he chinh quy hoc toi da may nam?",
    )

    assert not validate_router_decision(
        decision,
        query="Theo bang danh cho K48-K49, he chinh quy hoc toi da may nam?",
    )


def test_scoring_pass_fail_lookup_requires_operation_but_not_a_score() -> None:
    decision = normalize_router_decision(
        {
            "route": "structured",
            "execution_mode": "structured",
            "intent": "direct_value",
            "lookup_type": "scoring",
            "cohort": "K51",
            "slots": {"operation": "pass_fail_ungraded"},
            "retrieval_query": "học phần đạt không phân mức K51",
        },
        query="Học phần chỉ đánh giá đạt chưa đạt của K51 cần mấy điểm?",
    )

    assert not validate_router_decision(
        decision,
        query="Học phần chỉ đánh giá đạt chưa đạt của K51 cần mấy điểm?",
    )


def test_study_duration_sends_full_selected_table_to_answer_llm() -> None:
    result = _run_with_decision(
        "K50 he chinh quy cap bang thu nhat hoc toi da bao lau?",
        {
            "route": "deterministic",
            "intent": "direct_value",
            "lookup_type": "study_duration",
            "cohort": "K50",
            "slots": {
                "training_mode": "chinh_quy",
                "program_type": "first_degree",
            },
            "slot_spans": {
                "training_mode": "chinh quy",
                "program_type": "cap bang thu nhat",
            },
            "retrieval_query": "Thoi gian hoc toi da he chinh quy cap bang thu nhat K50",
        },
    )

    tables = result["structured_result"]["items"]
    assert result["strategy"] == "structured_table"
    assert len(tables) == 1
    assert all(table["selection_method"] == "full_table" for table in tables)
    assert "chính quy" in tables[0]["applicability"]
    assert any(
        row.get("Thời gian học tập tối đa") == "8 năm học"
        for table in tables
        for row in table["rows"]
    )
    assert result["needs_llm_answer"] is True
    assert "Structured table context" in result["context_for_llm"]
    assert "8 năm học" in result["context_for_llm"]


def test_typed_formula_uses_router_slots_without_query_keyword_parsing() -> None:
    formula = _run_with_decision(
        "Cho minh cong thuc diem hoc bong K50",
        {
            "route": "deterministic",
            "intent": "formula",
            "lookup_type": "formula",
            "cohort": "K50",
            "slots": {"formula_type": "scholarship_score"},
            "slot_spans": {},
            "retrieval_query": "Cong thuc tinh diem hoc bong K50",
        },
    )
    assert formula["strategy"] == "formula_lookup"
    assert formula["structured_result"]["rule_id"] == "scholarship_score"
    assert formula["needs_llm_answer"] is True


def test_key_pool_balances_keys_and_does_not_persist_secrets(tmp_path: Path) -> None:
    state_path = tmp_path / "router-state.json"
    pool = GroqRouterKeyPool(
        ["secret-key-one", "secret-key-two"],
        model_name="qwen/qwen3.6-27b",
        config={
            "rpm_limit_per_key": 1,
            "rpd_limit_per_key": 10,
            "tpm_limit_per_key": 1000,
            "tpd_limit_per_key": 10000,
            "state_path": str(state_path),
            "wait_when_limited": False,
        },
    )
    _, first_id, first_index = pool.acquire_key(100)
    _, second_id, second_index = pool.acquire_key(100)

    assert first_index != second_index
    assert first_id != second_id
    state_text = state_path.read_text(encoding="utf-8")
    assert "secret-key-one" not in state_text
    assert "secret-key-two" not in state_text


def test_rate_limit_failover_can_use_every_available_key(tmp_path: Path) -> None:
    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps(
                        {
                            "route": "rag",
                            "intent": "policy",
                            "lookup_type": None,
                            "cohort": "K50",
                            "slots": {},
                            "slot_spans": {},
                            "retrieval_query": "quy dinh hoc tap K50",
                            "target_chunk_types": ["regulation"],
                        }
                    )
                )
            )
        ],
        usage=SimpleNamespace(
            prompt_tokens=100,
            completion_tokens=40,
            total_tokens=140,
        ),
    )
    clients = []
    for side_effect in (RuntimeError("429 rate limit"), RuntimeError("429 quota"), response):
        client = Mock()
        client.chat.completions.create.side_effect = (
            [side_effect] if isinstance(side_effect, Exception) else None
        )
        if not isinstance(side_effect, Exception):
            client.chat.completions.create.return_value = side_effect
        clients.append(client)

    with (
        patch.dict(
            os.environ,
            {"GROQ_ROUTER_API_KEYS": "router-key-1,router-key-2,router-key-3"},
        ),
        patch("src.retrieval.core.ai_router.Groq", side_effect=clients),
    ):
        router = AIRouter(
            max_retries=0,
            cache_enabled=False,
            key_pool_config={
                "state_path": str(tmp_path / "state.json"),
                "wait_when_limited": False,
            },
        )
        decision = router.route("Quy dinh hoc tap K50", cohort="K50")

    assert decision["route"] == "rag"
    assert decision["attempts"] == 3
