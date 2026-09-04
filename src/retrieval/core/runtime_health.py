from __future__ import annotations

from threading import Lock
from typing import Literal, TypedDict


BM25RuntimeState = Literal["initializing", "ready", "degraded"]


class BM25RuntimeStatus(TypedDict):
    """Track local BM25 initialization state and failures."""

    status: BM25RuntimeState
    attempts: int
    error_type: str | None


_BM25_STATUS_LOCK = Lock()
_BM25_STATUS: BM25RuntimeStatus = {
    "status": "initializing",
    "attempts": 0,
    "error_type": None,
}


def set_bm25_runtime_status(
    status: BM25RuntimeState,
    *,
    attempts: int,
    error_type: str | None = None,
) -> None:
    """Publish a small, secret-free snapshot of BM25 startup health."""

    snapshot: BM25RuntimeStatus = {
        "status": status,
        "attempts": max(0, int(attempts)),
        "error_type": str(error_type) if error_type else None,
    }
    with _BM25_STATUS_LOCK:
        _BM25_STATUS.update(snapshot)


def get_bm25_runtime_status() -> BM25RuntimeStatus:
    """Return a serializable snapshot of BM25 runtime health."""

    with _BM25_STATUS_LOCK:
        return {
            "status": _BM25_STATUS["status"],
            "attempts": _BM25_STATUS["attempts"],
            "error_type": _BM25_STATUS["error_type"],
        }
