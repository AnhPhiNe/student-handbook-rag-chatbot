from __future__ import annotations

from src.generation.answer_pipeline import AnswerPipeline
from src.retrieval.core.query_context import (
    ReferencedEvidenceSpan,
    select_effective_query,
    validate_follow_up_query,
    validate_normalized_query,
)
from src.retrieval.core.slang_normalizer import SlangNormalizer


def _decision(**overrides):
    decision = {
        "context_mode": "standalone",
        "context_confidence": "high",
        "normalized_query": "K50 thời gian học tối đa là bao lâu?",
        "normalization_confidence": "high",
        "corrections": [],
        "standalone_query": None,
        "referenced_turn_ids": [],
        "referenced_evidence": [],
    }
    decision.update(overrides)
    return decision


def test_accepts_accent_only_normalization() -> None:
    result = select_effective_query(
        "K50 thoi gian hoc toi da la bao lau?",
        _decision(
            corrections=[
                {
                    "original_span": "K50 thoi gian hoc toi da la bao lau?",
                    "normalized_span": "K50 thời gian học tối đa là bao lâu?",
                }
            ]
        ),
    )

    assert result.effective_query == "K50 thời gian học tối đa là bao lâu?"
    assert result.source == "validated_normalization"
    assert result.validation_errors == ()


def test_accepts_declared_typo_correction() -> None:
    raw_query = "K50 hoc bong khuyen khich hc tap"
    normalized_query = "K50 hoc bong khuyen khich hoc tap"

    errors = validate_normalized_query(
        raw_query,
        normalized_query,
        confidence="high",
        corrections=[
            {
                "original_span": "hc",
                    "normalized_span": "hoc",
            }
        ],
    )

    assert errors == []


def test_accepts_single_character_typo_substitution() -> None:
    errors = validate_normalized_query(
        "K50 hox phi bao nhieu?",
        "K50 hoc phi bao nhieu?",
        confidence="high",
        corrections=[
            {
                "original_span": "hox",
                "normalized_span": "hoc",
            }
        ],
    )

    assert errors == []


def test_rejects_declared_valid_word_substitution() -> None:
    raw_query = "học lại hay học cải thiện mới bị hạ bằng"
    normalized_query = "học lại hay học cải thiện mới bị hủy bằng"

    result = select_effective_query(
        raw_query,
        _decision(
            normalized_query=normalized_query,
            corrections=[
                {
                    "original_span": "hạ bằng",
                    "normalized_span": "hủy bằng",
                }
            ],
        ),
    )

    assert result.effective_query == raw_query
    assert result.source == "raw_query_fallback"
    assert result.validation_errors == (
        "normalization_correction_substitutes_content",
    )


def test_rejects_undeclared_semantic_change() -> None:
    errors = validate_normalized_query(
        "K50 hình thức đào tạo được quy định sao?",
        "K50 địa chỉ Phòng Đào tạo ở đâu?",
        confidence="high",
        corrections=[],
    )

    assert "normalization_missing_corrections" in errors


def test_rejects_changed_cohort() -> None:
    errors = validate_normalized_query(
        "K50 chuẩn đầu ra ngoại ngữ",
        "K51 chuẩn đầu ra ngoại ngữ",
        confidence="high",
    )

    assert errors == ["normalization_changed_cohort"]


def test_rejects_changed_number() -> None:
    errors = validate_normalized_query(
        "Điểm rèn luyện 80 có được loại tốt không?",
        "Điểm rèn luyện 90 có được loại tốt không?",
        confidence="high",
    )

    assert errors == ["normalization_changed_number"]


def test_builds_valid_follow_up_from_referenced_history() -> None:
    history = [
        {
            "role": "user",
            "content": "K50 thời gian học tối đa của hệ chính quy là bao lâu?",
        },
        {
            "role": "assistant",
            "content": "K50 có thời gian học tối đa theo quy định của sổ tay.",
        },
    ]
    decision = _decision(
        context_mode="follow_up",
        normalized_query="Còn K51 thì sao?",
        standalone_query="K51 thời gian học tối đa của hệ chính quy là bao lâu?",
        referenced_turns=[0],
        referenced_evidence=[
            {
                "turn_id": 0,
                "evidence_span": "thời gian học tối đa của hệ chính quy là bao lâu?",
            }
        ],
    )

    result = select_effective_query(
        "Còn K51 thì sao?",
        decision,
        chat_history=history,
    )

    assert result.effective_query == decision["standalone_query"]
    assert result.source == "grounded_follow_up"
    assert not result.needs_clarification


