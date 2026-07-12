import os
from dotenv import load_dotenv
load_dotenv()
os.environ["TRANSFORMERS_VERBOSITY"] = "error"
import json
import logging
import time
import unicodedata
from collections import defaultdict
from typing import Any
from sentence_transformers import CrossEncoder
from src.retrieval.core.graph_traverser import NetworkXGraphTraverser
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

logger = logging.getLogger("hybrid_pipeline")

UNDERGRAD_SCOPE_TERMS = (
    "dai hoc",
    "daihoc",
    "trinh do dai hoc",
    "trinhdodaihoc",
    "dai hoc chinh quy",
    "daihocchinhquy",
    "he chinh quy",
    "hechinhquy",
    "sinh vien he chinh quy",
    "sinhvienhechinhquy",
)
COLLEGE_GDMN_SCOPE_TERMS = (
    "cao dang",
    "caodang",
    "gd mn",
    "gdmn",
    "giao duc mam non",
    "giaoducmamnon",
    "mam non",
    "mamnon",
    "nganh giao duc mam non",
    "nganhgiaoducmamnon",
)
COLLEGE_GDMN_QUERY_TERMS = (
    "cao dang",
    "caodang",
    "gd mn",
    "gdmn",
    "giao duc mam non",
    "giaoducmamnon",
    "mam non",
    "mamnon",
)
UNDERGRAD_SCOPE_BOOST = 0.035
COLLEGE_GDMN_SCOPE_PENALTY = -0.08


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


def _normalize_scope_text(value: Any) -> str:
    text = str(value or "").lower()
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    without_marks = without_marks.replace("đ", "d").replace("Đ", "d")
    return " ".join(without_marks.replace("_", " ").replace("-", " ").split())


