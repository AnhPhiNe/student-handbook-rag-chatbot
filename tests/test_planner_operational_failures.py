"""Offline regressions for planner operational failures; never call a provider."""
import json
from types import SimpleNamespace

import pytest

from src.common.key_pool import KeyPool, KeyPoolConfig, NoAvailableKey
from src.evaluation.deterministic import evaluate_deterministic
from src.retrieval.core import ai_router as router_module
from src.retrieval.core.ai_router import AIRouter, _RouterCompletion
from src.retrieval.core.planner_diagnostics import planner_diagnostics_scope


@pytest.fixture
def router(monkeypatch):
    monkeypatch.setattr(router_module, "load_project_env", lambda: None)
    monkeypatch.setenv("OPENAI_API_KEY", "offline-dummy-key")
    return AIRouter(
        cache_enabled=False, max_retries=1, reasoning_effort="low",
        key_pool_config=KeyPoolConfig(name="test", rpm_limit_per_key=600, state_path=None),
    )


@pytest.mark.parametrize("position", [401, 403, 429, 503, 1401, 1429])
def test_json_positions_are_not_http_statuses(position):
    with pytest.raises(json.JSONDecodeError) as caught:
        AIRouter._extract_json_object('{"x":' + ' ' * (position - 5) + '}')
    assert AIRouter._classify_error(caught.value) == "invalid_response"


@pytest.mark.parametrize(("status", "expected"), [
    (401, "auth_error"), (403, "auth_error"), (429, "rate_limit"),
    (503, "transient_error"), (408, "timeout"), (504, "timeout"), (400, "api_error"),
])
def test_real_http_status_takes_precedence(status, expected):
    error = RuntimeError("private body mentions quota and 401 and 429")
    error.response = SimpleNamespace(status_code=status)
    assert AIRouter._classify_error(error) == expected
    assert AIRouter.error_diagnostic(error)["http_status"] == status
    assert "private" not in json.dumps(AIRouter.error_diagnostic(error))


def _completion():
    return _RouterCompletion(json.dumps({
        "schema_version": "v1", "context_mode": "standalone", "out_of_domain": False,
        "tasks": [{"id": "t1", "question": "test", "mode": "rag", "intent": "open_question",
                   "cohorts": ["K51"], "slots": {}, "slot_spans": {}}],
    }), {"input": 1, "output": 1, "total": 2}, "stop")