def test_invalid_history_reference_requires_clarification() -> None:
    result = select_effective_query(
        "Còn K51 thì sao?",
        _decision(
            context_mode="follow_up",
            standalone_query="K51 thời gian học tối đa là bao lâu?",
            referenced_turns=[4],
        ),
        chat_history=[{"role": "user", "content": "K50 thời gian học tối đa?"}],
    )

    assert result.needs_clarification
    assert "follow_up_invalid_referenced_turn" in result.validation_errors


def test_standalone_query_does_not_inherit_old_history() -> None:
    result = select_effective_query(
        "Email Phòng Đào tạo là gì?",
        _decision(
            normalized_query="Email Phòng Đào tạo là gì?",
            context_mode="standalone",
        ),
        chat_history=[
            {"role": "user", "content": "K50 có được bảo lưu không?"},
            {"role": "assistant", "content": "Quy định bảo lưu của K50..."},
        ],
    )

    assert result.effective_query == "Email Phòng Đào tạo là gì?"
    assert result.source == "validated_normalization"


def test_no_history_follow_up_label_becomes_standalone_when_plan_is_grounded() -> None:
    query = "K51 quy định học lại và cảnh báo học vụ ra sao?"
    result = select_effective_query(
        query,
        _decision(
            context_mode="follow_up",
            normalized_query=query,
            standalone_query=query,
            lookup_requests=[
                {
                    "request_kind": "rag",
                    "lookup_type": None,
                    "intent": "policy",
                    "query_span": "quy định học lại",
                    "slots": {},
                    "slot_spans": {},
                    "cohort_refs": ["K51"],
                },
                {
                    "request_kind": "rag",
                    "lookup_type": None,
                    "intent": "policy",
                    "query_span": "cảnh báo học vụ",
                    "slots": {},
                    "slot_spans": {},
                    "cohort_refs": ["K51"],
                },
            ],
        ),
        chat_history=[],
        selected_cohort="K51",
    )

    assert result.context_mode == "standalone"
    assert result.effective_query == query
    assert not result.needs_clarification


def test_no_history_unresolved_follow_up_still_clarifies() -> None:
    query = "Nội dung đó có ngoại lệ nào?"
    result = select_effective_query(
        query,
        _decision(
            context_mode="follow_up",
            normalized_query=query,
            standalone_query="K51 quy định học lại có ngoại lệ nào?",
            lookup_requests=[
                {
                    "request_kind": "rag",
                    "lookup_type": None,
                    "intent": "consequence_or_exception",
                    "query_span": "quy định học lại",
                    "slots": {},
                    "slot_spans": {},
                    "cohort_refs": ["K51"],
                }
            ],
        ),
        chat_history=[],
        selected_cohort="K51",
    )

    assert result.context_mode == "follow_up"
    assert result.needs_clarification
    assert "follow_up_missing_referenced_history" in result.validation_errors


def test_ambiguous_context_requires_clarification() -> None:
    result = select_effective_query(
        "Còn trường hợp đó thì sao?",
        _decision(
            context_mode="ambiguous",
            context_confidence="low",
            normalized_query="Còn trường hợp đó thì sao?",
        ),
    )

    assert result.needs_clarification
    assert result.source == "clarification"


def test_query_handling_ab_modes() -> None:
    decision = _decision(
        normalized_query="K50 thời gian học tối đa là bao lâu?",
        corrections=[
            {
                "original_span": "K50 thoi gian hoc toi da la bao lau?",
                "normalized_span": "K50 thời gian học tối đa là bao lâu?",
            }
        ],
        retrieval_query="K50 thời lượng chương trình và giới hạn đào tạo",
    )

    raw = select_effective_query(
        "K50 thoi gian hoc toi da la bao lau?",
        decision,
        mode="raw",
    )
    router_generated = select_effective_query(
        "K50 thoi gian hoc toi da la bao lau?",
        decision,
        mode="router_generated",
    )
    context_only = select_effective_query(
        "K50 thoi gian hoc toi da la bao lau?",
        decision,
        mode="context_only",
    )

    assert raw.source == "raw_query"
    assert router_generated.source == "validated_normalization"
    assert router_generated.effective_query == decision["normalized_query"]
    assert context_only.source == "validated_normalization"
    assert context_only.effective_query == decision["normalized_query"]


def test_follow_up_validator_rejects_new_ungrounded_topic() -> None:
    errors = validate_follow_up_query(
        "Còn K51 thì sao?",
        "K51 chuyển đổi tín chỉ và công nhận kết quả học tập thế nào?",
        referenced_turns=(0,),
        referenced_evidence=(
            ReferencedEvidenceSpan(
                turn_id=0,
                evidence_span="thời gian học tối đa của hệ chính quy là bao lâu?",
            ),
        ),
        chat_history=[
            {
                "role": "user",
                "content": "K50 thời gian học tối đa của hệ chính quy là bao lâu?",
            }
        ],
        confidence="high",
        selected_cohort=None,
    )

    assert "follow_up_added_ungrounded_content" in errors


