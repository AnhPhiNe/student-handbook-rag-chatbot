"""Warm-up must be opt-in, must not block the port, and must never kill boot."""

import threading

import pytest

from src.api import warmup


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    monkeypatch.delenv(warmup.WARMUP_ENV, raising=False)
    warmup._warmup_state.update({"status": "disabled", "seconds": None})


def test_warmup_stays_off_unless_the_deployment_asks_for_it():
    assert warmup.start_warmup() is None
    assert warmup.warmup_status()["status"] == "disabled"


def test_warmup_runs_on_a_background_thread(monkeypatch):
    monkeypatch.setenv(warmup.WARMUP_ENV, "true")
    started = threading.Event()

    class _Service:
        def warm(self):
            started.set()

    monkeypatch.setattr("src.api.deps.get_answer_service", lambda: _Service())
    thread = warmup.start_warmup()
    assert thread is not None
    assert thread.daemon, "a blocked warm-up must never keep the process alive"
    thread.join(timeout=5)
    assert started.is_set()
    assert warmup.warmup_status()["status"] == "ready"


def test_a_dependency_down_at_boot_does_not_fail_the_process(monkeypatch):
    monkeypatch.setenv(warmup.WARMUP_ENV, "true")

    class _Service:
        def warm(self):
            raise RuntimeError("qdrant unreachable")

    monkeypatch.setattr("src.api.deps.get_answer_service", lambda: _Service())
    warmup.run_warmup()  # must not raise: the lazy path still serves requests
    assert warmup.warmup_status()["status"] == "failed"
