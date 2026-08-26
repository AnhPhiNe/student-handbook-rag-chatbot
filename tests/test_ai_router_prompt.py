from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import src.retrieval.core.ai_router as ai_router_module
from src.retrieval.core.ai_router import (
    AIRouter,
    PLANNER_SYSTEM_PROMPT,
    ROUTER_PROMPT_VERSION,
    ROUTER_SYSTEM_PROMPT,
)
from src.retrieval.core.query_plan import QUERY_PLAN_NORMALIZER_VERSION
from src.retrieval.core.structured_routing import (
    compact_registry_for_prompt,
    normalize_router_decision,
    router_json_schema,
    validate_router_decision,
)

PLANNER_PROMPT_TEXT = " ".join(PLANNER_SYSTEM_PROMPT.split())


def _router(monkeypatch, tmp_path: Path, *, model_name: str) -> AIRouter:
    monkeypatch.setenv("GROQ_API_KEYS", "test-router-key")
    return AIRouter(
        model_name=model_name,
        cache_enabled=False,
        key_pool_config={
            "state_path": str(tmp_path / f"{model_name.replace('/', '-')}.json"),
        },
    )


def test_compact_registry_omits_prompt_only_noise() -> None:
    prompt_registry = compact_registry_for_prompt()

    assert "examples" not in prompt_registry
    assert "operand_requirements" not in prompt_registry
    assert "required=" in prompt_registry
    assert "values" in prompt_registry


def test_router_contract_omits_fields_derived_by_code() -> None:
    contract = router_json_schema()

    assert "retrieval_query" not in contract
    assert "target_chunk_types" not in contract
    assert "needs_clarification" not in contract


def test_compact_prompt_stays_within_budget(monkeypatch, tmp_path: Path) -> None:
    router = _router(monkeypatch, tmp_path, model_name="qwen/qwen3.6-27b")
    dynamic_prompt = router._build_prompt(
        "K50 IELTS 5.5 là bậc mấy?",
        cohort="K50",
        chat_history=[],
    )

    assert len(ROUTER_SYSTEM_PROMPT.strip()) + len(dynamic_prompt) <= 6700
    assert ROUTER_PROMPT_VERSION == "structured-regulation-v28-target-first-contract"


def test_plan_cache_key_includes_normalizer_version(monkeypatch, tmp_path: Path) -> None:
    router = _router(monkeypatch, tmp_path, model_name="qwen/qwen3.6-27b")
    key = router._cache_key(
        "So sánh K50 và K51",
        cohort="K51",
        chat_history=[],
    )

    monkeypatch.setattr(
        ai_router_module,
        "QUERY_PLAN_NORMALIZER_VERSION",
        QUERY_PLAN_NORMALIZER_VERSION + "-changed",
    )
    changed_key = router._cache_key(
        "So sánh K50 và K51",
        cohort="K51",
        chat_history=[],
    )

    assert changed_key != key


def test_planner_prompt_stays_within_budget(monkeypatch, tmp_path: Path) -> None:
    router = _router(monkeypatch, tmp_path, model_name="qwen/qwen3.6-27b")
    dynamic_prompt = router._build_plan_prompt(
        "So sánh hai khóa về thời gian học và một quy định học vụ.",
        cohort="K51",
        chat_history=[],
    )
    stats = AIRouter._prompt_stats_for_system(
        PLANNER_SYSTEM_PROMPT,
        dynamic_prompt,
        {"type": "json_object"},
    )

    assert stats["total_chars"] <= 6800
    assert stats["estimated_input_tokens"] <= 1700


def test_planner_prompt_defines_cohort_independent_task_identity() -> None:
    assert "TASK IDENTITY không phụ thuộc cohort" in PLANNER_PROMPT_TEXT
    assert "không tạo M×N tasks" in PLANNER_PROMPT_TEXT
    assert "COHORT từ UI chỉ điền cho task vẫn chưa có cohort" in PLANNER_PROMPT_TEXT
    assert "không ghi đè" in PLANNER_PROMPT_TEXT
    assert "So sánh K50 và K51 về thời gian học tối đa" not in PLANNER_PROMPT_TEXT


def test_planner_prompt_treats_compare_as_presentation_and_slots_as_optional() -> None:
    assert "So sánh là yêu cầu trình bày" in PLANNER_PROMPT_TEXT
    assert "Không dùng intent=compare" in PLANNER_PROMPT_TEXT
    assert "intent/slots là metadata tương thích tùy chọn" in PLANNER_PROMPT_TEXT
    assert "chọn một bảng con" in PLANNER_PROMPT_TEXT
    assert "không dùng để lọc hàng bên trong bảng đã chọn" in PLANNER_PROMPT_TEXT


