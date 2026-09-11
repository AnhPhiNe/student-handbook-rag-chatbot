"""Quota-aware rotation over several API keys of one provider.

Each key keeps a 60-second window of (time, tokens) events and per-day request
and token counters. acquire() returns the least-used key that is under every
configured limit; a provider rate limit puts that key on cooldown. With a
state_path the counters survive restarts. Raw keys are never stored, only a
SHA-256 fingerprint.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

WINDOW_SECONDS = 60.0
_NEW_KEY_STATE: dict[str, Any] = {
    "minute_events": [],
    "requests_today": 0,
    "tokens_today": 0,
    "daily_reset_date": "",
    "cooldown_until": 0.0,
    "last_used_at": 0.0,
    "failure_count": 0,
    "last_error_type": None,
}


def key_fingerprint(key: str) -> str:
    """Non-secret identifier for an API key: the first 12 hex digits of its SHA-256."""

    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


class NoAvailableKey(RuntimeError):
    """Every key is over a limit, cooling down, or excluded."""


@dataclass(frozen=True)
class KeyPoolConfig:
    """Per-key limits for one provider; a limit left as None is not enforced."""

    name: str  # appears in errors, e.g. all_gemini_keys_temporarily_limited_...
    rpm_limit_per_key: int
    rpd_limit_per_key: int | None = None
    tpm_limit_per_key: int | None = None
    tpd_limit_per_key: int | None = None
    cooldown_seconds: float = 65.0  # used when the provider gives no retry time
    state_path: str | None = None  # None keeps state in memory only
    wait_when_limited: bool = False
    max_wait_seconds: float | None = None  # total wait budget; None waits indefinitely


class KeyPool:
    """Pick API keys under per-key request and token limits."""

    def __init__(
        self, keys: list[str], config: KeyPoolConfig, *, scope: str = ""
    ) -> None:
        self.keys = list(dict.fromkeys(key for key in keys if key))
        self.config = config
        # The model name: one state file can then hold separate quotas per model.
        self.scope = scope
        self._lock = threading.Lock()
        self._state_path = Path(config.state_path) if config.state_path else None
        self._states = self._load()
        for key in self.keys:
            self._state(key_fingerprint(key))
        self._save()

    @property
    def key_count(self) -> int:
        return len(self.keys)

    def acquire(
        self, estimated_tokens: int = 0, *, excluded: set[str] | None = None
    ) -> tuple[str, str, int]:
        """Reserve a request on the least-used eligible key: (key, key_id, index)."""

        config = self.config
        tokens = max(0, int(estimated_tokens))
        if config.tpm_limit_per_key is not None and tokens > config.tpm_limit_per_key:
            raise NoAvailableKey(f"{config.name}_request_exceeds_per_key_tpm_limit")
        deadline = (
            None
            if config.max_wait_seconds is None
            else time.monotonic() + config.max_wait_seconds
        )
        while True:
            with self._lock:
                now = time.time()
                today = date.today().isoformat()
                candidates: list[tuple[int, int, float, int, str]] = []
                ready_at: list[float] = []
                daily_reasons: set[str] = set()
                for index, key in enumerate(self.keys):
                    key_id = key_fingerprint(key)
                    if excluded and key_id in excluded:
                        continue
                    state = self._refresh(self._state(key_id), now, today)
                    reason = self._daily_limit_reason(state, tokens)
                    if reason:
                        daily_reasons.add(reason)
                        continue
                    if state["cooldown_until"] > now:
                        ready_at.append(state["cooldown_until"])
                        continue
                    events = state["minute_events"]
                    minute_tokens = sum(int(event["tokens"]) for event in events)
                    over_tpm = (
                        config.tpm_limit_per_key is not None
                        and minute_tokens + tokens > config.tpm_limit_per_key
                    )
                    if len(events) >= config.rpm_limit_per_key or over_tpm:
                        ready_at.append(
                            events[0]["at"] + WINDOW_SECONDS if events else now + 1.0
                        )
                        continue
                    candidates.append(
                        (
                            len(events),
                            minute_tokens,
                            state["last_used_at"],
                            index,
                            key_id,
                        )
                    )

                if candidates:
                    _, _, _, index, key_id = min(candidates)
                    self._record_request(key_id, now, today, tokens)
                    return self.keys[index], key_id, index
                if daily_reasons and not ready_at:  # every key is out for the day
                    reason = (
                        daily_reasons.pop()
                        if len(daily_reasons) == 1
                        else "daily_quota"
                    )
                    raise NoAvailableKey(
                        f"all_{config.name}_keys_{reason}_exhausted_"
                        f"retry_after_{_seconds_until_local_midnight():.1f}s"
                    )
                wait = max(
                    0.1, min(WINDOW_SECONDS, min(ready_at, default=now + 1.0) - now)
                )

            out_of_budget = deadline is not None and time.monotonic() + wait > deadline
            if not config.wait_when_limited or out_of_budget:
                raise NoAvailableKey(
                    f"all_{config.name}_keys_temporarily_limited_retry_after_{wait:.1f}s"
                )
            time.sleep(wait)

    def record_success(
        self, key_id: str, *, actual_tokens: int = 0, reserved_tokens: int = 0
    ) -> None:
        """Charge tokens used beyond the reservation and clear the failure streak."""

        with self._lock:
            state = self._state(key_id)
            extra = max(0, int(actual_tokens) - int(reserved_tokens))
            if extra:
                state["tokens_today"] += extra
                if state["minute_events"]:
                    state["minute_events"][-1]["tokens"] += extra
            state["failure_count"] = 0
            state["last_error_type"] = None
            self._save()

    def record_failure(self, key_id: str, error_type: str) -> None:
        with self._lock:
            state = self._state(key_id)
            state["failure_count"] += 1
            state["last_error_type"] = error_type
            self._save()

    def record_rate_limit(
        self, key_id: str, *, retry_after_seconds: float | None = None
    ) -> None:
        """Cool a key down for the provider's retry time, or the configured default."""

        with self._lock:
            state = self._state(key_id)
            cooldown = (
                max(0.1, float(retry_after_seconds))
                if retry_after_seconds is not None
                else self.config.cooldown_seconds
            )
            state["cooldown_until"] = time.time() + cooldown
            state["failure_count"] += 1
            state["last_error_type"] = "rate_limit"
            self._save()

    def _daily_limit_reason(self, state: dict[str, Any], tokens: int) -> str | None:
        config = self.config
        if (
            config.rpd_limit_per_key is not None
            and state["requests_today"] >= config.rpd_limit_per_key
        ):
            return "daily_request_quota"
        if (
            config.tpd_limit_per_key is not None
            and state["tokens_today"] + tokens > config.tpd_limit_per_key
        ):
            return "daily_token_quota"
        return None

    @staticmethod
    def _refresh(state: dict[str, Any], now: float, today: str) -> dict[str, Any]:
        state["minute_events"] = [
            event
            for event in state["minute_events"]
            if now - float(event["at"]) < WINDOW_SECONDS
        ]
        if state["daily_reset_date"] != today:
            state["daily_reset_date"] = today
            state["requests_today"] = 0
            state["tokens_today"] = 0
        return state

    def _record_request(self, key_id: str, now: float, today: str, tokens: int) -> None:
        state = self._state(key_id)
        state["minute_events"].append({"at": now, "tokens": tokens})
        state["requests_today"] += 1
        state["tokens_today"] += tokens
        state["daily_reset_date"] = today
        state["last_used_at"] = now
        self._save()

    def _state(self, key_id: str) -> dict[str, Any]:
        name = f"{self.scope}:{key_id}" if self.scope else key_id
        state = self._states.get(name)
        if not isinstance(state, dict) or state.keys() != _NEW_KEY_STATE.keys():
            # Keep known fields only; ones missing from older state files default.
            stored = state if isinstance(state, dict) else {}
            state = {
                field: stored.get(field, copy.deepcopy(default))
                for field, default in _NEW_KEY_STATE.items()
            }
            self._states[name] = state
        return state

    def _load(self) -> dict[str, Any]:
        if not self._state_path or not self._state_path.exists():
            return {}
        try:
            value = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        keys = value.get("keys") if isinstance(value, dict) else None
        return keys if isinstance(keys, dict) else {}

    def _save(self) -> None:
        if not self._state_path:
            return
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(
                json.dumps({"keys": self._states}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            return


def _seconds_until_local_midnight() -> float:
    local_now = datetime.now().astimezone()
    midnight = (local_now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(0.0, midnight.timestamp() - local_now.timestamp())


_DURATION_TOKEN_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(ms|[hms])", re.IGNORECASE)
_RETRY_TEXT_RE = re.compile(
    r"(?:try again in|retry after)\s+((?:\d+(?:\.\d+)?\s*(?:ms|[hms])\s*)+)",
    re.IGNORECASE,
)
_UNIT_SECONDS = {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 0.001}


def _parse_duration_seconds(value: Any) -> float | None:
    """Parse '12.5', '1m30.5s' or '250ms' into seconds."""

    text = str(value or "").strip()
    if not text:
        return None
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    parts = _DURATION_TOKEN_RE.findall(text)
    if not parts:
        return None
    return sum(float(amount) * _UNIT_SECONDS[unit.lower()] for amount, unit in parts)


def retry_after_seconds(error_or_response: Any) -> float | None:
    """Seconds the provider asked us to wait, from rate-limit headers or error text.

    Accepts an HTTP response or an exception that carries one in `.response`
    (Groq SDK errors do). Groq's reset headers use durations such as '1m30s';
    Retry-After may also be an HTTP date.
    """

    response = (
        error_or_response
        if hasattr(error_or_response, "headers")
        else getattr(error_or_response, "response", None)
    )
    headers = getattr(response, "headers", None) or {}
    for name in (
        "retry-after",
        "x-ratelimit-reset-tokens",
        "x-ratelimit-reset-requests",
    ):
        value = headers.get(name)
        if value is None:
            value = headers.get(name.title())
        seconds = _parse_duration_seconds(value)
        if seconds is not None:
            return seconds
        if name == "retry-after" and value:
            try:
                retry_at = parsedate_to_datetime(str(value))
            except (TypeError, ValueError, OverflowError):
                continue
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            return max(0.0, retry_at.timestamp() - time.time())
    if isinstance(error_or_response, BaseException):
        match = _RETRY_TEXT_RE.search(str(error_or_response))
        if match:
            return _parse_duration_seconds(match.group(1))
    return None
