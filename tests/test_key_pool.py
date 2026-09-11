from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from src.common.key_pool import (
    KeyPool,
    KeyPoolConfig,
    NoAvailableKey,
    key_fingerprint,
    retry_after_seconds,
)


class _Response:
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers


class _RateLimitError(Exception):
    def __init__(self, message: str, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.response = _Response(headers or {})


def _pool(tmp_path: Path, keys: list[str] | None = None, **overrides) -> KeyPool:
    values = {
        "name": "test",
        "rpm_limit_per_key": 30,
        "rpd_limit_per_key": 1000,
        "tpm_limit_per_key": 8000,
        "tpd_limit_per_key": 200000,
        "cooldown_seconds": 65.0,
        "state_path": str(tmp_path / "state.json"),
    }
    values.update(overrides)
    return KeyPool(keys or ["key-a"], KeyPoolConfig(**values), scope="model/test")


def _saved_key_state(tmp_path: Path) -> dict:
    value = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    return next(iter(value["keys"].values()))


def test_retry_after_uses_header_before_message() -> None:
    exc = _RateLimitError("Please try again in 9m30s.", {"retry-after": "12.5"})

    assert retry_after_seconds(exc) == pytest.approx(12.5)


def test_retry_after_parses_compound_duration_from_message() -> None:
    exc = _RateLimitError("Rate limit reached. Please try again in 1m30.5s.")

    assert retry_after_seconds(exc) == pytest.approx(90.5)


def test_retry_after_reads_a_plain_http_response() -> None:
    assert retry_after_seconds(_Response({"Retry-After": "7"})) == pytest.approx(7.0)
    assert retry_after_seconds(_Response({})) is None


def test_least_used_key_is_chosen_and_limits_are_per_key(tmp_path: Path) -> None:
    pool = _pool(tmp_path, ["key-a", "key-b"], rpm_limit_per_key=1)

    assert pool.acquire()[0] == "key-a"
    assert pool.acquire()[0] == "key-b"
    with pytest.raises(NoAvailableKey, match=r"all_test_keys_temporarily_limited_retry_after_"):
        pool.acquire()


def test_excluded_keys_are_skipped(tmp_path: Path) -> None:
    pool = _pool(tmp_path, ["key-a", "key-b"], state_path=None)

    key, _, _ = pool.acquire(excluded={key_fingerprint("key-a")})

    assert key == "key-b"


def test_record_rate_limit_uses_provider_retry_time_and_persists(tmp_path: Path) -> None:
    pool = _pool(tmp_path)
    before = time.time()

    pool.record_rate_limit(key_fingerprint("key-a"), retry_after_seconds=123.0)

    state = _saved_key_state(tmp_path)
    assert state["cooldown_until"] >= before + 122.0
    assert state["last_error_type"] == "rate_limit"
    with pytest.raises(NoAvailableKey, match="temporarily_limited"):
        pool.acquire()


def test_daily_token_exhaustion_reports_retry_and_reason(tmp_path: Path) -> None:
    pool = _pool(tmp_path, tpd_limit_per_key=100)
    pool.acquire(90)

    with pytest.raises(
        NoAvailableKey,
        match=r"all_test_keys_daily_token_quota_exhausted_retry_after_\d+\.\d+s",
    ):
        pool.acquire(20)


def test_request_larger_than_the_minute_token_limit_fails_fast(tmp_path: Path) -> None:
    pool = _pool(tmp_path, tpm_limit_per_key=100)

    with pytest.raises(NoAvailableKey, match="test_request_exceeds_per_key_tpm_limit"):
        pool.acquire(101)


def test_success_charges_tokens_beyond_the_reservation(tmp_path: Path) -> None:
    pool = _pool(tmp_path)
    _, key_id, _ = pool.acquire(100)

    pool.record_success(key_id, actual_tokens=150, reserved_tokens=100)

    state = _saved_key_state(tmp_path)
    assert state["tokens_today"] == 150
    assert state["minute_events"][-1]["tokens"] == 150


def test_state_survives_a_restart_and_ignores_unknown_fields(tmp_path: Path) -> None:
    pool = _pool(tmp_path, rpm_limit_per_key=1)
    pool.acquire()
    saved = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    next(iter(saved["keys"].values()))["legacy_field"] = "x"
    (tmp_path / "state.json").write_text(json.dumps(saved), encoding="utf-8")

    restarted = _pool(tmp_path, rpm_limit_per_key=1)

    with pytest.raises(NoAvailableKey, match="temporarily_limited"):
        restarted.acquire()
    assert "legacy_field" not in _saved_key_state(tmp_path)
