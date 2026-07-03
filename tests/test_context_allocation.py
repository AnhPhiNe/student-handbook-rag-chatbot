from __future__ import annotations

from src.generation.context_allocation import (
    ContextAllocationConfig,
    allocate_context_budget,
    build_context_for_prompt,
    prepare_content_for_prompt,
    truncate_text,
)


def _item(
    chunk_id: str,
    content: str,
    score: float | None = None,
) -> dict[str, object]:
    item: dict[str, object] = {
        "chunk_id": chunk_id,
        "content": content,
        "metadata": {
            "title": f"Section {chunk_id}",
            "chunk_type": "regulation",
            "source_pages": [1, 2],
        },
    }
    if score is not None:
        item["score"] = score
    return item


def test_score_weighted_budget_stays_within_total_budget() -> None:
    items = [
        _item("a", "A" * 4000, 0.9),
        _item("b", "B" * 4000, 0.6),
        _item("c", "C" * 4000, 0.3),
        _item("d", "D" * 4000, 0.2),
        _item("e", "E" * 4000, 0.1),
    ]

    budgets = allocate_context_budget(
        items,
        total_budget=6000,
        min_chars_per_doc=400,
        max_chars_per_doc=1800,
        strategy="score_weighted",
    )

    assert sum(budgets) <= 6000
    assert max(budgets) <= 1800
    assert min(budgets) >= 400
    assert budgets[0] > budgets[-1]


def test_equal_score_budget_does_not_overflow_worst_case() -> None:
    items = [_item(str(index), "X" * 4000, 0.5) for index in range(5)]

    budgets = allocate_context_budget(
        items,
        total_budget=6000,
        min_chars_per_doc=400,
        max_chars_per_doc=1800,
        strategy="score_weighted",
    )

    assert budgets == [1200, 1200, 1200, 1200, 1200]
    assert sum(budgets) == 6000


def test_budget_smaller_than_minimum_is_split_without_overflow() -> None:
    items = [_item(str(index), "X" * 4000, 0.5) for index in range(5)]

    budgets = allocate_context_budget(
        items,
        total_budget=1000,
        min_chars_per_doc=400,
        max_chars_per_doc=1800,
        strategy="score_weighted",
    )

    assert budgets == [200, 200, 200, 200, 200]
    assert sum(budgets) == 1000


def test_high_score_document_is_capped() -> None:
    items = [
        _item("a", "A" * 4000, 0.99),
        _item("b", "B" * 4000, 0.01),
        _item("c", "C" * 4000, 0.01),
        _item("d", "D" * 4000, 0.01),
        _item("e", "E" * 4000, 0.01),
    ]

    budgets = allocate_context_budget(
        items,
        total_budget=6000,
        min_chars_per_doc=400,
        max_chars_per_doc=1800,
        strategy="score_weighted",
    )

    assert budgets[0] == 1800
    assert sum(budgets) <= 6000


def test_truncate_text_prefers_sentence_boundary() -> None:
    text = "First sentence is complete. Second sentence should not be partial."

    truncated = truncate_text(text, 35, sentence_boundary=True)

    assert truncated == "First sentence is complete."


def test_build_context_for_prompt_respects_total_budget() -> None:
    retrieval_result = {
        "retrieved_items": [
            _item("high", "high " * 1200, 0.9),
            _item("low", "low " * 1200, 0.1),
        ],
    }

    context = build_context_for_prompt(
        retrieval_result,
        max_context_chars=1000,
        allocation_config=ContextAllocationConfig(
            strategy="score_weighted",
            min_chars_per_doc=100,
            max_chars_per_doc=700,
            sentence_boundary=True,
        ),
    )

    assert len(context) <= 1000
    assert "[Ngu" in context
    assert "high" in context


def test_build_context_for_prompt_keeps_query_snippet_near_chunk_end() -> None:
    long_intro = "Thông tin chung không liên quan. " * 80
    content = (
        long_intro
        + "6. Sinh viên đào tạo theo hình thức chính quy có 03 đợt xét tốt nghiệp "
        "chính thức, thường được tổ chức vào tháng 5, tháng 8 và tháng 11."
    )
    retrieval_result = {
        "query": "trường có những đợt xét tốt nghiệp nào",
        "retrieved_items": [_item("graduation", content, 0.9)],
    }

    context = build_context_for_prompt(
        retrieval_result,
        query="trường có những đợt xét tốt nghiệp nào",
        max_context_chars=900,
        allocation_config=ContextAllocationConfig(
            strategy="score_weighted",
            min_chars_per_doc=400,
            max_chars_per_doc=700,
            sentence_boundary=True,
        ),
    )

    assert "03 đợt xét tốt nghiệp" in context
    assert "tháng 5, tháng 8 và tháng 11" in context
    assert "ĐOẠN LIÊN QUAN" in context
    assert len(context) <= 900


def test_snippet_fallback_keeps_precise_match_when_sentence_boundary_drops_it() -> None:
    long_preceding_sentence = (
        "Sinh viên hết thời gian học tập theo hình thức chính quy được chuyển sang học tập "
        "theo hình thức vừa làm vừa học tại Trường nếu còn trong thời gian học tập theo quy "
        "định đối với hình thức đào tạo chuyển đến. "
    )
    content = (
        "Điều kiện công nhận tốt nghiệp được quy định chung trong điều này. " * 12
        + long_preceding_sentence
        + "6. Sinh viên đào tạo theo hình thức chính quy có 03 đợt xét tốt nghiệp "
        "chính thức, thường được tổ chức vào tháng 5, tháng 8 và tháng 11."
    )
    retrieval_result = {
        "query": "trường có những đợt xét tốt nghiệp nào",
        "retrieved_items": [_item("graduation", content, 0.9)],
    }

    context = build_context_for_prompt(
        retrieval_result,
        query="trường có những đợt xét tốt nghiệp nào",
        max_context_chars=900,
        allocation_config=ContextAllocationConfig(
            strategy="score_weighted",
            min_chars_per_doc=400,
            max_chars_per_doc=700,
            sentence_boundary=True,
        ),
    )

    assert "03 đợt xét tốt nghiệp" in context
    assert "tháng 5, tháng 8 và tháng 11" in context


def test_prepare_content_for_prompt_normalizes_flattened_study_duration_table() -> None:
    content = (
        "6. Thời gian học tập chuẩn toàn khóa và thời gian học tập tối đa của CTĐT "
        "a) Thời gian học tập chuẩn toàn khóa và thời gian học tập tối đa đối với "
        "hình thức đào tạo chính quy được quy định như sau: "
        "Chương trình đào tạo Thời gian học tập chuẩn Thời gian học tập tối đa "
        "Đào tạo đại học cấp bằng thứ nhất 4 năm học 8 năm học "
        "Đào tạo liên thông từ trình độ cao đẳng lên trình độ đại học 2 năm học 4 năm học "
        "Đào tạo liên thông từ trình độ trung cấp lên trình độ đại học 3 năm học 6 năm học"
    )

    prepared = prepare_content_for_prompt(
        content,
        item={"metadata": {"chunk_type": "regulation", "has_table": True}},
        query="thời gian học tập tối đa là bao nhiêu năm",
        budget=1200,
    )

    assert "BẢNG/DANH SÁCH ĐÃ CHUẨN HÓA" in prepared
    assert "Đào tạo đại học cấp bằng thứ nhất: chuẩn 4 năm học, tối đa 8 năm học" in prepared
    assert "Đào tạo liên thông từ trình độ cao đẳng lên trình độ đại học" in prepared
