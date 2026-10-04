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


def test_retry_failed_judges_only_the_failed_rows(monkeypatch, tmp_path) -> None:
    from src.evaluation.answers import judge_answers

    outcomes = {"C0": True, "C1": False}

    class Client:
        def __init__(self):
            self.seen = []

        def judge(self, packet):
            self.seen.append(packet["case_id"] if "case_id" in packet else packet.get("id"))
            ok = outcomes.pop(next(iter(outcomes)), True) if outcomes else True
            scores = {**{m: 1.0 for m in JUDGE_METRICS}, "unsupported_claim": False, "critical_false_pass": False}
            return {"ok": True, "scores": scores} if ok else {"ok": False, "error": "timeout"}

    cases = [{"id": f"C{i}", "query": "q", "required_facts": []} for i in range(2)]
    answers = [{"id": f"C{i}", "answer": "a", "status": "answered"} for i in range(2)]
    kwargs = dict(checkpoint_path=tmp_path / "cp.json", checkpoint_context={"t": 1})
    first = judge_answers(cases, answers, resume=False, judge_client=Client(), **kwargs)
    assert first["summary"]["judged_n"] == 1
    client = Client()
    second = judge_answers(cases, answers, resume=True, judge_client=client, retry_failed=True, **kwargs)
    assert len(client.seen) == 1
    assert second["summary"]["judged_n"] == 2


def test_answer_workers_answer_every_case_once_in_dataset_order(monkeypatch, tmp_path):
    import threading
    from src.evaluation.answers import generate_answers

    seen, lock = [], threading.Lock()

    class Pipeline:
        def answer(self, query, **kwargs):
            with lock:
                seen.append(query)
            return {"status": "answered", "answer": f"a:{query}"}

    monkeypatch.setenv("STUDENT_RAG_ANSWER_WORKERS", "4")
    cases = [{"id": f"C{i}", "query": f"q{i}", "cohort": "K51"} for i in range(12)]
    report = generate_answers(cases, cache_path=tmp_path / "answers.json", resume=False,
                              pipeline_factory=Pipeline, checkpoint_context={"t": 1})
    assert sorted(seen) == sorted(case["query"] for case in cases)
    assert [row["id"] for row in report["cases"]] == [case["id"] for case in cases]
    assert all(row["status"] == "answered" for row in report["cases"])
