import json
import sys

sys.stdout.reconfigure(encoding='utf-8')
report_path = 'data/eval/reports/v8/retrieval_qdrant_full_full.json'

with open(report_path, 'r', encoding='utf-8') as f:
    report = json.load(f)

failed = [c for c in report['cases'] if not c.get('hit_at_5') and c.get('case_type') == 'regulation_true_rag']

print(f"Tổng số câu bị rớt (Hit@5 = 0): {len(failed)}\n")

for i, c in enumerate(failed[:5], 1):
    print(f"--- CÂU {i} ---")
    print(f"Hỏi: {c['query']}")
    
    expected = [j['parent_section_id'] for j in c.get('relevance_judgments', [])]
    print(f"Đáp án BẮT BUỘC (Bot chấm điểm đòi):")
    for ex in expected:
        print(f"  - {ex}")
        
    ranked = c.get('ranked_parent_ids', [])[:3]
    print(f"Qdrant tìm ra (Top 3):")
    for r in ranked:
        print(f"  - {r}")
    print()
