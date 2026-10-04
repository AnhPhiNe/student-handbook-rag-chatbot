"""Provider fallback for the composer and the directory selector (offline)."""
import pytest

from src.generation import answer_pipeline
from src.generation.answer_pipeline import create_composer_client, create_directory_selector
from src.generation.fallback_client import FallbackLLMClient


class Provider:
    def __init__(self, name, *, result=None, chunks=(), fail_at=None, error_type="quota_exhausted"):
        self.model_name = name
        self.result = result or {"ok": True, "text": name, "model_used": name}
        self.chunks, self.fail_at, self.error_type = list(chunks), fail_at, error_type
        self.calls = 0

    def generate(self, prompt):
        self.calls += 1
        return self.result

    def generate_stream(self, prompt):
        self.calls += 1
        for index, chunk in enumerate(self.chunks):
            if index == self.fail_at:
                raise self._error()
            yield chunk
        if self.fail_at is not None and self.fail_at >= len(self.chunks):
            raise self._error()
        return {"model_used": self.model_name}

    def _error(self):
        error = RuntimeError("provider failed")
        error.error_type = self.error_type
        return error

    @staticmethod
    def _classify_error(exc):
        return "unknown"


def failed(error_type):
    return {"ok": False, "text": "", "error_type": error_type}


@pytest.mark.parametrize("error_type", [
    "quota_exhausted", "auth_error", "rate_limit", "timeout", "transient_error", "unknown"])
def test_provider_failures_are_answered_by_the_fallback(error_type):
    primary = Provider("deepseek-flash", result=failed(error_type))
    backup = Provider("deepinfra")
    result = FallbackLLMClient(primary, backup).generate("q")
    assert result["ok"] and result["model_used"] == "deepinfra"
    assert result["fallback_from"] == {"model": "deepseek-flash", "error_type": error_type}


@pytest.mark.parametrize("error_type", ["output_truncated", "content_filtered", "invalid_request"])
def test_answer_failures_are_not_sent_to_another_provider(error_type):
    primary, backup = Provider("deepseek-flash", result=failed(error_type)), Provider("deepinfra")
    assert FallbackLLMClient(primary, backup).generate("q")["error_type"] == error_type
    assert backup.calls == 0


def test_a_working_primary_answers_alone_and_names_the_client():
    primary, backup = Provider("deepseek-flash"), Provider("deepinfra")
    client = FallbackLLMClient(primary, backup)
    assert client.generate("q")["model_used"] == "deepseek-flash"
    assert (client.model_name, backup.calls) == ("deepseek-flash", 0)


def run_stream(client):
    stream, chunks = client.generate_stream("q"), []
    while True:
        try:
            chunks.append(next(stream))
        except StopIteration as done:
            return chunks, done.value


def test_stream_falls_back_when_the_primary_fails_before_any_text():
    primary = Provider("deepseek-flash", chunks=["a"], fail_at=0)
    backup = Provider("deepinfra", chunks=["b", "c"])
    chunks, result = run_stream(FallbackLLMClient(primary, backup))
    assert chunks == ["b", "c"]
    assert result["model_used"] == "deepinfra"
    assert result["fallback_from"]["error_type"] == "quota_exhausted"


def test_stream_does_not_restart_after_text_was_shown():
    primary = Provider("deepseek-flash", chunks=["a", "b"], fail_at=1, error_type="timeout")
    backup = Provider("deepinfra", chunks=["c"])
    with pytest.raises(RuntimeError):
        run_stream(FallbackLLMClient(primary, backup))
    assert backup.calls == 0


def test_stream_keeps_a_cut_off_answer_on_its_provider():
    primary = Provider("deepseek-flash", chunks=[], fail_at=0, error_type="output_truncated")
    backup = Provider("deepinfra", chunks=["c"])
    with pytest.raises(RuntimeError):
        run_stream(FallbackLLMClient(primary, backup))
    assert backup.calls == 0


def test_stream_unclassified_exhaustion_falls_back():
    primary = Provider("deepseek-flash", chunks=[], fail_at=0, error_type=None)
    chunks, result = run_stream(FallbackLLMClient(primary, Provider("deepinfra", chunks=["c"])))
    assert chunks == ["c"] and result["fallback_from"]["error_type"] == "unknown"


CONFIG = {
    "provider": "deepseek", "model_name": "deepseek-flash", "reasoning_effort": "low",
    "api_keys_env_var": "DEEPSEEK_API_KEY", "request_timeout_seconds": 60,
    "fallback": {"base_url": "https://api.deepinfra.com/v1/openai",
                 "model_name": "deepseek-ai/DeepSeek-V4.1-Flash",
                 "api_keys_env_var": "DEEPINFRA_API_KEY"},
}


@pytest.fixture
def offline(monkeypatch):
    from src.generation import deepseek_client
    monkeypatch.setattr(deepseek_client, "load_project_env", lambda: None)
    monkeypatch.setattr(answer_pipeline, "load_project_env", lambda: None)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "offline-deepseek-key")
    monkeypatch.setenv("DEEPINFRA_API_KEY", "offline-deepinfra-key")
    return monkeypatch


def test_the_fallback_inherits_everything_it_does_not_override(offline):
    client = create_composer_client(CONFIG)
    assert isinstance(client, FallbackLLMClient)
    assert client.primary.base_url == "https://api.deepseek.com"
    assert (client.fallback.base_url, client.fallback.model_name,
            client.fallback.reasoning_effort, client.fallback.request_timeout_seconds) == (
        "https://api.deepinfra.com/v1/openai", "deepseek-ai/DeepSeek-V4.1-Flash", "low", 60)


@pytest.mark.parametrize("missing,model", [
    ("DEEPSEEK_API_KEY", "deepseek-ai/DeepSeek-V4.1-Flash"),
    ("DEEPINFRA_API_KEY", "deepseek-flash"),
])
def test_a_provider_without_a_key_is_left_out(offline, missing, model):
    offline.delenv(missing)
    client = create_composer_client(CONFIG)
    assert not isinstance(client, FallbackLLMClient)
    assert client.model_name == model


def test_no_key_for_either_provider_names_both(offline):
    offline.delenv("DEEPSEEK_API_KEY")
    offline.delenv("DEEPINFRA_API_KEY")
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY and DEEPINFRA_API_KEY"):
        create_composer_client(CONFIG)


def test_selector_and_its_thinking_retry_both_fall_back(offline):
    config = {**CONFIG, "reasoning_effort": "none", "max_output_tokens": 200,
              "thinking_retry": {"reasoning_effort": "low", "max_output_tokens": 4096}}
    selector = create_directory_selector(config)
    assert selector.client.fallback.reasoning_effort == "none"
    assert selector.thinking_client.fallback.reasoning_effort == "low"
    assert selector.thinking_client.fallback.max_output_tokens == 4096
    assert selector.thinking_client.fallback.response_format == {"type": "json_object"}
