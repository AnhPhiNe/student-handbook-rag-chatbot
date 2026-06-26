from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from src.generation.answer_pipeline import DEFAULT_CONFIG_PATH, AnswerPipeline


class AnswerService:
    """Thin service contract shared by UI and future API adapters."""

    def __init__(
        self,
        pipeline: AnswerPipeline | None = None,
        config_path: str | Path | None = None,
    ) -> None:
        self._pipeline = pipeline
        if config_path is not None:
            self.config_path = Path(config_path)
        elif pipeline is not None and hasattr(pipeline, "config_path"):
            self.config_path = Path(pipeline.config_path)
        else:
            self.config_path = DEFAULT_CONFIG_PATH

    def answer(self, query: str, chat_history: list[dict[str, str]] | None = None, cohort: str | None = None) -> dict[str, Any]:
        return self._get_pipeline().answer(query, chat_history=chat_history, cohort=cohort)

    def answer_stream(
        self,
        query: str,
        chat_history: list[dict[str, str]] | None = None,
        cohort: str | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Stream answer chunks from the pipeline."""
        yield from self._get_pipeline().answer_stream(query, chat_history=chat_history, cohort=cohort)

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "service": self.__class__.__name__,
            "pipeline_class": AnswerPipeline.__name__,
            "pipeline_loaded": self._pipeline is not None,
            "config_path": str(self.config_path),
        }

    def _get_pipeline(self) -> AnswerPipeline:
        if self._pipeline is None:
            self._pipeline = AnswerPipeline(config_path=self.config_path)
        return self._pipeline

