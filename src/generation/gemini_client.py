import os
import queue
import random
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any

from langsmith import traceable

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
        api_key_env_var: str = "GEMINI_API_KEY",
    ) -> None:
        load_project_env()
        self.api_key_env_var = api_key_env_var
        api_key = os.environ.get(api_key_env_var)
        if not api_key:
            raise RuntimeError(
                f"Missing {api_key_env_var}. Add it to .env or set this environment variable before running Gemini calls."
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

    @traceable(name="Gemini Generation", run_type="llm")
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
                    "model_used": self.model_name,
                }
            except Exception as exc:
                last_error_type = self._classify_error(exc)
                last_error_message = str(exc)

                if attempt_index >= self.max_retries or not self._should_retry(
                    last_error_type
                ):
                    break

                time.sleep(self._retry_delay(attempt_index))

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
        exponential_delay = self.retry_base_delay_seconds * (2**attempt_index)
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

    @traceable(name="Gemini Generation Stream", run_type="llm")
    def generate_stream(self, prompt: str) -> Iterator[str]:
        """Trả dần các đoạn văn bản khi Gemini sinh ra theo thời gian thực.

        Khác với generate() phải đợi đủ câu trả lời, phương thức này stream token
        ngay khi API tạo ra. Được dùng bởi streaming answer pipeline và endpoint SSE.
        """
        try:
            yield from self._generate_stream_once(prompt)
        except Exception as exc:
            error_type = self._classify_error(exc)
            if self._should_retry(error_type):
                # Fallback to non-streaming on transient errors
                result = self.generate(prompt)
                if result.get("ok") and result.get("text"):
                    yield str(result["text"])
                    return
            raise

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
