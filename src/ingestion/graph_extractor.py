import json
import logging
import os
import time
from typing import Any, List
from pydantic import BaseModel, Field

# Khởi tạo logger
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger("graph_extractor")

# Đảm bảo google-genai được cài đặt
try:
    from google import genai
    from google.genai import types
except ImportError:
    logger.error("Vui lòng chạy 'pip install google-genai'")
    raise

# Danh sách các Mũi tên (Edges) được phép
ALLOWED_PREDICATES = [
    "QUY_DINH_TAI",
    "TINH_VAO",
    "LA_DIEU_KIEN_CUA",
    "BI_KY_LUAT_MUC",
    "DO_PHONG_BAN_QUAN_LY",
    "DAN_CHIEU_TOI",
    "LA_DONG_NGHIA_CUA",
    "BAT_BUOC_LAM",
    "DAN_DEN_HE_QUA",
    "SUA_DOI_TU"
]

# Định nghĩa Schema cho Pydantic (Vòng kim cô JSON)
class Triplet(BaseModel):
    subject: str = Field(description="Chủ thể chính (Ví dụ: Nghỉ học tạm thời, Điều 16)")
    predicate: str = Field(description=f"Mối quan hệ, CHỈ ĐƯỢC CHỌN từ: {', '.join(ALLOWED_PREDICATES)}")
    object: str = Field(description="Đối tượng bị tác động (Ví dụ: Thời gian học tập tối đa)")
    chunk_id: str = Field(description="ID của đoạn văn chứa bộ ba này để truy vết")

class GraphExtractionResponse(BaseModel):
    triplets: List[Triplet]

