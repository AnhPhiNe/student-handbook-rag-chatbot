"""The judge runs the same model on Groq (default) or DeepInfra, and records which."""
import pytest

from src.evaluation.judge import JUDGE_METRICS, GroqJudgeClient, JudgeConfig, judge_key_pool


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


def test_workers_judge_every_case_once(monkeypatch, tmp_path) -> None:
    from src.evaluation.answers import judge_answers

    calls = []

    class Client:
        def judge(self, packet):
            calls.append(packet)
            return {"ok": True, "scores": {**{m: 1.0 for m in JUDGE_METRICS}, "unsupported_claim": False, "critical_false_pass": False}}

    monkeypatch.setenv("STUDENT_RAG_JUDGE_WORKERS", "4")
    cases = [{"id": f"C{i}", "query": "q", "required_facts": []} for i in range(10)]
    answers = [{"id": f"C{i}", "answer": "a", "status": "answered"} for i in range(10)]
    report = judge_answers(cases, answers, checkpoint_path=tmp_path / "cp.json", resume=False,
                           judge_client=Client(), checkpoint_context={"t": 1})
    assert len(calls) == 10
    assert [row["id"] for row in report["cases"]] == [c["id"] for c in cases]
