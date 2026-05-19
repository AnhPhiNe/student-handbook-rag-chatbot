import time
from pathlib import Path
from typing import Any
from src.retrieval.phase7.retrieval_pipeline import run_retrieval_pipeline
from src.retrieval.phase7.vector_retriever import (
    get_chroma_collection,
    load_embedding_model,
)

from .answer_formatter import format_final_answer, format_final_response
from .answer_guardrails import (
    build_clarification_question,
    build_deterministic_answer,
    build_fallback_answer,
    can_answer_deterministically,
    detect_ambiguous_query,
    is_low_confidence,
    is_out_of_domain_query,
)
from .citation_formatter import format_sources_text, select_relevant_citations
from .gemini_client import GeminiClient
from .io_utils import load_json, load_yaml
from .prompt_builder import DEFAULT_MAX_CONTEXT_CHARS, build_answer_prompt, limit_context
from .response_cache import ResponseCache


DEFAULT_CONFIG_PATH = Path("configs/phase8_answer_generation.yaml")


class Phase8AnswerPipeline:
    def __init__(
        self,
        config_path: str | Path = DEFAULT_CONFIG_PATH,
        llm_client: GeminiClient | None = None,
    ) -> None:
        self.config_path = Path(config_path)
        self.config = load_yaml(self.config_path)

        self.scoring_tables = load_json(self.config["input"]["scoring_tables"])
        self.entity_registry = load_json(self.config["input"]["entity_registry"])
        self.expansion_rules = load_json(self.config["input"]["query_expansion_rules"])

        self.model = load_embedding_model(self.config["embedding"]["model_name"])
        self.collection = get_chroma_collection(
            persist_dir=self.config["vectorstore"]["persist_dir"],
            collection_name=self.config["vectorstore"]["collection_name"],
        )

        llm_config = self.config["llm"]
        if llm_config.get("provider") != "gemini":
            raise ValueError("Phase 8 currently supports only llm.provider='gemini'.")

        self._llm_client = llm_client
        self.max_context_chars = int(
            llm_config.get("max_context_chars", DEFAULT_MAX_CONTEXT_CHARS)
        )
        self.request_sleep_seconds = float(llm_config.get("request_sleep_seconds", 2))
        self._last_llm_call_at = 0.0

        cache_config = self.config.get("cache", {})
        self.response_cache = ResponseCache(
            path=cache_config.get("path", "data/cache/phase8_response_cache.json"),
            enabled=cache_config.get("enabled", True),
        )

    def answer(self, query: str) -> dict[str, Any]:
        try:
            retrieval_result = self._run_retrieval(query)
        except Exception as exc:
            final_answer = build_fallback_answer(
                query=query,
                retrieval_result=None,
                reason="retrieval_error",
            )
            return self._build_output(
                query=query,
                retrieval_result={},
                final_answer=final_answer,
                context_used="",
                selected_citations=[],
                status="retrieval_error",
                error_type="retrieval_error",
                error_message=str(exc),
                llm_called=False,
                used_cache=False,
            )

        context_used = limit_context(
            str(retrieval_result.get("context_for_llm") or ""),
            max_context_chars=self.max_context_chars,
        )

        if detect_ambiguous_query(query, retrieval_result):
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=build_clarification_question(query, retrieval_result),
                context_used=context_used,
                selected_citations=[],
                status="needs_clarification",
                error_type=None,
                error_message=None,
                llm_called=False,
                used_cache=False,
                clarification_needed=True,
            )
            
        if is_out_of_domain_query(query, retrieval_result):
            final_answer = build_fallback_answer(
                query=query,
                retrieval_result=retrieval_result,
                reason="out_of_domain",
            )

            return self._build_output(
                query=query,
                retrieval_result={},
                final_answer=final_answer,
                context_used="",
                selected_citations=[],
                status="out_of_domain",
                error_type=None,
                error_message=None,
                llm_called=False,
                used_cache=False,
            )

        citations_config = self.config.get("citations", {})

        guardrails_config = self.config.get("guardrails", {})
        if guardrails_config.get("allow_deterministic_direct_answer", True) and can_answer_deterministically(
            retrieval_result
        ):
            selected_citations = select_relevant_citations(
                retrieval_result.get("citations"),
                intent=retrieval_result.get("intent"),
                retrieval_result=retrieval_result,
                max_sources=int(citations_config.get("max_sources", 2)),
            )
            final_answer = format_final_answer(
                build_deterministic_answer(query, retrieval_result, selected_citations),
                selected_citations,
            )
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=final_answer,
                context_used=context_used,
                selected_citations=selected_citations,
                status="answered",
                error_type=None,
                error_message=None,
                llm_called=False,
                used_cache=False,
            )

        selected_citations = select_relevant_citations(
            retrieval_result.get("citations"),
            intent=retrieval_result.get("intent"),
            retrieval_result=retrieval_result,
            max_sources=int(citations_config.get("max_sources", 2)),
        )

        if guardrails_config.get("skip_llm_on_low_confidence", True) and is_low_confidence(
            retrieval_result
        ):
            final_answer = format_final_answer(
                build_fallback_answer(query, retrieval_result, reason="low_confidence"),
                selected_citations,
            )
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=final_answer,
                context_used=context_used,
                selected_citations=selected_citations,
                status="low_confidence",
                error_type="retrieval",
                error_message="Retrieval returned empty or insufficient context.",
                llm_called=False,
                used_cache=False,
            )

        cache_key = self.response_cache.make_cache_key(
            query=query,
            retrieval_result=retrieval_result,
            selected_citations=selected_citations,
        )
        cached = self.response_cache.get(cache_key)
        if cached:
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=str(cached.get("answer") or ""),
                context_used=context_used,
                selected_citations=selected_citations,
                status=str(cached.get("status") or "answered"),
                error_type=cached.get("error_type"),
                error_message=cached.get("error_message"),
                llm_called=False,
                used_cache=True,
            )

        prompt = build_answer_prompt(
            query=query,
            retrieval_result=retrieval_result,
            selected_citations=selected_citations,
            max_context_chars=self.max_context_chars,
        )

        try:
            llm_client = self._get_llm_client()
        except Exception as exc:
            final_answer = format_final_answer(
                build_fallback_answer(query, retrieval_result, reason="api_error"),
                selected_citations,
            )
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=final_answer,
                context_used=context_used,
                selected_citations=selected_citations,
                status="api_error",
                error_type="api_init_error",
                error_message=str(exc),
                llm_called=False,
                used_cache=False,
            )

        self._throttle_llm_call()
        llm_result = llm_client.generate(prompt)
        self._last_llm_call_at = time.monotonic()

        if not llm_result.get("ok"):
            error_type = llm_result.get("error_type") or "api_error"
            final_answer = format_final_answer(
                build_fallback_answer(query, retrieval_result, reason=error_type),
                selected_citations,
            )
            return self._build_output(
                query=query,
                retrieval_result=retrieval_result,
                final_answer=final_answer,
                context_used=context_used,
                selected_citations=selected_citations,
                status="api_error",
                error_type=error_type,
                error_message=llm_result.get("error_message"),
                llm_called=True,
                used_cache=False,
            )

        final_answer = format_final_response(
            str(llm_result.get("text") or ""),
            sources_text=format_sources_text(selected_citations),
        )
        output = self._build_output(
            query=query,
            retrieval_result=retrieval_result,
            final_answer=final_answer,
            context_used=context_used,
            selected_citations=selected_citations,
            status="answered",
            error_type=None,
            error_message=None,
            llm_called=True,
            used_cache=False,
        )
        self.response_cache.set(
            cache_key,
            {
                "answer": final_answer,
                "status": "answered",
                "error_type": None,
                "error_message": None,
            },
        )
        return output

    def _run_retrieval(self, query: str) -> dict[str, Any]:
        return run_retrieval_pipeline(
            query=query,
            model=self.model,
            collection=self.collection,
            scoring_tables=self.scoring_tables,
            entity_registry=self.entity_registry,
            expansion_rules=self.expansion_rules,
            top_k=self.config["retrieval"]["default_top_k"],
            batch_size=self.config["embedding"]["batch_size"],
            normalize_embeddings=self.config["embedding"]["normalize_embeddings"],
        )

    def _get_llm_client(self) -> GeminiClient:
        if self._llm_client is None:
            llm_config = self.config["llm"]
            self._llm_client = GeminiClient(
                model_name=llm_config.get("model_name", "gemini-2.5-flash"),
                temperature=llm_config.get("temperature", 0.2),
                max_output_tokens=llm_config.get("max_output_tokens", 1024),
                max_retries=llm_config.get("max_retries", 3),
                retry_base_delay_seconds=llm_config.get("retry_base_delay_seconds", 2),
                retry_max_delay_seconds=llm_config.get("retry_max_delay_seconds", 20),
                request_timeout_seconds=llm_config.get("request_timeout_seconds", 60),
            )
        return self._llm_client

    def _throttle_llm_call(self) -> None:
        if self.request_sleep_seconds <= 0 or self._last_llm_call_at <= 0:
            return

        elapsed = time.monotonic() - self._last_llm_call_at
        remaining = self.request_sleep_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def _build_output(
        self,
        query: str,
        retrieval_result: dict[str, Any],
        final_answer: str,
        context_used: str,
        selected_citations: list[dict[str, Any]],
        status: str,
        error_type: str | None,
        error_message: str | None,
        llm_called: bool,
        used_cache: bool,
        clarification_needed: bool = False,
    ) -> dict[str, Any]:
        return {
            "query": query,
            "answer": final_answer,
            "status": status,
            "error_type": error_type,
            "error_message": error_message,
            "intent": retrieval_result.get("intent"),
            "strategy": retrieval_result.get("strategy"),
            "retrieval_query": retrieval_result.get("retrieval_query"),
            "citations": retrieval_result.get("citations", []),
            "citations_used": selected_citations,
            "structured_result": retrieval_result.get("structured_result"),
            "tool_result": retrieval_result.get("tool_result"),
            "llm_called": llm_called,
            "used_cache": used_cache,
            "clarification_needed": clarification_needed,
            "context_used": context_used,
        }