class GraphExtractor:
    def __init__(self, api_key: str = None, model_name: str = "gemini-1.5-flash"):
        # Trong thực tế nếu có 3.5-flash thì đổi tên. Mặc định Google GenAI sdk dùng gemini-1.5-flash
        self.model_name = model_name
        self.client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"))
        
        # Load từ điển lóng (nếu có)
        self.expansion_rules = self._load_dictionary()

    def _load_dictionary(self) -> list[dict[str, Any]]:
        # Tải bộ từ điển lóng để chuẩn hóa Entity (Chống lệch chuẩn)
        dict_path = os.path.join("data", "raw", "query_expansion_rules.json")
        try:
            with open(dict_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return data.get("rules", [])
        except Exception as e:
            logger.warning(f"Không tìm thấy Từ điển lóng tại {dict_path}, bỏ qua bước chuẩn hóa. Lỗi: {e}")
            return []

    def _normalize_entity(self, entity_name: str) -> str:
        """Chuẩn hóa Entity dựa trên Từ điển (Entity Resolution)"""
        if not entity_name:
            return ""
        entity_lower = entity_name.lower().strip()
        
        for rule in self.expansion_rules:
            triggers = [t.lower().strip() for t in rule.get("trigger", [])]
            expand_to = rule.get("expand_to", [])
            if not expand_to:
                continue
                
            # Nếu tên nhập vào trùng với 1 từ lóng trong danh sách Trigger
            if any(t in entity_lower for t in triggers if t):
                # Trả về tên chuẩn đầu tiên
                return expand_to[0]
                
        # Fallback: Không có trong từ điển -> Cấp visa giữ nguyên tên gốc
        return entity_name.strip()

    def extract_batch(self, chunks: List[dict], max_retries=3) -> List[dict]:
        """Micro-Batching Extraction với Auto-Retry (Fail-fast)"""
        if not chunks:
            return []

        # Ghép 30 chunks thành 1 Prompt khổng lồ
        chunks_text = ""
        for c in chunks:
            chunk_id = c.get("chunk_id", "unknown")
            content = c.get("content", "")
            chunks_text += f"\n--- [CHUNK_ID: {chunk_id}] ---\n{content}\n"

        system_instruction = f"""
Bạn là một Chuyên gia Kỹ sư Đồ thị Tri thức (Knowledge Graph Engineer). 
PHẠM VI QUÉT (QUAN TRỌNG): Tập trung quét Quy chế Đào tạo, Rèn luyện, Kỷ luật, Khen thưởng. BỎ QUA các phần Lịch sử, Sứ mạng, Tầm nhìn.

NHIỆM VỤ: Trích xuất các "Bộ ba thực thể" (Triplets) thể hiện tính liên đới/dẫn chiếu chéo.

ĐỊNH DẠNG OUTPUT:
JSON (Mảng object):
{{
  "subject": "Tên Chủ Thể (Ví dụ: [Quy chế đào tạo K51] - Điều 10)",
  "predicate": "TÊN_MỐI_QUAN_HỆ (Bắt buộc dùng danh sách bên dưới)",
  "object": "Tên Khách Thể",
  "chunk_id": "COPY NGUYÊN BẢN 100% mã CHUNK_ID mà tôi đã cung cấp cho đoạn văn đó. TUYỆT ĐỐI KHÔNG ĐƯỢC CHẾ THÊM CHỮ, NẾU KHÔNG HỆ THỐNG SẼ LỖI CƠ SỞ DỮ LIỆU!"
}}

VÒNG KIM CÔ RÀNG BUỘC (QUAN TRỌNG NHẤT):
CHỈ ĐƯỢC PHÉP dùng một trong các từ khóa sau cho `predicate`: {', '.join(ALLOWED_PREDICATES)}. Nếu không phù hợp, BỎ QUA.
- LA_DONG_NGHIA_CUA: Luôn đặt Thuật ngữ dài làm Chủ thể, Thuật ngữ viết tắt làm Khách thể.

HƯỚNG DẪN NÂNG CAO (GIẢI PHÁP UNIFORM ID - SỐNG CÒN):
- Bạn sẽ thấy dòng đầu tiên của mỗi đoạn văn là một Thẻ Bài chứa Ngữ cảnh (Ví dụ: [ID CHUẨN: K48-49_QuyCheDaoTao_ChuongI_Dieu1 | K48-49 | Quy chế đào tạo...]).
- CHỐNG ĐỤNG ĐỘ ĐIỀU LUẬT: Khi Chủ thể hoặc Khách thể là một "Điều X", bạn TUYỆT ĐỐI KHÔNG ghi chữ "Điều X". BẠN BẮT BUỘC phải COPY Y CHANG cái "ID CHUẨN" nằm trong Thẻ Bài để làm Tên Chủ Thể hoặc Khách Thể.
- Tuyệt đối không tự suy diễn, gọt dấu hay chế ra ID khác. Chỉ Copy-Paste đúng cái chuỗi ID CHUẨN mà hệ thống đã cấp trong Thẻ Bài.
- Nếu đoạn văn hiện tại là Điều 1 dẫn chiếu đến Điều 2, thì Chủ thể là [ID CHUẨN của Điều 1], Khách thể là [ID CHUẨN của Điều 2] (Hãy tự suy luận ID CHUẨN của Điều 2 dựa theo quy tắc của Điều 1).
- Giải quyết triệt để các tham chiếu chéo pháp lý (Điều này dẫn chiếu Điều kia) và chuỗi nguyên nhân - hệ quả.
- Dùng tiếng Việt chuẩn, tên thực thể phổ thông, ngắn gọn nhất nếu nó KHÔNG PHẢI là Điều luật (VD: Thời gian bảo lưu).
- Quét đầy đủ {len(chunks)} đoạn văn bản. Không được lười biếng bỏ sót.
        """

        for attempt in range(max_retries):
            try:
                # Gọi API Gemini với Pydantic Schema (Ép khuôn JSON)
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=chunks_text,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=0.0, # Giảm sáng tạo xuống 0 để chống ảo giác
                        response_mime_type="application/json",
                        response_schema=GraphExtractionResponse,
                    ),
                )
                
                # Phân tích kết quả JSON
                result_text = response.text
                result_json = json.loads(result_text)
                
                extracted_triplets = []
                for triplet in result_json.get("triplets", []):
                    # CHUẨN HÓA THỰC THỂ (Entity Resolution)
                    clean_subject = self._normalize_entity(triplet["subject"])
                    clean_object = self._normalize_entity(triplet["object"])
                    
                    if clean_subject and clean_object:
                        extracted_triplets.append({
                            "subject": clean_subject,
                            "predicate": triplet["predicate"],
                            "object": clean_object,
                            "chunk_id": triplet["chunk_id"]
                        })
                        
                logger.info(f"Đã trích xuất thành công {len(extracted_triplets)} bộ ba từ {len(chunks)} chunks.")
                return extracted_triplets
                
            except Exception as e:
                logger.error(f"Lỗi ở attempt {attempt + 1}: {e}")
                if attempt == max_retries - 1:
                    logger.error("Bỏ qua lô này do lỗi liên tục.")
                    return []
                time.sleep(5) # Đợi 5 giây rồi thử lại

        return []

    def run_pipeline(self, all_chunks: List[dict], batch_size=30, delay_seconds=15):
        """Khởi chạy toàn bộ quá trình cào dữ liệu"""
        all_triplets = []
        total_batches = (len(all_chunks) + batch_size - 1) // batch_size
        
        for i in range(total_batches):
            batch = all_chunks[i * batch_size : (i + 1) * batch_size]
            logger.info(f"Đang xử lý Lô {i+1}/{total_batches} (gồm {len(batch)} chunks)...")
            
            triplets = self.extract_batch(batch)
            all_triplets.extend(triplets)
            
            # BÙA AN TOÀN (CHECKPOINT): Ghi tạc xuống đĩa ngay sau mỗi lô
            out_path = os.path.join("data", "processed", "knowledge_graph.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump({"triplets": all_triplets}, f, ensure_ascii=False, indent=2)
                
            if i < total_batches - 1:
                logger.info(f"Đợi {delay_seconds} giây để lách luật API (5 RPM)...")
                time.sleep(delay_seconds)
                
        # Lưu kết quả
        out_dir = os.path.join("data", "processed", "graph")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "triplets.json")
        
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"triplets": all_triplets}, f, ensure_ascii=False, indent=2)
            
        logger.info(f"Hoàn tất! Đã lưu {len(all_triplets)} bộ ba vào {out_path}.")
        return out_path

