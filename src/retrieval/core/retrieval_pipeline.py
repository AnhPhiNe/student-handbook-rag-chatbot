from typing import Any
from langsmith import traceable

from sentence_transformers import SentenceTransformer

from .calculator_tools import try_calculation
from .citation_builder import (
    build_citation_from_formula,
    build_citation_from_lookup,
    build_citations_from_vector_results,
)
from .context_builder import (
    build_context_from_formula,
    build_context_from_lookup,
    build_context_from_tool,
    build_context_from_vector_results,
)
from .entity_linker import (
    detect_entities,
    get_entity_target_chunk_types,
    normalize_query_with_entities,
)
from .formula_lookup import formula_lookup
from .query_expansion import expand_query
from .query_router import route_query
from .ai_router import AIRouter
from .cross_encoder_reranker import rerank_with_cross_encoder
from .bm25_retriever import get_bm25_retriever
from .retrieval_planner import build_retrieval_plan, merge_plan_results
from .structured_lookup import structured_lookup
from .vector_retriever import vector_search


def retrieve_with_plan(
    query: str,
    plan: dict[str, Any],
    model: SentenceTransformer,
    collection: Any,
    batch_size: int,
    normalize_embeddings: bool,
    detected_entities: list[dict[str, Any]],
    cohort: str | None = None,
) -> list[dict[str, Any]]:
    """Tìm kiếm Vector dựa trên bản kế hoạch (Retrieval Plan) và Xếp hạng lại (Reranking).
    
    Quy trình:
    1. Quét mở rộng danh sách candidate: Gấp 3 lần top_k (hoặc tối thiểu 10) từ VectorDB.
    2. Chạy thuật toán Heuristic Reranking: Chấm điểm lại (re-score) các document dựa vào keyword, regex, và loại tài liệu.
    3. Lọc nhiễu: Loại bỏ các document có final_score < 0.70 (Tránh ảo giác cho LLM).
    4. Trả về top_k kết quả tốt nhất.
    """
    candidate_k = max(plan["top_k"] * 4, 20)

    # 1. Vector Search (Dense)
    vector_results = vector_search(
        query=plan["query"],
        model=model,
        collection=collection,
        chunk_types=plan["chunk_types"],
        top_k=candidate_k,
        batch_size=batch_size,
        normalize_embeddings=normalize_embeddings,
        cohort=cohort,
    )

    # 2. BM25 Search (Sparse)
    bm25_retriever = get_bm25_retriever()
    sparse_results = bm25_retriever.sparse_search(plan["query"], top_k=candidate_k)

    # 3. Reciprocal Rank Fusion (RRF)
    # Combine results from both retrievers using RRF
    rrf_k = 60
    combined_scores = {}
    docs_map = {}

    for rank, doc in enumerate(vector_results):
        doc_id = doc["chunk_id"]
        docs_map[doc_id] = doc
        combined_scores[doc_id] = combined_scores.get(doc_id, 0.0) + 1.0 / (rrf_k + rank + 1)

    for rank, doc in enumerate(sparse_results):
        doc_id = doc["chunk_id"]
        # If document is only in BM25 results, keep its metadata structure
        if doc_id not in docs_map:
            docs_map[doc_id] = doc
        combined_scores[doc_id] = combined_scores.get(doc_id, 0.0) + 1.0 / (rrf_k + rank + 1)

    # Sort combined results by RRF score
    sorted_ids = sorted(combined_scores.keys(), key=lambda x: combined_scores[x], reverse=True)
    fused_results = [docs_map[doc_id] for doc_id in sorted_ids[:candidate_k]]

    # 4. Local Cross-Encoder Reranking
    reranked = rerank_with_cross_encoder(
        query=query,
        results=fused_results,
        top_n=plan["top_k"]
    )
    
    # 5. Lọc nhiễu (Dựa vào điểm Cohere)
    filtered = [doc for doc in reranked if doc["rerank"]["final_score"] >= 0.20]
    return filtered[: plan["top_k"]]

