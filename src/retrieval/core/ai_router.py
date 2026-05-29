import json
import os
import re
from typing import Any
from groq import Groq
from src.common.env_loader import load_project_env

DEFAULT_ROUTER_MODEL = "qwen/qwen3-32b"

class AIRouter:
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
            # We'll use a dummy or empty key just to initialize if not found,
            # but it will fail on call. Or we can just let Groq handle it.
            self.client = Groq(api_key="MISSING_KEY") if api_key is None else Groq(api_key=api_key)
        else:
            self.client = Groq(api_key=api_key)
            
    def route(self, query: str) -> dict[str, Any]:
        if self.client.api_key == "MISSING_KEY" or not self.client.api_key:
            return self._build_fallback(query, "regulation_query", "semantic_filtered", ["regulation"])
            
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
- mixed_query: Hỏi nhiều ý (ví dụ: xin mẫu đơn và hỏi nộp phòng nào -> form + office_directory)

Nếu câu hỏi quá ngắn hoặc cực kỳ mơ hồ (ví dụ: "hỏi ai?", "học vụ", "ở đâu"), hãy set needs_clarification = true và cung cấp clarification_question bằng tiếng Việt.

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
            # Fallback an toàn nếu Groq gọi thất bại (lỗi kết nối, lỗi API key)
            print(f"AIRouter error: {e}")
            return self._build_fallback(query, "regulation_query", "semantic_filtered", ["regulation"])
            
    def _build_fallback(self, query: str, intent: str, strategy: str, chunk_types: list[str]) -> dict[str, Any]:
        return {
            "intent": intent,
            "strategy": strategy,
            "target_chunk_types": chunk_types,
            "needs_clarification": False,
            "clarification_question": None
        }

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