def test_follow_up_may_drop_presentation_words_without_thresholds() -> None:
    errors = validate_follow_up_query(
        "Nội dung đó có ngoại lệ nào? Xin trích đúng nguồn tương ứng.",
        "K51 quy định bảo lưu có ngoại lệ nào?",
        referenced_turns=(0,),
        referenced_evidence=(
            ReferencedEvidenceSpan(turn_id=0, evidence_span="K51"),
            ReferencedEvidenceSpan(turn_id=0, evidence_span="quy định bảo lưu"),
        ),
        chat_history=[
            {
                "role": "user",
                "content": "Tôi là sinh viên K51, hãy tra quy định bảo lưu.",
            }
        ],
        confidence="high",
        selected_cohort=None,
    )

    assert errors == []


def test_follow_up_validator_rejects_forged_evidence_span() -> None:
    errors = validate_follow_up_query(
        "Còn K51 thì sao?",
        "K51 thời gian học tối đa là bao lâu?",
        referenced_turns=(0,),
        referenced_evidence=(
            ReferencedEvidenceSpan(
                turn_id=0,
                evidence_span="thời gian học tối đa là bao lâu?",
            ),
        ),
        chat_history=[
            {"role": "user", "content": "K50 thủ tục bảo lưu thế nào?"}
        ],
        confidence="high",
        selected_cohort=None,
    )

    assert errors == ["follow_up_evidence_span_not_grounded"]


def test_answer_output_propagates_query_handling() -> None:
    pipeline = AnswerPipeline.__new__(AnswerPipeline)
    handling = {
        "raw_query": "con K51 thi sao?",
        "effective_query": "K51 thời gian học tối đa là bao lâu?",
        "source": "grounded_follow_up",
    }
    output = pipeline._build_output(
        query="con K51 thi sao?",
        retrieval_result={
            "effective_query": handling["effective_query"],
            "query_handling": handling,
            "router_decision": {"query_handling": handling},
        },
        final_answer="test",
        context_used="",
        selected_citations=[],
        status="answered",
        error_type=None,
        error_message=None,
        llm_called=False,
        used_cache=False,
    )

    assert output["effective_query"] == handling["effective_query"]
    assert output["query_handling"] == handling
    assert output["router_decision"]["query_handling"] == handling


def _minimal_pipeline() -> AnswerPipeline:
    pipeline = AnswerPipeline.__new__(AnswerPipeline)
    pipeline.config = {
        "retrieval": {
            "default_top_k": 5,
            "candidate_multiplier": 5,
            "min_candidates": 25,
        },
        "embedding": {"normalize_embeddings": True},
    }
    pipeline.model = object()
    pipeline.collection = object()
    pipeline.scoring_tables = []
    pipeline.formula_rules = []
    pipeline.entity_registry = []
    pipeline.expansion_rules = {}
    pipeline.student_office_profiles = []
    pipeline.student_service_directory = []
    pipeline.student_faculty_profiles = []
    pipeline.foreign_language_tables = []
    pipeline.structured_tables_registry = []
    pipeline.program_directory = []

    class DummySlangNormalizer:
        def replace_for_router(self, value: str) -> str:
            return f"router::{value}"

        def normalize_for_retrieval(self, value: str) -> str:
            return f"slang::{value}"

        def normalize(self, value: str) -> str:
            return self.normalize_for_retrieval(value)

    pipeline.slang_normalizer = DummySlangNormalizer()
    return pipeline


def test_answer_pipeline_uses_validated_query_before_slang(monkeypatch) -> None:
    pipeline = _minimal_pipeline()
    routed = {}

    class DummyRouter:
        def route(self, query, chat_history=None):
            routed["query"] = query
            return _decision(
                route="rag",
                execution_mode="regulation",
                intent="open_question",
                lookup_type=None,
                normalized_query=query.removeprefix("router::"),
            )

    captured = {}

    def fake_hybrid_pipeline(**kwargs):
        captured.update(kwargs)
        return {
            "query": kwargs["query"],
            "retrieval_query": kwargs["retrieval_query"],
            "retrieved_items": [],
            "related_items": [],
            "citations": [],
            "needs_llm_answer": True,
        }

    pipeline.router = DummyRouter()
    monkeypatch.setattr(
        "src.generation.answer_pipeline.run_hybrid_retrieval_pipeline",
        fake_hybrid_pipeline,
    )

    result = pipeline._run_retrieval("K50 rot mon thi sao?", cohort="K50")

    assert captured["query"] == "K50 rot mon thi sao?"
    assert captured["retrieval_query"] == "slang::K50 rot mon thi sao?"
    assert routed["query"] == "K50 rot mon thi sao?"
    assert result["router_decision"]["router_input_query"] == "K50 rot mon thi sao?"
    assert result["effective_query"] == "K50 rot mon thi sao?"
    assert "retrieval_query" not in result["router_decision"]
    assert result["query_handling"]["source"] == "validated_normalization"


