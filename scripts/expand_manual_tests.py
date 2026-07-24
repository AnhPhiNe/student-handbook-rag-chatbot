import json
from pathlib import Path

def main():
    path = Path("data/eval/answer_eval_cases.json")
    with open(path, "r", encoding="utf-8") as f:
        cases = json.load(f)
        
    print(f"Current cases: {len(cases)}")
    
    new_cases = [
        # Deterministic Edge Cases
        {
            "id": "det_calc_edge_001",
            "category": "deterministic_exactness",
            "query": "Tính điểm học bổng nếu GPA 3.15 và rèn luyện 90",
            "expected_status": "answered",
            "expected_llm_called": False,
            "expected_tool_name": "calculate_scholarship_score",
            "expected_answer_contains": ["3.24", "calculate_scholarship_score"]
        },
        {
            "id": "det_calc_edge_002",
            "category": "deterministic_exactness",
            "query": "Tính điểm học bổng nếu GPA 4.0 và rèn luyện 100",
            "expected_status": "answered",
            "expected_llm_called": False,
            "expected_tool_name": "calculate_scholarship_score",
            "expected_answer_contains": ["4.0", "calculate_scholarship_score"]
        },
        {
            "id": "det_calc_edge_003",
            "category": "deterministic_exactness",
            "query": "Học bổng nếu GPA 1.0 rèn luyện 50",
            "expected_status": "answered",
            "expected_llm_called": False,
            "expected_tool_name": "calculate_scholarship_score",
            "expected_answer_contains": ["1.2", "calculate_scholarship_score"]
        },
        {
            "id": "det_score_edge_001",
            "category": "deterministic_exactness",
            "query": "GPA 1.99 xếp loại gì?",
            "expected_status": "answered",
            "expected_llm_called": False,
            "expected_lookup_type": "academic_classification",
            "expected_answer_contains": ["1.99", "Yếu"],
            "min_citations": 1,
            "expected_citation_chunk_types": ["structured_lookup"]
        },
        {
            "id": "det_score_edge_002",
            "category": "deterministic_exactness",
            "query": "GPA 2.0 xếp loại gì?",
            "expected_status": "answered",
            "expected_llm_called": False,
            "expected_lookup_type": "academic_classification",
            "expected_answer_contains": ["2.0", "Trung bình"],
            "min_citations": 1,
            "expected_citation_chunk_types": ["structured_lookup"]
        },
        {
            "id": "det_score_edge_003",
            "category": "deterministic_exactness",
            "query": "Điểm rèn luyện 69 loại gì?",
            "expected_status": "answered",
            "expected_llm_called": False,
            "expected_lookup_type": "conduct_classification",
            "expected_answer_contains": ["69", "Trung bình"],
            "min_citations": 1,
            "expected_citation_chunk_types": ["structured_lookup"]
        },
        {
            "id": "det_score_edge_004",
            "category": "deterministic_exactness",
            "query": "Điểm rèn luyện 70 loại gì?",
            "expected_status": "answered",
            "expected_llm_called": False,
            "expected_lookup_type": "conduct_classification",
            "expected_answer_contains": ["70", "Khá"],
            "min_citations": 1,
            "expected_citation_chunk_types": ["structured_lookup"]
        },
        {
            "id": "det_score_edge_005",
            "category": "deterministic_exactness",
            "query": "Điểm chữ F đổi sang hệ 4?",
            "expected_status": "answered",
            "expected_llm_called": False,
            "expected_lookup_type": "letter_to_grade_4",
            "expected_answer_contains": ["F", "0.0"],
            "min_citations": 1,
            "expected_citation_chunk_types": ["structured_lookup"]
        },
        
        # Guardrail & Ambiguity Cases
        {
            "id": "guard_ood_edge_001",
            "category": "guardrail_status",
            "query": "Làm thế nào để cua gái trong trường Sư phạm?",
            "expected_status": "out_of_domain",
            "expected_llm_called": False,
            "expected_answer_contains": ["Sổ tay"]
        },
        {
            "id": "guard_ood_edge_002",
            "category": "guardrail_status",
            "query": "Giá vàng hôm nay bao nhiêu?",
            "expected_status": "out_of_domain",
            "expected_llm_called": False,
            "expected_answer_contains": ["Sổ tay"]
        },
        {
            "id": "guard_amb_edge_001",
            "category": "guardrail_status",
            "query": "Phòng nào giải quyết chuyện đó?",
            "expected_status": "needs_clarification",
            "expected_llm_called": False,
            "expected_answer_contains": ["bạn muốn"]
        },
        {
            "id": "guard_amb_edge_002",
            "category": "guardrail_status",
            "query": "Tải mẫu đơn này ở đâu?",
            "expected_status": "needs_clarification",
            "expected_llm_called": False,
            "expected_answer_contains": ["bạn muốn"]
        },
        
        # Citation Extension
        {
            "id": "cite_proc_edge_001",
            "category": "citation_correctness",
            "query": "Cố vấn học tập có nhiệm vụ gì?",
            "expected_status": "answered",
            "expected_llm_called": True,
            "min_citations": 1,
            "expected_citation_chunk_types": ["regulation"]
        },
        {
            "id": "cite_office_edge_001",
            "category": "citation_correctness",
            "query": "Trung tâm Tin học làm gì?",
            "expected_status": "answered",
            "expected_llm_called": True,
            "min_citations": 1,
            "expected_citation_chunk_types": ["office_directory"]
        },
        {
            "id": "cite_fac_edge_001",
            "category": "citation_correctness",
            "query": "Khoa Tiếng Nhật dạy gì?",
            "expected_status": "answered",
            "expected_llm_called": True,
            "min_citations": 1,
            "expected_citation_chunk_types": ["faculty_program_directory"]
        }
    ]
    
    cases.extend(new_cases)
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)
        
    print(f"Added {len(new_cases)} cases to answer_eval_cases. Total now: {len(cases)}")
    
    # Expand golden queries
    gq_path = Path("data/eval/golden_queries.json")
    with open(gq_path, "r", encoding="utf-8") as f:
        gq_cases = json.load(f)
        
    print(f"Current golden queries: {len(gq_cases)}")
    
    new_gq_cases = [
        {
            "query": "Công thức tính điểm học bổng là gì?",
            "expected_intent": "formula_query",
            "expected_strategy": "formula_lookup",
            "expected_chunk_ids": []
        },
        {
            "query": "Cách tính GPA?",
            "expected_intent": "formula_query",
            "expected_strategy": "formula_lookup",
            "expected_chunk_ids": []
        },
        {
            "query": "Làm sao để tính điểm trung bình chung?",
            "expected_intent": "formula_query",
            "expected_strategy": "formula_lookup",
            "expected_chunk_ids": []
        },
        {
            "query": "Khoa tiếng Hàn Quốc có đào tạo ngành nào?",
            "expected_intent": "faculty_query",
            "expected_strategy": "semantic_filtered_rerank",
            "expected_chunk_ids": ["faculty_Khoa Tiếng Hàn Quốc"]
        },
        {
            "query": "Khoa Mầm non nằm ở đâu?",
            "expected_intent": "faculty_query",
            "expected_strategy": "semantic_filtered_rerank",
            "expected_chunk_ids": ["faculty_Khoa Giáo dục Mầm non"]
        },
        {
            "query": "Số điện thoại trung tâm tin học?",
            "expected_intent": "office_query",
            "expected_strategy": "semantic_filtered_rerank",
            "expected_chunk_ids": ["office_Trung tâm Tin học"]
        },
        {
            "query": "Phòng kế hoạch tài chính nằm ở đâu?",
            "expected_intent": "office_query",
            "expected_strategy": "semantic_filtered_rerank",
            "expected_chunk_ids": ["office_Phòng Kế hoạch - Tài chính"]
        },
        {
            "query": "Sinh viên trao đổi là gì?",
            "expected_intent": "regulation_query",
            "expected_strategy": "semantic_filtered",
            "expected_chunk_ids": ["reg_article_32_p56_82"]
        },
        {
            "query": "Cảnh báo học tập lần 2 thì sao?",
            "expected_intent": "regulation_query",
            "expected_strategy": "semantic_filtered",
            "expected_chunk_ids": ["reg_article_13_p24_23"]
        }
    ]
    
    gq_cases.extend(new_gq_cases)
    
    with open(gq_path, "w", encoding="utf-8") as f:
        json.dump(gq_cases, f, ensure_ascii=False, indent=2)
        
    print(f"Added {len(new_gq_cases)} cases to golden_queries. Total now: {len(gq_cases)}")

if __name__ == "__main__":
    main()
