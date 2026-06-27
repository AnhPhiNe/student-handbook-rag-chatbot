import logging
from typing import Any, Dict, List, Optional
from pymongo import MongoClient, UpdateOne
import os
from src.common.env_loader import load_project_env

logger = logging.getLogger(__name__)

class MongoDocStore:
    def __init__(self, uri: str, db_name: str = "chatbotHCMUE", collection_name: str = "parent_docs"):
        self.client = MongoClient(uri)
        self.db = self.client[db_name]
        self.collection = self.db[collection_name]

    def insert_documents(self, documents: List[Dict[str, Any]]) -> None:
        if not documents:
            return

        operations = []
        for doc in documents:
            if "_id" not in doc:
                continue
            operations.append(
                UpdateOne(
                    {"_id": doc["_id"]},
                    {"$set": doc},
                    upsert=True
                )
            )

        if operations:
            result = self.collection.bulk_write(operations)
            logger.info(f"Inserted/Updated {result.upserted_count + result.modified_count} docs into MongoDB.")

    def get_document_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        return self.collection.find_one({"_id": doc_id})

def get_mongo_store() -> MongoDocStore:
    load_project_env()
    uri = os.environ.get("MONGODB_URL")
    if not uri:
        raise ValueError("MONGODB_URL not found in environment variables")
    return MongoDocStore(uri=uri)
