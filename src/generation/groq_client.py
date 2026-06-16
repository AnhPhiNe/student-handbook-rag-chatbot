import os
import time
from collections.abc import Iterator
from typing import Any

from langsmith import traceable

from src.common.env_loader import load_project_env


class GroqClient:
    def __init__(
        self,
        model_name: str = "llama-3.3-70b-versatile",
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
        max_retries: int = 3,
        retry_base_delay_seconds: float = 2,
        retry_max_delay_seconds: float = 20,
        request_timeout_seconds: float = 60,
        api_key_env_var: str = "GROQ_API_KEY",
    ) -> None:
        load_project_env()
        self.api_key_env_var = api_key_env_var
        api_key = os.environ.get(api_key_env_var)
        if not api_key:
            raise RuntimeError(
                f"Missing {api_key_env_var}. Add it to .env or set this environment variable before running Groq calls."
            )

        try:
            from groq import Groq
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency groq. Install it with: pip install groq"
            ) from exc

        self.model_name = model_name
        self.max_retries = max(0, int(max_retries))
        self.retry_base_delay_seconds = float(retry_base_delay_seconds)
        self.retry_max_delay_seconds = float(retry_max_delay_seconds)
        self.request_timeout_seconds = float(request_timeout_seconds)

        self._client = Groq(
            api_key=api_key,
            timeout=self.request_timeout_seconds,
            max_retries=self.max_retries,
        )
        
        self._config = {
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }

    @traceable(name="Groq Generation", run_type="llm")
    def generate(self, prompt: str) -> dict[str, Any]:
        try:
            response = self._client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=self._config["temperature"],
                max_tokens=self._config["max_tokens"],
                stream=False,
            )
            text = response.choices[0].message.content
            if not text:
                raise RuntimeError("Groq API returned an empty response.")
            return {
                "ok": True,
                "text": text,
                "error_type": None,
                "error_message": None,
                "attempts": 1, # groq sdk handles internal retries
            }
        except Exception as exc:
            return {
                "ok": False,
                "text": None,
                "error_type": "api_error",
                "error_message": str(exc),
                "attempts": self.max_retries + 1,
            }

    @traceable(name="Groq Generation Stream", run_type="llm")
    def generate_stream(self, prompt: str) -> Iterator[str]:
        """Yield text chunks as Groq generates them in real-time."""
        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=self._config["temperature"],
            max_tokens=self._config["max_tokens"],
            stream=True,
        )
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
