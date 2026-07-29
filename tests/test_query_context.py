from __future__ import annotations

from src.generation.answer_pipeline import AnswerPipeline
from src.retrieval.core.query_context import (
    select_effective_query,
    validate_follow_up_query,
    validate_normalized_query,
)


def _decision(**overrides):
    decision = {
        "context_mode": "standalone",
        "context_confidence": "high",
        "normalized_query": "K50 thời gian học tối đa là bao lâu?",
        "normalization_confidence": "high",
        "corrections": [],
        "standalone_query": None,
        "referenced_turns": [],
        "retrieval_query": "router candidate",
    }
    decision.update(overrides)
    return decision


def test_accepts_accent_only_normalization() -> None:
    result = select_effective_query(
        "K50 thoi gian hoc toi da la bao lau?",
        _decision(),
    )

    assert result.effective_query == "K50 thời gian học tối đa là bao lâu?"
    assert result.source == "validated_normalization"
    assert result.validation_errors == ()


def test_accepts_declared_typo_correction() -> None:
    raw_query = "K50 hoc bong khuyen khich hc tap"
    normalized_query = "K50 học bổng khuyến khích học tập"

    errors = validate_normalized_query(
        raw_query,
        normalized_query,
        confidence="high",
        corrections=[
            {
                "original_span": "hc",
                "normalized_span": "học",
            }
        ],
    )

    assert errors == []


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
    assert router_generated.source == "router_retrieval_query"
    assert context_only.source == "validated_normalization"


def test_follow_up_validator_rejects_new_ungrounded_topic() -> None:
    errors = validate_follow_up_query(
        "Còn K51 thì sao?",
        "K51 chuyển đổi tín chỉ và công nhận kết quả học tập thế nào?",
        referenced_turns=(0,),
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
    assert output["query_rewrite"] is None


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
        def normalize(self, value: str) -> str:
            return f"slang::{value}"

    pipeline.slang_normalizer = DummySlangNormalizer()
    return pipeline


def test_answer_pipeline_uses_validated_query_before_slang(monkeypatch) -> None:
    pipeline = _minimal_pipeline()

    class DummyRouter:
        def route(self, query, chat_history=None):
            return _decision(
                route="rag",
                execution_mode="regulation",
                intent="open_question",
                lookup_type=None,
                normalized_query=query,
                retrieval_query="K50 dia chi phong dao tao",
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
    assert result["effective_query"] == "K50 rot mon thi sao?"
    assert result["router_decision"]["retrieval_query"] == "K50 dia chi phong dao tao"
    assert result["query_handling"]["source"] == "validated_normalization"


def test_answer_pipeline_uses_slang_normalization_for_structured_lookup(
    monkeypatch,
) -> None:
    pipeline = _minimal_pipeline()

    class DummyRouter:
        def route(self, query, chat_history=None):
            return _decision(
                route="structured",
                execution_mode="structured",
                intent="program_lookup",
                lookup_type="program",
                normalized_query=query,
                retrieval_query=query,
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

    assert captured["query"] == "slang::cntt có ngành nào?"
    assert result["retrieval_query"] == "slang::cntt có ngành nào?"
    assert result["strategy"] == "structured"


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
                retrieval_query=query,
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
