import json
import os
import re
import sys
from typing import Any

# Add the project root to sys.path so we can import src modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.generation.gemini_client import GeminiClient

def refactor_forms():
    forms_dir = os.path.join("data", "processed", "forms")
    
    # 1. Load the 4 messy JSON files
    source_files = [
        "K48-K49_form_templates.json",
        "K50_form_templates.json",
        "K51_form_templates.json",
        "form_templates.json"
    ]
    
    all_raw_forms = []
    for filename in source_files:
        filepath = os.path.join(forms_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                    all_raw_forms.extend(data)
                except json.JSONDecodeError:
                    print(f"Failed to parse {filename}")
    
    # 2. Extract valid forms (mostly from K48-K49) and deduplicate by name
    # Also ignore false positives like "Biểu mẫu trang 171" in K50 which is just a procedure
    valid_forms_dict = {}
    
    for form in all_raw_forms:
        name = form.get("form_name", "").strip()
        raw_text = form.get("raw_text", "").strip()
        
        if not name or not raw_text:
            continue
            
        # Filter out false positives (like procedure tables masquerading as forms)
        if "Biểu mẫu trang" in name:
            continue
            
        # Keep the most complete version (longest raw_text)
        if name not in valid_forms_dict or len(raw_text) > len(valid_forms_dict[name]["raw_text"]):
            valid_forms_dict[name] = form
            
    print(f"Found {len(valid_forms_dict)} unique valid forms.")
    
    # 3. Use Gemini to extract purpose_summary
    from src.generation.gemini_client import GeminiClient
    llm = GeminiClient(model_name="gemini-3.1-flash-lite", temperature=0.1, max_output_tokens=300)
    
    clean_forms = []
    
    for idx, (name, form) in enumerate(valid_forms_dict.items()):
        print(f"Processing ({idx+1}/{len(valid_forms_dict)}): {name}")
        raw_text = form.get("raw_text", "")
        
        prompt = f"""Bạn là một chuyên gia phân tích biểu mẫu hành chính.
Dưới đây là văn bản thô (raw text) được trích xuất từ một biểu mẫu/đơn từ của trường đại học.

Tên biểu mẫu: {name}

Nội dung thô:
{raw_text[:2000]}

NHIỆM VỤ CỦA BẠN:
Hãy viết một đoạn Tóm tắt mục đích (purpose_summary) ngắn gọn (dưới 100 chữ) mô tả:
1. Biểu mẫu này dùng để làm gì?
2. Những ai cần ký tên vào biểu mẫu này (nếu có)?
3. Phải nộp kèm những gì (nếu có)?

RÀNG BUỘC CỰC KỲ QUAN TRỌNG (ANTI-HALLUCINATION):
- CHỈ ĐƯỢC PHÉP dựa vào các thông tin có thật trong "Nội dung thô" ở trên.
- TUYỆT ĐỐI KHÔNG bịa thêm điều kiện áp dụng nếu không có trong chữ.
- Nếu không có thông tin về người ký hoặc giấy tờ kèm theo, hãy bỏ qua.

Chỉ xuất ra đúng 1 đoạn văn. Bắt đầu bằng: "Sử dụng khi..." hoặc "Dùng để..."
"""
        
        res = llm.generate(prompt)
        purpose_summary = res["text"].strip() if res.get("ok") else "Dùng để sinh viên điền thông tin và nộp cho nhà trường."
        
        # Clean up Markdown markdown blocks if LLM still wrapped it
        purpose_summary = re.sub(r'```[a-zA-Z]*\n', '', purpose_summary)
        purpose_summary = purpose_summary.replace('```', '').strip()
        
        clean_forms.append({
            "form_name": name,
            "source_pages": form.get("source_pages", []),
            "applicable_cohorts": ["K48", "K49", "K50", "K51"],
            "purpose_summary": purpose_summary
        })
        
    # 4. Add the Super Portal Forms for K50/K51
    clean_forms.append({
        "form_name": "Cổng Biểu mẫu Công tác Sinh viên (CTCT&HSSV)",
        "source_pages": [172],
        "applicable_cohorts": ["K50", "K51"],
        "purpose_summary": "Sử dụng để truy cập và tải tất cả các biểu mẫu, mẫu đơn liên quan đến công tác sinh viên của Phòng CTCT&HSSV (ví dụ: đánh giá rèn luyện, ngoại trú...). Sinh viên truy cập đường dẫn: http://tracuu.hcmue.edu.vn/bieumauctsv"
    })
    
    clean_forms.append({
        "form_name": "Cổng Biểu mẫu Phòng Đào tạo",
        "source_pages": [172],
        "applicable_cohorts": ["K50", "K51"],
        "purpose_summary": "Sử dụng để truy cập và tải tất cả các biểu mẫu, mẫu đơn liên quan đến các công việc của Phòng Đào tạo (ví dụ: xin tạm nghỉ học, bảo lưu, học lại, chuyển trường...). Sinh viên truy cập đường dẫn: http://tracuu.hcmue.edu.vn/Quytrinh_bieumau_daotao"
    })
    
    # 5. Save the clean JSON
    output_path = os.path.join(forms_dir, "clean_form_templates.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(clean_forms, f, ensure_ascii=False, indent=2)
        
    print(f"\nSuccessfully generated {output_path} with {len(clean_forms)} items.")
    
    # 6. Delete the old junk files
    for filename in source_files:
        filepath = os.path.join(forms_dir, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"Deleted old file: {filename}")

if __name__ == "__main__":
    refactor_forms()
