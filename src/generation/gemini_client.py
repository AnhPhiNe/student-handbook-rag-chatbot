import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any

from src.common.env_loader import load_project_env


class GeminiClient:
    def __init__(
        self,
        model_name: str = "gemini-2.5-flash-lite",
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
        max_retries: int = 3,
        retry_base_delay_seconds: float = 2,
        retry_max_delay_seconds: float = 20,
        request_timeout_seconds: float = 60,
    ) -> None:
        load_project_env()
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Missing GEMINI_API_KEY. Add it to .env or set this environment variable before running Gemini calls."
            )

        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency google-genai. Install it with: pip install google-genai"
            ) from exc

        self.model_name = model_name
        self.max_retries = max(0, int(max_retries))
        self.retry_base_delay_seconds = float(retry_base_delay_seconds)
        self.retry_max_delay_seconds = float(retry_max_delay_seconds)
        self.request_timeout_seconds = float(request_timeout_seconds)

        self._client = genai.Client(api_key=api_key)
        # google-genai does not expose a stable per-call timeout parameter across
        # all versions, so generate() enforces timeout around the blocking call.
        self._config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )

    def generate(self, prompt: str) -> dict[str, Any]:
        attempts = 0
        last_error_type = None
        last_error_message = None

        for attempt_index in range(self.max_retries + 1):
            attempts = attempt_index + 1
            try:
                text = self._generate_once(prompt)
                if not text:
                    raise RuntimeError("Gemini API returned an empty response.")
                return {
                    "ok": True,
                    "text": text,
                    "error_type": None,
                    "error_message": None,
                    "attempts": attempts,
                }
            except Exception as exc:
                last_error_type = self._classify_error(exc)
                last_error_message = str(exc)

                if attempt_index >= self.max_retries or not self._should_retry(last_error_type):
                    break

                time.sleep(self._retry_delay(attempt_index))

        return {
            "ok": False,
            "text": "",
            "error_type": last_error_type or "unknown",
            "error_message": last_error_message or "Unknown Gemini API error.",
            "attempts": attempts,
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
        exponential_delay = self.retry_base_delay_seconds * (2 ** attempt_index)
        capped_delay = min(exponential_delay, self.retry_max_delay_seconds)
        jitter = random.uniform(0, min(1.0, capped_delay * 0.25))
        return capped_delay + jitter

    @staticmethod
    def _should_retry(error_type: str | None) -> bool:
        return error_type in {"rate_limit", "timeout", "api_error", "transient_error"}

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        if isinstance(exc, TimeoutError):
            return "timeout"

        text = f"{type(exc).__name__}: {exc}".lower()
        if any(token in text for token in ["429", "resource_exhausted", "quota", "rate limit", "ratelimit"]):
            return "rate_limit"
        if any(token in text for token in ["503", "unavailable", "deadline", "temporarily", "transient"]):
            return "api_error"
        if any(token in text for token in ["timeout", "timed out"]):
            return "timeout"
        if any(token in text for token in ["api", "google", "gemini"]):
            return "api_error"
        return "unknown"