def _contains_any_term(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _scope_text_for_chunk(chunk: dict[str, Any]) -> str:
    metadata = chunk.get("metadata") or {}
    values = [
        chunk.get("_id"),
        chunk.get("chunk_id"),
        metadata.get("parent_section_id"),
        metadata.get("document_title"),
        metadata.get("chapter_title"),
        metadata.get("chapter"),
        metadata.get("section_title"),
        metadata.get("source_section"),
        metadata.get("title"),
    ]
    return _normalize_scope_text(" ".join(str(value or "") for value in values))


def _scope_preference_adjustment(query: str, chunk: dict[str, Any]) -> float:
    """Apply a small cohort-scope preference without overriding semantic ranking."""
    query_scope = _normalize_scope_text(query)
    chunk_scope = _scope_text_for_chunk(chunk)

    asks_for_college_gdmn = _contains_any_term(query_scope, COLLEGE_GDMN_QUERY_TERMS)
    adjustment = 0.0
    if (
        not asks_for_college_gdmn
        and _contains_any_term(chunk_scope, COLLEGE_GDMN_SCOPE_TERMS)
    ):
        adjustment += COLLEGE_GDMN_SCOPE_PENALTY
    if _contains_any_term(chunk_scope, UNDERGRAD_SCOPE_TERMS):
        adjustment += UNDERGRAD_SCOPE_BOOST
    return adjustment


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
        docstore_path: str = "data/processed/chunks/all_docstore_items.json",
        v7_chunks_path: str = "data/processed/chunks/v7_child_parent_chunks.json",
    ):
        self.qdrant_client = QdrantClient(url=qdrant_url, api_key=qdrant_key, timeout=60.0)
        self.collection_name = collection_name

        from sentence_transformers import SentenceTransformer

        self.embed_model = SentenceTransformer("BAAI/bge-m3")
        self.graph = NetworkXGraphTraverser()
        logger.info("Loading PhoRanker for V7 child-parent retrieval...")
        self.reranker = CrossEncoder("itdainb/PhoRanker", max_length=256)

        with open(docstore_path, "r", encoding="utf-8") as f:
            parents = json.load(f)
        self.parent_store: dict[str, dict[str, Any]] = {}
        for parent in parents:
            metadata = parent.get("metadata") or {}
            parent_id = metadata.get("parent_section_id") or parent.get("_id")
            if parent_id:
                self.parent_store[str(parent_id)] = parent

        with open(v7_chunks_path, "r", encoding="utf-8") as f:
            child_chunks = json.load(f)
        self.child_store: dict[str, dict[str, Any]] = {}
        self.children_by_parent: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for chunk in child_chunks:
            chunk_id = str(chunk.get("_id") or chunk.get("chunk_id") or "")
            metadata = chunk.get("metadata") or {}
            parent_id = str(metadata.get("parent_section_id") or "")
            if not chunk_id or not parent_id:
                continue
            self.child_store[chunk_id] = chunk
            self.children_by_parent[parent_id].append(chunk)

    def retrieve(
        self,
        query: str,
        top_k_vector: int = 12,
        top_k_final: int = 5,
        graph_depth: int = 2,
        cohort: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve parent-bound regulation sources using V7 child/table chunks.

        Vector search starts from small Qdrant chunks, graph expansion adds
        related parent sections, the cross-encoder reranks all child/table
        candidates, and the final result is grouped back to Mongo parent
        sections for stable citations.
        """
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

        seed_chunk_ids = [
            str(hit.payload.get("chunk_id"))
            for hit in search_results
            if hit.payload and hit.payload.get("chunk_id")
        ]
        seed_chunks = [
            self.child_store[chunk_id]
            for chunk_id in seed_chunk_ids
            if chunk_id in self.child_store
        ]
        if not seed_chunks:
            return []

        seed_parent_ids = [
            str((chunk.get("metadata") or {}).get("parent_section_id") or "")
            for chunk in seed_chunks
        ]
        seed_parent_ids = [parent_id for parent_id in seed_parent_ids if parent_id]
        expanded_parent_ids: list[str] = []
        parent_depths: dict[str, int] = {}
        parent_sources: dict[str, str] = {}
        try:
            expanded = self.graph.expand_context(seed_parent_ids, max_depth=graph_depth)
            for node in expanded:
                node_id = str(node.get("id"))
                if node_id in self.parent_store:
                    expanded_parent_ids.append(node_id)
                    parent_depths[node_id] = node.get("depth", 99)
                    parent_sources[node_id] = node.get("seed_source", "unknown")
        except Exception as exc:
            logger.warning("V7 graph expansion failed, using vector seeds only: %s", exc)

        neighbor_chunks = []
        seed_chunk_ids = {str(chunk.get("_id") or chunk.get("chunk_id") or "") for chunk in seed_chunks}
        
        for parent_id in dict.fromkeys(expanded_parent_ids):
            depth = parent_depths.get(parent_id, 99)
            source_seed = parent_sources.get(parent_id, "unknown")
            for chunk in self.children_by_parent.get(parent_id, []):
                metadata = chunk.get("metadata") or {}
                if cohort and metadata.get("cohort") != cohort:
                    continue
                chunk_id = str(chunk.get("_id") or chunk.get("chunk_id") or "")
                # Đã khử trùng lặp: Nếu chunk này đã là seed thì tuyệt đối không thêm vào neighbor
                if chunk_id and chunk_id not in seed_chunk_ids:
                    chunk_copy = dict(chunk)
                    chunk_copy["_graph_depth"] = depth
                    chunk_copy["_source_seed_id"] = source_seed
                    neighbor_chunks.append(chunk_copy)

        # --- BUDGET ALLOCATION ---
        # Ngân sách 1: Seed Chunks (~24) -> Pass thẳng
        final_candidates = list(seed_chunks)

        # Ngân sách 2: Neighbor Chunks -> Lọc bằng cấu trúc Graph (Depth) với Round-Robin theo Seed
        if neighbor_chunks:
            # Nhóm các láng giềng theo Parent ID để lấy TRỌN VẸN cả Điều, không băm nhỏ từng khoản
            neighbors_by_parent: dict[str, list] = defaultdict(list)
            parent_to_seed: dict[str, str] = {}
            parent_to_depth: dict[str, int] = {}
            for chunk in neighbor_chunks:
                pid = str((chunk.get("metadata") or {}).get("parent_section_id") or "")
                if pid:
                    neighbors_by_parent[pid].append(chunk)
                    parent_to_seed[pid] = chunk.get("_source_seed_id", "unknown")
                    parent_to_depth[pid] = min(parent_to_depth.get(pid, 99), chunk.get("_graph_depth", 99))

            # Nhóm các Parent ID theo Seed
            parents_by_seed: dict[str, list[str]] = defaultdict(list)
            for pid, sid in parent_to_seed.items():
                parents_by_seed[sid].append(pid)

            # Sắp xếp các Parent của mỗi Seed theo depth
            for sid in parents_by_seed:
                parents_by_seed[sid].sort(key=lambda pid: parent_to_depth[pid])

            # Round-robin: mỗi vòng lấy 1 Parent (nguyên Điều) của MỖI seed
            filtered_parent_ids = []
            seed_ids = list(parents_by_seed.keys())
            idx = 0
            while len(filtered_parent_ids) < 3 and any(parents_by_seed.values()):
                sid = seed_ids[idx % len(seed_ids)]
                if parents_by_seed[sid]:
                    filtered_parent_ids.append(parents_by_seed[sid].pop(0))
                idx += 1

            # Gom lại tất cả các chunk thuộc về các Parent đã chọn
            filtered_neighbors = []
            for pid in filtered_parent_ids:
                filtered_neighbors.extend(neighbors_by_parent[pid])

            final_candidates.extend(filtered_neighbors)

        if not final_candidates:
            return []

        # Lớp 2: Lọc tinh bằng Cross-Encoder trên Budget đã gộp (~40)
        scored = self._rerank_chunks(query, final_candidates)
        return self._group_parent_results(
            query=query,
            scored_chunks=scored,
            top_k_final=top_k_final,
        )

    def _rerank_chunks(
        self,
        query: str,
        chunks: list[dict[str, Any]],
    ) -> list[tuple[float, dict[str, Any]]]:
        """Score V7 child/table chunks with the cross-encoder and light scope boosts."""
        pairs = [[query, str(chunk.get("content") or "")] for chunk in chunks]
        scores = self.reranker.predict(pairs)
        scored: list[tuple[float, dict[str, Any]]] = []
        for index, chunk in enumerate(chunks):
            score = float(scores[index])
            metadata = dict(chunk.get("metadata") or {})
            granularity = metadata.get("chunk_granularity")
            if granularity == "table_like":
                score += 0.04
            elif granularity == "child":
                score += 0.02
            scope_adjustment = _scope_preference_adjustment(query, chunk)
            if scope_adjustment:
                chunk = dict(chunk)
                metadata["scope_preference_adjustment"] = round(scope_adjustment, 4)
                chunk["metadata"] = metadata
                score += scope_adjustment
            scored.append((score, chunk))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored

    def _group_parent_results(
        self,
        *,
        query: str,
        scored_chunks: list[tuple[float, dict[str, Any]]],
        top_k_final: int,
    ) -> list[dict[str, Any]]:
        """Group top child/table matches back into parent-section result objects."""
        parent_groups: dict[str, list[tuple[float, dict[str, Any]]]] = defaultdict(list)
        parent_best_score: dict[str, float] = {}
        for score, chunk in scored_chunks:
            parent_id = str((chunk.get("metadata") or {}).get("parent_section_id") or "")
            if not parent_id or parent_id not in self.parent_store:
                continue
            parent_groups[parent_id].append((score, chunk))
            parent_best_score[parent_id] = max(score, parent_best_score.get(parent_id, -999.0))

        ranked_parent_ids = sorted(
            parent_groups.keys(),
            key=lambda parent_id: parent_best_score[parent_id],
            reverse=True,
        )

        results: list[dict[str, Any]] = []
        for parent_id in ranked_parent_ids[:top_k_final]:
            parent = self.parent_store[parent_id]
            parent_metadata = dict(parent.get("metadata") or {})
            focused_chunks = self._focused_chunks_for_parent(
                query=query,
                parent_id=parent_id,
                scored_group=parent_groups[parent_id],
            )
            focused_context = _format_v7_focused_context(parent_metadata, focused_chunks)
            doc = dict(parent)
            doc["chunk_id"] = parent_id
            doc["rerank_score"] = float(parent_best_score[parent_id])
            doc["content"] = focused_context
            doc["document"] = parent.get("content") or ""
            doc["metadata"] = {
                **parent_metadata,
                "chunk_id": parent_id,
                "chunk_type": "regulation",
                "content_type": "regulation_text",
                "chunk_granularity": "parent_bound_context",
                "v7_collection": self.collection_name,
                "v7_matched_chunks": [
                    {
                        "chunk_id": chunk.get("_id") or chunk.get("chunk_id"),
                        "chunk_granularity": (chunk.get("metadata") or {}).get("chunk_granularity"),
                        "clause_marker": (chunk.get("metadata") or {}).get("clause_marker"),
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
        query: str,
        parent_id: str,
        scored_group: list[tuple[float, dict[str, Any]]],
    ) -> list[tuple[float, dict[str, Any]]]:
        """Choose the child/table snippets that should be shown before the parent text."""
        # Lấy tối đa 4 chunk cho các kết quả Vector/BM25 thông thường,
        # NHƯNG lấy TẤT CẢ các chunk nếu parent này là Graph Neighbor (có _graph_depth)
        # để tránh việc PhoRanker loại mất đoạn văn chứa câu trả lời do không khớp keyword.
        scored_group_sorted = sorted(scored_group, key=lambda pair: pair[0], reverse=True)
        selected = []
        for pair in scored_group_sorted:
            chunk = pair[1]
            if chunk.get("_graph_depth", 0) > 0 or len(selected) < 4:
                selected.append(pair)
        if any(
            (chunk.get("metadata") or {}).get("chunk_granularity") in {"child", "table_like"}
            for _, chunk in selected
        ):
            return selected

        candidates = [
            chunk
            for chunk in self.children_by_parent.get(parent_id, [])
            if (chunk.get("metadata") or {}).get("chunk_granularity") in {"child", "table_like"}
        ]
        if not candidates:
            return selected
        supplemental = self._rerank_chunks(query, candidates)[:3]
        return [*selected[:1], *supplemental]


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
    title = parent_metadata.get("title") or parent_metadata.get("article") or "Regulation source"
    lines = [
        "FOCUSED EVIDENCE FROM SOURCE:",
        f"Parent source: {title}",
    ]
    seen: set[str] = set()
    for score, chunk in focused_chunks:
        metadata = chunk.get("metadata") or {}
        content = str(chunk.get("content") or "").strip()
        content = content.split("Content:", 1)[-1].strip() if "Content:" in content else content
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
    query: str,
    top_k: int = 5,
    **kwargs
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
    for doc in docs:
        metadata = doc.get("metadata", {})
        doc_copy = dict(doc)
        doc_copy["chunk_id"] = doc.get("_id") or doc.get("id")
        doc_copy["chunk_type"] = doc_copy.get("chunk_type") or metadata.get("chunk_type") or "regulation"
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
        "citations": citations,
        "context_for_llm": build_context_from_vector_results(formatted_results),
        "needs_llm_answer": True,
        "needs_clarification": False,
        "out_of_domain": False
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