def test_answer_pipeline_passes_exact_catalog_hint_to_planner(monkeypatch) -> None:
    pipeline = _minimal_pipeline()
    pipeline.student_service_directory = [
        {
            "record_id": "student-service-pdt",
            "unit_name": "Phòng Đào tạo",
            "aliases": ["PĐT"],
        }
    ]
    routed = {}

    class DummyRouter:
        def route(self, query, **kwargs):
            routed["query"] = query
            routed.update(kwargs)
            return _decision(
                route="rag",
                execution_mode="regulation",
                intent="open_question",
                lookup_type=None,
                normalized_query=query,
                cohort="K51",
                cohorts=["K51"],
                is_multi_cohort=False,
            )

    def fake_hybrid_pipeline(**kwargs):
        return {
            "query": kwargs["query"],
            "retrieval_query": kwargs["retrieval_query"],
            "retrieved_items": [],
            "related_items": [],
            "citations": [],
            "needs_llm_answer": True,
        }

    pipeline.router = DummyRouter()
    monkeypatch.setattr(
        "src.generation.answer_pipeline.run_hybrid_retrieval_pipeline",
        fake_hybrid_pipeline,
    )

    result = pipeline._run_retrieval("Email PĐT là gì?", cohort="K51")

    assert routed["query"] == "Email PĐT là gì?"
    assert routed["routing_hint"] == {
        "lookup_type": "student_service",
        "entity_text": "PĐT",
        "unit_name": "Phòng Đào tạo",
        "match_type": "exact_catalog_span",
    }
    assert result["router_decision"]["routing_hint"] == routed["routing_hint"]


def test_answer_pipeline_uses_slang_normalization_for_structured_lookup(
    monkeypatch,
) -> None:
    pipeline = _minimal_pipeline()
    routed = {}

    class DummyRouter:
        def route(self, query, chat_history=None):
            routed["query"] = query
            return _decision(
                route="structured",
                execution_mode="structured",
                intent="program_lookup",
                lookup_type="program",
                normalized_query=query,
            )

    class StructuredResolution:
        result = {"items": [{"program_name": "Công nghệ Thông tin"}]}
        result_kind = "answer"
        strategy = "structured"

    captured = {}

    def fake_resolver(decision, **kwargs):
        captured.update(kwargs)
        return StructuredResolution()

    pipeline.router = DummyRouter()
    monkeypatch.setattr(
        "src.retrieval.core.structured_dispatcher.resolve_structured_decision",
        fake_resolver,
    )

    result = pipeline._run_retrieval("cntt có ngành nào?", cohort="K51")

    assert routed["query"] == "cntt có ngành nào?"
    assert captured["query"] == "slang::cntt có ngành nào?"
    assert result["retrieval_query"] == "slang::cntt có ngành nào?"
    assert result["strategy"] == "structured"


def test_answer_pipeline_appends_source_backed_citation_for_mixed_lookup(
    monkeypatch,
) -> None:
    pipeline = _minimal_pipeline()

    class DummyRouter:
        def route(self, query, chat_history=None):
            return _decision(
                route="mixed",
                execution_mode="mixed",
                intent="mixed_query",
                lookup_type="academic_classification",
                normalized_query=query,
            )

    class StructuredResolution:
        result = {
            "lookup_type": "academic_classification",
            "result": {"label": "Giỏi", "range": "3.20-3.59"},
            "table_name": "Xếp loại học lực",
            "source_pages": [42],
            "source_parent_id": "K51_Dieu18",
            "document_id": "so_tay_sinh_vien_khoa_51",
            "cohort": "K51",
        }

    def fake_hybrid_pipeline(**kwargs):
        return {
            "query": kwargs["query"],
            "retrieval_query": kwargs["retrieval_query"],
            "intent": "mixed_query",
            "strategy": "mixed",
            "structured_result": None,
            "retrieved_items": [],
            "citations": [],
            "out_of_domain": False,
        }

    pipeline.router = DummyRouter()
    monkeypatch.setattr(
        "src.generation.answer_pipeline.run_hybrid_retrieval_pipeline",
        fake_hybrid_pipeline,
    )
    monkeypatch.setattr(
        "src.retrieval.core.structured_dispatcher.resolve_structured_decision",
        lambda *args, **kwargs: StructuredResolution(),
    )

    result = pipeline._run_retrieval("GPA 3.4 được loại gì?", cohort="K51")

    assert result["structured_result"] == StructuredResolution.result
    assert result["citations"][0]["parent_section_id"] == "K51_Dieu18"
    assert result["citations"][0]["document_id"] == "so_tay_sinh_vien_khoa_51"
    assert result["citations"][0]["cohort"] == "K51"


