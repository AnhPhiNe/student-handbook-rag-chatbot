from __future__ import annotations

import hashlib
import json
import os
import queue
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from src.common.env_loader import load_project_env


@dataclass(frozen=True)
class GeminiKeyPoolConfig:
    rpm_limit_per_key: int = 12
    rpd_limit_per_key: int = 450
    cooldown_on_rate_limit_seconds: float = 65.0
    state_path: str = "data/cache/gemini_key_state.json"
    wait_when_all_keys_limited: bool = True

    @classmethod
    def from_config(cls, config: dict[str, Any] | None) -> "GeminiKeyPoolConfig":
        config = config or {}
        state_path = config.get("state_path", "data/cache/gemini_key_state.json")
        return cls(
            rpm_limit_per_key=max(1, int(config.get("rpm_limit_per_key", 12))),
            rpd_limit_per_key=max(1, int(config.get("rpd_limit_per_key", 450))),
            cooldown_on_rate_limit_seconds=max(
                1.0, float(config.get("cooldown_on_rate_limit_seconds", 65.0))
            ),
            state_path=str(state_path),
            wait_when_all_keys_limited=bool(config.get("wait_when_all_keys_limited", True)),
        )


class GeminiKeyPool:
    """Quota-aware load balancer for multiple Gemini API keys."""

    def __init__(
        self,
        keys: list[str],
        *,
        model_name: str,
        config: GeminiKeyPoolConfig | dict[str, Any] | None = None,
    ) -> None:
        self.keys = [key for key in keys if key]
        if not self.keys:
            raise RuntimeError("No Gemini API keys available.")
        self.model_name = model_name
        self.config = (
            config
            if isinstance(config, GeminiKeyPoolConfig)
            else GeminiKeyPoolConfig.from_config(config)
        )
        self._lock = threading.Lock()
        self._state_path = Path(self.config.state_path) if self.config.state_path else None
        self._state: dict[str, Any] = {"keys": {}}
        self._load_state()
        self._ensure_key_states()

    def acquire_key(self) -> tuple[str, str, int]:
        """Return a healthy key and record that a request is about to be sent."""
        while True:
            with self._lock:
                now = time.time()
                today = date.today().isoformat()
                self._reset_daily_counts(today)
                self._prune_request_windows(now)

                candidates: list[tuple[int, float, int, str]] = []
                wait_until_values: list[float] = []
                all_daily_exhausted = True

                for index, key in enumerate(self.keys):
                    key_id = self.fingerprint(key)
                    state = self._key_state(key_id)
                    daily_count = int(state.get("daily_count", 0))
                    if daily_count < self.config.rpd_limit_per_key:
                        all_daily_exhausted = False

                    cooldown_until = float(state.get("cooldown_until", 0.0))
                    if cooldown_until > now:
                        wait_until_values.append(cooldown_until)
                        continue
                    if daily_count >= self.config.rpd_limit_per_key:
                        continue

                    timestamps = list(state.get("request_timestamps", []))
                    if len(timestamps) >= self.config.rpm_limit_per_key:
                        wait_until_values.append(float(timestamps[0]) + 60.0)
                        continue

                    candidates.append(
                        (
                            len(timestamps),
                            float(state.get("last_used_at", 0.0)),
                            index,
                            key_id,
                        )
                    )

                if candidates:
                    _, _, index, key_id = min(candidates)
                    self._record_attempt(key_id, now, today)
                    return self.keys[index], key_id, index

                if all_daily_exhausted:
                    raise RuntimeError("all_gemini_keys_daily_quota_exhausted")

                wait_until = min(wait_until_values) if wait_until_values else now + 1.0
                wait_seconds = max(0.1, min(60.0, wait_until - now))

            if not self.config.wait_when_all_keys_limited:
                raise RuntimeError(
                    f"all_gemini_keys_temporarily_limited_retry_after_{wait_seconds:.1f}s"
                )
            time.sleep(wait_seconds)

    def record_success(self, key_id: str) -> None:
        with self._lock:
            state = self._key_state(key_id)
            state["failure_count"] = 0
            state["last_error_type"] = None
            self._save_state()

    def record_failure(self, key_id: str, error_type: str | None) -> None:
        with self._lock:
            state = self._key_state(key_id)
            state["failure_count"] = int(state.get("failure_count", 0)) + 1
            state["last_error_type"] = error_type or "unknown"
            self._save_state()

    def record_rate_limit(self, key_id: str, error_type: str | None = "rate_limit") -> None:
        with self._lock:
            state = self._key_state(key_id)
            state["cooldown_until"] = time.time() + self.config.cooldown_on_rate_limit_seconds
            state["failure_count"] = int(state.get("failure_count", 0)) + 1
            state["last_error_type"] = error_type or "rate_limit"
            self._save_state()

    def fingerprint(self, key: str) -> str:
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]

    def _state_key(self, key_id: str) -> str:
        return f"{self.model_name}:{key_id}"

    def _key_state(self, key_id: str) -> dict[str, Any]:
        states = self._state.setdefault("keys", {})
        state_key = self._state_key(key_id)
        if state_key not in states:
            states[state_key] = self._new_key_state()
        return states[state_key]

    def _new_key_state(self) -> dict[str, Any]:
        return {
            "request_timestamps": [],
            "daily_count": 0,
            "daily_reset_date": date.today().isoformat(),
            "cooldown_until": 0.0,
            "last_used_at": 0.0,
            "failure_count": 0,
            "last_error_type": None,
        }

    def _ensure_key_states(self) -> None:
        for key in self.keys:
            self._key_state(self.fingerprint(key))
        self._save_state()

    def _record_attempt(self, key_id: str, now: float, today: str) -> None:
        state = self._key_state(key_id)
        state["request_timestamps"] = [
            timestamp
            for timestamp in state.get("request_timestamps", [])
            if now - float(timestamp) < 60.0
        ]
        state["request_timestamps"].append(now)
        state["daily_reset_date"] = today
        state["daily_count"] = int(state.get("daily_count", 0)) + 1
        state["last_used_at"] = now
        self._save_state()

    def _reset_daily_counts(self, today: str) -> None:
        for state in self._state.get("keys", {}).values():
            if state.get("daily_reset_date") != today:
                state["daily_reset_date"] = today
                state["daily_count"] = 0

    def _prune_request_windows(self, now: float) -> None:
        for state in self._state.get("keys", {}).values():
            state["request_timestamps"] = [
                timestamp
                for timestamp in state.get("request_timestamps", [])
                if now - float(timestamp) < 60.0
            ]

    def _load_state(self) -> None:
        if not self._state_path or not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(data, dict):
            keys = data.get("keys")
            if isinstance(keys, dict):
                self._state = {"keys": keys}

    def _save_state(self) -> None:
        if not self._state_path:
            return
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(
                json.dumps(self._state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            return


class GeminiClient:
    def __init__(
        self,
        model_name: str = "gemini-2.5-flash",
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
        max_retries: int = 3,
        retry_base_delay_seconds: float = 2,
        retry_max_delay_seconds: float = 20,
        request_timeout_seconds: float = 60,
        api_key_env_var: str = "GEMINI_API_KEY",
        key_pool_config: GeminiKeyPoolConfig | dict[str, Any] | None = None,
    ) -> None:
        load_project_env()
        self.api_key_env_var = api_key_env_var

        keys_str = os.environ.get(f"{api_key_env_var}S") or os.environ.get(api_key_env_var)
        if not keys_str:
            raise RuntimeError(
                f"Missing {api_key_env_var}S or {api_key_env_var}. "
                "Add it to .env or set this environment variable before running Gemini calls."
            )
        self.available_keys = [key.strip() for key in keys_str.split(",") if key.strip()]

        try:
            from google import genai
            from google.genai import types

            self._types = types
            self._genai = genai
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency google-genai. Install it with: pip install google-genai"
            ) from exc

        self.model_name = model_name
        self.max_retries = max(0, int(max_retries))
        self.retry_base_delay_seconds = float(retry_base_delay_seconds)
        self.retry_max_delay_seconds = float(retry_max_delay_seconds)
        self.request_timeout_seconds = float(request_timeout_seconds)
        self.key_pool = GeminiKeyPool(
            self.available_keys,
            model_name=self.model_name,
            config=key_pool_config,
        )

        self._client = self._genai.Client(api_key=self.available_keys[0])
        # google-genai does not expose a stable per-call timeout parameter across
        # all versions, so generate() enforces timeout around the blocking call.
        self._config = self._types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )

    def generate(self, prompt: str) -> dict[str, Any]:
        attempts = 0
        max_attempts = max(1, (self.max_retries + 1) * len(self.available_keys))
        last_error_type = None
        last_error_message = None

        while attempts < max_attempts:
            current_key, key_id, key_index = self.key_pool.acquire_key()
            attempts += 1
            try:
                self._client = self._genai.Client(api_key=current_key)
                text = self._generate_once(prompt)
                if not text:
                    raise RuntimeError("Gemini API returned an empty response.")

                self.key_pool.record_success(key_id)
                return {
                    "ok": True,
                    "text": text,
                    "error_type": None,
                    "error_message": None,
                    "attempts": attempts,
                    "model_used": self.model_name,
                    "key_fingerprint": key_id,
                }
            except Exception as exc:
                last_error_type = self._classify_error(exc)
                last_error_message = str(exc)

                if last_error_type == "rate_limit":
                    print(
                        "[GeminiClient] Key "
                        f"{key_index}:{key_id} hit rate limit; cooling down."
                    )
                    self.key_pool.record_rate_limit(key_id, last_error_type)
                    continue

                self.key_pool.record_failure(key_id, last_error_type)
                if not self._should_retry(last_error_type):
                    break

                delay = self._retry_delay(attempts)
                print(
                    f"[GeminiClient] Retriable error ({last_error_type}) on "
                    f"key {key_index}:{key_id}. Sleeping {delay:.2f}s."
                )
                time.sleep(delay)

        return {
            "ok": False,
            "text": "",
            "error_type": last_error_type or "unknown",
            "error_message": last_error_message or "Unknown Gemini API error.",
            "attempts": attempts,
            "model_used": self.model_name,
        }

    def _generate_once(self, prompt: str) -> str:
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(
            self._client.models.generate_content,
            model=self.model_name,
            contents=prompt,
            config=self._config,
        )
        try:
            response = future.result(timeout=self.request_timeout_seconds)
        except FutureTimeoutError as exc:
            future.cancel()
            executor.shutdown(wait=False, cancel_futures=True)
            raise TimeoutError(
                f"Gemini request timed out after {self.request_timeout_seconds} seconds."
            ) from exc
        except Exception:
            executor.shutdown(wait=True, cancel_futures=False)
            raise
        else:
            executor.shutdown(wait=True, cancel_futures=False)

        return (getattr(response, "text", None) or "").strip()

    def _retry_delay(self, attempt_index: int) -> float:
        capped_attempt = max(0, attempt_index - 1)
        delay = self.retry_base_delay_seconds * (2**capped_attempt)
        return min(self.retry_max_delay_seconds, delay)

    @staticmethod
    def _should_retry(error_type: str | None) -> bool:
        return error_type in {"rate_limit", "timeout", "api_error", "transient_error"}

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        if isinstance(exc, TimeoutError):
            return "timeout"

        text = f"{type(exc).__name__}: {exc}".lower()
        if any(
            token in text
            for token in [
                "429",
                "resource_exhausted",
                "quota",
                "rate limit",
                "ratelimit",
            ]
        ):
            return "rate_limit"
        if any(
            token in text
            for token in ["503", "unavailable", "deadline", "temporarily", "transient"]
        ):
            return "api_error"
        if any(token in text for token in ["timeout", "timed out"]):
            return "timeout"
        if any(token in text for token in ["api", "google", "gemini"]):
            return "api_error"
        return "unknown"

    def generate_stream(self, prompt: str) -> Iterator[str]:
        """Yield Gemini response chunks as they arrive."""
        attempts = 0
        max_attempts = max(1, (self.max_retries + 1) * len(self.available_keys))
        while attempts < max_attempts:
            current_key, key_id, key_index = self.key_pool.acquire_key()
            attempts += 1
            try:
                self._client = self._genai.Client(api_key=current_key)
                yield from self._generate_stream_once(prompt)
                self.key_pool.record_success(key_id)
                return
            except Exception as exc:
                error_type = self._classify_error(exc)
                if error_type == "rate_limit":
                    print(
                        "[GeminiClient] Streaming key "
                        f"{key_index}:{key_id} hit rate limit; cooling down."
                    )
                    self.key_pool.record_rate_limit(key_id, error_type)
                    continue

                self.key_pool.record_failure(key_id, error_type)
                if not self._should_retry(error_type):
                    raise
                delay = self._retry_delay(attempts)
                print(
                    f"[GeminiClient] Streaming retryable error ({error_type}) on "
                    f"key {key_index}:{key_id}. Sleeping {delay:.2f}s."
                )
                time.sleep(delay)
        raise RuntimeError("Gemini streaming failed after all retry attempts.")

    def _generate_stream_once(self, prompt: str) -> Iterator[str]:
        output_queue: queue.Queue[tuple[str, str | Exception | None]] = queue.Queue()

        def worker() -> None:
            try:
                response = self._client.models.generate_content_stream(
                    model=self.model_name,
                    contents=prompt,
                    config=self._config,
                )
                for chunk in response:
                    text = getattr(chunk, "text", None) or ""
                    if text:
                        output_queue.put(("text", text))
                output_queue.put(("done", None))
            except Exception as exc:
                output_queue.put(("error", exc))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        while True:
            try:
                item_type, payload = output_queue.get(
                    timeout=self.request_timeout_seconds,
                )
            except queue.Empty as exc:
                raise TimeoutError(
                    "Gemini streaming request timed out after "
                    f"{self.request_timeout_seconds} seconds without a chunk."
                ) from exc

            if item_type == "text":
                yield str(payload)
            elif item_type == "error":
                if isinstance(payload, Exception):
                    raise payload
                raise RuntimeError("Unknown Gemini streaming error.")
            elif item_type == "done":
                return
