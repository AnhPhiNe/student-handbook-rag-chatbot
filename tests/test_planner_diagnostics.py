from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.retrieval.core.ai_router as ai_router_module
from src.evaluation.suites import evaluate_deterministic_v2
from src.retrieval.core.ai_router import (
    AIRouter,
    PLANNER_DIAGNOSTIC_SCHEMA_VERSION,
    _build_planner_diagnostics,
    _planner_decision_snapshot,
    planner_diagnostics_scope,
)
from src.retrieval.core.query_plan import (
    QUERY_PLAN_NORMALIZER_VERSION,
    QUERY_PLAN_SCHEMA_VERSION,
)


def _raw_task(label: str) -> dict:
    return {
        "id": "t1",
        "question": f"private task question {label}",
        "mode": "rag",
        "intent": "open_question",
        "lookup_type": "student_service",
        "slots": {
            "service": f"service-{label}",
            "unknown": {"secret": "nested secret"},
        },
        "slot_spans": {
            "service": f"service-{label}",
            "unknown": {"history": "private history"},
        },
        "cohorts": ["K51"],
        "validation_errors": ["private validation detail"],
        "source_document": "private source document",
    }


def _raw_payload(label: str) -> dict:
    return {
        "route": "structured",
        "execution_mode": "structured",
        "intent": "direct_value",
        "lookup_type": "student_service",
        "schema_version": QUERY_PLAN_SCHEMA_VERSION,
        "context_mode": "standalone",
        "normalized_query": "private normalized query",
        "standalone_query": "private history rewrite",
        "chat_history": [{"role": "user", "content": "private history"}],
        "api_key": "secret-api-key",
        "usage": {"total": 123},
        "answer": "private answer",
        "tasks": [_raw_task(label)],
    }


def _fake_router(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AIRouter:
    monkeypatch.setenv("GROQ_API_KEYS", "diagnostic-test-key")
    return AIRouter(
        model_name="qwen/qwen3.8-27b",
        cache_enabled=False,
        key_pool_config={"state_path": str(tmp_path / "router-state.json")},
    )


def test_planner_diagnostic_snapshot_is_whitelisted_and_detached() -> None:
    raw = _raw_payload("A")
    snapshot = _planner_decision_snapshot(raw)

    assert snapshot["tasks"][0]["slots"] == {"service": "service-A"}
    assert snapshot["tasks"][0]["slot_spans"] == {"service": "service-A"}
    assert "question" not in snapshot["tasks"][0]
    assert "source_document" not in snapshot["tasks"][0]
    assert "normalized_query" not in snapshot
    assert "standalone_query" not in snapshot
    assert "chat_history" not in snapshot
    assert "api_key" not in snapshot
    assert "usage" not in snapshot
    assert "answer" not in snapshot
    assert "unknown" not in snapshot["tasks"][0]["slots"]
    assert "unknown" not in snapshot["tasks"][0]["slot_spans"]

    raw["tasks"][0]["slots"]["service"] = "mutated"
    assert snapshot["tasks"][0]["slots"] == {"service": "service-A"}


def test_planner_diagnostics_capture_raw_and_normalized_without_aliasing() -> None:
    raw = _raw_payload("A")
    normalized = {
        "schema_version": QUERY_PLAN_SCHEMA_VERSION,
        "context_mode": "standalone",
        "out_of_domain": False,
        "tasks": [
            {
                "id": "t1",
                "mode": "rag",
                "intent": "open_question",
                "lookup_type": None,
                "slots": {},
                "slot_spans": {},
                "cohorts": ["K51"],
                "validation_errors": [],
            }
        ],
    }
    diagnostics = _build_planner_diagnostics(
        [
            {
                "label": "initial",
                "raw": _planner_decision_snapshot(raw),
                "normalized": _planner_decision_snapshot(normalized),
            }
        ],
        normalized,
    )

    assert diagnostics["schema_version"] == PLANNER_DIAGNOSTIC_SCHEMA_VERSION
    assert diagnostics["versions"]["query_plan_schema_version"] == QUERY_PLAN_SCHEMA_VERSION
    assert diagnostics["versions"]["query_plan_normalizer_version"] == QUERY_PLAN_NORMALIZER_VERSION
    assert diagnostics["attempts"][0]["raw"]["tasks"][0]["slots"]
    assert diagnostics["attempts"][0]["normalized"]["tasks"][0]["slots"] == {}

    diagnostics["attempts"][0]["raw"]["tasks"][0]["slots"]["service"] = "changed"
    assert diagnostics["attempts"][0]["normalized"]["tasks"][0]["slots"] == {}
    assert normalized["tasks"][0]["slots"] == {}

    serialized = json.dumps(diagnostics, ensure_ascii=False)
    for private_value in (
        "private normalized query",
        "private history rewrite",
        "private history",
        "private task question A",
        "private source document",
        "secret-api-key",
        "private answer",
    ):
        assert private_value not in serialized


def test_airouter_planner_diagnostics_are_opt_in(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = _raw_payload("A")

    class _FakeGroq:
        def __init__(self, **_kwargs) -> None:
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **_create_kwargs: SimpleNamespace(
                        choices=[
                            SimpleNamespace(
                                message=SimpleNamespace(
                                    content=json.dumps(payload, ensure_ascii=False)
                                )
                            )
                        ],
                        usage=None,
                    )
                )
            )

    monkeypatch.setattr(ai_router_module, "Groq", _FakeGroq)
    router = _fake_router(monkeypatch, tmp_path)

    default_result = router.plan("synthetic diagnostic query", cohort="K51")
    assert "planner_diagnostics" not in default_result

    with planner_diagnostics_scope(True):
        captured = router.plan("synthetic diagnostic query", cohort="K51")
    diagnostics = captured["planner_diagnostics"]
    assert diagnostics["cache_hit"] is False
    assert len(diagnostics["attempts"]) == 1
    assert diagnostics["attempts"][0]["label"] == "initial"
    assert diagnostics["attempts"][0]["raw"]["tasks"][0]["slots"] == {
        "service": "service-A"
    }
    assert diagnostics["attempts"][0]["normalized"]["tasks"][0]["slots"] == {}