def test_one_key_retries_timeout_then_succeeds(router, monkeypatch):
    calls = []
    def request(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            raise TimeoutError("secret-key-and-request-body")
        return _completion()
    monkeypatch.setattr(router, "_chat_completion", request)
    with planner_diagnostics_scope(True):
        result = router.plan("test", cohort="K51")
    assert len(calls) == 2
    assert not result.get("planner_fallback")
    diagnostic = result["planner_diagnostics"]
    assert diagnostic["attempts"][0]["error"]["type"] == "timeout"
    assert "secret-key" not in json.dumps(diagnostic)
    assert diagnostic["attempts"][1]["response"]["finish_reason"] == "stop"
    assert diagnostic["attempts"][1]["response"]["usage"]["total"] == 2


def test_successful_completion_saves_optional_counts_only_in_diagnostics(router, monkeypatch):
    response = _completion()
    completion = _RouterCompletion(response.text, response.usage, "stop", {"reasoning_tokens": 0})
    monkeypatch.setattr(router, "_chat_completion", lambda **kwargs: completion)
    with planner_diagnostics_scope(True):
        result = router.plan("test", cohort="K51")
    assert result["usage"] == {"input": 1, "output": 1, "total": 2}
    assert result["planner_diagnostics"]["attempts"][0]["response"]["token_details"] == {
        "reasoning_tokens": 0,
    }


@pytest.mark.parametrize("retries", [0, 1, 2])
def test_transient_retry_budget_is_bounded(router, monkeypatch, retries):
    router.max_retries = retries
    calls = []
    def request(**kwargs):
        calls.append(kwargs)
        raise TimeoutError("synthetic timeout")
    monkeypatch.setattr(router, "_chat_completion", request)
    result = router.plan("test", cohort="K51")
    assert len(calls) == retries + 1
    assert result["planner_error_type"] == "timeout"


def test_rejected_key_is_not_retried_or_cooled_as_rate_limit(router, monkeypatch):
    calls = []
    def request(**kwargs):
        calls.append(kwargs)
        error = RuntimeError("private credentials")
        error.status_code = 401
        raise error
    monkeypatch.setattr(router, "_chat_completion", request)
    result = router.plan("test", cohort="K51")
    assert len(calls) == 1
    assert result["planner_error_type"] == "auth_error"
    assert router.key_pool.acquire()  # No incorrect rate-limit cooldown.


def test_parser_failure_preserves_safe_truncation_metadata(router, monkeypatch):
    completion = _RouterCompletion('{"x":' + ' ' * 424 + '}',
                                   {"input": 100, "output": 768, "total": 868}, "length")
    monkeypatch.setattr(router, "_chat_completion", lambda **kwargs: completion)
    with planner_diagnostics_scope(True):
        result = router.plan("test", cohort="K51")
    assert result["planner_error_type"] == "invalid_response"
    failure = result["planner_diagnostics"]["attempts"][0]
    assert failure["stage"] == "parse"
    assert failure["error"]["json_position"] == 429
    assert failure["response"]["finish_reason"] == "length"
    assert failure["response"]["usage"]["output"] == 768
    assert completion.text not in json.dumps(failure)
    assert router.key_pool.acquire()


def test_real_rate_limit_rotates_to_another_key(router, monkeypatch):
    router.available_keys = ["dummy-a", "dummy-b"]
    router.key_pool = KeyPool(router.available_keys, router.key_pool.config)
    calls = []
    def request(**kwargs):
        calls.append(kwargs["api_key"])
        if len(calls) == 1:
            error = RuntimeError("private provider body")
            error.status_code = 429
            raise error
        return _completion()
    monkeypatch.setattr(router, "_chat_completion", request)
    with planner_diagnostics_scope(True):
        result = router.plan("test", cohort="K51")
    assert calls == ["dummy-a", "dummy-b"]
    assert result["planner_diagnostics"]["attempts"][0]["error"]["http_status"] == 429
    assert not result.get("planner_fallback")


def test_single_rate_limited_key_fails_fast_without_more_requests(router, monkeypatch):
    calls = []
    def request(**kwargs):
        calls.append(1)
        error = RuntimeError("private provider body")
        error.status_code = 429
        raise error
    monkeypatch.setattr(router, "_chat_completion", request)
    with planner_diagnostics_scope(True), pytest.raises(NoAvailableKey) as caught:
        router.plan("test", cohort="K51")
    assert calls == [1]
    attempts = caught.value.planner_diagnostics["attempts"]
    assert attempts[0]["error"]["http_status"] == 429
    assert attempts[-1]["stage"] == "key_acquire"
    assert "private provider body" not in json.dumps(attempts)


def _cases(n):
    return [{"id": f"synthetic-{i}", "query": "test", "cohort": "K51",
             "contract_version": "query-plan-grounded-outcome-v9", "accepted_outcomes": []}
            for i in range(n)]


@pytest.mark.parametrize("kind", ["key_error", "fallback"])
def test_eval_stops_operational_cascade_and_saves_partial_checkpoint(tmp_path, kind):
    calls = []
    class Pipeline:
        def _run_retrieval(self, *args, **kwargs):
            calls.append(1)
            if kind == "key_error":
                raise NoAvailableKey("private secret request text")
            return {"query_plan": {"tasks": []}, "planner_fallback": "safe_rag",
                    "planner_error_type": "invalid_response"}
    checkpoint = tmp_path / "checkpoint.json"
    report = evaluate_deterministic(
        _cases(87), pipeline_factory=Pipeline, checkpoint_path=checkpoint,
        checkpoint_context={"max_consecutive_runtime_failures": 3},
    )
    assert len(calls) == len(json.loads(checkpoint.read_text())) == 3
    assert report["summary"]["not_run_n"] == 84
    assert report["summary"]["completed"] is False
    assert report["summary"]["stopped_reason"] == "consecutive_runtime_failures"
    assert "private secret" not in json.dumps(report)


def test_eval_does_not_stop_on_wrong_answers_and_resets_failure_streak():
    calls = []
    class Pipeline:
        def _run_retrieval(self, *args, **kwargs):
            calls.append(1)
            if len(calls) in {1, 2, 4, 5}:
                raise TimeoutError("test")
            return {"query_plan": {"tasks": []}}  # Wrong answer, not an operational error.
    report = evaluate_deterministic(_cases(6), pipeline_factory=Pipeline,
        checkpoint_context={"max_consecutive_runtime_failures": 3})
    assert report["summary"]["completed"] is True
    assert report["summary"]["passed"] == 0
    assert len(calls) == 6
