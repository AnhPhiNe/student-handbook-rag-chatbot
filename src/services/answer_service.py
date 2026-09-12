from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
import time
from threading import Lock
from typing import Any

from src.generation.answer_pipeline import DEFAULT_CONFIG_PATH, AnswerPipeline


class AnswerService:
    """Share one lazily loaded answer pipeline across UI and API adapters."""

    def __init__(
        self,
        pipeline: AnswerPipeline | None = None,
        config_path: str | Path | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._pipeline_lock = Lock()
        if config_path is not None:
            self.config_path = Path(config_path)
        elif pipeline is not None and hasattr(pipeline, "config_path"):
            self.config_path = Path(pipeline.config_path)
        else:
            self.config_path = DEFAULT_CONFIG_PATH

    def answer(
        self,
        query: str,
        chat_history: list[dict[str, str]] | None = None,
        cohort: str | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Run the synchronous answer pipeline for one user query."""

        return self._get_pipeline().answer(
            query, chat_history=chat_history, cohort=cohort, **kwargs
        )

    def answer_stream(
        self,
        query: str,
        chat_history: list[dict[str, str]] | None = None,
        cohort: str | None = None,
        **kwargs,
    ) -> Iterator[dict[str, Any]]:
        """Yield incremental events from the streaming answer pipeline."""
        yield from self._get_pipeline().answer_stream(
            query, chat_history=chat_history, cohort=cohort, **kwargs
        )

    def warm(self, *, bm25_wait_seconds: float = 180.0) -> None:
        """Build everything the first question would otherwise build itself.

        The constructor loads the embedding model, catalogs and parent
        docstore; the router, plan executor and LLM client stay lazy behind
        properties. Touching all of them here means the first request runs the
        same code path as the hundredth.

        The regulation retriever is the expensive part a lazy first request
        pays for: creating the singleton and scrolling Qdrant to build the
        BM25 index costs roughly 15 seconds. Build it here too, and wait for
        BM25 to leave "initializing" so the first RAG question is as fast as
        the second. BM25 is fail-open, so a wait that times out or a degraded
        index still leaves dense retrieval serving.
        """
        pipeline = self._get_pipeline()
        pipeline._get_router()
        _ = pipeline.plan_executor
        pipeline._get_llm_client()

        from src.retrieval.core.hybrid_pipeline import initialize_hybrid_retriever
        from src.retrieval.core.runtime_health import get_bm25_runtime_status

        initialize_hybrid_retriever()
        deadline = time.monotonic() + max(0.0, bm25_wait_seconds)
        while get_bm25_runtime_status()["status"] == "initializing":
            if time.monotonic() >= deadline:
                break
            time.sleep(1.0)

    def _get_pipeline(self) -> AnswerPipeline:
        """Initialize the shared pipeline once, guarded against concurrent requests."""

        if self._pipeline is None:
            with self._pipeline_lock:
                if self._pipeline is None:
                    self._pipeline = AnswerPipeline(config_path=self.config_path)
        return self._pipeline
