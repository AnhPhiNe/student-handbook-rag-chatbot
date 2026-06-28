import logging
import os
import time
from typing import Any, Dict, List, Optional

from pymongo import MongoClient, UpdateOne

from src.common.env_loader import load_project_env

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
    def insert_documents(self, documents: List[Dict[str, Any]]) -> None:
        raise RuntimeError("MongoDB parent lookup is disabled.")

    def get_document_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        return None

    def drop_collection(self) -> None:
        raise RuntimeError("MongoDB parent lookup is disabled.")


class MongoDocStore:
    def __init__(
        self,
        uri: str,
        db_name: str = "chatbotHCMUE",
        collection_name: str = "parent_docs",
        timeout_ms: int = 3000,
        failure_backoff_seconds: int = 300,
    ):
        self.client = MongoClient(
            uri,
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
            socketTimeoutMS=timeout_ms,
        )
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]
        self.failure_backoff_seconds = max(0, failure_backoff_seconds)
        self._disabled_until = 0.0

    def insert_documents(self, documents: List[Dict[str, Any]]) -> None:
        if not documents:
            return

        operations = []
        for doc in documents:
            if "_id" not in doc:
                continue
            operations.append(
                UpdateOne({"_id": doc["_id"]}, {"$set": doc}, upsert=True)
            )

        if operations:
            result = self.collection.bulk_write(operations)
            logger.info(
                f"Inserted/Updated {result.upserted_count + result.modified_count} docs into MongoDB."
            )

    def get_document_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
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

    def drop_collection(self) -> None:
        """Drops the entire collection. Use with caution."""
        self.collection.drop()
        logger.info(f"Dropped collection {self.collection.name}.")


def get_mongo_store() -> MongoDocStore | DisabledMongoDocStore:
    load_project_env()

    if not _env_bool("MONGODB_PARENT_LOOKUP_ENABLED", default=True):
        return DisabledMongoDocStore()

    uri = os.environ.get("MONGODB_URL")
    if not uri:
        raise ValueError("MONGODB_URL not found in environment variables")

    timeout_ms = _env_int("MONGODB_TIMEOUT_MS", 3000)
    failure_backoff_seconds = _env_int("MONGODB_FAILURE_BACKOFF_SECONDS", 300)
    return MongoDocStore(
        uri=uri,
        timeout_ms=timeout_ms,
        failure_backoff_seconds=failure_backoff_seconds,
    )
