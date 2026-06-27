import json
import random

def augment_data(file_path, target_count):
    with open(file_path, 'r', encoding='utf-8') as f:
        cases = json.load(f)
    
    current_count = len(cases)
    needed = target_count - current_count
    if needed <= 0: return
    
    new_cases = []
    
    # Words to swap for augmentation
    synonyms = {
        "sinh viên": ["hssv", "người học", "bạn học", "tân sinh viên", "SV"],
        "rớt môn": ["trượt môn", "học lại", "không qua môn"],
        "học phí": ["tiền học", "mức thu", "học phí tín chỉ"],
        "bảo lưu": ["nghỉ học tạm thời", "tạm nghỉ học"],
        "điểm rèn luyện": ["điểm RL", "ĐRL", "điểm đánh giá rèn luyện"],
        "K48": ["Khóa 48", "K49", "Khóa 49"],
        "K50": ["Khóa 50", "K51", "Khóa 51"],
    }
    
    for i in range(needed):
        base_case = random.choice(cases)
        new_case = base_case.copy()
        
        # Modify ID
        new_case["id"] = f"{base_case.get('id', 'case')}_aug_{i}"
        
        # Modify query
        query = base_case["query"]
        for word, syn_list in synonyms.items():
            if word.lower() in query.lower():
                import re
                query = re.sub(word, random.choice(syn_list), query, flags=re.IGNORECASE)
        
        # if not modified, append a random context
        if query == base_case["query"]:
            query = query + random.choice([" ạ?", " hả phòng đào tạo?", " cho em hỏi với.", " cụ thể là sao ạ?", " tư vấn giúp mình nhé!"])
            
        new_case["query"] = query
        new_cases.append(new_case)
        
    cases.extend(new_cases)
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(cases, f, indent=4, ensure_ascii=False)
        
    print(f"Augmented {file_path}: {current_count} -> {len(cases)}")

if __name__ == "__main__":
    augment_data('data/eval/generation_eval_cases.json', 100)
    augment_data('data/eval/golden_queries.json', 100)
    augment_data('data/eval/answer_eval_cases.json', 50)
