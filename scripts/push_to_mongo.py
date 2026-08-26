import os
import hashlib
import json
import sys
from collections import Counter
# Thêm thư mục gốc vào PYTHONPATH để có thể import src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.retrieval.vectorstore.mongo_store import get_mongo_store
from src.chunking.io_utils import load_json
from pathlib import Path


BUILD_MANIFEST_PATH = Path("data/processed/metadata/build_manifest.json")
DOCSTORE_DEFAULT_PATH = Path("data/processed/chunks/all_docstore_items.json")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_build_contract(
    docstore_items: list[dict],
    *,
    docstore_path: Path,
    collection_name: str,
) -> str:
    if not BUILD_MANIFEST_PATH.is_file():
        raise RuntimeError(f"Missing build manifest: {BUILD_MANIFEST_PATH}")
    manifest = json.loads(BUILD_MANIFEST_PATH.read_text(encoding="utf-8"))
    build_id = str(manifest.get("build_id") or "")
    if not build_id:
        raise RuntimeError("Build manifest does not contain build_id.")
    targets = manifest.get("storage_targets") or {}
    if targets.get("mongo_parent_collection") != collection_name:
        raise RuntimeError(
            "MongoDB target does not match the collection locked in the build manifest."
        )
    parent_artifact = (manifest.get("artifacts") or {}).get("parent_docstore") or {}
    if parent_artifact.get("sha256") != sha256_file(docstore_path):
        raise RuntimeError("Parent docstore hash does not match the build manifest.")
    if int(parent_artifact.get("count") or 0) != len(docstore_items):
        raise RuntimeError("Parent document count does not match the build manifest.")
    build_ids = {
        str(
            item.get("build_id")
            or (item.get("metadata") or {}).get("build_id")
            or ""
        )
        for item in docstore_items
    }
    if build_ids != {build_id}:
        raise RuntimeError(
            "Parent documents are not uniformly tagged with the manifest build_id."
        )
    return build_id


def ensure_empty_collection(collection) -> None:
    existing_count = collection.estimated_document_count()
    if existing_count:
        raise RuntimeError(
            "Từ chối ghi đè MongoDB collection đang có dữ liệu: "
            f"{collection.name!r} ({existing_count} documents). "
            "Hãy dùng một collection version mới và chỉ chuyển environment "
            "sau khi verification đạt."
        )

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    docstore_path = Path(
        os.getenv(
            "MONGO_DOCSTORE_PATH",
            str(DOCSTORE_DEFAULT_PATH),
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

    build_id = validate_build_contract(
        docstore_items,
        docstore_path=docstore_path,
        collection_name=mongo_store.collection.name,
    )
    print(f"Validated build contract: {build_id}")

    ensure_empty_collection(mongo_store.collection)
    
    print("Inserting documents into MongoDB...")
    mongo_store.insert_documents(docstore_items)
    print("MongoDB push completed successfully!")

if __name__ == "__main__":
    main()
