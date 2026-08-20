from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import src.retrieval.core.ai_router as ai_router_module
from src.retrieval.core.ai_router import (
    AIRouter,
    ROUTER_PROMPT_VERSION,
    ROUTER_SYSTEM_PROMPT,
    RouterDecisionCache,
)
from src.retrieval.core.structured_routing import (
    compact_registry_for_prompt,
    normalize_router_decision,
    router_json_schema,
    router_response_schema,
    validate_router_decision,
)


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
    assert "student_service|" in prompt_registry
    assert "default=contact" in prompt_registry


def test_router_contract_omits_fields_derived_by_code() -> None:
    contract = router_json_schema()

    assert "retrieval_query" not in contract
    assert "target_chunk_types" not in contract
    assert "needs_clarification" not in contract
    assert "execution_mode" not in contract
    assert "intent" not in contract
    assert "lookup_type" not in contract
    assert "slots" not in contract
    assert "slot_spans" not in contract
    assert "referenced_turn_ids" in contract
    assert "referenced_evidence" in contract
    assert "referenced_turns" not in contract

    response_properties = router_response_schema()["properties"]
    assert "execution_mode" not in response_properties
    assert "intent" not in response_properties
    assert "lookup_type" not in response_properties
    assert "slots" not in response_properties
    assert "slot_spans" not in response_properties


def test_router_cache_removes_legacy_retrieval_query(tmp_path: Path) -> None:
    cache_path = tmp_path / "router-cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "cache-key": {
                    "route": "rag",
                    "normalized_query": "K50 điều kiện tốt nghiệp",
                    "retrieval_query": "legacy router rewrite",
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    decision = RouterDecisionCache(str(cache_path)).get("cache-key")

    assert decision is not None
    assert decision["normalized_query"] == "K50 điều kiện tốt nghiệp"
    assert "retrieval_query" not in decision


def test_router_cache_key_is_bound_to_validator_version(
    monkeypatch, tmp_path: Path
) -> None:
    router = _router(monkeypatch, tmp_path, model_name="qwen/qwen3.6-27b")
    original = router._cache_key("K51 GPA 3.2", cohort="K51", chat_history=[])
    monkeypatch.setattr(
        ai_router_module,
        "ROUTER_VALIDATOR_VERSION",
        "single-cohort-validator-next",
    )

    changed = router._cache_key("K51 GPA 3.2", cohort="K51", chat_history=[])

    assert changed != original


def test_compact_prompt_stays_within_budget(monkeypatch, tmp_path: Path) -> None:
    router = _router(monkeypatch, tmp_path, model_name="qwen/qwen3.6-27b")
    dynamic_prompt = router._build_prompt(
        "K50 IELTS 5.5 là bậc mấy?",
        cohort="K50",
        chat_history=[],
    )

    assert len(ROUTER_SYSTEM_PROMPT.strip()) + len(dynamic_prompt) <= 6700
    assert ROUTER_PROMPT_VERSION == "single-cohort-planner-v2.8"
    assert "không dùng dấu \"...\"" in ROUTER_SYSTEM_PROMPT
    assert "không phải request" in ROUTER_SYSTEM_PROMPT
    assert "request.query_span" in ROUTER_SYSTEM_PROMPT
    assert "span trong QUERY hiện tại" in ROUTER_SYSTEM_PROMPT
    assert "cohort_refs chỉ chứa chuỗi cohort đã grounding" in ROUTER_SYSTEM_PROMPT
    assert "nguồn lịch sử chỉ ở" in ROUTER_SYSTEM_PROMPT
    assert 'cohort_refs=["K51"]' not in ROUTER_SYSTEM_PROMPT
    assert "Chọn theo fact" in ROUTER_SYSTEM_PROMPT
    assert "cả hai fact độc lập=tạo hai request" in ROUTER_SYSTEM_PROMPT
    assert "JSON null thật" in ROUTER_SYSTEM_PROMPT
    assert "trước normalization" in ROUTER_SYSTEM_PROMPT


