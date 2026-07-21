import os
from dotenv import load_dotenv
from src.retrieval.vectorstore.mongo_store import get_mongo_store
load_dotenv()
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
import logging
import time
from collections import defaultdict
from typing import Any
from src.retrieval.core.cross_encoder_reranker import get_local_reranker
from src.retrieval.core.graph_traverser import NetworkXGraphTraverser
from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
)

logger = logging.getLogger("hybrid_pipeline")

DEFAULT_RETRIEVAL_MODE = "vector_primary_graph_supplement"
SUPPORTED_RETRIEVAL_MODES = {
    "full",
    "no_graph",
    "vector_only",
    DEFAULT_RETRIEVAL_MODE,
}
GRAPH_SUPPLEMENT_PARENT_LIMIT = 5
PHORANKER_EVAL_MODES = {"full", "no_graph"}

def _query_points_with_retry(
    client: QdrantClient,
    *,
    collection_name: str,
    query: list[float],
    limit: int,
    query_filter: Filter | None = None,
    attempts: int = 3,
):
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            kwargs: dict[str, Any] = {
                "collection_name": collection_name,
                "query": query,
                "limit": limit,
            }
            if query_filter is not None:
                kwargs["query_filter"] = query_filter
            return client.query_points(**kwargs).points
        except Exception as exc:
            last_error = exc
            if attempt >= attempts:
                break
            sleep_seconds = 1.5 * attempt
            logger.warning(
                "Qdrant query failed on attempt %s/%s; retrying in %.1fs: %s",
                attempt,
                attempts,
                sleep_seconds,
                exc,
            )
            time.sleep(sleep_seconds)
    assert last_error is not None
    raise last_error


def _is_supplemental_regulation_metadata(metadata: dict[str, Any]) -> bool:
    source_type = str(metadata.get("source_type") or "").strip().lower()
    parent_id = str(metadata.get("parent_section_id") or metadata.get("chunk_id") or "")
    return source_type == "supplemental_regulation" or "_Supplement_" in parent_id


def select_graph_related_parent_candidates(
    primary_parent_ids: list[str],
    expanded_nodes: list[dict[str, Any]],
    *,
    max_related_total: int = GRAPH_SUPPLEMENT_PARENT_LIMIT,
) -> list[dict[str, Any]]:
    """Select context-only graph neighbors without changing primary ranking.

    Priority follows the production rule:
    lower graph depth first, then higher-ranked primary source, then graph
    traversal order. Primary parents are never returned as related parents.
    """

    primary_ids = [
        str(parent_id)
        for parent_id in primary_parent_ids
        if str(parent_id).strip()
    ]
    primary_set = set(primary_ids)
    primary_rank = {
        parent_id: index
        for index, parent_id in enumerate(primary_ids)
    }
    best_by_parent: dict[str, dict[str, Any]] = {}

    for edge_order, node in enumerate(expanded_nodes):
        parent_id = str(node.get("id") or "").strip()
        if not parent_id or parent_id in primary_set:
            continue

        try:
            depth = int(node.get("depth", 99))
        except (TypeError, ValueError):
            depth = 99
        source_primary_id = str(node.get("seed_source") or "").strip()
        source_primary_rank = primary_rank.get(source_primary_id, 999)
        candidate = {
            "parent_id": parent_id,
            "depth": depth,
            "source_primary_id": source_primary_id,
            "source_primary_rank": source_primary_rank,
            "edge_order": edge_order,
        }
        existing = best_by_parent.get(parent_id)
        candidate_key = (depth, source_primary_rank, edge_order)
        if existing is None:
            best_by_parent[parent_id] = candidate
            continue
        existing_key = (
            existing["depth"],
            existing["source_primary_rank"],
            existing["edge_order"],
        )
        if candidate_key < existing_key:
            best_by_parent[parent_id] = candidate

    ranked = sorted(
        best_by_parent.values(),
        key=lambda item: (
            item["depth"],
            item["source_primary_rank"],
            item["edge_order"],
        ),
    )
    return ranked[: max(0, int(max_related_total))]


