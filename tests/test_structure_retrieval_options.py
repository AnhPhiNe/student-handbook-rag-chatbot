"""Retrieval options for structure chunks; each is off by default (offline)."""
from src.retrieval.core.bm25_retriever import BM25Retriever
from src.retrieval.core.hybrid_pipeline import cap_children_per_parent
from src.retrieval.core.reranker import _rerank_text


def chunk(chunk_id, parent, content="x", header=None):
    metadata = {"chunk_id": chunk_id, "parent_section_id": parent, "title": "Buộc thôi học",
                "article": "Điều 31.", "document_title": "Quy chế công tác sinh viên"}
    if header:
        metadata["context_header"] = header
    return {"chunk_id": chunk_id, "content": content, "metadata": metadata}


def test_cap_keeps_the_best_children_of_each_article_in_rank_order():
    scored = [(1.0, chunk("a1", "A")), (0.9, chunk("a2", "A")), (0.8, chunk("b1", "B")),
              (0.7, chunk("a3", "A")), (0.6, chunk("a4", "A")), (0.5, chunk("b2", "B"))]
    capped = cap_children_per_parent(scored, 2)
    assert [c["chunk_id"] for _, c in capped] == ["a1", "a2", "b1", "b2"]
    assert cap_children_per_parent(scored, 0) == scored  # off by default


def test_bm25_title_fields_are_kept_unless_switched_off():
    retriever = BM25Retriever.__new__(BM25Retriever)
    retriever.title_fields = True
    item = chunk("a1", "A", content="2. Sinh viên bị buộc thôi học")
    assert retriever._index_text(item).count("Buộc thôi học") == 3
    retriever.title_fields = False
    assert retriever._index_text(item) == "2. Sinh viên bị buộc thôi học"


def test_reranker_reads_the_context_line_only_when_the_chunk_has_one():
    plain = chunk("a1", "A", content="2. Sinh viên bị buộc thôi học")
    assert _rerank_text(plain) == "2. Sinh viên bị buộc thôi học"
    structured = chunk("a1", "A", content="2. Sinh viên bị buộc thôi học",
                       header="Quy chế đào tạo › Điều 12. Xử lý kết quả học tập")
    assert _rerank_text(structured) == "Quy chế đào tạo › Điều 12. Xử lý kết quả học tập\n2. Sinh viên bị buộc thôi học"