def test_catalog_hint_is_candidate_not_tool_override(monkeypatch, tmp_path: Path) -> None:
    router = _router(monkeypatch, tmp_path, model_name="qwen/qwen3.6-27b")

    prompt = router._build_prompt(
        "đơn vị hỗ trợ bảo hiểm y tế",
        cohort="K51",
        chat_history=[],
        routing_hint={
            "lookup_type": "office",
            "entity_text": "y tế",
            "unit_name": "Trạm Y tế",
            "match_type": "exact_catalog_span",
        },
    )

    assert "not a routing command" in prompt
    assert "choose the tool from QUERY" in prompt
    assert "Never copy unit_name" in prompt


def test_history_window_uses_absolute_turn_ids(monkeypatch, tmp_path: Path) -> None:
    router = _router(monkeypatch, tmp_path, model_name="qwen/qwen3.6-27b")
    history = [
        {"role": "user", "content": f"turn-{index}"} for index in range(6)
    ]

    prompt = router._build_prompt(
        "Còn trường hợp đó?",
        cohort=None,
        chat_history=history,
    )

    assert "[2] user:turn-2" in prompt
    assert "[5] user:turn-5" in prompt
    assert "[0] user:turn-0" not in prompt

    longer_history = [
        {"role": "user", "content": "older-turn"},
        *history,
    ]
    assert router._cache_key(
        "Còn trường hợp đó?",
        cohort=None,
        chat_history=history,
    ) != router._cache_key(
        "Còn trường hợp đó?",
        cohort=None,
        chat_history=longer_history,
    )


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


def test_router_clarifies_after_provider_error(
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

    assert decision["route"] == "clarify"
    assert decision["execution_mode"] == "regulation"
    assert decision["target_chunk_types"] == []
    assert decision["retrieval_query"] is None
    assert decision["normalized_query"].startswith("K48-K49")
    assert decision["router_error_type"] == "transient_error"
    assert decision["router_fallback"] == "router_error_to_clarify"


def test_router_does_not_rotate_keys_for_internal_code_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    calls = 0

    class _Completions:
        @staticmethod
        def create(**_kwargs):
            nonlocal calls
            calls += 1
            raise TypeError("malformed internal payload")

    class _FakeGroq:
        def __init__(self, **_kwargs) -> None:
            self.chat = SimpleNamespace(completions=_Completions())

    monkeypatch.setattr(ai_router_module, "Groq", _FakeGroq)
    router = _router(monkeypatch, tmp_path, model_name="qwen/qwen3.6-27b")

    decision = router.route("K51 quy định bảo lưu thế nào?", cohort="K51")

    assert calls == 1
    assert decision["attempts"] == 1
    assert decision["router_error_type"] == "internal_code_error"
    assert decision["router_fallback"] == "router_error_to_clarify"


def test_router_accepts_provider_json_object_content() -> None:
    payload = {"outcome": "clarify", "lookup_requests": []}

    assert AIRouter._extract_json_object(payload) == payload


def test_router_accepts_provider_text_content_blocks() -> None:
    payload = [{"type": "text", "text": '{"outcome":"clarify"}'}]

    assert AIRouter._extract_json_object(payload) == {"outcome": "clarify"}


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


def test_from_config_cache_override_is_explicit_for_evaluators(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("GROQ_API_KEYS", "test-router-key")
    config_path = tmp_path / "router.yaml"
    config_path.write_text("cache_enabled: true\n", encoding="utf-8")

    router = AIRouter.from_config(config_path, cache_enabled=False)

    assert router.cache is None


def test_invalid_structured_decision_clarifies_without_retrieval(
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
        "referenced_turn_ids": [],
        "referenced_evidence": [],
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

    assert decision["route"] == "clarify"
    assert decision["lookup_requests"] == []
    assert decision["retrieval_executed"] is False
    assert "request:0:missing_slot:scope" in decision["router_validation_errors"]
    assert request["reasoning_effort"] == "low"
    assert request["response_format"]["type"] == "json_schema"


def test_router_normalization_does_not_infer_missing_jlpt_slot() -> None:
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

    assert "score_or_level" not in decision["slots"]
    assert "request:0:missing_slot:score_or_level" in (
        validate_router_decision(
            decision,
            query=query,
            selected_cohort="K50",
        )
    )


def test_router_normalization_does_not_infer_program_scope_from_keywords() -> None:
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

    assert "scope" not in decision["slots"]
    assert "request:0:missing_slot:scope" in (
        validate_router_decision(
            decision,
            query=query,
            selected_cohort="K51",
        )
    )


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

