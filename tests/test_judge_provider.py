"""The judge runs the same model on Groq (default) or DeepInfra, and records which."""
import pytest

from src.evaluation.judge import GroqJudgeClient, JudgeConfig, judge_key_pool


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(ValueError):
        JudgeConfig(provider="somewhere")


def test_deepinfra_pool_limits_requests_only() -> None:
    pool = judge_key_pool(["k"], JudgeConfig(provider="deepinfra"))
    assert pool.config.name == "deepinfra_judge"
    assert pool.config.tpd_limit_per_key is None and pool.config.tpm_limit_per_key is None
    groq = judge_key_pool(["k"], JudgeConfig())
    assert groq.config.tpd_limit_per_key == 200_000


def test_provider_comes_from_the_environment_and_is_recorded(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("STUDENT_RAG_JUDGE_PROVIDER", "deepinfra")
    monkeypatch.setenv("DEEPINFRA_API_KEY", "k")
    monkeypatch.chdir(tmp_path)
    client = GroqJudgeClient(request_fn=lambda key, prompt, config: ('{"answer_correctness": 1}', {}))
    result = client.judge({"question": "q", "answer": "a", "required_facts": [], "evidence": []})
    assert client.config.provider == "deepinfra"
    assert result["provider"] == "deepinfra"
