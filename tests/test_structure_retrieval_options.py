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


def test_composer_answers_for_main_campus_regular_students_only():
    import re

    from src.generation.prompt_builder import render_answer_prompt

    prompt, _ = render_answer_prompt("Hỏi thử", {"units": []})
    prompt = " ".join(prompt.split())
    assert "Trợ lý phục vụ sinh viên đại học hệ chính quy tại cơ sở chính" in prompt
    assert "không dùng quy định của sinh viên đại học chính quy để trả lời thay" in prompt
    # The rule names kinds of study, never a question or an article.
    rule = prompt.split("Trợ lý phục vụ", 1)[1].split("- Trả lời đúng", 1)[0]
    assert not re.search(r"Điều \d|rớt|đuổi học", rule)
