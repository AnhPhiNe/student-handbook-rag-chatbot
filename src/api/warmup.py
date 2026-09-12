"""Load the answer pipeline before the first student question arrives.

The pipeline builds itself lazily, so on a fresh container the first request
pays for the embedding model, the catalogs, the parent docstore and the
Qdrant/MongoDB clients. Warming happens on a background thread rather than in
the startup path: the container must answer ``/health`` immediately or the
platform health check fails while the model is still loading.

Warm-up never fails the process. If a dependency is down at boot the first
real request falls back to the lazy path, which is exactly today's behaviour.
"""

from __future__ import annotations

import logging
import threading
import time

from src.common.env_loader import env_bool

logger = logging.getLogger(__name__)

WARMUP_ENV = "STUDENT_RAG_WARMUP_ON_STARTUP"

_warmup_state: dict[str, object] = {"status": "disabled", "seconds": None}


def warmup_status() -> dict[str, object]:
    """Report what the background warm-up has managed so far."""
    return dict(_warmup_state)


def run_warmup() -> None:
    """Build the answer service once, recording the outcome either way."""
    from src.api.deps import get_answer_service

    _warmup_state["status"] = "running"
    started = time.monotonic()
    try:
        get_answer_service().warm()
    except Exception:
        _warmup_state["status"] = "failed"
        _warmup_state["seconds"] = round(time.monotonic() - started, 1)
        logger.exception("startup_warmup_failed")
        return
    _warmup_state["status"] = "ready"
    _warmup_state["seconds"] = round(time.monotonic() - started, 1)
    logger.info("startup_warmup_complete", extra=dict(_warmup_state))


def start_warmup() -> threading.Thread | None:
    """Start warm-up in the background when the deployment asks for it."""
    if not env_bool(WARMUP_ENV):
        _warmup_state["status"] = "disabled"
        return None
    thread = threading.Thread(target=run_warmup, name="pipeline-warmup", daemon=True)
    thread.start()
    return thread
