from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from typing import Deque

from fastapi import HTTPException, Request


DEFAULT_MAX_QUERY_CHARS = 500
DEFAULT_RATE_LIMIT_PER_MINUTE = 20
_RATE_LIMIT_BUCKETS: dict[str, Deque[float]] = defaultdict(deque)


def validate_chat_query(raw_query: str) -> str:
    query = raw_query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query must not be empty")

    max_chars = max_query_chars()
    if len(query) > max_chars:
        raise HTTPException(
            status_code=400,
            detail=f"Query must be at most {max_chars} characters",
        )
    return query


def enforce_chat_rate_limit(request: Request) -> None:
    limit = rate_limit_per_minute()
    if limit <= 0:
        return

    client_host = request.client.host if request.client else "unknown"
    now = time.monotonic()
    bucket = _RATE_LIMIT_BUCKETS[client_host]
    while bucket and now - bucket[0] >= 60:
        bucket.popleft()

    if len(bucket) >= limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    bucket.append(now)


def max_query_chars() -> int:
    raw_value = os.getenv("STUDENT_RAG_MAX_QUERY_CHARS", str(DEFAULT_MAX_QUERY_CHARS))
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_MAX_QUERY_CHARS
    return max(1, value)


def rate_limit_per_minute() -> int:
    raw_value = os.getenv(
        "STUDENT_RAG_RATE_LIMIT_PER_MINUTE",
        str(DEFAULT_RATE_LIMIT_PER_MINUTE),
    )
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_RATE_LIMIT_PER_MINUTE
    return max(0, value)


def should_include_debug(include_debug: bool) -> bool:
    return include_debug and os.getenv("STUDENT_RAG_SHOW_DEBUG", "false").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