def test_planner_prompt_splits_independent_answer_targets() -> None:
    assert "Tách QUERY thành answer target theo kết luận/nguồn" in PLANNER_PROMPT_TEXT
    assert "Mỗi target cần mode/tool khác nhau phải là task riêng" in PLANNER_PROMPT_TEXT
    assert "Task cần cả structured và RAG chưa atomic" in PLANNER_PROMPT_TEXT


def test_planner_prompt_requires_grounded_slots_for_structured_mode() -> None:
    assert "Nếu xuất entity/value slots, chúng phải được grounding" in PLANNER_PROMPT_TEXT
    assert "Control slots" in PLANNER_PROMPT_TEXT
    assert "được phép chuẩn" in PLANNER_PROMPT_TEXT
    assert "Không chọn structured chỉ vì trùng từ chủ đề" in PLANNER_PROMPT_TEXT
    assert "Chỉ clarify task bị thiếu thông tin" in PLANNER_PROMPT_TEXT


def test_planner_prompt_defines_context_and_hint_precedence_once() -> None:
    assert "standalone_query" in PLANNER_PROMPT_TEXT
    assert "referenced_turns" in PLANNER_PROMPT_TEXT
    assert "CATALOG_HINT là metadata đã được grounding" in PLANNER_PROMPT_TEXT
    assert PLANNER_PROMPT_TEXT.count("hơn 3 yêu cầu độc lập") == 1


def test_planner_prompt_matches_global_context_and_rag_contract() -> None:
    assert "Chỉ đặt context_mode=ambiguous khi toàn bộ QUERY" in PLANNER_PROMPT_TEXT
    assert "clarify cho riêng task đó" in PLANNER_PROMPT_TEXT
    assert "Mọi RAG task dùng intent=open_question" in PLANNER_PROMPT_TEXT
    assert "thiếu evidence" not in PLANNER_PROMPT_TEXT


def test_planner_prompt_protects_normalized_query_semantics() -> None:
    assert "normalized_query chỉ sửa dấu, chính tả nhẹ" in PLANNER_PROMPT_TEXT
    for protected_value in ("entity", "cohort", "số liệu", "phủ định", "chủ đề", "ý định"):
        assert protected_value in PLANNER_PROMPT_TEXT


def test_model_defaults_select_supported_reasoning_and_format(
    monkeypatch,
    tmp_path: Path,
) -> None:
    qwen = _router(monkeypatch, tmp_path, model_name="qwen/qwen3.6-27b")
    gpt_oss = _router(monkeypatch, tmp_path, model_name="openai/gpt-oss-20b")

    assert qwen._resolved_reasoning_effort() == "none"
    assert qwen._response_format_payload() == {"type": "json_object"}
    assert gpt_oss._resolved_reasoning_effort() == "low"
    assert gpt_oss._response_format_payload()["type"] == "json_schema"


def test_router_treats_upstream_disconnect_as_transient() -> None:
    error = RuntimeError("Server disconnected without sending a response.")

    assert AIRouter._classify_error(error) == "transient_error"


def test_router_treats_provider_json_validation_failure_as_transient() -> None:
    error = RuntimeError("json_validate_failed: Failed to generate JSON.")

    assert AIRouter._classify_error(error) == "transient_error"


def test_router_falls_back_to_regulation_rag_after_provider_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class _Completions:
        @staticmethod
        def create(**_kwargs):
            raise RuntimeError("json_validate_failed: Failed to generate JSON.")

    class _FakeGroq:
        def __init__(self, **_kwargs) -> None:
            self.chat = SimpleNamespace(completions=_Completions())

    monkeypatch.setattr(ai_router_module, "Groq", _FakeGroq)
    router = _router(monkeypatch, tmp_path, model_name="qwen/qwen3.6-27b")

    decision = router.route(
        "K48-K49: co duoc xin nang diem ren luyen neu thieu minh chung khong?",
        cohort="K48-K49",
    )

    assert decision["route"] == "rag"
    assert decision["execution_mode"] == "regulation"
    assert decision["target_chunk_types"] == ["regulation"]
    assert decision["retrieval_query"].startswith("K48-K49")
    assert decision["router_error_type"] == "transient_error"
    assert decision["router_fallback"] == "router_error_to_rag"


