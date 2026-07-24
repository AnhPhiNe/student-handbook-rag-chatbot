import json
from pathlib import Path

def patch_dataset():
    path = Path("data/eval/v8/retrieval_cases.json")
    with open(path, "r", encoding="utf-8") as f:
        cases = json.load(f)
    
    new_cases = []
    for case in cases:
        if case.get("cohort") == "general":
            continue
            
        if case.get("case_type") == "regulation_true_rag":
            cohort = case.get("cohort")
            topic = str(case.get("topic", "")).lower()
            # Rewrite query to be a pure regulation query
            case["query"] = f"Em thuộc {cohort}, cho em hỏi quy định về {topic} là như thế nào?"
            
        new_cases.append(case)
        
    with open(path, "w", encoding="utf-8") as f:
        json.dump(new_cases, f, ensure_ascii=False, indent=2)
        
    print(f"Patched {path}: kept {len(new_cases)} out of {len(cases)} cases.")
    
    # Also patch answers cases if needed
    ans_path = Path("data/eval/v8/generated_answer_cases.json")
    if ans_path.exists():
        with open(ans_path, "r", encoding="utf-8") as f:
            ans_cases = json.load(f)
        new_ans = []
        for case in ans_cases:
            if case.get("cohort") == "general":
                continue
            if case.get("case_type") == "regulation_true_rag":
                cohort = case.get("cohort")
                topic = str(case.get("topic", "")).lower()
                case["query"] = f"Em thuộc {cohort}, cho em hỏi quy định về {topic} là như thế nào?"
            new_ans.append(case)
        with open(ans_path, "w", encoding="utf-8") as f:
            json.dump(new_ans, f, ensure_ascii=False, indent=2)
        print(f"Patched {ans_path}: kept {len(new_ans)} out of {len(ans_cases)} cases.")

if __name__ == "__main__":
    patch_dataset()
