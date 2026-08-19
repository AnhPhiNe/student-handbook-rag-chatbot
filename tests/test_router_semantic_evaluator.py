from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate_router_semantic_v2 import (
    _evaluate_case_with_retries,
    run_evaluation,
)


class _Normalizer:
    @staticmethod
    def replace_for_router(query: str) -> str:
        return query


def _case(case_id: str) -> dict:
    return {
        "id": case_id,
        "category": "test",
        "query": "Điều kiện tốt nghiệp là gì?",
        "expected_requests": [
            {
                "request_kind": "rag",
                "span_contains": ["Điều kiện tốt nghiệp"],
            }
        ],
    }


def _valid_decision() -> dict:
    return {
        "outcome": "execute",
        "route": "rag",
        "lookup_requests": [
            {
                "request_kind": "rag",
                "lookup_type": None,
                "intent": "open_question",
                "query_span": "Điều kiện tốt nghiệp là gì?",
                "slots": {},
                "cohort_refs": [],
            }
        ],
        "router_validation_errors": [],
        "router_cache_hit": False,
    }


def test_capacity_interruption_retries_same_case_after_retry_after() -> None:
    class _Router:
        def __init__(self) -> None:
            self.calls = 0

        def route(self, *_args, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                return {
                    "lookup_requests": [],
                    "router_validation_errors": [],
                    "router_fallback": "capacity",
                    "router_retry_after_seconds": 4.5,
                }
            return _valid_decision()

    router = _Router()
    sleeps: list[float] = []

    result = _evaluate_case_with_retries(
        router,
        _Normalizer(),
        _case("case-1"),
        max_attempts=3,
        sleep_fn=sleeps.append,
    )

    assert result["outcome"] == "passed"
    assert result["evaluation_attempts"] == 2
    assert router.calls == 2
    assert sleeps == [4.5]


def test_resume_skips_completed_and_reruns_provider_failure(tmp_path: Path) -> None:
    output_path = tmp_path / "results.json"
    output_path.write_text(
        json.dumps(
            {
                "results": [
                    {"id": "done", "outcome": "passed", "passed": True},
                    {
                        "id": "retry",
                        "outcome": "provider_failure",
                        "passed": False,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    class _Router:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def route(self, query: str, **_kwargs):
            self.queries.append(query)
            return _valid_decision()

    router = _Router()
    summary = run_evaluation(
        router,
        _Normalizer(),
        [_case("done"), _case("retry")],
        output_path=output_path,
        resume=True,
        max_attempts=2,
        sleep_fn=lambda _seconds: None,
    )

    assert router.queries == ["Điều kiện tốt nghiệp là gì?"]
    assert summary["passed"] == 2
    assert summary["provider_failed"] == 0
    persisted = json.loads(output_path.read_text(encoding="utf-8"))
    assert [result["id"] for result in persisted["results"]] == ["done", "retry"]


def test_resume_reruns_completed_case_from_older_prompt(tmp_path: Path) -> None:
    output_path = tmp_path / "results.json"
    output_path.write_text(
        json.dumps(
            {
                "results": [
                    {
                        "id": "stale",
                        "outcome": "passed",
                        "passed": True,
                        "router_prompt_version": "older-prompt",
                        "decision": _valid_decision(),
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    class _Router:
        def __init__(self) -> None:
            self.calls = 0

        def route(self, *_args, **_kwargs):
            self.calls += 1
            return _valid_decision()

    router = _Router()
    summary = run_evaluation(
        router,
        _Normalizer(),
        [_case("stale")],
        output_path=output_path,
        resume=True,
        max_attempts=1,
        sleep_fn=lambda _seconds: None,
    )

    assert router.calls == 1
    assert summary["passed"] == 1

