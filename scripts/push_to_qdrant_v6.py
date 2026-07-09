import os
import sys
import json
import uuid
import hashlib
from tqdm import tqdm
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from dotenv import load_dotenv

load_dotenv()

def string_to_uuid(s: str) -> str:
    m = hashlib.md5()
    m.update(s.encode('utf-8'))
    return str(uuid.UUID(m.hexdigest()))

def main():
    print("=== PUSH 503 CHUNKS VÀNG MƯỜI LÊN QDRANT V6 ===")
    
    # Lấy thông tin Qdrant từ .env
    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_api_key = os.getenv("QDRANT_API_KEY")
    if not qdrant_url or not qdrant_api_key:
        print("[!] LỖI: Chưa có biến môi trường QDRANT_URL hoặc QDRANT_API_KEY")
        sys.exit(1)

    # Khởi tạo Model
    model_name = "BAAI/bge-m3"
    print(f"[*] Đang tải mô hình Embedding {model_name}...")
    model = SentenceTransformer(model_name)
    vector_size = model.get_sentence_embedding_dimension()

    # Đọc dữ liệu 503 chunks Vàng Mười
    data_path = "data/processed/chunks/all_docstore_items.json"
    with open(data_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)
    print(f"[*] Đã nạp {len(chunks)} chunks từ {data_path}")

    # Kết nối Qdrant và thiết lập Collection
    client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key, timeout=60.0)
    collection_name = "student_handbook_semantic_v6"
    
    if client.collection_exists(collection_name):
        print(f"[*] Collection '{collection_name}' đã tồn tại, đang dọn dẹp để nạp mới...")
        client.delete_collection(collection_name)
    
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
    )
    print(f"[*] Đã tạo Collection {collection_name} (Size: {vector_size})")

    # Chuẩn bị dữ liệu và Embeddings
    print("[*] Đang mã hóa (Embedding) 503 Chunks (Vui lòng chờ)...")
    texts = [chunk["content"] for chunk in chunks]
    embeddings = model.encode(texts, batch_size=8, show_progress_bar=True, normalize_embeddings=True)

    # Đóng gói và Push
    print(f"[*] Đang đẩy dữ liệu lên Qdrant Cloud...")
    points = []
    for i, chunk in enumerate(chunks):
        qdrant_id = string_to_uuid(chunk["_id"])
        
        # Format metadata khớp với cấu trúc
        metadata = chunk.get("metadata", {})
        metadata["content"] = chunk["content"]
        metadata["chunk_id"] = chunk["_id"]
        
        points.append(PointStruct(
            id=qdrant_id,
            vector=embeddings[i].tolist(),
            payload=metadata
        ))

    # Đẩy theo batch
    batch_size = 50
    for i in tqdm(range(0, len(points), batch_size), desc="Upserting Qdrant"):
        batch = points[i:i+batch_size]
        client.upsert(collection_name=collection_name, points=batch)

    print(f"\n[+] HOÀN TẤT THÀNH CÔNG! Đã đẩy {len(points)} khối Vàng Mười lên Qdrant {collection_name}.")

if __name__ == "__main__":
    main()
