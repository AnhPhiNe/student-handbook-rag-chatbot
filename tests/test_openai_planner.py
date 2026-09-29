"""Offline Responses transport/contract tests; never use real credentials."""
import json
from types import SimpleNamespace as NS

import httpx
import openai
import pytest

from src.retrieval.core import ai_router as module
from src.retrieval.core.ai_router import AIRouter
from src.retrieval.core.planner_diagnostics import planner_diagnostics_scope
from src.retrieval.core.structured_routing import compact_registry_for_prompt


@pytest.fixture
def router(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "load_project_env", lambda: None)
    monkeypatch.setenv("OPENAI_API_KEY", "offline-openai-key")
    return AIRouter(
        cache_enabled=False,
        max_output_tokens=8192, hard_max_output_tokens=8192,
        request_timeout_seconds=20, max_retries=1,
        key_pool_config={"state_path": str(tmp_path / "keys.json"),
                         "tpm_limit_per_key": None},
    )


def _plan():
    return {"schema_version": "v1", "context_mode": "standalone",
            "normalized_query": "Quy định học vụ?", "standalone_query": None,
            "referenced_turns": [], "out_of_domain": False,
            "tasks": [{"id": "t1", "question": "Quy định học vụ?", "mode": "rag",
                       "intent": "open_question", "lookup_type": None,
                       "slots": {}, "slot_spans": {}, "cohorts": ["K51"],
                       "clarification_question": None}]}


def _response(status="completed", reason=None, refusal=False):
    return NS(status=status, incomplete_details=NS(reason=reason),
              output_text=json.dumps(_plan()),
              output=[NS(type="reasoning", content="PRIVATE REASONING"),
                      NS(type="message", content=[NS(type="refusal" if refusal else "output_text",
                                                      refusal="PRIVATE REFUSAL")])],
              usage=NS(input_tokens=100, output_tokens=35, total_tokens=135,
                       input_tokens_details=NS(cached_tokens=20),
                       output_tokens_details=NS(reasoning_tokens=10)))


def _fake(monkeypatch, responses):
    calls = []
    pending = iter(responses)
    class Client:
        def __init__(self, **kwargs):
            self.options = kwargs
            self.responses = NS(create=self.create)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def create(self, **kwargs):
            calls.append({"client": self.options, "request": kwargs})
            result = next(pending)
            if isinstance(result, Exception):
                raise result
            return result
    monkeypatch.setattr(openai, "OpenAI", Client)
    return calls


@pytest.mark.parametrize("effort", ["none", "low", "medium"])
def test_responses_request_and_usage(router, monkeypatch, effort):
    router.reasoning_effort = effort
    calls = _fake(monkeypatch, [_response()])
    with planner_diagnostics_scope(True):
        result = router.plan("Quy định học vụ?", cohort="K51")
    request = calls[0]["request"]
    assert request["model"] == "gpt-6-luna"
    assert request["reasoning"] == {"effort": effort}
    assert request["text"] == {"format": router._plan_response_format_payload()}
    assert request["store"] is False
    assert request["max_output_tokens"] == 8192
    assert not {"temperature", "max_tokens", "response_format", "tools"} & request.keys()
    assert calls[0]["client"] == {
        "api_key": "offline-openai-key", "base_url": "https://api.openai.com/v1",
        "timeout": 20, "max_retries": 0,
    }
    assert result["usage"] == {"input": 100, "output": 35, "total": 135}
    assert not result.get("planner_fallback")
    response = result["planner_diagnostics"]["attempts"][0]["response"]
    assert response["token_details"] == {"reasoning_tokens": 10, "prompt_cache_hit_tokens": 20}
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize(("status", "reason", "refusal", "finish"), [
    ("incomplete", "max_output_tokens", False, "length"),
    ("incomplete", "content_filter", False, "content_filter"),
    ("completed", None, True, "content_filter"),
    ("failed", None, False, "error"),
])
def test_partial_or_refused_json_never_executes(router, monkeypatch, status, reason, refusal, finish):
    calls = _fake(monkeypatch, [_response(status, reason, refusal)])
    with planner_diagnostics_scope(True):
        result = router.plan("Quy định học vụ?", cohort="K51")
    assert result["planner_fallback"]
    assert result["planner_error_type"] == "invalid_response"
    assert len(calls) == 1
    diagnostic = result["planner_diagnostics"]["attempts"][0]
    assert diagnostic["response"]["finish_reason"] == finish
    assert diagnostic["response"]["usage"]["total"] == 135
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize(("status", "kind"), [(401, "auth_error"), (429, "rate_limit"),
                                              (400, "api_error"), (503, "transient_error")])
