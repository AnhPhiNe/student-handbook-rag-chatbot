import sys
import os
import yaml
from collections import Counter
# Thêm thư mục gốc vào PYTHONPATH để có thể import src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.retrieval.vectorstore.mongo_store import get_mongo_store
from src.chunking.io_utils import load_json
from pathlib import Path

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    print("Loading chunking config...")
    with open("configs/chunking.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    docstore_path = Path(
        os.getenv(
            "MONGO_DOCSTORE_PATH",
            "data/processed/chunks/all_docstore_items.json",
        )
    )
    print(f"Loading docstore items from {docstore_path}...")
    try:
        docstore_items = load_json(docstore_path)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Không tìm thấy file docstore: {docstore_path}"
        ) from exc

    print(f"Total docstore items: {len(docstore_items)}")
    
    if not isinstance(docstore_items, list) or not docstore_items:
        raise RuntimeError(
            "Từ chối push MongoDB vì docstore rỗng hoặc sai định dạng."
        )

    cohort_counts = Counter(
        item.get("cohort")
        or (item.get("metadata") or {}).get("cohort")
        for item in docstore_items
    )

    expected_cohorts = {"K48-K49", "K50", "K51"}
    actual_cohorts = {
        cohort
        for cohort, count in cohort_counts.items()
        if cohort and count > 0
    }

    print(f"Documents by cohort: {dict(cohort_counts)}")

    if actual_cohorts != expected_cohorts:
        raise RuntimeError(
            "Từ chối ghi đè MongoDB vì file tổng không đủ 3 cohort. "
            f"Hiện có: {sorted(actual_cohorts)}"
        )

    document_ids = [
        str(item.get("_id") or "")
        for item in docstore_items
    ]

    if any(not document_id for document_id in document_ids):
        raise RuntimeError(
            "Từ chối push MongoDB vì có document thiếu _id."
        )

    if len(document_ids) != len(set(document_ids)):
        raise RuntimeError(
            "Từ chối push MongoDB vì phát hiện _id bị trùng."
        )
    
    print("Connecting to MongoDB Atlas...")
    mongo_store = get_mongo_store()
    print(f"Target MongoDB collection: {mongo_store.collection.name}")
    
    print("Dropping old collection to avoid orphaned data...")
    mongo_store.drop_collection()
    
    print("Inserting documents into MongoDB...")
    mongo_store.insert_documents(docstore_items)
    print("MongoDB push completed successfully!")

if __name__ == "__main__":
    main()