def test_from_config_accepts_model_environment_override(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("GROQ_API_KEYS", "test-router-key")
    monkeypatch.setenv("STUDENT_RAG_ROUTER_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("STUDENT_RAG_ROUTER_MAX_OUTPUT_TOKENS", "1024")
    config_path = tmp_path / "router.yaml"
    state_path = tmp_path / "router-state.json"
    config_path.write_text(
        "\n".join(
            (
                "model_name: qwen/qwen3.6-27b",
                "reasoning_effort: auto",
                "response_format: auto",
                "cache_enabled: false",
                "key_pool:",
                f"  state_path: {json.dumps(str(state_path))}",
            )
        ),
        encoding="utf-8",
    )

    router = AIRouter.from_config(config_path)

    assert router.model_name == "openai/gpt-oss-20b"
    assert router._resolved_reasoning_effort() == "none"
    assert router.max_output_tokens == 1024


def test_invalid_structured_decision_falls_back_to_safe_rag(
    monkeypatch,
    tmp_path: Path,
) -> None:
    request: dict = {}
    payload = {
        "context_mode": "standalone",
        "context_confidence": "high",
        "normalized_query": "K50 học gì?",
        "normalization_confidence": "high",
        "corrections": [],
        "standalone_query": None,
        "referenced_turns": [],
        "route": "structured",
        "execution_mode": "structured",
        "intent": "list_items",
        "lookup_type": "program",
        "cohort": "K50",
        "slots": {},
        "slot_spans": {},
        "clarification_question": None,
    }

    class _Completions:
        @staticmethod
        def create(**kwargs):
            request.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(payload, ensure_ascii=False)
                        )
                    )
                ],
                usage=SimpleNamespace(
                    prompt_tokens=100,
                    completion_tokens=40,
                    total_tokens=140,
                ),
            )

    class _FakeGroq:
        def __init__(self, **_kwargs) -> None:
            self.chat = SimpleNamespace(completions=_Completions())

    monkeypatch.setattr(ai_router_module, "Groq", _FakeGroq)
    router = _router(monkeypatch, tmp_path, model_name="openai/gpt-oss-20b")

    decision = router.route("K50 học gì?", cohort="K50")

    assert decision["route"] == "rag"
    assert "missing_slot:scope" in decision["router_validation_errors"]
    assert request["reasoning_effort"] == "low"
    assert request["response_format"]["type"] == "json_schema"


def test_router_normalization_infers_explicit_jlpt_level_slot() -> None:
    query = "K50 JLPT N3 tương đương bậc mấy?"
    decision = normalize_router_decision(
        {
            "route": "structured",
            "execution_mode": "structured",
            "intent": "direct_value",
            "lookup_type": "foreign_language",
            "cohort": "K50",
            "slots": {"certificate_or_language": "JLPT"},
            "slot_spans": {"certificate_or_language": "JLPT"},
        },
        query=query,
        selected_cohort="K50",
    )

    assert decision["slots"]["score_or_level"] == "N3"
    assert validate_router_decision(
        decision,
        query=query,
        selected_cohort="K50",
    ) == []


def test_router_normalization_infers_program_list_scope_from_faculty_query() -> None:
    query = "Khoa Công nghệ Thông tin có những ngành nào?"
    decision = normalize_router_decision(
        {
            "route": "structured",
            "execution_mode": "structured",
            "intent": "list_items",
            "lookup_type": "program",
            "cohort": "K51",
            "slots": {},
            "slot_spans": {},
        },
        query=query,
        selected_cohort="K51",
    )

    assert decision["slots"]["scope"] == "faculty"
    assert validate_router_decision(
        decision,
        query=query,
        selected_cohort="K51",
    ) == []


def test_router_normalization_handles_multi_cohort_comparison() -> None:
    query = "K50 và K51 thì mấy điểm mới qua môn?"
    decision = normalize_router_decision(
        {
            "route": "rag",
            "execution_mode": "regulation",
            "intent": "regulation",
            "lookup_type": None,
            "cohort": "K50",
            "cohorts": ["K50", "K51"],
            "is_multi_cohort": True,
            "slots": {},
            "slot_spans": {},
        },
        query=query,
        selected_cohort="K50",
    )

    assert decision["is_multi_cohort"] is True
    assert decision["cohorts"] == ["K50", "K51"]
    assert decision["cohort"] == "K50"


def test_router_normalization_preserves_single_cohort_backward_compatibility() -> None:
    query = "K50 mấy điểm qua môn?"
    decision = normalize_router_decision(
        {
            "route": "rag",
            "execution_mode": "regulation",
            "intent": "regulation",
            "lookup_type": None,
            "cohort": "K50",
            "cohorts": ["K50"],
            "is_multi_cohort": False,
            "slots": {},
            "slot_spans": {},
        },
        query=query,
        selected_cohort="K50",
    )

    assert decision["is_multi_cohort"] is False
    assert decision["cohorts"] == ["K50"]
    assert decision["cohort"] == "K50"

