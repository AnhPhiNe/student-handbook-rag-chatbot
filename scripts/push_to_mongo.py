import argparse
import sys
import os
import yaml

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
    
    docstore_path = Path(config["output"]["docstore_items"])
    print(f"Loading docstore items from {docstore_path}...")
    try:
        docstore_items = load_json(docstore_path)
    except FileNotFoundError:
        print(f"Lỗi: Không tìm thấy file {docstore_path}.")
        return

    print(f"Total docstore items: {len(docstore_items)}")
    
    print("Connecting to MongoDB Atlas...")
    mongo_store = get_mongo_store()
    
    print("Inserting documents into MongoDB...")
    mongo_store.insert_documents(docstore_items)
    print("MongoDB push completed successfully!")

if __name__ == "__main__":
    main()
