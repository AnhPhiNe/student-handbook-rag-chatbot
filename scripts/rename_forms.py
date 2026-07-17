import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.generation.gemini_client import GeminiClient

def rename_forms():
    forms_dir = os.path.join("data", "processed", "forms")
    filepath = os.path.join(forms_dir, "clean_form_templates.json")
    
    with open(filepath, "r", encoding="utf-8") as f:
        forms = json.load(f)
        
    llm = GeminiClient(model_name="gemini-3.1-flash-lite", temperature=0.1, max_output_tokens=100)
    
    for idx, form in enumerate(forms):
        old_name = form["form_name"]
        summary = form["purpose_summary"]
        
        # Don't rename the portal ones as they are already perfect
        if "Cổng Biểu mẫu" in old_name:
            continue
            
        prompt = f"""Bạn là một chuyên gia hành chính.
Tên biểu mẫu gốc: {old_name}
Tóm tắt mục đích: {summary}

NHIỆM VỤ:
Dựa vào tóm tắt mục đích, hãy đặt lại tên biểu mẫu sao cho rõ ràng, đầy đủ và chuyên nghiệp nhất.
Ví dụ: 
- Gốc: "GIẤY XÁC NHẬN" -> Mới: "Giấy xác nhận sinh viên (vay vốn ngân hàng)"
- Gốc: "BIÊN BẢN HỌP LỚP ......" -> Mới: "Biên bản họp lớp (Đánh giá kết quả rèn luyện)"
- Gốc: "ĐƠN ĐỀ NGHỊ" -> Mới: "Đơn đề nghị hỗ trợ chi phí học tập" (nếu tóm tắt nhắc đến chi phí)

YÊU CẦU:
- Tên mới phải viết hoa chữ cái đầu, các chữ sau viết thường cho chuẩn format.
- Chỉ trả về đúng 1 dòng là tên mới, không giải thích, không dùng ngoặc kép.
"""
        res = llm.generate(prompt)
        new_name = res["text"].strip() if res.get("ok") else old_name
        
        # Clean up markdown
        new_name = new_name.replace('```', '').strip()
        
        print(f"[{idx+1}/{len(forms)}] {old_name}  =>  {new_name}")
        form["form_name"] = new_name
        
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(forms, f, ensure_ascii=False, indent=2)
        
    print(f"\nSuccessfully renamed forms in {filepath}")

if __name__ == "__main__":
    rename_forms()
