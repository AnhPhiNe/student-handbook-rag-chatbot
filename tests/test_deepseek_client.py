"""Offline DeepSeek composer tests; never use real credentials or the network."""
import os
from types import SimpleNamespace as NS

import httpx
import openai
import pytest

from src.common.key_pool import KeyPoolConfig
from src.generation import deepseek_client as module
from src.generation.deepseek_client import DeepSeekClient


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


def _completion(text="Câu trả lời.", reasoning="PRIVATE REASONING"):
    return NS(choices=[NS(message=NS(content=text, reasoning_content=reasoning))],
              usage=NS(prompt_tokens=100, completion_tokens=20, total_tokens=120))


def _chunk(content=None, reasoning=None, usage=None):
    choices = [] if usage else [NS(delta=NS(content=content, reasoning_content=reasoning))]
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


def _status_error(status):
    response = httpx.Response(status, request=httpx.Request("POST", "https://api.deepseek.com/chat/completions"))
    return openai.APIStatusError("failure", response=response, body={})


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


@pytest.mark.parametrize("effort", ["none", "low"])
def test_pipeline_builds_the_configured_deepseek_composer(monkeypatch, effort):
    from src.generation.answer_pipeline import AnswerPipeline

    monkeypatch.setattr(module, "load_project_env", lambda: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "offline-deepseek-key")
    pipeline = object.__new__(AnswerPipeline)
    pipeline.config = __import__("yaml").safe_load(
        open(f"configs/experiments/answer_deepseek_{effort}.yaml", encoding="utf-8"))
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
