import logging
import os
import re
import unicodedata
from typing import Any
from langsmith import traceable
from src.retrieval.vectorstore.mongo_store import get_mongo_store

logger = logging.getLogger(__name__)
_mongo_store = None


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


CHUNK_TYPE_ALIASES = {
    "faculty_program_directory": ["faculty_directory", "program_directory"],
}

COMPATIBLE_ENTITY_CHUNK_TYPES = {
    "office_query": {"office_directory"},
    "faculty_query": {"faculty_directory", "program_directory"},
    "procedure_query": {"procedure", "office_directory"},
    "form_query": {"form", "procedure", "office_directory"},
    "regulation_query": {"regulation", "office_directory"},
    "mixed_query": {
        "faculty_directory",
        "form",
        "office_directory",
        "procedure",
        "program_directory",
        "regulation",
    },
}


def normalize_chunk_types(chunk_types: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for chunk_type in chunk_types or []:
        normalized.extend(CHUNK_TYPE_ALIASES.get(chunk_type, [chunk_type]))
    return list(dict.fromkeys(normalized))


def filter_entity_chunk_types(intent: str, chunk_types: list[str]) -> list[str]:
    allowed = COMPATIBLE_ENTITY_CHUNK_TYPES.get(intent)
    if not allowed:
        return chunk_types
    return [chunk_type for chunk_type in chunk_types if chunk_type in allowed]


def _get_docstore():
    global _mongo_store
    if _mongo_store is None:
        _mongo_store = get_mongo_store()
    return _mongo_store


def _normalize_text(text: Any) -> str:
    value = str(text or "").lower().replace("–", "-")
    value = value.replace("đ", "d").replace("Đ", "D")
    value = unicodedata.normalize("NFD", value)
    value = "".join(ch for ch in value if unicodedata.category(ch) != "Mn")
    value = re.sub(r"[^\w\s+-]", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _metadata_text(doc: dict[str, Any]) -> str:
    metadata = doc.get("metadata") or {}
    parts = [
        doc.get("chunk_id"),
        doc.get("chunk_type"),
        metadata.get("chunk_type"),
        metadata.get("source_type"),
        metadata.get("content_type"),
        metadata.get("title"),
        metadata.get("document_title"),
        metadata.get("chapter"),
        metadata.get("article"),
        metadata.get("source_section"),
        metadata.get("unit_name"),
        metadata.get("faculty_or_unit_name"),
        metadata.get("procedure_name"),
        metadata.get("form_name"),
    ]
    return _normalize_text(" ".join(str(part) for part in parts if part))


def _infer_chunk_type(doc: dict[str, Any]) -> str | None:
    metadata = doc.get("metadata") or {}
    explicit = doc.get("chunk_type") or metadata.get("chunk_type")
    if explicit:
        return str(explicit)

    source_type = str(metadata.get("source_type") or "")
    content_type = str(metadata.get("content_type") or "")
    chunk_id = str(doc.get("chunk_id") or "")

    if source_type in {
        "faculty_directory",
        "office_directory",
        "program_directory",
        "procedure",
        "form",
    }:
        return source_type
    if source_type == "structured_section" or content_type == "regulation_text":
        return "regulation"

    id_markers = {
        "_reg_": "regulation",
        "_faculty_": "faculty_directory",
        "_office_": "office_directory",
        "_program_": "program_directory",
        "_procedure_": "procedure",
        "_form_": "form",
    }
    for marker, chunk_type in id_markers.items():
        if marker in chunk_id:
            return chunk_type
    return None


def _ensure_chunk_type_metadata(doc: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(doc.get("metadata") or {})
    chunk_type = _infer_chunk_type({**doc, "metadata": metadata})
    if chunk_type:
        metadata["chunk_type"] = chunk_type
        doc["chunk_type"] = chunk_type
    doc["metadata"] = metadata
    return doc


def _entity_aliases(detected_entities: list[dict[str, Any]]) -> list[str]:
    aliases: list[str] = []
    for entity in detected_entities:
        aliases.append(str(entity.get("canonical_name") or ""))
        aliases.extend(str(alias) for alias in entity.get("aliases") or [])
    return [_normalize_text(alias) for alias in aliases if str(alias).strip()]


def _query_phrase_match_count(query_text: str, metadata_text: str) -> int:
    generic_phrases = {
        "dao tao",
        "hinh thuc",
        "hoc tap",
        "ket qua",
        "nha truong",
        "sinh vien",
    }
    stopwords = {
        "ban",
        "bi",
        "cua",
        "cho",
        "co",
        "duoc",
        "em",
        "gi",
        "khong",
        "la",
        "minh",
        "nao",
        "neu",
        "oan",
        "quy",
        "thi",
        "truong",
        "ve",
        "viec",
    }
    tokens = [
        token
        for token in re.findall(r"\w+", query_text)
        if token not in stopwords and len(token) >= 2
    ]
    if len(tokens) < 2:
        return 0

    matches = 0
    matched_phrases: set[str] = set()
    for size in range(min(4, len(tokens)), 1, -1):
        for index in range(0, len(tokens) - size + 1):
            phrase = " ".join(tokens[index : index + size])
            if phrase in matched_phrases:
                continue
            if phrase in generic_phrases:
                continue
            if phrase in metadata_text:
                matched_phrases.add(phrase)
                matches += 1

    return matches


def _metadata_boost(
    query: str,
    doc: dict[str, Any],
    plan: dict[str, Any],
    detected_entities: list[dict[str, Any]],
    cohort: str | None = None,
) -> float:
    metadata = doc.get("metadata") or {}
    metadata_text = _metadata_text(doc)
    query_text = _normalize_text(query)
    boost = 0.0

    doc_type = _infer_chunk_type(doc)
    if doc_type in set(plan.get("chunk_types") or []):
        boost += 0.05

    purpose_to_type = {
        "faculty": {"faculty_directory", "program_directory"},
        "faculty_query": {"faculty_directory", "program_directory"},
        "office": {"office_directory"},
        "office_query": {"office_directory"},
        "procedure": {"procedure"},
        "procedure_query": {"procedure"},
        "regulation": {"regulation"},
        "regulation_query": {"regulation"},
    }
    preferred_types = purpose_to_type.get(str(plan.get("purpose")), set())
    if doc_type in preferred_types:
        boost += 0.08

    if cohort and metadata.get("cohort") == cohort:
        boost += 0.04

    for alias in _entity_aliases(detected_entities):
        if len(alias) >= 5 and alias in metadata_text:
            boost += 0.12
            break

    query_terms = {
        term
        for term in re.findall(r"\w+", query_text)
        if len(term) >= 4 and term not in {"nhung", "nganh", "khoa", "phong", "truong"}
    }
    if query_terms:
        matches = sum(1 for term in query_terms if term in metadata_text)
        boost += min(matches * 0.025, 0.10)

    phrase_matches = _query_phrase_match_count(query_text, metadata_text)
    if phrase_matches:
        boost += min(phrase_matches * 0.12, 0.24)
        if phrase_matches >= 2:
            boost += 0.10

    article_match = re.search(r"\b(?:dieu|article)\s*(\d+)\b", query_text)
    if article_match and article_match.group(1) in metadata_text:
        boost += 0.18

    return min(boost, 0.50)


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
from .form_lookup import form_lookup
from .program_lookup import program_lookup
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
    candidate_multiplier: int = 5,
    min_candidates: int = 25,
) -> list[dict[str, Any]]:
    """Tìm kiếm Vector dựa trên bản kế hoạch (Retrieval Plan) và Xếp hạng lại (Reranking).

    Quy trình:
    1. Quét mở rộng danh sách candidate: Gấp 3 lần top_k (hoặc tối thiểu 10) từ VectorDB.
    2. Chạy thuật toán Heuristic Reranking: Chấm điểm lại (re-score) các document dựa vào keyword, regex, và loại tài liệu.
    3. Lọc nhiễu: Loại bỏ các document có final_score < 0.70 (Tránh ảo giác cho LLM).
    4. Trả về top_k kết quả tốt nhất.
    """
    candidate_k = max(plan["top_k"] * candidate_multiplier, min_candidates)

    # 1. Vector Search (Dense)
    vector_results = [
        _ensure_chunk_type_metadata(doc)
        for doc in vector_search(
        query=plan["query"],
        model=model,
        collection=collection,
        chunk_types=plan["chunk_types"],
        top_k=candidate_k,
        batch_size=batch_size,
        normalize_embeddings=normalize_embeddings,
        cohort=cohort,
        )
    ]

    # 2. BM25 Search (Sparse)
    bm25_retriever = get_bm25_retriever()
    sparse_results = [
        _ensure_chunk_type_metadata(doc)
        for doc in bm25_retriever.sparse_search(
        plan["query"],
        top_k=candidate_k,
        chunk_types=plan["chunk_types"],
        cohort=cohort,
        )
    ]

    # 3. Reciprocal Rank Fusion (RRF)
    # Combine results from both retrievers using RRF
    rrf_k = 60
    combined_scores = {}
    docs_map = {}

    for rank, doc in enumerate(vector_results):
        doc_id = doc["chunk_id"]
        docs_map[doc_id] = doc
        combined_scores[doc_id] = combined_scores.get(doc_id, 0.0) + 1.0 / (
            rrf_k + rank + 1
        )

    for rank, doc in enumerate(sparse_results):
        doc_id = doc["chunk_id"]
        # If document is only in BM25 results, keep its metadata structure
        if doc_id not in docs_map:
            docs_map[doc_id] = doc
        combined_scores[doc_id] = combined_scores.get(doc_id, 0.0) + 1.0 / (
            rrf_k + rank + 1
        )

    # Sort combined results by RRF score
    sorted_ids = sorted(
        combined_scores.keys(), key=lambda x: combined_scores[x], reverse=True
    )
    fused_results = [
        _ensure_chunk_type_metadata(docs_map[doc_id]) for doc_id in sorted_ids[:candidate_k]
    ]

    # 4. Local Cross-Encoder Reranking
    reranked = rerank_with_cross_encoder(
        query=query, results=fused_results, top_n=candidate_k
    )
    reranked = [_ensure_chunk_type_metadata(doc) for doc in reranked]
    for doc in reranked:
        rerank = dict(doc.get("rerank") or {})
        semantic_score = float(rerank.get("final_score") or 0.0)
        boost = _metadata_boost(
            query=query,
            doc=doc,
            plan=plan,
            detected_entities=detected_entities,
            cohort=cohort,
        )
        rerank["semantic_score"] = semantic_score
        rerank["metadata_boost"] = boost
        rerank["final_score"] = min(semantic_score + boost, 1.0)
        doc["rerank"] = rerank
    reranked = sorted(
        reranked,
        key=lambda item: item.get("rerank", {}).get("final_score", 0.0),
        reverse=True,
    )[: plan["top_k"]]

    # 5. Lọc nhiễu
    filtered = [doc for doc in reranked if doc["rerank"]["final_score"] >= 0.20]

    # 6. Small-to-Big Deduplication
    final_docs = []
    seen_parents = set()

    for doc in filtered:
        parent_id = doc.get("metadata", {}).get("parent_section_id")

        if parent_id:
            if parent_id in seen_parents:
                continue
            seen_parents.add(parent_id)

            try:
                store = _get_docstore()
                parent_doc = store.get_document_by_id(parent_id)
                if parent_doc and "content" in parent_doc:
                    doc["content"] = parent_doc["content"]
            except Exception as e:
                logger.error(f"Error fetching parent doc {parent_id} from MongoDB: {e}")
        else:
            chunk_id = doc.get("chunk_id")
            if chunk_id in seen_parents:
                continue
            seen_parents.add(chunk_id)

        final_docs.append(doc)

    return final_docs[: plan["top_k"]]


@traceable(name="Retrieval Pipeline", run_type="retriever")
def run_retrieval_pipeline(
    query: str,
    model: SentenceTransformer,
    collection: Any,
    scoring_tables: list[dict[str, Any]],
    formula_rules: list[dict[str, Any]] | None,
    entity_registry: list[dict[str, Any]],
    expansion_rules: list[dict[str, Any]],
    form_templates: list[dict[str, Any]] | None = None,
    program_directory: list[dict[str, Any]] | None = None,
    top_k: int = 5,
    batch_size: int = 8,
    normalize_embeddings: bool = True,
    cohort: str | None = None,
    candidate_multiplier: int = 5,
    min_candidates: int = 25,
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
    if routing["intent"] == "unknown" and not _env_bool("STUDENT_RAG_DISABLE_AI_ROUTER"):
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
    elif routing["intent"] == "unknown":
        routing = {
            "intent": "regulation_query",
            "strategy": "semantic_filtered",
            "target_chunk_types": ["regulation"],
            "router_error": "AI Router disabled by STUDENT_RAG_DISABLE_AI_ROUTER",
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
            "clarification_question": routing.get("clarification_question"),
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

    entity_chunk_types = filter_entity_chunk_types(
        intent,
        get_entity_target_chunk_types(detected_entities),
    )

    if entity_chunk_types and strategy.startswith("semantic"):
        # Neu entity da biet loai chunk muc tieu, ep retrieval tim dung vung du lieu cua entity do.
        routing["target_chunk_types"] = list(
            dict.fromkeys(routing.get("target_chunk_types", []) + entity_chunk_types)
        )

    routing["target_chunk_types"] = normalize_chunk_types(
        routing.get("target_chunk_types", [])
    )
    target_chunk_types = routing.get("target_chunk_types", [])
    candidate_options = {
        "candidate_multiplier": candidate_multiplier,
        "min_candidates": min_candidates,
    }

    program_lookup_result = program_lookup(
        query,
        program_directory or [],
        cohort=cohort,
        detected_entities=detected_entities,
        routing=routing,
    )
    if program_lookup_result is not None:
        return {
            "query": query,
            "retrieval_query": retrieval_query,
            "detected_entities": detected_entities,
            "intent": "faculty_query",
            "strategy": "program_lookup",
            "target_chunk_types": ["program_directory"],
            "structured_result": program_lookup_result,
            "retrieved_items": [],
            "citations": build_citation_from_lookup(program_lookup_result),
            "context_for_llm": build_context_from_lookup(program_lookup_result),
            "needs_llm_answer": False,
        }

    form_lookup_result = None
    if intent == "form_query" or "form" in target_chunk_types:
        form_lookup_result = form_lookup(
            query,
            form_templates or [],
            cohort=cohort,
        )

    if intent == "form_query":
        if form_lookup_result is not None:
            return {
                "query": query,
                "retrieval_query": retrieval_query,
                "detected_entities": detected_entities,
                "intent": intent,
                "strategy": "form_lookup",
                "target_chunk_types": target_chunk_types,
                "structured_result": form_lookup_result,
                "retrieved_items": [],
                "citations": build_citation_from_lookup(form_lookup_result),
                "context_for_llm": build_context_from_lookup(form_lookup_result),
                "needs_llm_answer": True,
            }

        fallback_plan = {
            "purpose": "form_fallback",
            "query": retrieval_query,
            "chunk_types": ["procedure", "regulation"],
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
            **candidate_options,
        )

        return {
            "query": query,
            "retrieval_query": retrieval_query,
            "detected_entities": detected_entities,
            "intent": intent,
            "strategy": "form_lookup_fallback_to_vector",
            "target_chunk_types": target_chunk_types,
            "structured_result": None,
            "retrieved_items": fallback_results,
            "citations": build_citations_from_vector_results(fallback_results),
            "context_for_llm": build_context_from_vector_results(fallback_results),
            "needs_llm_answer": True,
        }

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
            "context_for_llm": build_context_from_tool(tool_result)
            if tool_result
            else "",
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
                **candidate_options,
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

        # Vẫn tiếp tục vector search để lấy thêm các quy định/văn bản xung quanh
        supplement_plan = {
            "purpose": "formula_supplement",
            "query": retrieval_query,
            "chunk_types": ["regulation"],
            "top_k": top_k,
        }
        supplement_results = retrieve_with_plan(
            query=query,
            plan=supplement_plan,
            model=model,
            collection=collection,
            batch_size=batch_size,
            normalize_embeddings=normalize_embeddings,
            detected_entities=detected_entities,
            cohort=cohort,
            **candidate_options,
        )

        return {
            "query": query,
            "retrieval_query": retrieval_query,
            "detected_entities": detected_entities,
            "intent": intent,
            "strategy": strategy,
            "target_chunk_types": target_chunk_types,
            "formula_result": formula_result,
            "retrieved_items": supplement_results,
            "citations": build_citation_from_formula(formula_result)
            + build_citations_from_vector_results(supplement_results),
            "context_for_llm": build_context_from_formula(formula_result)
            + "\n\n---\n\n"
            + build_context_from_vector_results(supplement_results),
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
                **candidate_options,
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

        supplement_plan = {
            "purpose": "structured_supplement",
            "query": retrieval_query,
            "chunk_types": ["regulation"],
            "top_k": top_k,
        }
        supplement_results = retrieve_with_plan(
            query=query,
            plan=supplement_plan,
            model=model,
            collection=collection,
            batch_size=batch_size,
            normalize_embeddings=normalize_embeddings,
            detected_entities=detected_entities,
            cohort=cohort,
            **candidate_options,
        )

        return {
            "query": query,
            "retrieval_query": retrieval_query,
            "detected_entities": detected_entities,
            "intent": intent,
            "strategy": strategy,
            "target_chunk_types": target_chunk_types,
            "structured_result": lookup_result,
            "retrieved_items": supplement_results,
            "citations": build_citation_from_lookup(lookup_result)
            + build_citations_from_vector_results(supplement_results),
            "context_for_llm": build_context_from_lookup(lookup_result)
            + "\n\n---\n\n"
            + build_context_from_vector_results(supplement_results),
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
            **candidate_options,
        )

        results_by_plan.append(
            {
                "purpose": plan["purpose"],
                "results": plan_results,
            }
        )

    merged_results = merge_plan_results(results_by_plan)
    citations = build_citations_from_vector_results(merged_results)
    context_blocks = []
    if form_lookup_result is not None:
        citations = build_citation_from_lookup(form_lookup_result) + citations
        context_blocks.append(build_context_from_lookup(form_lookup_result))

    vector_context = build_context_from_vector_results(merged_results)
    if vector_context:
        context_blocks.append(vector_context)

    return {
        "query": query,
        "retrieval_query": retrieval_query,
        "detected_entities": detected_entities,
        "intent": intent,
        "strategy": strategy,
        "target_chunk_types": target_chunk_types,
        "retrieval_plan": retrieval_plan,
        "structured_result": form_lookup_result,
        "retrieved_items": merged_results,
        "citations": citations,
        "context_for_llm": "\n\n---\n\n".join(context_blocks),
        "needs_llm_answer": True,
    }