# ==============================================================================
# HỖ TRỢ CHẠY SCRIPT TRỰC TIẾP TỪ TERMINAL ĐỂ NẠP DỮ LIỆU
# ==============================================================================
if __name__ == "__main__":
    import argparse
    import sys
    import os
    
    # Fix lỗi in tiếng Việt trên Terminal Windows
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
    
    # Tự động thêm thư mục gốc của dự án vào PYTHONPATH để tránh lỗi "No module named 'src'"
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
        
    from src.retrieval.vectorstore.mongo_store import get_mongo_store
    from src.retrieval.vectorstore.kuzu_store import KuzuGraphStore
    from dotenv import load_dotenv
    
    # Load các biến môi trường từ file .env
    load_dotenv()

    parser = argparse.ArgumentParser(description="Chạy bộ cào Triplet để nhúng GraphDB")
    parser.add_argument("--batch-size", type=int, default=30, help="Số chunks / 1 lô")
    parser.add_argument("--model", type=str, default="gemini-3.5-flash", help="Tên model Gemini")
    args = parser.parse_args()

    print("\n[1] KẾT NỐI MONGODB ĐỂ LẤY TOÀN BỘ CHUNKS...")
    store = get_mongo_store()
    # Kéo các chunk dạng regulation và procedure (Phù hợp nhất cho Graph)
    all_chunks = []
    # (Mô phỏng lấy chunks từ Mongo, trong thực tế sẽ gọi hàm store.get_all_documents())
    try:
        # Lấy các document có content_type là regulation_text hoặc procedure
        raw_docs = store.collection.find({"metadata.content_type": {"$in": ["regulation_text", "procedure"]}})
        for doc in raw_docs:
            all_chunks.append({
                "chunk_id": str(doc["_id"]),
                "content": doc.get("content", "")
            })
    except Exception as e:
        logger.error(f"Không thể lấy dữ liệu từ MongoDB: {e}")
        print("Vui lòng đảm bảo MongoDB đang chạy và đã có dữ liệu.")
        exit(1)

    print(f"-> Tìm thấy {len(all_chunks)} đoạn văn bản cần xử lý.")

    if len(all_chunks) == 0:
        print("Không có dữ liệu, hủy bỏ.")
        exit(0)

    print(f"\n[2] KHỞI ĐỘNG GEMINI AI ({args.model}) ĐỂ ÉP KHUÔN ĐỒ THỊ...")
    if "GEMINI_API_KEY" not in os.environ:
        print("LỖI CHÍ MẠNG: Bạn chưa set biến môi trường GEMINI_API_KEY.")
        print("Vui lòng dán key vào file .env hoặc chạy: $env:GEMINI_API_KEY='...'")
        exit(1)

    extractor = GraphExtractor(model_name=args.model)
    triplets_file = extractor.run_pipeline(all_chunks, batch_size=args.batch_size)

    print("\n[3] NẠP KẾT QUẢ VÀO KÙZU DB CHÍNH THỨC...")
    db_store = KuzuGraphStore(db_path="data/processed/kuzu_db")
    db_store.clear_database() # Xóa db cũ để tránh rác
    db_store.import_triplets(triplets_file)
    
    print("\n🎉 HOÀN TẤT INGESTION! BẠN ĐÃ CÓ THỂ CHẠY EVALUATION ĐƯỢC RỒI! 🎉")
