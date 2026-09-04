import logging
import os
import time
from typing import Any, Dict, List, Optional

from pymongo import MongoClient, UpdateOne

from src.common.env_loader import load_project_env
from src.common.storage_config import require_mongo_parent_collection_name

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool = True) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


class DisabledMongoDocStore:
    """Expose a no-op docstore when MongoDB parent lookup is disabled."""

    def insert_documents(self, documents: List[Dict[str, Any]]) -> None:
        """Reject writes because this docstore is intentionally disabled."""

        raise RuntimeError("MongoDB parent lookup is disabled.")

    def get_document_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Return no parent while lookup is disabled."""

        return None


class MongoDocStore:
    """Persist and retrieve full parent documents in MongoDB."""

    def __init__(
        self,
        uri: str,
        db_name: str = "chatbotHCMUE",
        collection_name: str | None = None,
        timeout_ms: int = 30000,
        failure_backoff_seconds: int = 300,
    ):
        if not collection_name or not collection_name.strip():
            raise ValueError("MongoDB parent collection name must be explicit.")
        self.client = MongoClient(
            uri,
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
            socketTimeoutMS=timeout_ms,
        )
        self.db = self.client[db_name]
        self.collection = self.db[collection_name.strip()]
        self.failure_backoff_seconds = max(0, failure_backoff_seconds)
        self._disabled_until = 0.0

    def insert_documents(self, documents: List[Dict[str, Any]]) -> None:
        """Upsert parent documents in bounded unordered batches."""

        if not documents:
            return

        operations = []
        for doc in documents:
            if "_id" not in doc:
                continue
            operations.append(
                UpdateOne({"_id": doc["_id"]}, {"$set": doc}, upsert=True)
            )

        inserted_or_updated = 0
        for start in range(0, len(operations), 100):
            result = self.collection.bulk_write(
                operations[start : start + 100],
                ordered=False,
            )
            inserted_or_updated += result.upserted_count + result.modified_count
        if operations:
            logger.info(f"Inserted/Updated {inserted_or_updated} docs into MongoDB.")

    def get_document_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Fetch one parent document with temporary backoff after failures."""

        if time.monotonic() < self._disabled_until:
            return None

        try:
            return self.collection.find_one({"_id": doc_id})
        except Exception as exc:
            self._disabled_until = time.monotonic() + self.failure_backoff_seconds
            logger.warning(
                "mongo_parent_lookup_failed",
                extra={"doc_id": doc_id, "error": str(exc)},
            )
            return None


def get_mongo_store() -> MongoDocStore | DisabledMongoDocStore:
    """Create the configured MongoDB docstore or its disabled fallback."""

    if not _env_bool("MONGODB_PARENT_LOOKUP_ENABLED", default=True):
        return DisabledMongoDocStore()

    load_project_env(override=False)

    if not _env_bool("MONGODB_PARENT_LOOKUP_ENABLED", default=True):
        return DisabledMongoDocStore()

    uri = os.environ.get("MONGODB_URL")
    if not uri:
        raise ValueError("MONGODB_URL not found in environment variables")

    timeout_ms = _env_int("MONGODB_TIMEOUT_MS", 30000)
    failure_backoff_seconds = _env_int("MONGODB_FAILURE_BACKOFF_SECONDS", 300)
    db_name = str(os.environ.get("MONGODB_DB_NAME") or "chatbotHCMUE").strip()
    collection_name = require_mongo_parent_collection_name()
    return MongoDocStore(
        uri=uri,
        db_name=db_name,
        collection_name=collection_name,
        timeout_ms=timeout_ms,
        failure_backoff_seconds=failure_backoff_seconds,
    )
