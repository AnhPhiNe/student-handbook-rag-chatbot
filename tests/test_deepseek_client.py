"""Offline DeepSeek composer tests; never use real credentials or the network."""
import os
from types import SimpleNamespace as NS

import httpx
import openai
import pytest

from src.common.key_pool import KeyPoolConfig
from src.generation import deepseek_client as module
from src.generation.deepseek_client import DeepSeekClient, IncompleteGenerationError


def _client(monkeypatch, **kwargs) -> DeepSeekClient:
    monkeypatch.setattr(module, "load_project_env", lambda: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "offline-deepseek-key")
    return DeepSeekClient(
        key_pool_config=KeyPoolConfig(name="test", rpm_limit_per_key=600, state_path=None),
        max_retries=1, retry_base_delay_seconds=0, **kwargs,
    )


def _fake_openai(monkeypatch, responses):
    calls = []
    pending = iter(responses)

    class Client:
        def __init__(self, **options):
            self.options = options
            self.chat = NS(completions=NS(create=self.create))

        def create(self, **request):
            calls.append({"client": self.options, "request": request})
            result = next(pending)
            if isinstance(result, Exception):
                raise result
            return result

    monkeypatch.setattr(openai, "OpenAI", Client)
    return calls


def _completion(text="Câu trả lời.", reasoning="PRIVATE REASONING", finish_reason="stop"):
    return NS(choices=[NS(message=NS(content=text, reasoning_content=reasoning), finish_reason=finish_reason)],
              usage=NS(prompt_tokens=100, completion_tokens=20, total_tokens=120))


def _chunk(content=None, reasoning=None, usage=None, finish_reason=None):
    choices = [] if usage else [NS(delta=NS(content=content, reasoning_content=reasoning), finish_reason=finish_reason)]
    return NS(choices=choices, usage=usage)


@pytest.mark.parametrize(("effort", "thinking"), [
    ("none", {"thinking": {"type": "disabled"}}),
    ("low", {"reasoning_effort": "low"}),
])
def test_request_sets_thinking_and_returns_only_the_answer(monkeypatch, effort, thinking):
    calls = _fake_openai(monkeypatch, [_completion()])
    result = _client(monkeypatch, reasoning_effort=effort, max_output_tokens=4096).generate("PROMPT")
    request = calls[0]["request"]
    assert request["extra_body"] == thinking
    assert request["messages"] == [{"role": "user", "content": "PROMPT"}]
    assert request["model"] == "deepseek-flash" and request["max_tokens"] == 4096
    assert calls[0]["client"]["base_url"] == "https://api.deepseek.com"
    assert calls[0]["client"]["max_retries"] == 0
    assert result["ok"] and result["text"] == "Câu trả lời."
    assert result["usage"] == {"input": 100, "output": 20, "total": 120}
    assert "PRIVATE" not in str(result)


def test_stream_yields_answer_chunks_but_never_reasoning(monkeypatch):
    stream = [_chunk(reasoning="PRIVATE REASONING"), _chunk("Câu "), _chunk("trả lời."),
              _chunk(finish_reason="stop"),
              _chunk(usage=NS(prompt_tokens=10, completion_tokens=5, total_tokens=15))]
    calls = _fake_openai(monkeypatch, [iter(stream)])
    generator = _client(monkeypatch).generate_stream("PROMPT")
    chunks = []
    while True:
        try:
            chunks.append(next(generator))
        except StopIteration as done:
            final = done.value
            break
    assert chunks == ["Câu ", "trả lời."]
    assert final["usage"] == {"input": 10, "output": 5, "total": 15}
    assert calls[0]["request"]["stream"] is True
    assert calls[0]["request"]["stream_options"] == {"include_usage": True}


@pytest.mark.parametrize("stream", [False, True])
def test_provider_request_omits_max_tokens_when_no_application_ceiling(monkeypatch, stream):
    import json

    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"id": "offline", "object": "chat.completion",
            "created": 0, "model": "deepseek-flash", "choices": [],
            "usage": {"prompt_tokens": 1, "completion_tokens": 0, "total_tokens": 1}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as http_client:
        with openai.OpenAI(api_key="offline", base_url="https://api.deepseek.com",
                           http_client=http_client, max_retries=0) as sdk:
            response = _client(monkeypatch, max_output_tokens=None)._request("PROMPT", sdk, stream=stream)
            if stream:
                response.close()
    assert "max_tokens" not in requests[0]
    assert "max_completion_tokens" not in requests[0]
    assert requests[0]["thinking"] == {"type": "disabled"}


def test_composer_default_and_explicit_caps_do_not_change_selector_budgets(monkeypatch):
    import copy
    import yaml
    from src.generation.answer_pipeline import create_composer_client, create_directory_selector

    monkeypatch.setattr(module, "load_project_env", lambda: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "offline-deepseek-key")
    with open("configs/answer_generation.yaml", encoding="utf-8") as file:
        config = yaml.safe_load(file)
    assert create_composer_client(config["llm"]).max_output_tokens is None
    without_setting = {key: value for key, value in config["llm"].items() if key != "max_output_tokens"}
    assert create_composer_client(without_setting).max_output_tokens is None
    explicit = copy.deepcopy(config["llm"])
    explicit["max_output_tokens"] = 16384
    assert create_composer_client(explicit).max_output_tokens == 16384
    selector = create_directory_selector(config["directory_selector"])
    assert selector.client.max_output_tokens == 200
    assert selector.thinking_client.max_output_tokens == 4096


