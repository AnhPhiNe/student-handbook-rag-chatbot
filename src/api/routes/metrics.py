import os
import time
from typing import Any

from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

VISIT_TOTAL_KEY = "metrics:visits_total"
ACTIVE_USERS_ZSET_KEY = "metrics:active_users_zset"
ACTIVE_USERS_TTL_SECONDS = 300
DEFAULT_VISIT_COUNT_OFFSET = 150

_redis_client = None


def get_redis_client():
    """Return a cached Redis client for metrics collection."""

    global _redis_client
    if _redis_client is not None:
        return _redis_client

    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        _redis_client = False
        return _redis_client

    try:
        import redis

        _redis_client = redis.from_url(redis_url, decode_responses=True)
        _redis_client.ping()
    except Exception as e:
        print(f"[Metrics] Redis connection failed: {e}")
        _redis_client = False

    return _redis_client


@router.get("/visits")
async def get_visit_count(
    increment: bool = Query(False, description="Increment total visit counter"),
) -> dict[str, Any]:
    """Return the total frontend visit count, backed by Redis when available."""
    r = get_redis_client()
    if not r:
        return {"count": None, "status": "redis_unavailable"}

    try:
        raw_count = (
            int(r.incr(VISIT_TOTAL_KEY))
            if increment
            else int(r.get(VISIT_TOTAL_KEY) or 0)
        )
        offset = int(
            os.getenv("STUDENT_RAG_VISIT_COUNT_OFFSET", str(DEFAULT_VISIT_COUNT_OFFSET))
        )
        return {"count": offset + raw_count, "raw_count": raw_count, "status": "ok"}
    except Exception as e:
        print(f"[Metrics] Error tracking visits: {e}")
        return {"count": None, "status": "error"}


@router.get("/active-users")
async def get_active_users(
    session_id: str = Query(None, description="Unique session ID of the client"),
) -> dict[str, Any]:
    """Track approximate active sessions with a Redis sorted set."""
    r = get_redis_client()
    if not r:
        return {"active_users": 1, "status": "fallback"}

    try:
        current_time = int(time.time())

        if session_id:
            r.zadd(ACTIVE_USERS_ZSET_KEY, {session_id: current_time})

        r.zremrangebyscore(
            ACTIVE_USERS_ZSET_KEY,
            "-inf",
            current_time - ACTIVE_USERS_TTL_SECONDS,
        )
        active_count = r.zcard(ACTIVE_USERS_ZSET_KEY)
        r.expire(ACTIVE_USERS_ZSET_KEY, ACTIVE_USERS_TTL_SECONDS * 2)

        return {"active_users": active_count, "status": "ok"}
    except Exception as e:
        print(f"[Metrics] Error tracking active users: {e}")
        return {"active_users": 1, "status": "error"}
