import json
import random
from pathlib import Path
from src.generation.groq_client import GroqClient

CHUNKS_PATH = Path("data/processed/chunks/all_chunks.json")
OUTPUT_PATH = Path("data/eval/generation_eval_cases.json")

def load_chunks():
    with open(CHUNKS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def build_prompt(chunk_text, chunk_type):
    return f"""Bạn là một chuyên gia tạo dữ liệu đánh giá hệ thống RAG cho Sổ tay sinh viên trường Đại học Sư phạm TP.HCM (HCMUE).
Dựa vào đoạn văn bản dưới đây (trích từ sổ tay), hãy đóng vai một sinh viên để đặt 1 câu hỏi thực tế, và viết 1 đáp án chuẩn xác.

ĐOẠN VĂN BẢN (Loại: {chunk_type}):
{chunk_text}

Yêu cầu:
1. Câu hỏi (query) phải tự nhiên, giống như sinh viên nhắn tin hỏi (có thể dùng từ ngữ sinh viên như "rớt môn", "học bổng", "trường mình"). KHÔNG ĐƯỢC nhắc đến số trang hay "Điều mấy" trong câu hỏi.
2. Đáp án chuẩn (ground_truth) phải trả lời đầy đủ, chi tiết, bám sát đoạn văn bản trên.

Trả về DUY NHẤT một chuỗi JSON hợp lệ, không có markdown formatting, không có backticks, với cấu trúc:
{{
  "query": "câu hỏi của sinh viên",
  "ground_truth": "đáp án chuẩn",
  "expected_intent": "{chunk_type}_query"
}}"""

def main():
    from src.common.console import configure_utf8_stdio
    configure_utf8_stdio()
    print("Loading chunks...")
    chunks = load_chunks()
    
    # Filter out pure tables and structured lookups which might be hard to parse
    valid_chunks = [c for c in chunks if c["chunk_type"] not in ["table", "structured_lookup", "formula"]]
    
    print(f"Loaded {len(valid_chunks)} valid chunks.")
    
    # Sample 90 chunks
    random.seed(42)
    sampled_chunks = random.sample(valid_chunks, 90)
    
    from src.common.env_loader import load_project_env
    load_project_env()
    
    client = GroqClient(model_name="llama-3.3-70b-versatile", temperature=0.2)
    
    cases = []
    print("Generating 90 evaluation cases...")
    for i, chunk in enumerate(sampled_chunks, 1):
        print(f"[{i}/90] Generating case from chunk {chunk['chunk_id']} ({chunk['chunk_type']})...")
        prompt = build_prompt(chunk["content"], chunk["chunk_type"])
        result = client.generate(prompt)
        
        if result["ok"]:
            try:
                # Clean up markdown if any
                text = result["text"].strip()
                if text.startswith("```json"):
                    text = text[7:]
                if text.endswith("```"):
                    text = text[:-3]
                
                case = json.loads(text)
                case["id"] = f"gen_case_{i:03d}"
                case["chunk_id"] = chunk["chunk_id"]
                cases.append(case)
                print(f"  -> Success: {case['query']}")
            except json.JSONDecodeError:
                print(f"  -> Failed to parse JSON: {result['text'][:50]}...")
        else:
            print(f"  -> API Error: {result['error_message']}")
            
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)
        
    print(f"\nSuccessfully generated {len(cases)} cases and saved to {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
