from __future__ import annotations

from pathlib import Path
from typing import Any

from src.chatbot.phase8.phase8_pipeline import DEFAULT_CONFIG_PATH, Phase8AnswerPipeline


class AnswerService:
    """Thin service contract shared by UI and future API adapters."""

    def __init__(
        self,
        pipeline: Phase8AnswerPipeline | None = None,
        config_path: str | Path | None = None,
    ) -> None:
        self._pipeline = pipeline
        if config_path is not None:
            self.config_path = Path(config_path)
        elif pipeline is not None and hasattr(pipeline, "config_path"):
            self.config_path = Path(pipeline.config_path)
        else:
            self.config_path = DEFAULT_CONFIG_PATH

    def answer(self, query: str) -> dict[str, Any]:
        return self._get_pipeline().answer(query)

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "service": self.__class__.__name__,
            "pipeline_class": Phase8AnswerPipeline.__name__,
            "pipeline_loaded": self._pipeline is not None,
            "config_path": str(self.config_path),
        }

    def _get_pipeline(self) -> Phase8AnswerPipeline:
        if self._pipeline is None:
            self._pipeline = Phase8AnswerPipeline(config_path=self.config_path)
        return self._pipeline
