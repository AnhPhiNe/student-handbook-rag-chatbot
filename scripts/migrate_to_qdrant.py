import os
import sys
import argparse
import yaml
from tqdm import tqdm
import hashlib
import uuid

def string_to_uuid(s: str) -> str:
    m = hashlib.md5()
    m.update(s.encode('utf-8'))
    return str(uuid.UUID(m.hexdigest()))

# Thêm thư mục gốc vào PYTHONPATH để có thể import src
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_chroma_client(persist_dir: str):
    import chromadb
    return chromadb.PersistentClient(path=persist_dir)

def get_qdrant_client(url: str, api_key: str):
    try:
        from qdrant_client import QdrantClient
    except ImportError:
        raise RuntimeError("Vui lòng cài đặt: pip install qdrant-client")
    
    return QdrantClient(url=url, api_key=api_key, timeout=60.0)

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description="Chuyển dữ liệu từ ChromaDB (Local) sang Qdrant (Cloud)")
    parser.add_argument("--config", type=str, default="configs/embedding.yaml", help="Đường dẫn file config")
    parser.add_argument("--batch-size", type=int, default=30, help="Batch size để đẩy dữ liệu lên Qdrant")
    args = parser.parse_args()

    # 1. Đọc cấu hình ChromaDB hiện tại
    print("1. Đọc cấu hình từ:", args.config)
    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    chroma_dir = config.get("vectorstore", {}).get("persist_dir", "data/vectorstore/chroma")
    collection_name = config.get("vectorstore", {}).get("collection_name", "student_handbook_semantic")
    
    print(f"   Thư mục ChromaDB: {chroma_dir}")
    print(f"   Tên Collection nguồn: {collection_name}")

    # 2. Lấy dữ liệu từ ChromaDB
    print("\n2. Kết nối ChromaDB và trích xuất dữ liệu...")
    chroma_client = get_chroma_client(chroma_dir)
    try:
        chroma_col = chroma_client.get_collection(collection_name)
    except Exception:
        print(f"   Lỗi: Không tìm thấy collection '{collection_name}' trong ChromaDB.")
        return

    chroma_data = chroma_col.get(include=["documents", "metadatas", "embeddings"])
    ids = chroma_data.get("ids", [])
    documents = chroma_data.get("documents", [])
    metadatas = chroma_data.get("metadatas", [])
    embeddings = chroma_data.get("embeddings", [])

    total_chunks = len(ids)
    print(f"   Đã lấy {total_chunks} chunks từ ChromaDB.")
    
    if total_chunks == 0:
        print("   Không có dữ liệu để chuyển. Kết thúc.")
        return

    # 3. Kết nối Qdrant Cloud
    print("\n3. Kết nối Qdrant Cloud...")
    from src.common.env_loader import load_project_env
    load_project_env()
    
    qdrant_url = os.environ.get("QDRANT_URL")
    qdrant_key = os.environ.get("QDRANT_API_KEY")
    
    if not qdrant_url or not qdrant_key:
        print("   LỖI: Bạn chưa cấu hình QDRANT_URL và QDRANT_API_KEY trong file .env!")
        return
        
    qdrant_client = get_qdrant_client(qdrant_url, qdrant_key)
    
    # 4. Kiểm tra và tạo Collection trên Qdrant
    print("\n4. Khởi tạo Collection trên Qdrant...")
    from qdrant_client.models import Distance, VectorParams, PointStruct
    
    vector_size = len(embeddings[0])
    qdrant_collection = collection_name
    
    if qdrant_client.collection_exists(qdrant_collection):
        print(f"   Collection '{qdrant_collection}' đã tồn tại trên Qdrant. Đang xóa để nạp lại...")
        qdrant_client.delete_collection(qdrant_collection)
        
    qdrant_client.create_collection(
        collection_name=qdrant_collection,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )
    from src.retrieval.vectorstore.vectorstore_factory import ensure_payload_indexes

    ensure_payload_indexes(qdrant_client, qdrant_collection)
    print(f"   Đã tạo thành công Collection '{qdrant_collection}' với vector_size={vector_size}")

    # 5. Đẩy dữ liệu lên Qdrant
    print("\n5. Bắt đầu đẩy dữ liệu lên Qdrant Cloud...")
    
    points = []
    for i in range(total_chunks):
        metadata = metadatas[i] or {}
        # Đưa document text vào metadata để tương thích với Factory Adapter
        metadata["content"] = documents[i]
        
        # Qdrant yêu cầu ID phải là int hoặc UUID hợp lệ
        qdrant_id = string_to_uuid(str(ids[i]))
        
        points.append(
            PointStruct(
                id=qdrant_id,
                vector=embeddings[i],
                payload=metadata
            )
        )

    # Đẩy theo batch
    for i in tqdm(range(0, total_chunks, args.batch_size), desc="Đang upload"):
        batch = points[i:i + args.batch_size]
        qdrant_client.upsert(
            collection_name=qdrant_collection,
            points=batch
        )

    print(f"\n✅ HOÀN TẤT! Đã đẩy thành công {total_chunks} chunks lên Qdrant Cloud (Collection: {qdrant_collection}).")
    print("Bây giờ bạn chỉ cần cấu hình VECTORDB_PROVIDER=qdrant_cloud và cập nhật collection_name=_v2 trong embedding.yaml.")

if __name__ == "__main__":
    main()