def test_sdk_http_errors_classified(status, kind):
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.openai.com/v1/responses"))
    error = openai.APIStatusError("failure", response=response, body={})
    assert AIRouter._classify_error(error) == kind


def test_sdk_timeout_retries_once_then_succeeds(router, monkeypatch):
    error = openai.APITimeoutError(request=httpx.Request("POST", "https://api.openai.com/v1/responses"))
    calls = _fake(monkeypatch, [error, _response()])
    with planner_diagnostics_scope(True):
        result = router.plan("Quy định học vụ?", cohort="K51")
    assert len(calls) == 2
    assert result["attempts"] == 2
    assert not result.get("planner_fallback")
    assert result["planner_diagnostics"]["attempts"][0]["error"]["type"] == "timeout"


def test_missing_key_does_not_use_groq_or_deepseek(router, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    monkeypatch.setenv("GROQ_API_KEYS", "not-openai")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "not-openai")
    with pytest.raises(RuntimeError, match="Missing OPENAI_API_KEY"):
        AIRouter()


@pytest.mark.parametrize("kwargs", [{"model_name": "qwen/qwen3.8-27b"},
                                    {"reasoning_effort": "minimal"}])
def test_reject_stale_or_unsupported_config(router, kwargs):
    with pytest.raises(ValueError):
        AIRouter(**kwargs)