def test_answer_pipeline_replaces_acronym_before_program_routing() -> None:
    pipeline = _minimal_pipeline()
    pipeline.program_directory = [
        {
            "program_name": "Công nghệ Thông tin",
            "faculty_name": "Khoa Công nghệ Thông tin",
            "cohort": "K51",
            "document_id": "so_tay_sinh_vien_khoa_51",
            "source_section": "program_directory",
        }
    ]
    pipeline.slang_normalizer = SlangNormalizer(
        program_directory=pipeline.program_directory,
    )
    routed = {}

    class DummyRouter:
        def route(self, query, chat_history=None):
            routed["query"] = query
            return _decision(
                route="structured",
                execution_mode="structured",
                intent="direct_value",
                lookup_type="program",
                normalized_query=query,
                slots={
                    "program_or_faculty": "Công nghệ Thông tin",
                    "requested_field": "faculty",
                    "scope": "school",
                },
            )

    pipeline.router = DummyRouter()
    result = pipeline._run_retrieval("ngành cntt ở khoa nào", cohort="K51")

    assert routed["query"] == "ngành cntt ở khoa nào"
    assert result["raw_query"] == "ngành cntt ở khoa nào"
    assert result["retrieval_query"] == "ngành công nghệ thông tin ở khoa nào"
    assert result["citations"][0]["chunk_type"] == "program_directory"
    assert result["citations"][0]["document_id"] == "so_tay_sinh_vien_khoa_51"
    assert result["citations"][0]["source_section"] == "program_directory"
    assert result["citations"][0]["cohort"] == "K51"
    assert result["structured_result"]["result"] == [
        {
            "program_name": "Công nghệ Thông tin",
            "faculty_name": "Khoa Công nghệ Thông tin",
            "source_pages": [],
            "source_section": "program_directory",
            "cohort": "K51",
            "document_id": "so_tay_sinh_vien_khoa_51",
            "summary": None,
            "raw_text": None,
        }
    ]


def test_answer_pipeline_canonicalizes_out_of_domain_metadata() -> None:
    pipeline = _minimal_pipeline()

    class DummyRouter:
        def route(self, query, chat_history=None):
            return _decision(
                route="out_of_domain",
                execution_mode="regulation",
                intent="open_question",
                lookup_type=None,
                normalized_query=query,
            )

    pipeline.router = DummyRouter()
    result = pipeline._run_retrieval("Ty gia do la hom nay the nao?")

    assert result["out_of_domain"] is True
    assert result["intent"] == "out_of_domain"
    assert result["strategy"] == "none"
    assert result["needs_llm_answer"] is False
    assert result["router_decision"]["intent"] == "out_of_domain"


def test_answer_pipeline_pure_retrieval_bypasses_router(monkeypatch) -> None:
    pipeline = _minimal_pipeline()

    class FailingRouter:
        def route(self, query, chat_history=None):
            raise AssertionError("router should not be called in pure retrieval eval")

    captured = {}

    def fake_hybrid_pipeline(**kwargs):
        captured.update(kwargs)
        return {
            "query": kwargs["query"],
            "retrieval_query": kwargs["retrieval_query"],
            "retrieved_items": [],
            "related_items": [],
            "citations": [],
            "needs_llm_answer": True,
        }

    pipeline.router = FailingRouter()
    monkeypatch.setenv("STUDENT_RAG_EVAL_FORCE_REGULATION_RAG", "1")
    monkeypatch.setattr(
        "src.generation.answer_pipeline.run_hybrid_retrieval_pipeline",
        fake_hybrid_pipeline,
    )

    result = pipeline._run_retrieval("K50 bao luu duoc bao lau?", cohort="K50")

    assert captured["query"] == "K50 bao luu duoc bao lau?"
    assert captured["retrieval_query"] == "slang::K50 bao luu duoc bao lau?"
    assert result["router_decision"]["eval_force_regulation"] is True
    assert result["query_handling"]["source"] == "eval_force_regulation"
