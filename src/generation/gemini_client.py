import os
import queue
import random
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any


from src.common.env_loader import load_project_env


class GeminiClient:
    _current_key_index = 0
    _rate_limited_providers = {}

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
    ) -> None:
        load_project_env()
        self.api_key_env_var = api_key_env_var
        
        # Load multiple keys if GEMINI_API_KEYS exists, else fallback to GEMINI_API_KEY
        keys_str = os.environ.get(api_key_env_var + "S") or os.environ.get(api_key_env_var)
        if not keys_str:
            raise RuntimeError(
                f"Missing {api_key_env_var}S or {api_key_env_var}. Add it to .env or set this environment variable before running Gemini calls."
            )
        self.available_keys = [k.strip() for k in keys_str.split(",") if k.strip()]

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

        self._client = self._genai.Client(api_key=self.available_keys[0])
        # google-genai does not expose a stable per-call timeout parameter across
        # all versions, so generate() enforces timeout around the blocking call.
        self._config = self._types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )

    def generate(self, prompt: str) -> dict[str, Any]:
        attempts = 0
        last_error_type = None
        last_error_message = None

        while True:
            attempts += 1
            if not self.available_keys:
                raise RuntimeError("No Gemini API keys available.")
                
            current_key = self.available_keys[GeminiClient._current_key_index]
            provider_key = f"{self.model_name}:{current_key}"
            
            # Check penalty box for the current key
            if provider_key in GeminiClient._rate_limited_providers:
                wait_time = GeminiClient._rate_limited_providers[provider_key] - time.time()
                if wait_time > 0:
                    print(f"[GeminiClient] Key {GeminiClient._current_key_index} still in penalty. Waiting {wait_time:.2f}s for RPM/TPD recovery...")
                    time.sleep(wait_time)
                else:
                    del GeminiClient._rate_limited_providers[provider_key]

            try:
                # Update client to use the current key
                self._client = self._genai.Client(api_key=current_key)
                text = self._generate_once(prompt)
                if not text:
                    raise RuntimeError("Gemini API returned an empty response.")
                
                # If successful, we DON'T change the index. We exhaust this key for the next requests.
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
                
                if last_error_type == "rate_limit":
                    print(f"[Fallback] Gemini Key {GeminiClient._current_key_index} hit rate limit (RPM/TPM). Penalty Box for 65 seconds...")
                    GeminiClient._rate_limited_providers[provider_key] = time.time() + 65
                    # Move to next key IMMEDIATELY
                    GeminiClient._current_key_index = (GeminiClient._current_key_index + 1) % len(self.available_keys)
                    continue
                else:
                    print(f"[Fallback] Gemini generation failed. Error: {last_error_message}")
                    if self._should_retry(last_error_type):
                        delay = self._retry_delay(attempts)
                        print(f"[GeminiClient] Server error ({last_error_type}). Sleeping {delay:.2f}s to wait for server recovery...")
                        time.sleep(delay)
                        # Don't switch key if it's just a server transient error, but for safety we can switch
                        GeminiClient._current_key_index = (GeminiClient._current_key_index + 1) % len(self.available_keys)
                        continue
                    else:
                        print("Fatal error. Switching to next key...")
                        GeminiClient._current_key_index = (GeminiClient._current_key_index + 1) % len(self.available_keys)
                        if attempts >= self.max_retries * len(self.available_keys):
                            break
                        continue

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
        return 5.0

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
        """Trả dần các đoạn văn bản khi Gemini sinh ra theo thời gian thực."""
        # For simplicity in stream, we just wrap generate logic if it's transient, 
        # but ideal streaming fallback requires identical while True logic.
        while True:
            current_key = self.available_keys[GeminiClient._current_key_index]
            provider_key = f"{self.model_name}:{current_key}"
            
            if provider_key in GeminiClient._rate_limited_providers:
                wait_time = GeminiClient._rate_limited_providers[provider_key] - time.time()
                if wait_time > 0:
                    time.sleep(wait_time)
                else:
                    del GeminiClient._rate_limited_providers[provider_key]

            try:
                self._client = self._genai.Client(api_key=current_key)
                yield from self._generate_stream_once(prompt)
                return
            except Exception as exc:
                error_type = self._classify_error(exc)
                if error_type == "rate_limit":
                    GeminiClient._rate_limited_providers[provider_key] = time.time() + 65
                    GeminiClient._current_key_index = (GeminiClient._current_key_index + 1) % len(self.available_keys)
                    continue
                else:
                    if self._should_retry(error_type):
                        delay = self._retry_delay(1)
                        print(f"[GeminiClient] Server error ({error_type}). Sleeping {delay:.2f}s to wait for server recovery...")
                        time.sleep(delay)
                        GeminiClient._current_key_index = (GeminiClient._current_key_index + 1) % len(self.available_keys)
                        continue
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
