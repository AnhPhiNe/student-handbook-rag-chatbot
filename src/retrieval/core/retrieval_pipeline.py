import chromadb
from typing import Any

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
from .reranker import rerank_results
from .retrieval_planner import build_retrieval_plan, merge_plan_results
from .structured_lookup import structured_lookup
from .vector_retriever import vector_search


def retrieve_with_plan(
    query: str,
    plan: dict[str, Any],
    model: SentenceTransformer,
    collection: chromadb.Collection,
    batch_size: int,
    normalize_embeddings: bool,
    detected_entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidate_k = max(plan["top_k"] * 3, 10)

    vector_results = vector_search(
        query=plan["query"],
        model=model,
        collection=collection,
        chunk_types=plan["chunk_types"],
        top_k=candidate_k,
        batch_size=batch_size,
        normalize_embeddings=normalize_embeddings,
    )

    reranked = rerank_results(
        query=query,
        results=vector_results,
        target_chunk_types=plan["chunk_types"],
        detected_entities=detected_entities,
    )

    return reranked[: plan["top_k"]]


def run_retrieval_pipeline(
    query: str,
    model: SentenceTransformer,
    collection: chromadb.Collection,
    scoring_tables: list[dict[str, Any]],
    formula_rules: list[dict[str, Any]] | None,
    entity_registry: list[dict[str, Any]],
    expansion_rules: list[dict[str, Any]],
    top_k: int = 5,
    batch_size: int = 8,
    normalize_embeddings: bool = True,
) -> dict[str, Any]:
    detected_entities = detect_entities(query, entity_registry)
    entity_normalized_query = normalize_query_with_entities(query, detected_entities)
    retrieval_query = expand_query(entity_normalized_query, expansion_rules)

    routing = route_query(query)
    intent = routing["intent"]
    strategy = routing["strategy"]

    entity_chunk_types = get_entity_target_chunk_types(detected_entities)

    # Không để entity linker mở rộng sai chunk_type khi router đã xác định rõ nguồn.
    # Ví dụ: "Website phòng CNTT" phải giữ office_directory,
    # không được thêm faculty_program_directory chỉ vì có alias CNTT.
    STRICT_INTENTS = {
        "office_query",
        "faculty_query",
        "form_query",
        "procedure_query",
    }

    if (
        entity_chunk_types
        and strategy.startswith("semantic")
        and intent not in STRICT_INTENTS
    ):
        routing["target_chunk_types"] = list(
            dict.fromkeys(routing.get("target_chunk_types", []) + entity_chunk_types)
        )

    target_chunk_types = routing.get("target_chunk_types", [])

    if strategy == "calculator_tool":
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
        formula_result = formula_lookup(query, formula_rules or [])
        if formula_result is None:
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
        lookup_result = structured_lookup(query, scoring_tables)

        if lookup_result is None:
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
        plan_results = retrieve_with_plan(
            query=query,
            plan=plan,
            model=model,
            collection=collection,
            batch_size=batch_size,
            normalize_embeddings=normalize_embeddings,
            detected_entities=detected_entities,
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
