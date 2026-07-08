import logging
from typing import List, Dict, Any

from src.retrieval.vectorstore.kuzu_store import KuzuGraphStore

logger = logging.getLogger("graph_retriever")

# Mapping từ điển để dịch Mũi tên (Predicate) thành tiếng Việt tự nhiên
PREDICATE_VERBALIZATION = {
    "QUY_DINH_TAI": "được quy định chi tiết tại",
    "TINH_VAO": "được tính vào",
    "LA_DIEU_KIEN_CUA": "là điều kiện bắt buộc của",
    "BI_KY_LUAT_MUC": "sẽ bị xử lý kỷ luật ở mức",
    "DO_PHONG_BAN_QUAN_LY": "được quản lý và xử lý bởi",
    "DAN_CHIEU_TOI": "có liên quan và dẫn chiếu tới",
    "LA_DONG_NGHIA_CUA": "có ý nghĩa tương đương với",
    "BAT_BUOC_LAM": "phải thực hiện công việc"
}

class GraphRetriever:
    def __init__(self, db_path: str = "data/processed/kuzu_db"):
        self.store = KuzuGraphStore(db_path=db_path)

    def verbalize(self, triplet: Dict[str, Any]) -> str:
        """Dịch một Bộ ba (Triplet) thành một câu văn xuôi tự nhiên"""
        subject = triplet.get("source", "")
        predicate = triplet.get("predicate", "")
        obj = triplet.get("target", "")
        
        # Dịch Predicate ra tiếng Việt (nếu không có thì dùng dạng thô)
        verb = PREDICATE_VERBALIZATION.get(predicate, f"có quan hệ {predicate} với")
        
        return f"{subject} {verb} {obj}."

    def retrieve(self, entities: List[str], depth: int = 2, cohort: str = None) -> List[Dict[str, Any]]:
        """
        Lùng sục Đồ thị để lấy mạng lưới lân cận và dịch thành văn xuôi.
        Trả về danh sách các document giống format của BM25/Qdrant để đưa vào RRF.
        """
        if not entities:
            logger.info("Không nhận diện được Entity nào trong câu hỏi. Bỏ qua Graph Search.")
            return []
            
        logger.info(f"Bắt đầu Graph Search cho các entities: {entities} (Depth={depth}, Cohort={cohort})")
        
        # Lấy mạng lưới đồ thị (danh sách các mối quan hệ)
        raw_subgraph = self.store.get_subgraph(entities, depth=depth, cohort=cohort)
        
        if not raw_subgraph:
            logger.info("Graph Search không tìm thấy liên kết nào.")
            return []
            
        # Gom nhóm các câu văn theo chunk_id để tái tạo lại Context lớn hơn
        graph_documents = []
        
        # Import mongo_store để móc nội dung
        from src.retrieval.vectorstore.mongo_store import get_mongo_store
        mongo_store = get_mongo_store()
        
        for rel in raw_subgraph:
            verbalized_text = self.verbalize(rel)
            chunk_id = rel.get("chunk_id", "graph_node")
            source_id = rel.get("source", "")
            target_id = rel.get("target", "")
            
            # Lặn xuống Mongo lấy Content của Source và Target
            source_content = ""
            target_content = ""
            if source_id:
                s_doc = mongo_store.get_document_by_id(source_id)
                if s_doc and "content" in s_doc:
                    source_content = f"\\n--- Nội dung {source_id} ---\\n{s_doc['content']}"
            if target_id:
                t_doc = mongo_store.get_document_by_id(target_id)
                if t_doc and "content" in t_doc:
                    target_content = f"\\n--- Nội dung {target_id} ---\\n{t_doc['content']}"
                    
            full_text = f"[GRAPH CONTEXT] {verbalized_text}{source_content}{target_content}"
            
            doc = {
                "id": chunk_id,
                "text": full_text,
                "score": 1.0,
                "metadata": {
                    "source": "knowledge_graph",
                    "predicate": rel.get("predicate", ""),
                    "source_node": source_id,
                    "target_node": target_id
                }
            }
            graph_documents.append(doc)
            
        logger.info(f"Graph Search tìm được {len(graph_documents)} câu dẫn chiếu (kèm full context).")
        return graph_documents
