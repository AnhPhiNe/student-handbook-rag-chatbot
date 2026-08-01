from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import src.retrieval.core.ai_router as ai_router_module
from src.retrieval.core.ai_router import (
    AIRouter,
    ROUTER_PROMPT_VERSION,
    ROUTER_SYSTEM_PROMPT,
)
from src.retrieval.core.structured_routing import (
    compact_registry_for_prompt,
    normalize_router_decision,
    router_json_schema,
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

    assert len(ROUTER_SYSTEM_PROMPT.strip()) + len(dynamic_prompt) <= 6500
    assert ROUTER_PROMPT_VERSION.endswith("compact")


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