def test_production_config_is_the_measured_luna_setup(monkeypatch, tmp_path):
    from dataclasses import replace
    original_pool = module.KeyPool
    monkeypatch.setattr(module, "KeyPool", lambda keys, config, **kwargs: original_pool(
        keys, replace(config, state_path=str(tmp_path / "keys.json")), **kwargs))
    for name in list(module.os.environ):
        if name.startswith("STUDENT_RAG_ROUTER_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("STUDENT_RAG_DISABLE_ROUTER_CACHE", "1")
    router = AIRouter.from_config("configs/ai_router.yaml")
    assert (router.provider, router.model_name, router.reasoning_effort) == (
        "openai", "gpt-6-luna", "medium")
    assert router.cache is None
    assert router.max_retries == 1 and router.request_timeout_seconds == 20
    assert router._planner_output_token_limit(3) == 8192
    assert router._plan_response_format_payload()["strict"] is True
    # Production keeps the decision cache; evaluation runs disable it.
    monkeypatch.delenv("STUDENT_RAG_DISABLE_ROUTER_CACHE")
    monkeypatch.setattr(module, "RouterDecisionCache", lambda path: ("cache", path))
    assert AIRouter.from_config("configs/ai_router.yaml").cache == ("cache", "data/cache/planner_cache.json")


def test_two_timeouts_stop_at_retry_limit(router, monkeypatch):
    calls = _fake(monkeypatch, [TimeoutError("timeout"), TimeoutError("timeout")])
    with planner_diagnostics_scope(True):
        result = router.plan("Quy định học vụ?", cohort="K51")
    assert len(calls) == 2
    assert result["planner_fallback"]
    assert result["planner_error_type"] == "timeout"


@pytest.mark.parametrize("text", ["", "not JSON", '{"tasks":'])
def test_invalid_completed_output_is_not_executed(router, monkeypatch, text):
    response = _response()
    response.output_text = text
    _fake(monkeypatch, [response])
    result = router.plan("Quy định học vụ?", cohort="K51")
    assert result["planner_fallback"]
    assert result["planner_error_type"] == "invalid_response"


def test_repair_reuses_responses_contract_and_sums_usage(router, monkeypatch):
    calls = _fake(monkeypatch, [_response(), _response()])
    result = router.plan("Thứ nhất: quy định A. Thứ hai: quy định B.", cohort="K51")
    assert result["planner_repairs"] == 1
    assert result["usage"]["total"] == 270
    assert len(calls) == 2
    repair = calls[1]["request"]
    assert [message["role"] for message in repair["input"]] == ["system", "user", "assistant", "user"]
    assert "VALIDATION_FEEDBACK" in repair["input"][-1]["content"]
    assert repair["text"] == calls[0]["request"]["text"]


def test_cache_isolates_model_configuration(router):
    key = router._cache_key("test", cohort="K51", chat_history=[])
    for field, value in [("reasoning_effort", "none"),
                         ("max_output_tokens", 4096), ("hard_max_output_tokens", 4096),
                         ("output_tokens_per_task", 2048)]:
        old = getattr(router, field)
        setattr(router, field, value)
        assert key != router._cache_key("test", cohort="K51", chat_history=[])
        setattr(router, field, old)


def test_rendered_registry_explains_fields_not_specific_cases():
    rendered = compact_registry_for_prompt()
    assert "Tên đơn vị/phòng ban đầu vào, không phải địa chỉ" in rendered
    assert "services=danh sách dịch vụ" in rendered
    assert "faculty=khoa phụ trách ngành" in rendered
    assert "liên hệ khoa phụ trách ngành qua relationship" in rendered
    assert "graded=môn tính GPA, chưa xác định foundation/remaining" in rendered
    assert "không dùng all để né chọn field" in rendered
    assert "trách nhiệm theo quy chế/chính sách" in module.PLANNER_SYSTEM_PROMPT
    for text in ("official_det_093", "official_det_096", "DeepSeek", "Qwen", "Luna"):
        assert text not in rendered


def test_actual_sdk_serializes_responses_without_network(router, monkeypatch):
    """Exercise installed SDK, not just a fake client's keyword arguments."""
    sent = []
    def handle(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "resp_offline", "object": "response", "created_at": 0,
            "model": "gpt-6-luna", "status": "completed",
            "output": [{"id": "msg_offline", "type": "message", "role": "assistant",
                        "status": "completed", "content": [{"type": "output_text",
                        "text": json.dumps(_plan()), "annotations": []}]}],
            "usage": {"input_tokens": 100, "output_tokens": 35, "total_tokens": 135},
        })
    real_client = openai.OpenAI
    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: real_client(
        **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handle))))
    result = router.plan("Quy định học vụ?", cohort="K51")
    assert not result.get("planner_fallback")
    assert result["usage"]["total"] == 135
    assert sent[0]["text"]["format"] == router._plan_response_format_payload()
    assert sent[0]["text"]["format"]["strict"] is True
    assert "json_schema" not in sent[0]["text"]["format"]


def test_strict_requests_keep_validation_and_incomplete_response_handling(router, monkeypatch):
    from src.retrieval.core.query_plan import query_plan_strict_response_schema
    router.reasoning_effort = "medium"
    calls = _fake(monkeypatch, [_response("incomplete", "max_output_tokens")])
    result = router.plan("Quy định học vụ?", cohort="K51")
    request = calls[0]["request"]
    assert request["text"]["format"] == {
        "type": "json_schema", "name": "query_plan", "strict": True,
        "schema": query_plan_strict_response_schema(router.registry),
    }
    assert request["reasoning"] == {"effort": "medium"}
    # Strict output rules sit in the cached system prompt, not the per-query message.
    assert "slot không cung cấp là null" in request["input"][0]["content"]
    assert "slot không cung cấp là null" not in request["input"][1]["content"]
    assert "OUTPUT CONTRACT" not in request["input"][1]["content"]
    assert result["planner_fallback"]
    assert result["planner_error_type"] == "invalid_response"


def test_strict_prompt_moves_slot_descriptions_into_the_schema(router):
    description = "Dịch vụ cần hỗ trợ, không phải tên đơn vị."
    assert description not in router._build_plan_prompt("Hỏi?", cohort="K51", chat_history=[])
    assert description in json.dumps(router._plan_response_format_payload(), ensure_ascii=False)
    assert "slot không cung cấp là null" in router._planner_system_prompt()