def test_airouter_diagnostics_are_request_isolated_under_concurrency(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class _Completions:
        @staticmethod
        def create(**kwargs):
            prompt = str(kwargs["messages"][1]["content"])
            label = "A" if "SYNTHETIC_A" in prompt else "B"
            payload = _raw_payload(label)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            content=json.dumps(payload, ensure_ascii=False)
                        )
                    )
                ],
                usage=None,
            )

    class _FakeGroq:
        def __init__(self, **_kwargs) -> None:
            self.chat = SimpleNamespace(completions=_Completions())

    monkeypatch.setattr(ai_router_module, "Groq", _FakeGroq)
    monkeypatch.setenv("GROQ_API_KEYS", "diagnostic-test-key")

    def run(label: str) -> dict:
        router = AIRouter(
            model_name="qwen/qwen3.8-27b",
            cache_enabled=False,
            key_pool_config={"state_path": str(tmp_path / f"{label}.json")},
        )
        with planner_diagnostics_scope(label == "A"):
            return router.plan(f"SYNTHETIC_{label}", cohort="K51")

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, ("A", "B")))

    assert "planner_diagnostics" in results[0]
    assert "planner_diagnostics" not in results[1]
    assert (
        results[0]["planner_diagnostics"]["attempts"][0]["raw"]["tasks"][0][
            "slots"
        ]["service"]
        == "service-A"
    )


def test_deterministic_eval_context_propagates_capture_to_rows(tmp_path: Path) -> None:
    calls: list[bool] = []

    class Pipeline:
        def _run_retrieval(
            self,
            query: str,
            cohort: str | None = None,
            chat_history: list[dict[str, str]] | None = None,
        ) -> dict:
            del query, cohort, chat_history
            enabled = ai_router_module._planner_diagnostics_scope.get()
            calls.append(enabled)
            result = {
                "query_plan": {
                    "tasks": [
                        {
                            "mode": "rag",
                            "lookup_type": None,
                        }
                    ]
                },
                "task_results": [],
                "needs_llm_answer": True,
            }
            if enabled:
                result["planner_diagnostics"] = {"schema_version": "test"}
            return result

    case = {
        "id": "synthetic-diagnostic",
        "query": "synthetic query",
        "cohort": "K51",
        "expected_llm_called": True,
        "expected_plan": {"task_count": 1, "allowed_modes": ["rag"]},
    }
    history_case = {
        **case,
        "id": "synthetic-diagnostic-history",
        "chat_history": [{"role": "user", "content": "private history"}],
    }
    checkpoint = tmp_path / "diagnostics.json"
    report = evaluate_deterministic_v2(
        [case, history_case],
        pipeline_factory=Pipeline,
        checkpoint_path=checkpoint,
        checkpoint_context={"capture_planner_diagnostics": True},
    )

    assert calls == [True, False]
    assert report["cases"][0]["planner_diagnostics"] == {"schema_version": "test"}
    assert "planner_diagnostics" not in report["cases"][1]
    assert json.loads(checkpoint.read_text(encoding="utf-8"))[0][
        "planner_diagnostics"
    ] == {"schema_version": "test"}
