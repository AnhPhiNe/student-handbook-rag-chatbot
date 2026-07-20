import logging
import os
import re
import unicodedata
from typing import Any
from src.common.cohort import normalize_cohort
from src.retrieval.vectorstore.mongo_store import get_mongo_store

logger = logging.getLogger(__name__)
_mongo_store = None


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


CHUNK_TYPE_ALIASES = {
    "faculty_directory": ["faculty_directory", "faculty_program_directory"],
    "faculty_program_directory": [
        "faculty_directory",
        "faculty_program_directory",
        "program_directory",
    ],
    "program_directory": ["program_directory", "faculty_program_directory"],
    "regulation_sections": ["regulation"],
    "regulation_text": ["regulation"],
}

HYBRID_REGULATION_CHUNK_TYPES = {"regulation"}

CONTENT_TYPES_BY_CHUNK_TYPE = {
    "faculty_directory": {"faculty_directory", "faculty_program_directory"},
    "faculty_program_directory": {
        "faculty_directory",
        "faculty_program_directory",
        "student_faculty_profile",
    },
    "form": {"form", "form_template"},
    "formula": {"formula_rule"},
    "office_directory": {
        "office_directory",
        "student_office_profile",
        "student_service_directory",
    },
    "program_directory": {"faculty_program_directory", "program_directory"},
    "regulation": {"regulation", "regulation_sections", "regulation_text"},
    "structured_lookup": {
        "foreign_language_equivalency",
        "scoring_table",
        "structured_lookup",
        "threshold_rule",
    },
}

