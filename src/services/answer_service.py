from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
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

    def _get_pipeline(self) -> AnswerPipeline:
        """Initialize the shared pipeline once, guarded against concurrent requests."""

        if self._pipeline is None:
            with self._pipeline_lock:
                if self._pipeline is None:
                    self._pipeline = AnswerPipeline(config_path=self.config_path)
        return self._pipeline
