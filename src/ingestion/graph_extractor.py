import os
import json
import time
import re
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

class GeminiGraphExtractor:
    def __init__(self, all_ids):
        keys_str = os.getenv("GEMINI_API_KEYS", "")
        self.api_keys = [k.strip() for k in keys_str.split(",") if k.strip()]
        if not self.api_keys:
            raise ValueError("Cảnh báo: Chưa có GEMINI_API_KEYS trong file .env!")
        
        self.all_ids = all_ids
        self.all_ids_str = "\n".join([f"- {i}" for i in all_ids])
        
        self.current_key_idx = 0
        self.requests_on_current_key = 0
        
        # Thông số tối ưu RPM 5, RPD 20
        self.MAX_RPM = 4  
        self.MAX_RPD = 19 
        self.key_usage_day = {k: 0 for k in self.api_keys}
        
        print(f"[*] Khởi tạo Thợ Xây Graph với {len(self.api_keys)} Keys xoay vòng (Model: Gemini 3.5 Flash).")
        self._configure_current_key()
        
    def _configure_current_key(self):
        key = self.api_keys[self.current_key_idx]
        genai.configure(api_key=key)
        # SỬ DỤNG ĐÚNG MODEL GEMINI 3.5 FLASH NHƯ USER YÊU CẦU!
        self.model = genai.GenerativeModel('gemini-3.5-flash')
        
    def _rotate_key(self):
        self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
        self.requests_on_current_key = 0
        print(f"[>] Xoay sang API Key mới (Vị trí {self.current_key_idx + 1}/{len(self.api_keys)})")
        self._configure_current_key()

    def extract_batch(self, chunks_batch):
        current_key = self.api_keys[self.current_key_idx]
        if self.key_usage_day[current_key] >= self.MAX_RPD:
            print(f"[!] Key {self.current_key_idx + 1} đã hết RPD. Xoay key...")
            self._rotate_key()
            return self.extract_batch(chunks_batch)
            
        if self.requests_on_current_key >= self.MAX_RPM:
            print(f"[!] Key {self.current_key_idx + 1} đạt đỉnh RPM. Xoay key để tránh chờ đợi...")
            self._rotate_key()
            
        prompt = self._build_prompt(chunks_batch)
        
        retries = 3
        while retries > 0:
            try:
                self.requests_on_current_key += 1
                self.key_usage_day[self.api_keys[self.current_key_idx]] += 1
                
                response = self.model.generate_content(prompt)
                text = response.text
                json_str = self._extract_json(text)
                
                if json_str:
                    return json.loads(json_str)
                else:
                    return []
                    
            except Exception as e:
                error_msg = str(e)
                print(f"[x] Lỗi API: {error_msg[:100]}... Đang xoay key và thử lại (Còn {retries-1} lần)")
                self._rotate_key()
                retries -= 1
                time.sleep(3) 
                
        print("[-] Bỏ cuộc với Batch này sau nhiều lần thử thất bại!")
        return []

    def _build_prompt(self, chunks):
        text_blocks = ""
        for i, chunk in enumerate(chunks):
            content = chunk.get("content", "")
            text_blocks += f"--- ĐOẠN {i+1} ---\n{content}\n\n"
            
        return f"""Bạn là một chuyên gia Pháp chế. Nhiệm vụ của bạn là đọc các đoạn văn bên dưới và trích xuất MỐI QUAN HỆ DẪN CHIẾU chéo giữa các Điều luật (Document Graph).

Tuyệt đối tuân thủ các quy tắc Vàng sau:
1. Nút (Node) ở đây chính là các Điều luật. Tuyệt đối không trích xuất Thực thể tự do.
2. Mỗi đoạn văn đều có một thẻ bài ở đầu dạng: [ID CHUẨN: abc... | Khóa...]. Bạn PHẢI dùng chuỗi "ID CHUẨN" này làm giá trị cho trường `source`.
3. Khi tìm thấy 1 câu nhắc đến một Điều luật khác, hãy tìm ID CHUẨN của Điều luật đó để điền vào trường `target`.
4. Quan hệ (relation) LUÔN LUÔN LÀ: "LIEN_QUAN_TOI".
5. Xử lý "Tự tham chiếu": Tự động BỎ QUA nếu source trùng target (VD: "Khoản 1 Điều này...").
6. Xử lý "Dẫn chiếu nhiều Điều": Tách riêng từng Điều thành nhiều object nếu 1 câu chứa nhiều Điều (VD: "theo Điều 3, Điều 4").
7. QUY TẮC TỪ ĐIỂN (QUAN TRỌNG NHẤT): Mọi giá trị `target` bạn trích xuất BẮT BUỘC phải nằm trong [TỪ ĐIỂN ID CHUẨN] bên dưới. Nếu có dẫn chiếu nhưng ID không tồn tại trong Từ điển này, HÃY BỎ QUA mối quan hệ đó!

[TỪ ĐIỂN ID CHUẨN CÁC NÚT ĐƯỢC PHÉP SỬ DỤNG]
{self.all_ids_str}

Trả về ĐÚNG MỘT MẢNG JSON, không giải thích gì thêm:
[
  {{
    "source": "<ID CHUẨN của đoạn văn>",
    "target": "<Một ID trích từ TỪ ĐIỂN ID CHUẨN>",
    "relation": "LIEN_QUAN_TOI",
    "reason": "<trích dẫn câu chữ gốc chứng minh sự dẫn chiếu>"
  }}
]

DỮ LIỆU ĐẦU VÀO:
{text_blocks}
"""

    def _extract_json(self, text):
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            return match.group(1)
        if text.strip().startswith("[") and text.strip().endswith("]"):
            return text.strip()
        return None

def main():
    input_file = "data/processed/chunks/all_docstore_items.json"
    output_file = "data/processed/graphs/document_edges.json"
    
    # Tạo thư mục nếu chưa có
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    if not os.path.exists(input_file):
        print("Lỗi: Không tìm thấy file Vàng Mười!")
        return
        
    with open(input_file, "r", encoding="utf-8") as f:
        all_chunks = json.load(f)
        
    print(f"Tổng số chunks tải lên: {len(all_chunks)}")
    
    # Rút trích danh sách ID để làm Từ điển
    all_ids = [chunk.get("_id") for chunk in all_chunks if chunk.get("_id")]
    print(f"Đã tạo Từ điển chứa {len(all_ids)} ID chuẩn.")
    
    extractor = GeminiGraphExtractor(all_ids)
    
    batch_size = 10
    all_edges = []
    
    print(f"\n[>] Bắt đầu cày nát {len(all_chunks)} chunks (Batch={batch_size})...")
    
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i:i+batch_size]
        print(f"[*] Đang xử lý Batch {i//batch_size + 1}/{(len(all_chunks)+batch_size-1)//batch_size} (Chunks {i} đến {i+len(batch)-1})", flush=True)
        
        edges = extractor.extract_batch(batch)
        if edges:
            all_edges.extend(edges)
            # Lưu liên tục để lỡ Crash thì không mất kết quả
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(all_edges, f, ensure_ascii=False, indent=2)
            
        time.sleep(2)
    
    print(f"\n=== HOÀN TẤT TRÍCH XUẤT ===", flush=True)
    print(f"Tổng số Cạnh (Edges) thu được: {len(all_edges)}", flush=True)
        
    print(f"Đã lưu Đồ thị vào {output_file}")

if __name__ == "__main__":
    main()
