import os
from dotenv import load_dotenv
load_dotenv()
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
import json
import logging
from typing import List, Dict, Any
from sentence_transformers import CrossEncoder
from src.retrieval.core.graph_traverser import NetworkXGraphTraverser
from qdrant_client import QdrantClient

logger = logging.getLogger("hybrid_pipeline")

class HybridRetrieverV6:
    def __init__(self, qdrant_url: str, qdrant_key: str, collection_name: str = "student_handbook_semantic_v6"):
        # 1. Khởi tạo Qdrant Client (Vector Search)
        self.qdrant_client = QdrantClient(url=qdrant_url, api_key=qdrant_key, timeout=60.0)
        self.collection_name = collection_name
        
        # Lấy mô hình Embedding (để mã hóa câu hỏi thành Vector)
        from sentence_transformers import SentenceTransformer
        self.embed_model = SentenceTransformer("BAAI/bge-m3")
        
        # 2. Khởi tạo Graph Traverser (NetworkX)
        self.graph = NetworkXGraphTraverser()
        
        # 3. Khởi tạo Reranker (PhoRanker - Offline)
        logger.info("Đang nạp mô hình PhoRanker (Offline)...")
        self.reranker = CrossEncoder("itdainb/PhoRanker", max_length=256)
        
        # Load Content Memory (Để bốc nội dung nhanh mà không cần chọc Mongo nhiều lần)
        with open("data/processed/chunks/all_docstore_items.json", "r", encoding="utf-8") as f:
            chunks = json.load(f)
            self.content_store = {c["_id"]: c for c in chunks}

    def retrieve(self, query: str, top_k_vector: int = 5, top_k_final: int = 5, graph_depth: int = 3) -> List[Dict[str, Any]]:
        logger.info(f"==> Câu hỏi: {query}")
        
        # BƯỚC 1: VECTOR SEARCH (Tìm Top K ban đầu)
        query_vector = self.embed_model.encode(query).tolist()
        search_results = self.qdrant_client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=top_k_vector
        ).points
        
        seed_ids = [hit.payload["chunk_id"] for hit in search_results if hit.payload]
        logger.info(f"[*] Vector Search nhặt được {len(seed_ids)} khối Vàng (Seed Nodes).")

        # BƯỚC 2: GRAPH EXPANSION (Đào bới Đồ thị)
        expanded_nodes = self.graph.expand_context(seed_ids, max_depth=graph_depth)
        expanded_ids = [n["id"] for n in expanded_nodes]
        
        # Gộp và loại bỏ trùng lặp
        candidate_ids = list(set(seed_ids + expanded_ids))
        logger.info(f"[*] Graph Traversal mở rộng ra thêm {len(expanded_ids)} khối láng giềng. Tổng Candidates: {len(candidate_ids)}.")

        if not candidate_ids:
            return []

        # BƯỚC 3: CHUẨN BỊ NỘI DUNG (Content Retrieval)
        candidate_contents = []
        candidate_docs = []
        for cid in candidate_ids:
            if cid in self.content_store:
                doc = self.content_store[cid]
                # PhoRanker yêu cầu cặp (Query, Document)
                candidate_contents.append(doc["content"])
                candidate_docs.append(doc)

        # BƯỚC 4: RERANKING VỚI PHORANKER
        logger.info(f"[*] Chấm điểm lại (Reranking) {len(candidate_docs)} khối bằng PhoRanker...")
        # Tạo mảng các cặp [ [query, doc1], [query, doc2], ... ]
        cross_inp = [[query, content] for content in candidate_contents]
        scores = self.reranker.predict(cross_inp)
        
        # Ghép điểm số vào docs và sắp xếp giảm dần
        for i, doc in enumerate(candidate_docs):
            doc["rerank_score"] = float(scores[i])
            
        candidate_docs.sort(key=lambda x: x["rerank_score"], reverse=True)
        
        # BƯỚC 5: LỌC KẾT QUẢ CUỐI CÙNG (Áp dụng Tối đa K và Ngưỡng Điểm)
        final_results = []
        for doc in candidate_docs:
            # PhoRanker xuất ra dạng Logit (Score > 0.0 là ranh giới phân biệt Rác và Thật)
            if doc["rerank_score"] > 0.0:
                final_results.append(doc)
            if len(final_results) == top_k_final:
                break
                
        logger.info(f"[*] Hoàn tất lọc Top {len(final_results)} kết quả xuất sắc nhất (Ngưỡng Logit > 0.0).")
        
        return final_results

_GLOBAL_RETRIEVER = None

def run_hybrid_retrieval_pipeline(
    query: str,
    top_k: int = 5,
    **kwargs
) -> dict[str, Any]:
    """
    Adapter tương thích ngược: Bọc HybridRetrieverV6 để trả về cấu trúc output giống 
    hệt như run_retrieval_pipeline cũ, giúp Chatbot UI không bị gãy.
    Đã được tối ưu hóa Singleton Caching: Khởi tạo mô hình AI 1 lần duy nhất để giải phóng RAM.
    """
    global _GLOBAL_RETRIEVER
    
    if _GLOBAL_RETRIEVER is None:
        import os
        from src.common.env_loader import load_project_env
        load_project_env()
        
        qdrant_url = os.getenv("QDRANT_URL")
        qdrant_key = os.getenv("QDRANT_API_KEY")
        
        # Khởi tạo cỗ máy V6 (Chỉ chạy 1 lần)
        logger.info("[*] Đang khởi tạo Cỗ Máy Tìm Kiếm V6 vào Bộ Nhớ Đệm Toàn Cục...")
        _GLOBAL_RETRIEVER = HybridRetrieverV6(qdrant_url, qdrant_key)
    
    # Gọi hàm truy xuất Top K
    docs = _GLOBAL_RETRIEVER.retrieve(query, top_k_final=top_k)
    
    # Format lại Citations cho UI (Lấy nguyên khối metadata)
    citations = []
    formatted_results = []
    for doc in docs:
        metadata = doc.get("metadata", {})
        if metadata and metadata not in citations:
            citations.append(metadata)
        
        doc_copy = dict(doc)
        doc_copy["chunk_id"] = doc.get("_id") or doc.get("id")
        formatted_results.append(doc_copy)
            
    # Bọc lại thành Hộp Quà (Dictionary) y như hệ thống cũ yêu cầu
    return {
        "query": query,
        "retrieval_query": query,
        "detected_entities": [],
        "intent": "regulation_query",
        "strategy": "semantic_filtered",
        "target_chunk_types": ["regulation"],
        "retrieved_items": formatted_results,
        "citations": citations,
        "needs_llm_answer": True,
        "needs_clarification": False,
        "out_of_domain": False
    }

if __name__ == "__main__":
    from src.common.env_loader import load_project_env
    load_project_env()
    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_key = os.getenv("QDRANT_API_KEY")
    
    retriever = HybridRetrieverV6(qdrant_url, qdrant_key)
    res = retriever.retrieve("Điều kiện xét học bổng là gì?")
    for r in res:
        print(f"[{r['rerank_score']:.4f}] {r['metadata']['title']}")
