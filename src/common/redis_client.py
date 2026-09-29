"""Redis connections with bounded waits.

Redis only serves optional features (the answer cache, the visit counter), so
a slow or unreachable server must turn into a miss, never a hung request. The
redis client waits forever by default. Measured from Vietnam, the Upstash
database answered PING in about 100 ms, with one wait of 1.0 s in five
(2026-09-29), so the limits leave room for such spikes.
"""
from __future__ import annotations

from typing import Any

from src.common.env_loader import env_bool

# Seconds to open a connection (TLS included) and to wait for one reply.
CONNECT_TIMEOUT_SECONDS = 3.0
REPLY_TIMEOUT_SECONDS = 2.0


def redis_disabled() -> bool:
    """STUDENT_RAG_DISABLE_REDIS turns off every Redis use, e.g. on a developer machine."""
    return env_bool("STUDENT_RAG_DISABLE_REDIS")


def connect(url: str, **options: Any) -> Any:
    """A Redis client whose commands fail after the timeouts above instead of hanging."""
    import redis

    return redis.from_url(
        url,
        socket_connect_timeout=CONNECT_TIMEOUT_SECONDS,
        socket_timeout=REPLY_TIMEOUT_SECONDS,
        **options,
    )
