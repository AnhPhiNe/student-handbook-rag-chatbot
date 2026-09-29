import os
from typing import Any

from fastapi import APIRouter, Query

from src.common.redis_client import connect as connect_redis
from src.common.redis_client import redis_disabled

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

VISIT_TOTAL_KEY = "metrics:visits_total"
DEFAULT_VISIT_COUNT_OFFSET = 150

_redis_client = None


def get_redis_client():
    """Return a cached Redis client for metrics collection."""

    global _redis_client
    if _redis_client is not None:
        return _redis_client

    redis_url = os.environ.get("REDIS_URL")
    # A developer machine sets STUDENT_RAG_DISABLE_REDIS so its page loads do
    # not add to the public counter kept in the shared Redis.
    if not redis_url or redis_disabled():
        _redis_client = False
        return _redis_client

    try:
        _redis_client = connect_redis(redis_url, decode_responses=True)
        _redis_client.ping()
    except Exception as e:
        print(f"[Metrics] Redis connection failed: {e}")
        _redis_client = False

    return _redis_client


@router.get("/visits")
def get_visit_count(  # sync: FastAPI runs it off the event loop, so a slow Redis blocks only this request
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