COMPATIBLE_ENTITY_CHUNK_TYPES = {
    "office_query": {"office_directory"},
    "faculty_query": {
        "faculty_directory",
        "program_directory",
    },
    "form_query": {
        "form",
        "regulation",
        "office_directory",
    },
    "regulation_query": {
        "regulation",
        "office_directory",
    },
    "mixed_query": {
        "faculty_directory",
        "form",
        "office_directory",
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


def content_types_for_chunk_types(chunk_types: list[str] | None) -> list[str]:
    content_types: list[str] = []
    for chunk_type in normalize_chunk_types(chunk_types or []):
        content_types.extend(sorted(CONTENT_TYPES_BY_CHUNK_TYPE.get(chunk_type, set())))
    return list(dict.fromkeys(content_types))


def _is_hybrid_regulation_plan(plan: dict[str, Any]) -> bool:
    chunk_types = set(
        normalize_chunk_types(plan.get("chunk_types") or [])
    )
    return chunk_types == HYBRID_REGULATION_CHUNK_TYPES


def _retrieve_with_hybrid_regulation(
    query: str,
    plan: dict[str, Any],
    detected_entities: list[dict[str, Any]],
    cohort: str | None,
) -> list[dict[str, Any]]:
    """Run V7 hybrid child-parent retrieval for regulation questions."""

    from .hybrid_pipeline import run_hybrid_retrieval_pipeline

    retrieval_query = str(plan.get("query") or query)
    top_k = int(plan.get("top_k") or 5)

    result = run_hybrid_retrieval_pipeline(
        retrieval_query,
        top_k=top_k,
        cohort=cohort,
        retrieval_query=retrieval_query,
        detected_entities=detected_entities,
        intent="regulation_query",
        strategy="hybrid_graph_retrieval",
        target_chunk_types=["regulation"],
    )

    items = [
        _ensure_chunk_type_metadata(doc)
        for doc in result.get("retrieved_items", [])
        if isinstance(doc, dict)
    ]
    related_items = [
        item
        for item in result.get("related_items", [])
        if isinstance(item, dict)
    ]
    if items and related_items:
        metadata = dict(items[0].get("metadata") or {})
        metadata["related_items"] = related_items
        items[0]["metadata"] = metadata
    return items


def _should_force_regulation_rag(
    query: str,
    router_decision: dict[str, Any] | None,
    *,
    cohort: str | None,
) -> bool:
    """Recover from over-cautious AI routing for in-handbook questions."""

    if not router_decision or router_decision.get("route") not in {
        "clarify",
        "out_of_domain",
    }:
        return False

    query_text = _normalize_text(query)
    explicit_scope_terms = {
        "so tay",
        "quy dinh",
        "quy che",
        "theo so tay",
        "dieu ",
        "chuong ",
        "k48",
        "k49",
        "k50",
        "k51",
    }
    handbook_topic_terms = {
        "sinh vien",
        "hoc bong",
        "hoc phi",
        "ngoai ngu",
        "ngoai tru",
        "ren luyen",
        "co van hoc tap",
        "ke hoach giang day",
        "ke hoach hoc tap",
        "lop sinh vien",
        "hieu luc",
        "trach nhiem",
        "cac khoa",
        "don vi",
        "ho tro",
        "dich vu sinh vien",
        "dao tao",
        "hinh thuc dao tao",
    }
    unresolved_terms = {
        "muc nay",
        "truong hop do",
        "bieu mau kia",
        "diem nhu vay",
        "chung chi do",
        "nganh nay",
        "cong thuc nay",
        "loai do",
        "phong do",
        "thu tuc nay",
    }
    if any(term in query_text for term in unresolved_terms):
        return False

    has_explicit_scope = any(term in query_text for term in explicit_scope_terms)
    has_handbook_topic = any(term in query_text for term in handbook_topic_terms)
    has_selected_cohort = bool(normalize_cohort(cohort))
    return has_handbook_topic and (has_explicit_scope or has_selected_cohort)


def _force_regulation_rag_decision(
    router_decision: dict[str, Any],
    *,
    query: str,
) -> dict[str, Any]:
    return {
        **router_decision,
        "route": "rag",
        "execution_mode": "regulation",
        "intent": "regulation_query",
        "lookup_type": None,
        "slots": {},
        "slot_spans": {},
        "retrieval_query": router_decision.get("retrieval_query") or query,
        "target_chunk_types": ["regulation"],
        "needs_clarification": False,
        "clarification_question": None,
        "router_fallback": "handbook_scoped_query_to_regulation_rag",
    }


def _extract_related_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    related_items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in items:
        metadata = dict(item.get("metadata") or {})
        raw_related = metadata.pop("related_items", [])
        if raw_related:
            item["metadata"] = metadata
        if not isinstance(raw_related, list):
            continue
        for related in raw_related:
            if not isinstance(related, dict):
                continue
            related_id = str(
                related.get("chunk_id")
                or related.get("_id")
                or related.get("id")
                or ""
            )
            if not related_id or related_id in seen_ids:
                continue
            seen_ids.add(related_id)
            related_items.append(related)
    return related_items


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
    """Return a bounded metadata boost applied after semantic reranking."""
    metadata = doc.get("metadata") or {}
    metadata_text = _metadata_text(doc)
    query_text = _normalize_text(query)
    boost = 0.0

    # Apply a small graph-source boost without letting metadata override semantic relevance.
    if metadata.get("source") == "knowledge_graph":
        boost += 0.05


    doc_type = _infer_chunk_type(doc)
    if doc_type in set(plan.get("chunk_types") or []):
        boost += 0.05

    purpose_to_type = {
        "faculty": {
            "faculty_directory",
            "program_directory",
        },
        "faculty_query": {
            "faculty_directory",
            "program_directory",
        },
        "office": {"office_directory"},
        "office_query": {"office_directory"},
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

from .citation_builder import (
    build_citation_from_formula,
    build_citation_from_lookup,
    build_citations_from_vector_results,
)
from .context_builder import (
    build_context_from_formula,
    build_context_from_lookup,
    build_context_from_vector_results,
)
from .entity_linker import (
    detect_entities,
    get_entity_target_chunk_types,
    normalize_query_with_entities,
)
from .formula_lookup import formula_lookup
from .form_lookup import form_lookup
from .foreign_language_lookup import foreign_language_lookup
from .office_lookup import find_grounded_catalog_hint, office_lookup
from .program_lookup import program_lookup
from .query_expansion import expand_query
from .query_router import deterministic_lookup_allowed, route_query
from .ai_router import AIRouter
from .cross_encoder_reranker import rerank_with_cross_encoder
from .bm25_retriever import get_bm25_retriever
from .retrieval_planner import build_retrieval_plan, merge_plan_results
from .scholarship_lookup import scholarship_classification_lookup
from .study_duration_lookup import study_duration_lookup
from .structured_lookup import structured_lookup
from .structured_dispatcher import StructuredResolution, resolve_structured_decision
from .structured_context import build_structured_context
from .structured_routing import (
    decision_to_legacy_routing,
    fallback_to_rag,
    normalize_router_decision,
    validate_router_decision,
)
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
    """Execute one retrieval plan and return reranked source candidates.

    Regulation-only plans are delegated to the V7 child-parent hybrid retriever.
    Other content types use the legacy dense + sparse + graph fusion path,
    followed by cross-encoder reranking and lightweight metadata boosts.
    """
    candidate_k = max(plan["top_k"] * candidate_multiplier, min_candidates)
    plan_content_types = plan.get("content_types") or content_types_for_chunk_types(
        plan.get("chunk_types") or []
    )

    if _is_hybrid_regulation_plan(plan) and not _env_bool("STUDENT_RAG_DISABLE_HYBRID_RETRIEVAL"):
        try:
            return _retrieve_with_hybrid_regulation(
                query=query,
                plan=plan,
                detected_entities=detected_entities,
                cohort=cohort,
            )
        except Exception as exc:
            logger.error("Hybrid regulation retrieval failed: %s", exc)
            if collection is None or _env_bool("STUDENT_RAG_OFFLINE_EVAL"):
                return []

    # 1. Vector Search (Dense)
    if collection is None:
        logger.warning("Skip legacy vector search because collection is unavailable.")
        vector_results = []
    else:
        vector_results = [
            _ensure_chunk_type_metadata(doc)
            for doc in vector_search(
            query=plan["query"],
            model=model,
            collection=collection,
            chunk_types=plan["chunk_types"],
            content_types=plan_content_types,
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
        content_types=plan_content_types,
        cohort=cohort,
        )
    ]

    # 2.5 Graph Search (Knowledge Graph)
    # Lớp này đã bị gỡ bỏ vì chuyển sang dùng NetworkX ở Hybrid Pipeline
    graph_results = []

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

    for rank, doc in enumerate(graph_results):
        doc_id = doc["id"]
        doc["chunk_id"] = doc_id
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

    # 5. Filter weak reranked candidates
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
            
            try:
                store = _get_docstore()
                origin_doc = store.get_document_by_id(chunk_id)
                if origin_doc and "content" in origin_doc:
                    doc["content"] = doc.get("text", "") + "\n\n[RAW TEXT]\n" + origin_doc["content"]
            except Exception as e:
                logger.error(f"Error fetching chunk doc {chunk_id} from MongoDB: {e}")

        final_docs.append(doc)

    return final_docs[: plan["top_k"]]


def _build_ai_structured_response(
    resolution: StructuredResolution,
    *,
    query: str,
    retrieval_query: str,
    detected_entities: list[dict[str, Any]],
    routing: dict[str, Any],
    cohort: str | None,
    router_decision: dict[str, Any],
) -> dict[str, Any] | None:
    result = resolution.result
    if resolution.result_kind == "clarification":
        return {
            "query": query,
            "retrieval_query": retrieval_query,
            "detected_entities": detected_entities,
            "intent": "needs_clarification",
            "strategy": resolution.strategy,
            "target_chunk_types": [],
            "retrieved_items": [],
            "citations": [],
            "context_for_llm": "",
            "needs_llm_answer": False,
            "needs_clarification": True,
            "clarification_question": result.get("clarification_question"),
            "clarification_options": result.get("clarification_options") or [],
            "router_usage": routing.get("usage"),
            "router_model": routing.get("model_used"),
            "router_cache_hit": routing.get("router_cache_hit", False),
            "router_decision": router_decision,
        }
    expected_cohort = normalize_cohort(cohort)
    result_cohort = normalize_cohort(result.get("cohort"))
    if expected_cohort and result_cohort and expected_cohort != result_cohort:
        return None

    if resolution.result_kind == "formula":
        citations = build_citation_from_formula(result)
        context = build_context_from_formula(result)
    else:
        citations = build_citation_from_lookup(result)
        context = build_context_from_lookup(result)

    if not citations:
        return None
    for citation in citations:
        citation_cohort = normalize_cohort(
            citation.get("cohort") or (citation.get("metadata") or {}).get("cohort")
        )
        if expected_cohort and citation_cohort and expected_cohort != citation_cohort:
            return None

    return {
        "query": query,
        "retrieval_query": retrieval_query,
        "detected_entities": detected_entities,
        "intent": routing["intent"],
        "strategy": resolution.strategy,
        "target_chunk_types": resolution.target_chunk_types,
        "structured_result": result,
        "retrieved_items": [],
        "citations": citations,
        "context_for_llm": context,
        "needs_llm_answer": True,
        "router_usage": routing.get("usage"),
        "router_model": routing.get("model_used"),
        "router_cache_hit": routing.get("router_cache_hit", False),
        "router_decision": router_decision,
        "execution_mode": "structured",
    }


def _build_lookup_clarification_response(
    *,
    query: str,
    retrieval_query: str,
    detected_entities: list[dict[str, Any]],
    routing: dict[str, Any],
    router_decision: dict[str, Any],
) -> dict[str, Any]:
    return {
        "query": query,
        "retrieval_query": retrieval_query,
        "detected_entities": detected_entities,
        "intent": "needs_clarification",
        "strategy": "structured_lookup_clarification",
        "target_chunk_types": [],
        "retrieved_items": [],
        "citations": [],
        "context_for_llm": "",
        "needs_llm_answer": False,
        "needs_clarification": True,
        "clarification_question": (
            "Mình chưa xác định được chính xác dữ liệu cần tra. "
            "Bạn hãy nêu rõ khóa sinh viên và đối tượng hoặc giá trị cần hỏi."
        ),
        "clarification_options": [],
        "router_usage": routing.get("usage"),
        "router_model": routing.get("model_used"),
        "router_cache_hit": routing.get("router_cache_hit", False),
        "router_decision": router_decision,
        "unresolved_lookup_type": router_decision.get("lookup_type"),
    }


def run_retrieval_pipeline(
    query: str,
    model: SentenceTransformer,
    collection: Any,
    scoring_tables: list[dict[str, Any]],
    formula_rules: list[dict[str, Any]] | None,
    entity_registry: list[dict[str, Any]],
    expansion_rules: list[dict[str, Any]],
    form_templates: list[dict[str, Any]] | None = None,
    office_directory: list[dict[str, Any]] | None = None,
    student_service_directory: list[dict[str, Any]] | None = None,
    student_faculty_profiles: list[dict[str, Any]] | None = None,
    foreign_language_tables: list[dict[str, Any]] | None = None,
    structured_tables_registry: list[dict[str, Any]] | None = None,
    program_directory: list[dict[str, Any]] | None = None,
    top_k: int = 5,
    batch_size: int = 8,
    normalize_embeddings: bool = True,
    cohort: str | None = None,
    candidate_multiplier: int = 5,
    min_candidates: int = 25,
    chat_history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Route a user query to structured JSON or true-RAG retrieval.

    Qwen first decides whether the question is structured/tool-friendly or
    requires reading handbook regulations. Structured requests select one
    validated typed source for the answer LLM. RAG requests are normalized,
    expanded, planned, and sent to the hybrid child-parent retriever.
    """
    ai_router_enabled = not _env_bool("STUDENT_RAG_DISABLE_AI_ROUTER")
    query = expand_query(query, expansion_rules)
    router_decision: dict[str, Any] | None = None
    structured_context_result: dict[str, Any] | None = None
    structured_context_citations: list[dict[str, Any]] = []
    detected_entities: list[dict[str, Any]] = []
    legacy_retrieval_query = query

    if ai_router_enabled:
        grounding_context = "\n".join(
            str(item.get("content") or "")
            for item in (chat_history or [])[-2:]
        )
        try:
            ai_router = AIRouter.from_config()
            router_decision = ai_router.route(
                query,
                cohort=cohort,
                chat_history=chat_history,
            )
            if router_decision.get("route") == "clarify":
                routing_hint = find_grounded_catalog_hint(
                    query,
                    office_directory or [],
                    student_service_directory or [],
                    student_faculty_profiles or [],
                    cohort=cohort,
                )
                if routing_hint:
                    repaired_decision = ai_router.route(
                        query,
                        cohort=cohort,
                        chat_history=chat_history,
                        routing_hint=routing_hint,
                    )
                    if repaired_decision.get("route") != "clarify":
                        router_decision = repaired_decision
            router_decision = normalize_router_decision(
                router_decision,
                query=query,
                selected_cohort=cohort,
            ) | {
                key: router_decision.get(key)
                for key in (
                    "model_used",
                    "usage",
                    "key_fingerprint",
                    "router_cache_hit",
                    "attempts",
                )
                if key in router_decision
            }
            
            validation_errors = validate_router_decision(
                router_decision,
                query=query,
                selected_cohort=cohort,
                grounding_context=grounding_context,
            )
            
            
            if validation_errors:
                if "missing_cohort" in validation_errors:
                    router_decision = {
                        **router_decision,
                        "route": "clarify",
                        "clarification_question": (
                            "Bạn đang thuộc khóa K48-K49, K50 hay K51? "
                            "Mình cần khóa để tra đúng bảng và không trộn quy định."
                        ),
                        "router_validation_errors": validation_errors,
                    }
                else:
                    router_decision = fallback_to_rag(
                        router_decision,
                        validation_errors,
                        query=query,
                    )
            if _should_force_regulation_rag(
                query,
                router_decision,
                cohort=cohort,
            ):
                router_decision = _force_regulation_rag_decision(
                    router_decision,
                    query=query,
                )
            routing = decision_to_legacy_routing(router_decision)
            routing["usage"] = router_decision.get("usage")
            routing["model_used"] = router_decision.get("model_used")
            routing["router_cache_hit"] = router_decision.get("router_cache_hit", False)
            routing["router_validation_errors"] = router_decision.get(
                "router_validation_errors", []
            )
            rewritten = router_decision.get("retrieval_query") or query
            detected_entities = detect_entities(rewritten, entity_registry)
            if router_decision["route"] == "rag":
                rewritten_with_entities = normalize_query_with_entities(
                    rewritten,
                    detected_entities,
                )
                retrieval_query = expand_query(rewritten_with_entities, expansion_rules)
            else:
                retrieval_query = rewritten
        except Exception as exc:
            detected_entities = detect_entities(query, entity_registry)
            entity_normalized_query = normalize_query_with_entities(
                query, detected_entities
            )
            legacy_retrieval_query = expand_query(
                entity_normalized_query, expansion_rules
            )
            router_decision = {
                "route": "rag",
                "execution_mode": "regulation",
                "intent": "open_question",
                "lookup_type": None,
                "slots": {},
                "slot_spans": {},
                "retrieval_query": legacy_retrieval_query,
                "target_chunk_types": ["regulation"],
                "router_error": str(exc),
                "router_fallback": "qwen_failure_to_raw_query_rag",
            }
            routing = decision_to_legacy_routing(router_decision)
            routing["router_error"] = str(exc)
            retrieval_query = legacy_retrieval_query
    else:
        detected_entities = detect_entities(query, entity_registry)
        entity_normalized_query = normalize_query_with_entities(
            query, detected_entities
        )
        legacy_retrieval_query = expand_query(entity_normalized_query, expansion_rules)
        routing = route_query(query)
        retrieval_query = legacy_retrieval_query

    foreign_language_lookup_result = None
    if not ai_router_enabled and deterministic_lookup_allowed(query, "foreign_language"):
        foreign_language_lookup_result = foreign_language_lookup(
            query,
            foreign_language_tables or [],
            cohort=cohort,
        )
    if foreign_language_lookup_result is not None:
        return {
            "query": query,
            "retrieval_query": retrieval_query,
            "detected_entities": detected_entities,
            "intent": "foreign_language_lookup_query",
            "strategy": "foreign_language_lookup",
            "target_chunk_types": ["structured_lookup"],
            "structured_result": foreign_language_lookup_result,
            "retrieved_items": [],
            "citations": build_citation_from_lookup(foreign_language_lookup_result),
            "context_for_llm": build_context_from_lookup(foreign_language_lookup_result),
            "needs_llm_answer": False,
            "deterministic_validated": True,
            "deterministic_provenance": "legacy_validated_resolver",
            "router_usage": None,
            "router_model": None,
        }

    study_duration_lookup_result = None
    if not ai_router_enabled and deterministic_lookup_allowed(query, "study_duration"):
        study_duration_lookup_result = study_duration_lookup(
            query,
            structured_tables_registry or [],
            cohort=cohort,
        )
    if study_duration_lookup_result is not None:
        return {
            "query": query,
            "retrieval_query": retrieval_query,
            "detected_entities": detected_entities,
            "intent": "study_duration_lookup_query",
            "strategy": "study_duration_lookup",
            "target_chunk_types": ["structured_lookup"],
            "structured_result": study_duration_lookup_result,
            "retrieved_items": [],
            "citations": build_citation_from_lookup(study_duration_lookup_result),
            "context_for_llm": build_context_from_lookup(study_duration_lookup_result),
            "needs_llm_answer": False,
            "deterministic_validated": True,
            "deterministic_provenance": "legacy_validated_resolver",
            "router_usage": None,
            "router_model": None,
        }

    scholarship_lookup_result = None
    if not ai_router_enabled and deterministic_lookup_allowed(query, "scholarship"):
        scholarship_lookup_result = scholarship_classification_lookup(
            query,
            scoring_tables,
            cohort=cohort,
        )
    if scholarship_lookup_result is not None:
        return {
            "query": query,
            "retrieval_query": retrieval_query,
            "detected_entities": detected_entities,
            "intent": "scholarship_classification_lookup_query",
            "strategy": "scholarship_classification_lookup",
            "target_chunk_types": ["structured_lookup"],
            "structured_result": scholarship_lookup_result,
            "retrieved_items": [],
            "citations": build_citation_from_lookup(scholarship_lookup_result),
            "context_for_llm": build_context_from_lookup(scholarship_lookup_result),
            "needs_llm_answer": False,
            "deterministic_validated": True,
            "deterministic_provenance": "legacy_validated_resolver",
            "router_usage": None,
            "router_model": None,
        }

    if not ai_router_enabled and routing["intent"] == "unknown":
        routing = {
            "intent": "regulation_query",
            "strategy": "semantic_filtered",
            "target_chunk_types": ["regulation"],
            "router_error": "AI Router disabled by STUDENT_RAG_DISABLE_AI_ROUTER",
        }

    execution_mode = (
        str((router_decision or {}).get("execution_mode") or "regulation")
        if ai_router_enabled
        else "regulation"
    )
    if (
        ai_router_enabled
        and router_decision
        and router_decision.get("route") in {"structured", "rag"}
        and execution_mode in {"structured", "mixed"}
    ):
        table_context = build_structured_context(
            router_decision,
            structured_tables_registry or [],
            query=query,
            cohort=cohort,
        )
        resolution = None
        if table_context is None:
            resolution = resolve_structured_decision(
                router_decision,
                query=query,
                cohort=cohort,
                scoring_tables=scoring_tables,
                formula_rules=formula_rules or [],
                form_templates=form_templates or [],
                office_directory=office_directory or [],
                student_service_directory=student_service_directory or [],
                student_faculty_profiles=student_faculty_profiles or [],
                foreign_language_tables=foreign_language_tables or [],
                structured_tables_registry=structured_tables_registry or [],
                program_directory=program_directory or [],
                detected_entities=detected_entities,
                model=model,
            )
        if resolution is not None and resolution.result_kind == "clarification":
            response = _build_ai_structured_response(
                resolution,
                query=query,
                retrieval_query=retrieval_query,
                detected_entities=detected_entities,
                routing=routing,
                cohort=cohort,
                router_decision=router_decision,
            )
            if response is not None:
                return response

        structured_context_result = table_context or (
            resolution.result if resolution is not None else None
        )
        structured_strategy = (
            "structured_table"
            if table_context is not None
            else resolution.strategy
            if resolution is not None
            else "structured_json"
        )

        if structured_context_result is None:
            # Structured lookup failed — fallback to RAG instead of dead-end
            import logging as _fb_log
            _fb_log.getLogger(__name__).info(
                "Structured lookup returned None for %s; falling back to RAG",
                router_decision.get("lookup_type"),
            )
            router_decision = fallback_to_rag(
                router_decision,
                ["structured_lookup_returned_none"],
                query=query,
            )
            routing = decision_to_legacy_routing(router_decision)
            routing["usage"] = router_decision.get("usage")
            routing["model_used"] = router_decision.get("model_used")
            execution_mode = "regulation"
            # Fall through to the RAG retrieval path below
        else:
            # Structured lookup succeeded — process citations and return
            if resolution is not None and resolution.result_kind == "formula":
                structured_context_citations = build_citation_from_formula(
                    structured_context_result
                )
            else:
                structured_context_citations = build_citation_from_lookup(
                    structured_context_result
                )
            if not structured_context_citations:
                return {
                    "query": query,
                    "retrieval_query": retrieval_query,
                    "detected_entities": detected_entities,
                    "intent": "needs_clarification",
                    "strategy": "structured_source_validation_failed",
                    "target_chunk_types": [],
                    "retrieved_items": [],
                    "citations": [],
                    "context_for_llm": "",
                    "needs_llm_answer": False,
                    "needs_clarification": True,
                    "clarification_question": "Nguồn bảng chưa đủ thông tin để trích dẫn chính xác.",
                    "router_decision": router_decision,
                    "execution_mode": execution_mode,
                }
            expected_cohort = normalize_cohort(cohort)
            if expected_cohort and any(
                normalize_cohort(
                    citation.get("cohort")
                    or (citation.get("metadata") or {}).get("cohort")
                )
                not in {None, expected_cohort}
                for citation in structured_context_citations
            ):
                return _build_lookup_clarification_response(
                    query=query,
                    retrieval_query=retrieval_query,
                    detected_entities=detected_entities,
                    routing=routing,
                    router_decision=router_decision,
                )
            if execution_mode == "structured":
                return {
                    "query": query,
                    "retrieval_query": retrieval_query,
                    "detected_entities": detected_entities,
                    "intent": "structured_query",
                    "strategy": structured_strategy,
                    "target_chunk_types": [],
                    "structured_result": structured_context_result,
                    "retrieved_items": [],
                    "citations": structured_context_citations,
                    "context_for_llm": build_context_from_lookup(
                        structured_context_result
                    ),
                    "needs_llm_answer": True,
                    "router_usage": routing.get("usage"),
                    "router_model": routing.get("model_used"),
                    "router_cache_hit": routing.get("router_cache_hit", False),
                    "router_decision": router_decision,
                    "execution_mode": execution_mode,
                }

    intent = routing["intent"]
    strategy = routing["strategy"]
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
            "router_usage": routing.get("usage"),
            "router_model": routing.get("model_used"),
            "router_cache_hit": routing.get("router_cache_hit", False),
            "router_decision": router_decision,
            "router_validation_errors": routing.get(
                "router_validation_errors", []
            ),
        }
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
            "router_usage": routing.get("usage"),
            "router_model": routing.get("model_used"),
            "router_cache_hit": routing.get("router_cache_hit", False),
            "router_decision": router_decision,
            "router_validation_errors": routing.get(
                "router_validation_errors", []
            ),
        }

    entity_chunk_types = filter_entity_chunk_types(
        intent,
        get_entity_target_chunk_types(detected_entities),
    )

    if entity_chunk_types and strategy.startswith("semantic"):
        if (
            intent == "regulation_query"
            and execution_mode == "regulation"
            and "regulation" in routing.get("target_chunk_types", [])
        ):
            entity_chunk_types = [
                chunk_type
                for chunk_type in entity_chunk_types
                if chunk_type == "regulation"
            ]
        # Neu entity da biet loai chunk muc tieu, ep retrieval tim dung vung du lieu cua entity do.
        if entity_chunk_types:
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

    program_lookup_result = None
    if not ai_router_enabled:
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
            "deterministic_validated": not ai_router_enabled,
            "deterministic_provenance": (
                "legacy_validated_resolver" if not ai_router_enabled else None
            ),
            "router_usage": routing.get("usage"),
            "router_model": routing.get("model_used"),
        }

    office_lookup_result = None
    lookup_scope = routing.get("lookup_scope")
    if lookup_scope == "student_service":
        office_lookup_directory = student_service_directory or []
    elif lookup_scope == "office":
        office_lookup_directory = office_directory or []
    else:
        office_lookup_directory = office_directory or student_service_directory or []
    if intent == "office_query" or "office_directory" in target_chunk_types:
        office_lookup_result = office_lookup(
            query,
            office_lookup_directory or [],
            cohort=cohort,
            detected_entities=detected_entities,
            routing=routing,
        )

    if intent == "office_query" and office_lookup_result is not None:
        return {
            "query": query,
            "retrieval_query": retrieval_query,
            "detected_entities": detected_entities,
            "intent": intent,
            "strategy": routing.get("strategy")
            if routing.get("strategy") in {"student_service_lookup", "office_lookup"}
            else (
                "student_service_lookup"
                if office_lookup_result.get("lookup_scope") == "student_service"
                else "office_lookup"
            ),
            "target_chunk_types": [office_lookup_result.get("content_type") or "office_directory"],
            "structured_result": office_lookup_result,
            "retrieved_items": [],
            "citations": build_citation_from_lookup(office_lookup_result),
            "context_for_llm": build_context_from_lookup(office_lookup_result),
            "needs_llm_answer": False,
            "deterministic_validated": not ai_router_enabled,
            "deterministic_provenance": (
                "legacy_validated_resolver" if not ai_router_enabled else None
            ),
            "router_usage": routing.get("usage"),
            "router_model": routing.get("model_used"),
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
                "needs_llm_answer": False,
                "deterministic_validated": not ai_router_enabled,
                "deterministic_provenance": (
                    "legacy_validated_resolver" if not ai_router_enabled else None
                ),
                "router_usage": routing.get("usage"),
                "router_model": routing.get("model_used"),
            }

        fallback_plan = {
            "purpose": "form_fallback",
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
            "intent": intent,
            "strategy": "form_lookup_fallback_to_vector",
            "target_chunk_types": target_chunk_types,
            "structured_result": None,
            "retrieved_items": fallback_results,
            "citations": build_citations_from_vector_results(fallback_results),
            "context_for_llm": build_context_from_vector_results(fallback_results),
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
            "needs_llm_answer": False,
            "deterministic_validated": not ai_router_enabled,
            "deterministic_provenance": (
                "legacy_validated_resolver" if not ai_router_enabled else None
            ),
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
            "needs_llm_answer": False,
            "deterministic_validated": not ai_router_enabled,
            "deterministic_provenance": (
                "legacy_validated_resolver" if not ai_router_enabled else None
            ),
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
    related_items = _extract_related_items(merged_results)
    citations = structured_context_citations + build_citations_from_vector_results(
        merged_results
    )
    context_blocks = []
    if form_lookup_result is not None:
        citations = build_citation_from_lookup(form_lookup_result) + citations
        context_blocks.append(build_context_from_lookup(form_lookup_result))

    vector_context = build_context_from_vector_results(
        merged_results,
        related_items=related_items,
    )
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
        "structured_result": structured_context_result or form_lookup_result,
        "retrieved_items": merged_results,
        "related_items": related_items,
        "citations": citations,
        "context_for_llm": "\n\n---\n\n".join(context_blocks),
        "needs_llm_answer": True,
        "router_usage": routing.get("usage"),
        "router_model": routing.get("model_used"),
        "router_cache_hit": routing.get("router_cache_hit", False),
        "router_decision": router_decision,
        "router_validation_errors": routing.get("router_validation_errors", []),
        "execution_mode": execution_mode,
    }
