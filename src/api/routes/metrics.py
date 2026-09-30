"""The public visit counter shown in the frontend, kept in MongoDB.

MongoDB already holds the handbook's parent documents, so the counter needs no
other service. One document in the `app_metrics` collection holds the raw
count; `$inc` is atomic, so concurrent visits are all counted. Displayed
counts add STUDENT_RAG_VISIT_COUNT_OFFSET to the raw count.

A developer machine that shares the production database sets
STUDENT_RAG_VISIT_COUNTER=false, so its page loads are not counted.
"""
import os
from typing import Any

from fastapi import APIRouter, Query

from src.common.env_loader import env_bool

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

METRICS_COLLECTION = "app_metrics"
VISIT_TOTAL_ID = "visits_total"
DEFAULT_VISIT_COUNT_OFFSET = 150
# The counter is optional: a slow database answers "unavailable", never a hung page.
TIMEOUT_MS = 3000

_collection = None


def get_metrics_collection():
    """The MongoDB collection holding the counter, or False when the counter is off or unreachable."""

    global _collection
    if _collection is not None:
        return _collection

    uri = os.environ.get("MONGODB_URL")
    if not uri or not env_bool("STUDENT_RAG_VISIT_COUNTER", default=True):
        _collection = False
        return _collection

    try:
        from pymongo import MongoClient

        client = MongoClient(
            uri,
            serverSelectionTimeoutMS=TIMEOUT_MS,
            connectTimeoutMS=TIMEOUT_MS,
            socketTimeoutMS=TIMEOUT_MS,
        )
        db_name = str(os.environ.get("MONGODB_DB_NAME") or "chatbotHCMUE").strip()
        _collection = client[db_name][METRICS_COLLECTION]
    except Exception as e:
        print(f"[Metrics] MongoDB connection failed: {e}")
        _collection = False

    return _collection


@router.get("/visits")
def get_visit_count(  # sync: FastAPI runs it off the event loop, so a slow database blocks only this request
    increment: bool = Query(False, description="Increment total visit counter"),
) -> dict[str, Any]:
    """Return the total frontend visit count, counting this visit when asked."""
    collection = get_metrics_collection()
    if collection is False:
        return {"count": None, "status": "unavailable"}

    try:
        if increment:
            from pymongo import ReturnDocument

            document = collection.find_one_and_update(
                {"_id": VISIT_TOTAL_ID},
                {"$inc": {"count": 1}},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
        else:
            document = collection.find_one({"_id": VISIT_TOTAL_ID})
        raw_count = int((document or {}).get("count") or 0)
        offset = int(
            os.getenv("STUDENT_RAG_VISIT_COUNT_OFFSET", str(DEFAULT_VISIT_COUNT_OFFSET))
        )
        return {"count": offset + raw_count, "raw_count": raw_count, "status": "ok"}
    except Exception as e:
        print(f"[Metrics] Error tracking visits: {e}")
        return {"count": None, "status": "error"}