@traceable(name="Retrieval Pipeline", run_type="retriever")
def run_retrieval_pipeline(
    query: str,
    model: SentenceTransformer,
    collection: Any,
    scoring_tables: list[dict[str, Any]],
    formula_rules: list[dict[str, Any]] | None,
    entity_registry: list[dict[str, Any]],
    expansion_rules: list[dict[str, Any]],
    top_k: int = 5,
    batch_size: int = 8,
    normalize_embeddings: bool = True,
    cohort: str | None = None,
) -> dict[str, Any]:
    """Hàm lõi điều phối toàn bộ quá trình Tìm kiếm dữ liệu (Retrieval Pipeline).
    
    Quy trình hoạt động (Workflow):
    1. Tiền xử lý (Preprocessing): Nhận diện thực thể (Entity Linking) và mở rộng câu hỏi (Query Expansion).
    2. Định tuyến (Routing): 
       - Chạy Rule-based Router siêu tốc độ (0 chi phí).
       - Nếu không hiểu (unknown), gọi AI Router (LLM) để phân tích sâu.
    3. Tra cứu có cấu trúc (Structured / Formula Lookup): 
       - Nếu là câu hỏi tính điểm/rèn luyện -> Dùng công thức cứng thay vì tìm văn bản.
    4. Lập kế hoạch & Tìm kiếm Vector (Retrieval Planner & Vector Search):
       - Chạy nhiều luồng tìm kiếm song song vào VectorDB (Chroma/Qdrant).
    5. Xếp hạng lại (Heuristic Reranking): 
       - Dùng thuật toán tự viết để cộng/trừ điểm các tài liệu dựa vào mức độ trùng khớp từ khóa.
       
    Args:
        query: Câu hỏi gốc của người dùng.
        model: Mô hình Embedding (bge-m3).
        collection: Đối tượng VectorDB (Chroma hoặc Qdrant Adapter).
        scoring_tables, formula_rules, entity_registry, expansion_rules: Các tệp metadata luật.
        top_k: Số lượng tài liệu trả về tối đa.
        
    Returns:
        dict chứa context, citations, và các kết quả có cấu trúc (nếu có).
    """
    detected_entities = detect_entities(query, entity_registry)
    # Entity linking append canonical name vao retrieval query de vector search bat dung don vi/khoa.
    entity_normalized_query = normalize_query_with_entities(query, detected_entities)
    # Query expansion them synonym/tu khoa lien quan, nhung van giu query goc de router khong bi lech.
    retrieval_query = expand_query(entity_normalized_query, expansion_rules)

    # 1. Chạy Rule-based Router siêu tốc độ trước
    routing = route_query(query)
    
    # 2. Nếu Rule-based không hiểu, dùng AI Router để phân tích sâu
    if routing["intent"] == "unknown":
        try:
            routing = AIRouter().route(query)
        except Exception as exc:
            # AI Router là lớp hỗ trợ, không để thiếu API key làm hỏng retrieval offline.
            routing = {
                "intent": "regulation_query",
                "strategy": "semantic_filtered",
                "target_chunk_types": ["regulation"],
                "router_error": str(exc),
            }
    
    intent = routing["intent"]
    strategy = routing["strategy"]
    
    # Bắt tín hiệu cần làm rõ từ AI Router
    if routing.get("needs_clarification"):
        return {
            "query": query,
            "retrieval_query": retrieval_query,
            "detected_entities": detected_entities,
            "intent": intent,
            "strategy": strategy,
            "target_chunk_types": routing.get("target_chunk_types", []),
            "retrieved_items": [],
            "citations": [],
            "context_for_llm": "",
            "needs_llm_answer": False,
            "needs_clarification": True,
            "clarification_question": routing.get("clarification_question")
        }

    # Câu hỏi nằm ngoài phạm vi Sổ tay sinh viên → từ chối thẳng
    if intent == "out_of_domain":
        return {
            "query": query,
            "retrieval_query": retrieval_query,
            "detected_entities": detected_entities,
            "intent": "out_of_domain",
            "strategy": "none",
            "target_chunk_types": [],
            "retrieved_items": [],
            "citations": [],
            "context_for_llm": "",
            "needs_llm_answer": False,
            "needs_clarification": False,
            "out_of_domain": True,
        }

    entity_chunk_types = get_entity_target_chunk_types(detected_entities)

    if entity_chunk_types and strategy.startswith("semantic"):
        # Neu entity da biet loai chunk muc tieu, ep retrieval tim dung vung du lieu cua entity do.
        routing["target_chunk_types"] = list(
            dict.fromkeys(routing.get("target_chunk_types", []) + entity_chunk_types)
        )

    target_chunk_types = routing.get("target_chunk_types", [])

    if strategy == "calculator_tool":
        # Calculator tra ket qua co cau truc, khong can vector search.
        tool_result = try_calculation(query)

        return {
            "query": query,
            "retrieval_query": retrieval_query,
            "detected_entities": detected_entities,
            "intent": intent,
            "strategy": strategy,
            "target_chunk_types": target_chunk_types,
            "tool_result": tool_result,
            "retrieved_items": [],
            "citations": [],
            "context_for_llm": build_context_from_tool(tool_result) if tool_result else "",
            "needs_llm_answer": True,
        }

    if strategy == "formula_lookup":
        formula_result = formula_lookup(query, formula_rules or [], cohort=cohort)
        if formula_result is None:
            # Neu khong tim thay cong thuc cung, fallback sang regulation de user van co nguon tham khao.
            fallback_plan = {
                "purpose": "formula_fallback",
                "query": retrieval_query,
                "chunk_types": ["regulation"],
                "top_k": top_k,
            }
            fallback_results = retrieve_with_plan(
                query=query,
                plan=fallback_plan,
                model=model,
                collection=collection,
                batch_size=batch_size,
                normalize_embeddings=normalize_embeddings,
                detected_entities=detected_entities,
                cohort=cohort,
            )

            return {
                "query": query,
                "retrieval_query": retrieval_query,
                "detected_entities": detected_entities,
                "intent": "regulation_query",
                "strategy": "formula_lookup_fallback_to_vector",
                "target_chunk_types": ["regulation"],
                "formula_result": None,
                "retrieved_items": fallback_results,
                "citations": build_citations_from_vector_results(fallback_results),
                "context_for_llm": build_context_from_vector_results(fallback_results),
                "needs_llm_answer": True,
            }

        return {
            "query": query,
            "retrieval_query": retrieval_query,
            "detected_entities": detected_entities,
            "intent": intent,
            "strategy": strategy,
            "target_chunk_types": target_chunk_types,
            "formula_result": formula_result,
            "retrieved_items": [],
            "citations": build_citation_from_formula(formula_result),
            "context_for_llm": build_context_from_formula(formula_result),
            "needs_llm_answer": True,
        }

    if strategy == "structured_lookup":
        lookup_result = structured_lookup(query, scoring_tables, cohort=cohort)

        if lookup_result is None:
            # Cau duoc route vao lookup nhung bang tra khong match, fallback sang regulation thay vi tra rong.
            fallback_plan = {
                "purpose": "regulation_fallback",
                "query": retrieval_query,
                "chunk_types": ["regulation"],
                "top_k": top_k,
            }

            fallback_results = retrieve_with_plan(
                query=query,
                plan=fallback_plan,
                model=model,
                collection=collection,
                batch_size=batch_size,
                normalize_embeddings=normalize_embeddings,
                detected_entities=detected_entities,
                cohort=cohort,
            )

            return {
                "query": query,
                "retrieval_query": retrieval_query,
                "detected_entities": detected_entities,
                "intent": "regulation_query",
                "strategy": "structured_lookup_fallback_to_vector",
                "target_chunk_types": ["regulation"],
                "structured_result": None,
                "retrieved_items": fallback_results,
                "citations": build_citations_from_vector_results(fallback_results),
                "context_for_llm": build_context_from_vector_results(fallback_results),
                "needs_llm_answer": True,
            }

        return {
            "query": query,
            "retrieval_query": retrieval_query,
            "detected_entities": detected_entities,
            "intent": intent,
            "strategy": strategy,
            "target_chunk_types": target_chunk_types,
            "structured_result": lookup_result,
            "retrieved_items": [],
            "citations": build_citation_from_lookup(lookup_result),
            "context_for_llm": build_context_from_lookup(lookup_result),
            "needs_llm_answer": True,
        }

    retrieval_plan = build_retrieval_plan(
        query=query,
        routing=routing,
        retrieval_query=retrieval_query,
        detected_entities=detected_entities,
    )

    results_by_plan = []

    for plan in retrieval_plan:
        # Moi plan co the nham mot chunk_type/intent khac nhau; sau do merge de bo trung.
        plan_results = retrieve_with_plan(
            query=query,
            plan=plan,
            model=model,
            collection=collection,
            batch_size=batch_size,
            normalize_embeddings=normalize_embeddings,
            detected_entities=detected_entities,
            cohort=cohort,
        )

        results_by_plan.append(
            {
                "purpose": plan["purpose"],
                "results": plan_results,
            }
        )

    merged_results = merge_plan_results(results_by_plan)

    return {
        "query": query,
        "retrieval_query": retrieval_query,
        "detected_entities": detected_entities,
        "intent": intent,
        "strategy": strategy,
        "target_chunk_types": target_chunk_types,
        "retrieval_plan": retrieval_plan,
        "retrieved_items": merged_results,
        "citations": build_citations_from_vector_results(merged_results),
        "context_for_llm": build_context_from_vector_results(merged_results),
        "needs_llm_answer": True,
    }
