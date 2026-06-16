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
        
        # Load dynamic keys (comma separated)
        keys_str = os.environ.get("GROQ_API_KEYS", os.environ.get("GROQ_API_KEY", ""))
        self.available_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        
        if not self.available_keys:
            raise RuntimeError(
                "Missing GROQ_API_KEYS or GROQ_API_KEY. Add it to .env or set this environment variable."
            )

        try:
            import groq
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency groq. Install it with: pip install groq"
            ) from exc

        # Build fallback matrix (Model x Key)
        fallback_models = [model_name, "meta-llama/llama-4-scout-17b-16e-instruct", "qwen-2.5-32b-it"]
        models = []
        for m in fallback_models:
            if m not in models:
                models.append(m)
        
        self.providers = []
        for m in models:
            for k in self.available_keys:
                self.providers.append({"model": m, "api_key": k})

        self._config = {
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }

    @traceable(name="Groq Generation", run_type="llm")
    def generate(self, prompt: str) -> dict[str, Any]:
        from groq import Groq, RateLimitError, APITimeoutError, InternalServerError, APIConnectionError
        
        last_error = None
        for provider in self.providers:
            try:
                client = Groq(api_key=provider["api_key"], timeout=15.0, max_retries=0)
                response = client.chat.completions.create(
                    model=provider["model"],
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
                    "attempts": 1, 
                }
            except (RateLimitError, APITimeoutError, InternalServerError, APIConnectionError) as exc:
                last_error = exc
                print(f"[Fallback] Groq generation failed with model {provider['model']}. Trying next... Error: {str(exc)}")
                continue
                
        return {
            "ok": False,
            "text": None,
            "error_type": "api_error",
            "error_message": str(last_error),
            "attempts": len(self.providers),
        }

    @traceable(name="Groq Generation Stream", run_type="llm")
    def generate_stream(self, prompt: str) -> Iterator[str]:
        """Yield text chunks as Groq generates them in real-time, with Double Loop Fallback and TTFT."""
        from groq import Groq, RateLimitError, APITimeoutError, InternalServerError, APIConnectionError
        
        last_error = None
        for provider in self.providers:
            try:
                # HTTP timeout 10.0s will implicitly act as TTFT timeout
                client = Groq(api_key=provider["api_key"], timeout=10.0, max_retries=0)
                response = client.chat.completions.create(
                    model=provider["model"],
                    messages=[{"role": "user", "content": prompt}],
                    temperature=self._config["temperature"],
                    max_tokens=self._config["max_tokens"],
                    stream=True,
                )
                
                # Fetch first chunk to verify TTFT and API health
                iterator = iter(response)
                try:
                    first_chunk = next(iterator)
                except StopIteration:
                    first_chunk = None
                    
                if first_chunk and first_chunk.choices and first_chunk.choices[0].delta.content:
                    yield first_chunk.choices[0].delta.content
                
                # Yield remaining chunks
                for chunk in iterator:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                        
                return # Successfully finished streaming
                
            except (RateLimitError, APITimeoutError, InternalServerError, APIConnectionError) as exc:
                last_error = exc
                print(f"[Fallback] Groq stream failed with model {provider['model']}. Trying next... Error: {str(exc)}")
                continue
                
        # If all providers fail
        raise RuntimeError(f"All Groq fallback providers failed. Last error: {str(last_error)}")