class HybridRetrieverV7:
    """Child-parent retriever for regulation_text.

    Qdrant stores small section_heading/child/table_like chunks. Mongo/docstore keeps
    the full parent section. Returned items are parent-bound: ``content`` is focused
    child/table context for the LLM, while ``document`` is the full parent text for
    citation display.
    """

    def __init__(
        self,
        qdrant_url: str,
        qdrant_key: str,
        collection_name: str = "student_handbook_semantic_v7",
    ):
        self.qdrant_client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_key,
            timeout=60.0,
        )
        self.collection_name = collection_name

        from sentence_transformers import SentenceTransformer

        self.embed_model = SentenceTransformer("BAAI/bge-m3")
        self.graph = NetworkXGraphTraverser()

        # PhoRanker is evaluation-only and is loaded lazily by its ablation modes.
        self.reranker = None

        # Parent đầy đủ lấy từ MongoDB.
        self.mongo_store = get_mongo_store()

        # Cache runtime, không phải dữ liệu local.
        self.parent_cache: dict[str, dict[str, Any]] = {}

    def _get_parent(self, parent_id: str) -> dict[str, Any] | None:
        if not parent_id:
            return None

        cached = self.parent_cache.get(parent_id)
        if cached is not None:
            return cached

        parent = self.mongo_store.get_document_by_id(parent_id)

        if parent is not None:
            self.parent_cache[parent_id] = parent

        return parent
    
    @staticmethod
    def _qdrant_point_to_chunk(point: Any) -> dict[str, Any]:
        """Chuyển một Qdrant point thành cấu trúc chunk nội bộ."""
        payload = dict(point.payload or {})
        chunk_id = str(payload.get("chunk_id") or point.id)

        return {
            "_id": chunk_id,
            "chunk_id": chunk_id,
            "content": str(payload.get("content") or ""),
            "metadata": payload,
        }


    def retrieve(
        self,
        query: str,
        top_k_vector: int = 12,
        top_k_final: int = 5,
        graph_depth: int = 2,
        cohort: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve parent-bound regulation sources using V7 child/table chunks.

        Production ranks parents by their best vector hit, then attaches
        outbound graph neighbors as context-only related sources. PhoRanker is
        reserved for controlled evaluation modes over the same vector pool.
        """
        eval_mode = (
            os.environ.get(
                "STUDENT_RAG_EVAL_RETRIEVAL_MODE",
                DEFAULT_RETRIEVAL_MODE,
            )
            .strip()
            .lower()
        )
        if eval_mode not in SUPPORTED_RETRIEVAL_MODES:
            raise ValueError(
                f"Unsupported STUDENT_RAG_EVAL_RETRIEVAL_MODE={eval_mode!r}"
            )
        if eval_mode in {"no_graph", "vector_only"}:
            graph_depth = 0

        retrieval_started = time.perf_counter()
        logger.info("==> V7 query: %s", query)
        query_vector = self.embed_model.encode(query).tolist()
        query_filter = _v7_query_filter(cohort)
        search_limit = max(top_k_vector * 2, 24)
        search_results = _query_points_with_retry(
            self.qdrant_client,
            collection_name=self.collection_name,
            query=query_vector,
            query_filter=query_filter,
            limit=search_limit,
        )

        seed_chunks = [
            self._qdrant_point_to_chunk(hit)
            for hit in search_results
            if hit.payload
        ]

        seed_chunks = [
            chunk
            for chunk in seed_chunks
            if chunk.get("chunk_id")
            and not _is_supplemental_regulation_metadata(chunk.get("metadata") or {})
        ]
        qdrant_seed_chunk_count = len(seed_chunks)

        if not seed_chunks:
            return []

        vector_scores = {
            str(hit.payload.get("chunk_id")): float(
                getattr(hit, "score", 0.0) or 0.0
            )
            for hit in search_results
            if hit.payload and hit.payload.get("chunk_id")
        }
        vector_scored = [
            (
                vector_scores.get(
                    str(chunk.get("_id") or chunk.get("chunk_id") or ""),
                    0.0,
                ),
                chunk,
            )
            for chunk in seed_chunks
        ]
        
        import re
        query_terms = set(re.findall(r"\w+", query.lower()))
        if query_terms:
            lexical_scored = []
            for dense_score, chunk in vector_scored:
                chunk_text = str(chunk.get("content") or "").lower()
                doc_terms = set(re.findall(r"\w+", chunk_text))
                coverage = len(query_terms & doc_terms) / len(query_terms)
                lexical_boost = coverage * 0.3
                lexical_scored.append((dense_score + lexical_boost, chunk))
            vector_scored = lexical_scored
        seed_parent_ids = {
            str((chunk.get("metadata") or {}).get("parent_section_id") or "")
            for chunk in seed_chunks
            if (chunk.get("metadata") or {}).get("parent_section_id")
        }

        phoranker_used = eval_mode in PHORANKER_EVAL_MODES
        if phoranker_used:
            rerank_started = time.perf_counter()
            primary_scored = self._rerank_chunks(query, seed_chunks)
            phoranker_latency_ms = (time.perf_counter() - rerank_started) * 1000
        else:
            primary_scored = vector_scored
            phoranker_latency_ms = 0.0

        retrieval_telemetry = {
            "retrieval_mode": eval_mode,
            "qdrant_search_limit": search_limit,
            "qdrant_seed_chunks": qdrant_seed_chunk_count,
            "qdrant_seed_parents": len(seed_parent_ids),
            "ranking_method": "phoranker" if phoranker_used else "vector",
            "phoranker_used": phoranker_used,
            "phoranker_candidate_chunks": (
                qdrant_seed_chunk_count if phoranker_used else 0
            ),
            "phoranker_candidate_parents": (
                len(seed_parent_ids) if phoranker_used else 0
            ),
            "phoranker_latency_ms": phoranker_latency_ms,
        }
        primary_results = self._group_parent_results(
            query=query,
            scored_chunks=primary_scored,
            top_k_final=top_k_final,
            retrieval_telemetry=retrieval_telemetry,
        )
        if eval_mode in {"vector_only", "no_graph"}:
            retrieval_telemetry["retrieval_latency_ms"] = (
                time.perf_counter() - retrieval_started
            ) * 1000
            for item in primary_results:
                item_metadata = dict(item.get("metadata") or {})
                item_metadata["retrieval_telemetry"] = retrieval_telemetry
                item["metadata"] = item_metadata
            return primary_results

        related_results, related_telemetry = self._graph_related_parent_results(
            primary_results,
            graph_depth=graph_depth,
            cohort=cohort,
        )
        supplement_telemetry = {
            **retrieval_telemetry,
            **related_telemetry,
            "retrieval_latency_ms": (
                time.perf_counter() - retrieval_started
            ) * 1000,
        }
        for item in primary_results:
            item_metadata = dict(item.get("metadata") or {})
            item_metadata["retrieval_telemetry"] = supplement_telemetry
            item["metadata"] = item_metadata
        if primary_results and related_results:
            primary_metadata = dict(primary_results[0].get("metadata") or {})
            primary_metadata["related_items"] = related_results
            primary_results[0]["metadata"] = primary_metadata
        return primary_results

    def _graph_related_parent_results(
        self,
        primary_results: list[dict[str, Any]],
        *,
        graph_depth: int,
        cohort: str | None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Fetch outbound graph neighbors as context-only related sources."""

        primary_parent_ids = [
            str(item.get("chunk_id") or item.get("_id") or item.get("id") or "")
            for item in primary_results
        ]
        primary_parent_ids = [
            parent_id for parent_id in primary_parent_ids if parent_id
        ]
        expanded: list[dict[str, Any]] = []
        if primary_parent_ids and graph_depth > 0:
            try:
                expanded = self.graph.expand_context(
                    primary_parent_ids,
                    max_depth=graph_depth,
                )
            except Exception as exc:
                logger.warning(
                    "V7 graph supplement expansion failed, using primary only: %s",
                    exc,
                )

        related_candidates = select_graph_related_parent_candidates(
            primary_parent_ids,
            expanded,
            max_related_total=GRAPH_SUPPLEMENT_PARENT_LIMIT,
        )
        related_results: list[dict[str, Any]] = []
        for rank, candidate in enumerate(related_candidates, start=1):
            parent_id = candidate["parent_id"]
            parent = self._get_parent(parent_id)
            if parent is None:
                logger.warning(
                    "Cannot attach graph related parent %s because Mongo lookup missed.",
                    parent_id,
                )
                continue

            parent_metadata = dict(parent.get("metadata") or {})
            if _is_supplemental_regulation_metadata(
                {
                    **parent_metadata,
                    "parent_section_id": parent_id,
                }
            ):
                continue
            if cohort and parent_metadata.get("cohort") != cohort:
                continue

            doc = dict(parent)
            doc["chunk_id"] = parent_id
            doc["rerank_score"] = 0.0
            doc["content"] = parent.get("content") or ""
            doc["document"] = parent.get("content") or ""
            doc["metadata"] = {
                **parent_metadata,
                "chunk_id": parent_id,
                "chunk_type": "regulation",
                "content_type": "regulation_text",
                "chunk_granularity": "parent_graph_related_context",
                "retrieval_role": "related",
                "related_rank": rank,
                "related_graph_depth": candidate["depth"],
                "related_source_primary_id": candidate["source_primary_id"],
                "related_source_primary_rank": candidate["source_primary_rank"],
                "v7_collection": self.collection_name,
                "parent_source": "mongodb",
                "child_source": "graph",
            }
            related_results.append(doc)

        telemetry = {
            "graph_depth": graph_depth,
            "graph_expanded_parents": len(
                {
                    str(node.get("id") or "")
                    for node in expanded
                    if node.get("id")
                }
            ),
            "graph_related_parent_limit": GRAPH_SUPPLEMENT_PARENT_LIMIT,
            "graph_related_parents_selected": len(related_results),
            "graph_neighbor_parent_limit": GRAPH_SUPPLEMENT_PARENT_LIMIT,
            "graph_neighbor_parents_selected": len(related_results),
            "graph_neighbor_chunks_available": 0,
            "graph_neighbor_chunks_selected": 0,
            "related_source_count": len(related_results),
        }
        return related_results, telemetry

    def _rerank_chunks(
        self,
        query: str,
        chunks: list[dict[str, Any]],
    ) -> list[tuple[float, dict[str, Any]]]:
        """Score the fixed vector candidate set with PhoRanker."""
        pairs = [[query, str(chunk.get("content") or "")] for chunk in chunks]
        scores = self._get_reranker_model().predict(pairs)
        scored = [
            (float(scores[index]), dict(chunk))
            for index, chunk in enumerate(chunks)
        ]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored

    def _get_reranker_model(self):
        if self.reranker is None:
            logger.info("Loading shared PhoRanker singleton for retrieval ablation...")
            self.reranker = get_local_reranker().model
        return self.reranker

    def _group_parent_results(
        self,
        *,
        query: str,
        scored_chunks: list[tuple[float, dict[str, Any]]],
        top_k_final: int,
        retrieval_telemetry: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Group top child/table matches back into parent-section result objects."""
        parent_groups: dict[str, list[tuple[float, dict[str, Any]]]] = defaultdict(list)
        parent_best_score: dict[str, float] = {}
        for score, chunk in scored_chunks:
            parent_id = str(
                (chunk.get("metadata") or {}).get("parent_section_id") or ""
            )
            if not parent_id:
                continue
            parent_groups[parent_id].append((score, chunk))
            parent_best_score[parent_id] = max(
                score, parent_best_score.get(parent_id, -999.0)
            )

        ranked_parent_ids = sorted(
            parent_groups.keys(),
            key=lambda parent_id: parent_best_score[parent_id],
            reverse=True,
        )

        results: list[dict[str, Any]] = []
        for parent_id in ranked_parent_ids:
            if len(results) >= top_k_final:
                break

            parent = self._get_parent(parent_id)

            if parent is None:
                logger.warning(
                    "Không tìm thấy parent %s trong MongoDB collection.",
                    parent_id,
                )
                continue
    
            parent_metadata = dict(parent.get("metadata") or {})
            focused_chunks = self._focused_chunks_for_parent(
                scored_group=parent_groups[parent_id],
            )
            doc = dict(parent)
            doc["chunk_id"] = parent_id
            doc["rerank_score"] = float(parent_best_score[parent_id])
            # PHỤC HỒI TOÀN BỘ NỘI DUNG TỪ MONGODB THAY VÌ FOCUSED CHUNKS
            doc["content"] = parent.get("content") or ""
            doc["document"] = parent.get("content") or ""
            doc["metadata"] = {
                **parent_metadata,
                "chunk_id": parent_id,
                "chunk_type": "regulation",
                "content_type": "regulation_text",
                "chunk_granularity": "parent_bound_context",
                "retrieval_role": "primary",
                "v7_collection": self.collection_name,
                "parent_source": "mongodb",
                "child_source": "qdrant",
                "retrieval_telemetry": retrieval_telemetry or {},
                "v7_matched_chunks": [
                    {
                        "chunk_id": chunk.get("_id") or chunk.get("chunk_id"),
                        "chunk_granularity": (chunk.get("metadata") or {}).get(
                            "chunk_granularity"
                        ),
                        "clause_marker": (chunk.get("metadata") or {}).get(
                            "clause_marker"
                        ),
                        "score": float(score),
                        "_graph_depth": chunk.get("_graph_depth"),
                        "_source_seed_id": chunk.get("_source_seed_id"),
                    }
                    for score, chunk in focused_chunks
                ],
            }
            results.append(doc)
        return results

    def _focused_chunks_for_parent(
        self,
        *,
        scored_group: list[tuple[float, dict[str, Any]]],
    ) -> list[tuple[float, dict[str, Any]]]:
        """Keep the strongest matched children for provenance/debug metadata."""
        return sorted(scored_group, key=lambda pair: pair[0], reverse=True)[:12]


def _v7_query_filter(cohort: str | None) -> Filter:
    conditions = [
        FieldCondition(key="content_type", match=MatchValue(value="regulation_text")),
    ]
    if cohort:
        conditions.append(FieldCondition(key="cohort", match=MatchValue(value=cohort)))
    return Filter(must=conditions)


def _format_v7_focused_context(
    parent_metadata: dict[str, Any],
    focused_chunks: list[tuple[float, dict[str, Any]]],
) -> str:
    title = (
        parent_metadata.get("title")
        or parent_metadata.get("article")
        or "Regulation source"
    )
    lines = [
        "FOCUSED EVIDENCE FROM SOURCE:",
        f"Parent source: {title}",
    ]
    seen: set[str] = set()
    for score, chunk in focused_chunks:
        metadata = chunk.get("metadata") or {}
        content = str(chunk.get("content") or "").strip()
        content = (
            content.split("Content:", 1)[-1].strip()
            if "Content:" in content
            else content
        )
        if not content:
            continue
        key = " ".join(content.lower().split())
        if key in seen:
            continue
        seen.add(key)
        granularity = metadata.get("chunk_granularity") or "child"
        marker = metadata.get("clause_marker")
        prefix = f"- [{granularity}"
        if marker:
            prefix += f" {marker}"
        prefix += f" | score {float(score):.3f}] "
        lines.append(prefix + content)
    return "\n".join(lines)


_GLOBAL_RETRIEVER = None


def run_hybrid_retrieval_pipeline(
    query: str, top_k: int = 5, **kwargs
) -> dict[str, Any]:
    """Run the configured hybrid regulation retriever and return pipeline-shaped output.

    Runtime uses the V7 child-parent retriever. The adapter keeps the same
    output contract as the broader retrieval pipeline so the answer layer and
    UI do not need separate code paths.
    """
    global _GLOBAL_RETRIEVER

    if _GLOBAL_RETRIEVER is None:
        import os
        from src.common.env_loader import load_project_env

        load_project_env()

        qdrant_url = os.getenv("QDRANT_URL")
        qdrant_key = os.getenv("QDRANT_API_KEY")
        collection_name = os.getenv(
            "STUDENT_RAG_HYBRID_COLLECTION",
            "student_handbook_semantic_v7",
        )
        logger.info("Initializing hybrid regulation retriever V7...")
        _GLOBAL_RETRIEVER = HybridRetrieverV7(
            qdrant_url,
            qdrant_key,
            collection_name=collection_name,
        )

    cohort = kwargs.get("cohort")
    retrieval_query = kwargs.get("retrieval_query") or query
    detected_entities = kwargs.get("detected_entities") or []
    intent = kwargs.get("intent") or "regulation_query"
    strategy = kwargs.get("strategy") or "hybrid_graph_retrieval"
    target_chunk_types = kwargs.get("target_chunk_types") or ["regulation"]

    docs = _GLOBAL_RETRIEVER.retrieve(
        retrieval_query,
        top_k_final=top_k,
        cohort=cohort,
    )

    formatted_results = []
    related_items: list[dict[str, Any]] = []
    for doc in docs:
        metadata = dict(doc.get("metadata", {}) or {})
        if not related_items:
            raw_related = metadata.pop("related_items", [])
            if isinstance(raw_related, list):
                related_items = [
                    item for item in raw_related if isinstance(item, dict)
                ]
        doc_copy = dict(doc)
        doc_copy["metadata"] = metadata
        doc_copy["chunk_id"] = doc.get("chunk_id") or doc.get("_id") or doc.get("id")
        doc_copy["chunk_type"] = (
            doc_copy.get("chunk_type") or metadata.get("chunk_type") or "regulation"
        )
        formatted_results.append(doc_copy)

    from .citation_builder import build_citations_from_vector_results
    from .context_builder import build_context_from_vector_results

    citations = build_citations_from_vector_results(formatted_results)

    return {
        "query": query,
        "retrieval_query": retrieval_query,
        "detected_entities": detected_entities,
        "intent": intent,
        "strategy": strategy,
        "target_chunk_types": target_chunk_types,
        "structured_result": None,
        "tool_result": None,
        "retrieved_items": formatted_results,
        "related_items": related_items,
        "citations": citations,
        "context_for_llm": build_context_from_vector_results(
            formatted_results,
            related_items=related_items,
        ),
        "needs_llm_answer": True,
        "needs_clarification": False,
        "out_of_domain": False,
    }


if __name__ == "__main__":
    from src.common.env_loader import load_project_env

    load_project_env()
    qdrant_url = os.getenv("QDRANT_URL")
    qdrant_key = os.getenv("QDRANT_API_KEY")

    retriever = HybridRetrieverV7(qdrant_url, qdrant_key)
    res = retriever.retrieve("Dieu kien xet hoc bong la gi?")
    for r in res:
        print(f"[{r['rerank_score']:.4f}] {r['metadata']['title']}")
