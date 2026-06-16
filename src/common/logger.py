import logging
import json
import os
import time
from typing import Any


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter for production observability."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        extra_keys = [
            "intent", "strategy", "latency_ms", "query_length",
            "effective_query", "retrieval_query", "llm_called",
            "used_cache", "status", "step", "duration_ms",
            "chunk_count", "error_type", "error_message",
        ]
        for key in extra_keys:
            value = getattr(record, key, None)
            if value is not None:
                log_entry[key] = value
        return json.dumps(log_entry, ensure_ascii=False, default=str)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with structured JSON output for production use."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        level = os.environ.get("LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, level, logging.INFO))
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger


class PipelineTimer:
    """Context manager to measure and log pipeline step durations."""

    def __init__(self, logger: logging.Logger, step_name: str, **extra: Any) -> None:
        self.logger = logger
        self.step_name = step_name
        self.extra = extra
        self._start = 0.0

    def __enter__(self) -> "PipelineTimer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: Any) -> None:
        duration_ms = round((time.perf_counter() - self._start) * 1000, 2)
        self.logger.info(
            f"pipeline_step:{self.step_name}",
            extra={"step": self.step_name, "duration_ms": duration_ms, **self.extra},
        )
