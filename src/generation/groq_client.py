import os
from collections.abc import Iterator
from typing import Any

from src.common.env_loader import load_project_env


import time

class GroqClient:
    _rate_limited_providers = {}  # Lưu trữ các Model/Key bị cấm (Key -> Expiration Timestamp)
    
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
            import groq  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "Missing dependency groq. Install it with: pip install groq"
            ) from exc

        # Build fallback matrix (Model x Key). Eval runs can disable fallback
        # to compare model behavior cleanly without changing production config.
        if os.environ.get("STUDENT_RAG_DISABLE_GROQ_FALLBACK", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            fallback_models = [model_name]
        else:
            fallback_models = [
                model_name,
                "openai/gpt-oss-120b",
                "qwen/qwen3.6-27b",
                "llama-3.1-8b-instant",
            ]
        self.models = []
        for m in fallback_models:
            if m not in self.models:
                self.models.append(m)

        self._config = {
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }
    def generate(self, prompt: str) -> dict[str, Any]:
        from groq import Groq
        import random

        while True:
            last_error = None
            keys = list(self.available_keys)
            random.shuffle(keys)
            providers = [{"model": m, "api_key": k} for m in self.models for k in keys]
            
            all_skipped = True

            for provider in providers:
                provider_key = f"{provider['model']}:{provider['api_key']}"
                if provider_key in GroqClient._rate_limited_providers:
                    if time.time() < GroqClient._rate_limited_providers[provider_key]:
                        continue
                    else:
                        del GroqClient._rate_limited_providers[provider_key]

                all_skipped = False
                try:
                    client = Groq(api_key=provider["api_key"], timeout=20.0, max_retries=0)
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
                    print(f"[GroqClient] mode=generate model_used={provider['model']}")
                    
                    return {
                        "ok": True,
                        "text": text,
                        "error_type": None,
                        "error_message": None,
                        "attempts": 1,
                        "model_used": provider["model"],
                    }
                except Exception as exc:
                    last_error = exc
                    err_str = str(exc)
                    if "429" in err_str or "rate_limit" in err_str.lower():
                        print(f"[Fallback] Groq Key hit rate limit. Penalty Box for 65 seconds...")
                        GroqClient._rate_limited_providers[provider_key] = time.time() + 65
                    else:
                        print(f"[Fallback] Groq server error. Sleep 5s... Error: {err_str}")
                        time.sleep(5)
                    continue

            # Nếu tất cả các Key đều nằm trong Penalty Box
            if all_skipped:
                print("[GroqClient] All keys are exhausted/rate-limited. Hibernating for 15 seconds before retry...")
                time.sleep(15)
    def generate_stream(self, prompt: str) -> Iterator[str]:
        """Trả dần văn bản từ Groq theo thời gian thực, kèm fallback hai vòng và TTFT."""
        from groq import Groq
        import random

        last_error = None

        keys = list(self.available_keys)
        random.shuffle(keys)
        providers = [{"model": m, "api_key": k} for m in self.models for k in keys]

        for provider in providers:
            provider_key = f"{provider['model']}:{provider['api_key']}"
            if provider_key in GroqClient._rate_limited_providers:
                if time.time() < GroqClient._rate_limited_providers[provider_key]:
                    print(f"[Skip] Provider {provider['model']} is in Penalty Box (Rate Limited). Skipping...")
                    continue
                else:
                    del GroqClient._rate_limited_providers[provider_key]

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
                # Groq stream provides usage via x_groq attribute in the last chunk natively.
                
                print(f"[GroqClient] mode=stream model_used={provider['model']}")
                
                self._last_stream_usage = None
                self._last_stream_model = provider["model"]

                # Fetch first chunk to verify TTFT and API health
                iterator = iter(response)
                try:
                    first_chunk = next(iterator)
                except StopIteration:
                    first_chunk = None

                if (
                    first_chunk
                    and first_chunk.choices
                    and first_chunk.choices[0].delta.content
                ):
                    yield first_chunk.choices[0].delta.content

                # Yield remaining chunks
                for chunk in iterator:
                    if chunk.choices and len(chunk.choices) > 0 and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                        
                    # Check for usage in x_groq
                    if hasattr(chunk, "x_groq") and chunk.x_groq and hasattr(chunk.x_groq, "usage"):
                        self._last_stream_usage = {
                            "input": getattr(chunk.x_groq.usage, "prompt_tokens", 0),
                            "output": getattr(chunk.x_groq.usage, "completion_tokens", 0),
                            "total": getattr(chunk.x_groq.usage, "total_tokens", 0),
                        }

                return  # Successfully finished streaming

            except Exception as exc:
                last_error = exc
                err_str = str(exc)
                if "429" in err_str or "rate_limit" in err_str.lower():
                    print(f"[Fallback] Groq model {provider['model']} hit rate limit (429). Blocking for 1 hour...")
                    GroqClient._rate_limited_providers[provider_key] = time.time() + 3600
                else:
                    print(f"[Fallback] Groq stream failed with model {provider['model']}. Trying next... Error: {err_str}")
                continue

        # If all providers fail
        raise RuntimeError(
            f"All Groq fallback providers failed. Last error: {str(last_error)}"
        )
