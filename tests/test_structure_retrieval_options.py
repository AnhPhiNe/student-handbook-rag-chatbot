"""The reranker reads a structure chunk's context line (offline)."""
from src.retrieval.core.reranker import _rerank_text


def chunk(chunk_id, parent, content="x", header=None):
    metadata = {"chunk_id": chunk_id, "parent_section_id": parent, "title": "Buộc thôi học",
                "article": "Điều 31.", "document_title": "Quy chế công tác sinh viên"}
    if header:
        metadata["context_header"] = header
    return {"chunk_id": chunk_id, "content": content, "metadata": metadata}


def test_reranker_reads_the_context_line_only_when_the_chunk_has_one():
    plain = chunk("a1", "A", content="2. Sinh viên bị buộc thôi học")
    assert _rerank_text(plain) == "2. Sinh viên bị buộc thôi học"
    structured = chunk("a1", "A", content="2. Sinh viên bị buộc thôi học",
                       header="Quy chế đào tạo › Điều 12. Xử lý kết quả học tập")
    assert _rerank_text(structured) == "Quy chế đào tạo › Điều 12. Xử lý kết quả học tập\n2. Sinh viên bị buộc thôi học"


def test_composer_defaults_to_regular_students_and_names_whom_a_rule_covers():
    import re

    from src.generation.prompt_builder import render_answer_prompt

    prompt, _ = render_answer_prompt("Hỏi thử", {"units": []})
    prompt = " ".join(prompt.split())
    rule = ("Câu hỏi không nêu đối tượng được trả lời theo quy định dành cho sinh viên đại học hệ chính quy; "
            "khi nguồn có quy định riêng cho từng hình thức hoặc trình độ đào tạo, nói rõ quy định áp dụng cho ai, "
            "không trình bày quy định của đối tượng này như thể áp dụng cho đối tượng khác.")
    assert rule in prompt
    # No refusal and no list of "other groups": a question is answered from what the sources say.
    assert "ngoài phạm vi" not in prompt.split("1. PHẠM VI TRẢ LỜI", 1)[1].split("2.", 1)[0]
    assert not re.search(r"Điều \d|rớt|đuổi học", rule)