def _status_error(status):
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.deepseek.com/chat/completions"))
    return openai.APIStatusError("failure", response=response, body={})


@pytest.mark.parametrize(("finish_reason", "error_type"), [
    ("length", "output_truncated"), ("content_filter", "content_filtered"),
    ("tool_calls", "invalid_completion"), (None, "incomplete_stream"),
])
@pytest.mark.parametrize("text", ["", "Câu trả lời bị cắt"])
def test_incomplete_sync_answer_is_not_success_and_not_retried(monkeypatch, finish_reason, error_type, text):
    calls = _fake_openai(monkeypatch, [_completion(text=text, finish_reason=finish_reason), _completion()])
    result = _client(monkeypatch).generate("PROMPT")
    assert not result["ok"] and result["error_type"] == error_type
    assert result["attempts"] == len(calls) == 1
    assert result["usage"]["total"] == 120


@pytest.mark.parametrize(("finish_reason", "error_type"), [
    ("length", "output_truncated"), ("content_filter", "content_filtered"),
    (None, "incomplete_stream"),
])
@pytest.mark.parametrize("partial", ["", "Phần đầu."])
def test_incomplete_stream_preserves_tokens_closes_and_does_not_retry(monkeypatch, finish_reason, error_type, partial):
    class Stream:
        closed = False

        def __iter__(self):
            if partial:
                yield _chunk(partial)
            if finish_reason:
                yield _chunk(finish_reason=finish_reason)
            yield _chunk(usage=NS(prompt_tokens=10, completion_tokens=5, total_tokens=15))

        def close(self):
            self.closed = True

    source = Stream()
    calls = _fake_openai(monkeypatch, [source, iter([_chunk("Retry", finish_reason="stop")])])
    client = _client(monkeypatch)
    stream = client.generate_stream("PROMPT")
    if partial:
        assert next(stream) == partial
    with pytest.raises(IncompleteGenerationError) as failed:
        next(stream)
    assert failed.value.error_type == error_type
    assert failed.value.usage["total"] == 15
    assert source.closed and len(calls) == 1


@pytest.mark.parametrize(("error", "kind"), [
    (_status_error(401), "auth_error"), (_status_error(402), "quota_exhausted"),
    (_status_error(429), "rate_limit"), (_status_error(503), "transient_error"),
    (_status_error(400), "invalid_request"),
    (openai.APITimeoutError(request=httpx.Request("POST", "https://api.deepseek.com")), "timeout"),
    (openai.APIConnectionError(request=httpx.Request("POST", "https://api.deepseek.com")), "transient_error"),
])
def test_errors_are_classified(error, kind):
    assert DeepSeekClient._classify_error(error) == kind


def test_overload_is_retried_but_a_bad_request_is_not(monkeypatch):
    calls = _fake_openai(monkeypatch, [_status_error(503), _completion()])
    assert _client(monkeypatch).generate("PROMPT")["ok"]
    assert len(calls) == 2
    calls = _fake_openai(monkeypatch, [_status_error(400), _completion()])
    result = _client(monkeypatch).generate("PROMPT")
    assert not result["ok"] and result["error_type"] == "invalid_request"
    assert len(calls) == 1


def test_rejects_missing_key_and_unknown_effort(monkeypatch):
    monkeypatch.setattr(module, "load_project_env", lambda: None)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        DeepSeekClient()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "offline-deepseek-key")
    with pytest.raises(ValueError):
        DeepSeekClient(reasoning_effort="medium")


@pytest.mark.parametrize(("config_path", "effort"), [
    ("configs/answer_generation.yaml", "none"),
    ("configs/experiments/answer_deepseek_low.yaml", "low"),
])
def test_pipeline_builds_the_configured_deepseek_composer(monkeypatch, config_path, effort):
    from src.generation.answer_pipeline import AnswerPipeline

    monkeypatch.setattr(module, "load_project_env", lambda: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "offline-deepseek-key")
    pipeline = object.__new__(AnswerPipeline)
    pipeline.config = __import__("yaml").safe_load(
        open(config_path, encoding="utf-8"))
    pipeline._llm_client = None
    pipeline._component_init_lock = __import__("threading").Lock()
    client = pipeline._get_llm_client()
    assert isinstance(client, DeepSeekClient)
    assert (client.model_name, client.reasoning_effort, client.request_timeout_seconds) == (
        "deepseek-flash", effort, 60)


def test_shared_plans_enable_the_planner_cache_only_for_the_run(monkeypatch, tmp_path):
    from src.evaluation import answers

    seen = {}

    class Pipeline:
        def answer(self, query, **kwargs):
            seen["disable"] = os.environ.get("STUDENT_RAG_DISABLE_ROUTER_CACHE")
            seen["path"] = os.environ.get("STUDENT_RAG_ROUTER_CACHE_PATH")
            return {"answer": "ok", "status": "ok"}

    monkeypatch.setenv("STUDENT_RAG_DISABLE_ROUTER_CACHE", "1")
    monkeypatch.delenv("STUDENT_RAG_ROUTER_CACHE_PATH", raising=False)
    cases = [{"id": "c1", "query": "Hỏi?", "cohort": "K51"}]
    answers.generate_answers(cases, cache_path=tmp_path / "answers.json", resume=False,
                             pipeline_factory=Pipeline, shared_plans=tmp_path / "plans.json")
    assert seen == {"disable": None, "path": str(tmp_path / "plans.json")}
    assert os.environ["STUDENT_RAG_DISABLE_ROUTER_CACHE"] == "1"
    assert "STUDENT_RAG_ROUTER_CACHE_PATH" not in os.environ
