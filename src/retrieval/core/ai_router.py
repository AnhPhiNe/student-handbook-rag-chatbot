import json
import os
import re
from typing import Any
from groq import Groq
from src.common.env_loader import load_project_env

DEFAULT_ROUTER_MODEL = "qwen/qwen3-32b"

class AIRouter:
    """
    Người Gác Cổng (AI Router) - Sử dụng LLM (Groq) để phân tích ý định (Intent) phức tạp.
    
    Trong mô hình kiến trúc, AI Router được kích hoạt khi các luật (Rules) tĩnh không
    thể giải quyết triệt để câu hỏi của người dùng. AI Router giúp:
    1. Lọc bỏ các câu hỏi rác (out_of_domain).
    2. Yêu cầu làm rõ các câu hỏi quá mơ hồ (needs_clarification).
    3. Trích xuất chính xác các loại tài liệu cần tìm (target_chunk_types) để tối ưu hoá VectorDB.
    """
    def __init__(
        self,
        model_name: str = DEFAULT_ROUTER_MODEL,
        api_key_env_var: str = "GROQ_API_KEY",
        temperature: float = 0.0,
    ):
        load_project_env(override=True)
        self.model_name = model_name
        self.temperature = temperature
        
        api_key = os.environ.get(api_key_env_var)
        if not api_key:
            # Khởi tạo tạm bằng một key giả để xử lý lỗi thanh lịch hơn khi gọi API,
            # tránh ứng dụng bị sập (crash) ngay lúc khởi động do thiếu biến môi trường.
            self.client = Groq(api_key="MISSING_KEY") if api_key is None else Groq(api_key=api_key)
        else:
            self.client = Groq(api_key=api_key)
            
    def route(self, query: str) -> dict[str, Any]:
        """Phân tích câu hỏi và trả về chiến lược tìm kiếm (Routing Strategy).
        
        Luồng xử lý:
        - Xây dựng prompt chứa các chỉ thị (guidelines) phân loại.
        - Gọi API LLM để lấy kết quả dạng JSON format.
        - Phân giải JSON để lấy `intent` và `target_chunk_types`.
        """
        if self.client.api_key == "MISSING_KEY" or not self.client.api_key:
            raise ValueError("Thiếu API Key cho hệ thống AI Router.")
            
        prompt = f"""
Bạn là AI Router của ứng dụng Sổ tay Sinh viên HCMUE. Nhiệm vụ của bạn là phân tích câu hỏi và trả về cấu trúc JSON để hệ thống biết cần tìm kiếm tài liệu nào.
Mục tiêu là tránh các quy tắc từ khóa cứng ngắc và hiểu đúng ý người dùng.

Các loại tài liệu (target_chunk_types):
- "form": biểu mẫu, đơn từ
- "procedure": quy trình, thủ tục (ví dụ: làm thế nào, quy trình xét học bổng)
- "regulation": quy định, điều kiện, điểm số, học vụ, cảnh cáo, thôi học, học phí
- "office_directory": thông tin liên hệ phòng ban, trung tâm, địa chỉ, số điện thoại
- "faculty_program_directory": thông tin khoa, ngành học

Các quy tắc (Intent):
- formula_query: Câu hỏi cần tính toán công thức (điểm trung bình, học phí)
- calculation_query: Câu hỏi có nhiều con số cần tính
- form_query: Câu hỏi xin mẫu đơn, biểu mẫu
- procedure_query: Câu hỏi về quy trình, thủ tục
- regulation_query: Câu hỏi về quy chế đào tạo, điểm số, rớt môn, học bổng
- office_query: Hỏi thông tin liên hệ, website, email phòng ban
- faculty_query: Hỏi thông tin khoa, ngành
- mixed_query: Hỏi nhiều ý HOẶC hỏi phòng ban thực hiện một thủ tục/quy định (ví dụ: xin mẫu đơn và hỏi nộp phòng nào, làm hồ sơ chuyển trường đến phòng nào -> BẮT BUỘC target_chunk_types phải có 'procedure', 'regulation' và 'office_directory')

Nếu câu hỏi quá ngắn hoặc cực kỳ mơ hồ (ví dụ: "hỏi ai?", "học vụ", "ở đâu"), hãy set needs_clarification = true và cung cấp clarification_question bằng tiếng Việt.

Nếu câu hỏi HOÀN TOÀN KHÔNG liên quan đến nội dung Sổ tay sinh viên (quy chế, quy định, học vụ, biểu mẫu, phòng ban, khoa ngành, học bổng, ký túc xá, rèn luyện, học phí, thủ tục hành chính), hãy set intent = "out_of_domain". Ví dụ: hỏi về nhà vệ sinh, căn tin, thời tiết, giải trí, chuyện cá nhân... đều là out_of_domain.

Chỉ trả về JSON hợp lệ:
{{
  "intent": "tên_intent",
  "strategy": "semantic_filtered",
  "target_chunk_types": ["danh sách chunk types phù hợp"],
  "needs_clarification": false,
  "clarification_question": null
}}

Câu hỏi của sinh viên: "{query}"
"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.temperature,
                response_format={"type": "json_object"}
            )
            
            raw_text = response.choices[0].message.content
            parsed = self._extract_json_object(raw_text)
            
            intent = parsed.get("intent", "regulation_query")
            strategy = parsed.get("strategy", "semantic_filtered")
            target_chunk_types = parsed.get("target_chunk_types", ["regulation"])
            needs_clarification = parsed.get("needs_clarification", False)
            clarification_question = parsed.get("clarification_question")
            
            # Đảm bảo strategy là hợp lệ
            if "formula" in intent:
                strategy = "formula_lookup"
            
            return {
                "intent": intent,
                "strategy": strategy,
                "target_chunk_types": target_chunk_types,
                "needs_clarification": needs_clarification,
                "clarification_question": clarification_question
            }
        except Exception as e:
            # Báo lỗi và ngắt luồng nếu LLM sập
            print(f"AIRouter error: {e}")
            raise RuntimeError(f"Lỗi khi kết nối với AI Router: {e}") from e

    def _extract_json_object(self, text: str) -> dict[str, Any]:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
            stripped = re.sub(r"\s*```$", "", stripped)

        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end < start:
            raise ValueError("LLM response did not contain a JSON object.")

        parsed = json.loads(stripped[start : end + 1])
        return parsed
