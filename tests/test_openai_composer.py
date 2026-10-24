"""Offline checks for Responses transport, completion and streaming contracts."""

from threading import Lock
from types import SimpleNamespace as NS
from unittest.mock import Mock

import openai
import pytest
import yaml

from src.generation import openai_composer as module
from src.generation.openai_composer import OpenAIComposerClient


def _response(status="completed", text="Câu trả lời.", reason=None):
    return NS(
        status=status, output_text=text, incomplete_details=NS(reason=reason),
        usage=NS(input_tokens=100, output_tokens=30, total_tokens=130,
                 input_tokens_details=NS(cached_tokens=80),
                 output_tokens_details=NS(reasoning_tokens=10)),
    )


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(module, "load_project_env", lambda: None)
    monkeypatch.setenv("OPENAI_API_KEY", "offline-openai-key")
    return OpenAIComposerClient(max_retries=0)


def test_default_factory_builds_luna_medium_without_changing_directory_selector(client):
    from pathlib import Path
    from src.generation.answer_pipeline import AnswerPipeline

    pipeline = object.__new__(AnswerPipeline)
    pipeline.config = yaml.safe_load(Path("configs/answer_generation.yaml").read_text(encoding="utf-8"))
    pipeline._llm_client = None
    pipeline._component_init_lock = Lock()
    configured = pipeline._get_llm_client()
    assert type(configured) is OpenAIComposerClient
    assert (configured.model_name, configured.reasoning_effort, configured.verbosity) == (
        "gpt-6-luna", "medium", "medium"
    )
    assert pipeline.config["directory_selector"]["provider"] == "deepseek"


def test_responses_request_uses_medium_and_omits_unsupported_sampling(client, monkeypatch):
    sdk = Mock()
    sdk.responses.create.return_value = _response()
    constructor = Mock(return_value=sdk)
    monkeypatch.setattr(openai, "OpenAI", constructor)
    result = client.generate("PROMPT")
    assert result["ok"] and result["text"] == "Câu trả lời."
    constructor.assert_called_once_with(
        api_key="offline-openai-key", base_url="https://api.openai.com/v1",
        timeout=60.0, max_retries=0,
    )
    sdk.responses.create.assert_called_once_with(
        model="gpt-6-luna", input=[{"role": "user", "content": "PROMPT"}],
        reasoning={"effort": "medium"}, text={"verbosity": "medium"},
        store=False, stream=False,
    )
    assert result["usage"] == {
        "input": 100, "output": 30, "total": 130, "cache_read": 80, "reasoning": 10,
    }


def test_incomplete_response_is_not_accepted_as_a_complete_answer(client, monkeypatch):
    from src.generation.answer_guardrails import build_fallback_answer

    sdk = Mock()
    sdk.responses.create.return_value = _response(
        status="incomplete", text="Chỉ trả lời được một phần", reason="max_output_tokens"
    )
    monkeypatch.setattr(client, "_create_client", lambda key: sdk)
    result = client.generate("PROMPT")
    assert not result["ok"] and result["error_type"] == "output_truncated"
    assert result["text"] == ""
    assert result["usage"]["total"] == 130
    assert sdk.responses.create.call_count == 1
    fallback = build_fallback_answer("Hỏi?", reason=result["error_type"])
    assert "chưa gọi được mô hình" in fallback
    assert "chưa tìm thấy thông tin" not in fallback


class _Stream:
    def __init__(self, events):
        self.events = events
        self.closed = False

    def __iter__(self):
        return iter(self.events)

    def close(self):
        self.closed = True


def test_stream_only_emits_answer_text_and_uses_final_usage(client):
    stream = _Stream([
        NS(type="response.created"),
        NS(type="response.reasoning_summary_text.delta", delta="private reasoning"),
        NS(type="response.output_text.delta", delta="Kết quả"),
        NS(type="response.completed", response=_response()),
    ])
    sdk = Mock()
    sdk.responses.create.return_value = stream
    output = client._generate_stream_once("PROMPT", client=sdk)
    assert next(output) == "Kết quả"
    with pytest.raises(StopIteration) as done:
        next(output)
    assert done.value.value["reasoning"] == 10 and done.value.value["cache_read"] == 80
    assert stream.closed and sdk.responses.create.call_args.kwargs["stream"]


def test_partial_stream_failure_does_not_restart_or_silently_succeed(client, monkeypatch):
    client.max_retries = 2
    stream = _Stream([
        NS(type="response.output_text.delta", delta="Một phần"),
        NS(type="response.incomplete", response=_response("incomplete", reason="max_output_tokens")),
    ])
    sdk = Mock()
    sdk.responses.create.return_value = stream
    monkeypatch.setattr(client, "_create_client", lambda key: sdk)
    output = client.generate_stream("PROMPT")
    assert next(output) == "Một phần"
    with pytest.raises(module.IncompleteComposerResponse):
        next(output)
    assert sdk.responses.create.call_count == 1 and stream.closed


def test_stream_without_terminal_event_is_an_error(client):
    stream = _Stream([NS(type="response.created")])
    sdk = Mock()
    sdk.responses.create.return_value = stream
    with pytest.raises(ConnectionError, match="without completion"):
        list(client._generate_stream_once("PROMPT", client=sdk))
    assert stream.closed


def test_missing_key_and_invalid_controls_fail_before_network(monkeypatch):
    monkeypatch.setattr(module, "load_project_env", lambda: None)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Missing OPENAI_API_KEY"):
        OpenAIComposerClient()
    monkeypatch.setenv("OPENAI_API_KEY", "offline-openai-key")
    with pytest.raises(ValueError, match="reasoning"):
        OpenAIComposerClient(reasoning_effort="invalid")
    with pytest.raises(ValueError, match="verbosity"):
        OpenAIComposerClient(verbosity="invalid")
