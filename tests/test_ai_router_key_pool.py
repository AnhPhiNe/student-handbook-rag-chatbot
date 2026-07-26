from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from src.retrieval.core.ai_router import (
    GroqRouterKeyPool,
    GroqRouterPoolConfig,
    _retry_after_seconds,
)


class _Response:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers


class _RateLimitError(Exception):
    def __init__(self, message: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.response = _Response(headers or {})


def _pool(tmp_path: Path, **overrides) -> GroqRouterKeyPool:
    values = {
        "rpm_limit_per_key": 30,
        "rpd_limit_per_key": 1000,
        "tpm_limit_per_key": 8000,
        "tpd_limit_per_key": 200000,
        "cooldown_seconds": 65.0,
        "state_path": str(tmp_path / "router-state.json"),
        "wait_when_limited": False,
    }
    values.update(overrides)
    return GroqRouterKeyPool(
        ["router-key"],
        model_name="qwen/test",
        config=GroqRouterPoolConfig(**values),
    )


def _saved_key_state(pool: GroqRouterKeyPool) -> dict:
    value = json.loads(pool.config.state_path and Path(pool.config.state_path).read_text())
    return next(iter(value["keys"].values()))


def test_retry_after_uses_header_before_message() -> None:
    exc = _RateLimitError(
        "Please try again in 9m30s.",
        {"retry-after": "12.5"},
    )

    assert _retry_after_seconds(exc) == pytest.approx(12.5)


def test_retry_after_parses_compound_duration_from_message() -> None:
    exc = _RateLimitError("Rate limit reached. Please try again in 1m30.5s.")

    assert _retry_after_seconds(exc) == pytest.approx(90.5)


def test_record_rate_limit_persists_server_availability(tmp_path: Path) -> None:
    pool = _pool(tmp_path)
    key_id = pool.fingerprint("router-key")
    before = time.time()

    pool.record_rate_limit(key_id, retry_after_seconds=123.0)

    state = _saved_key_state(pool)
    assert state["unavailable_reason"] == "api_rate_limit"
    assert state["available_at"] >= before + 122.0
    assert state["cooldown_until"] == state["available_at"]


def test_daily_token_exhaustion_reports_retry_and_reason(tmp_path: Path) -> None:
    pool = _pool(tmp_path, tpd_limit_per_key=100)
    pool.acquire_key(90)

    with pytest.raises(
        RuntimeError,
        match=r"daily_token_quota_exhausted_retry_after_\d+\.\d+s",
    ):
        pool.acquire_key(20)

    state = _saved_key_state(pool)
    assert state["unavailable_reason"] == "daily_token_quota"
    assert state["available_at"] > time.time()
