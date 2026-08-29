from src.generation.answer_formatter import (
    clean_answer,
    ensure_primary_article_anchors,
    missing_primary_article_anchors,
    normalize_unlabeled_enumeration_references,
)


def test_clean_answer_removes_internal_source_packet_labels() -> None:
    answer = "Căn cứ Điều 35 (S1, S6) và Điều 21 (S2/S8), sinh viên bị xử lý."

    assert clean_answer(answer) == "Căn cứ Điều 35 và Điều 21, sinh viên bị xử lý."


def test_appends_primary_article_anchor_when_llm_omits_it() -> None:
    answer = "Sinh viên được đăng ký học lại học phần chưa đạt."
    citations = [{"source_section": "Điều 24. Học lại", "title": "Quy chế đào tạo"}]

    assert ensure_primary_article_anchors(answer, citations) == (
        "Sinh viên được đăng ký học lại học phần chưa đạt."
    )


def test_does_not_duplicate_article_anchor_already_in_answer() -> None:
    answer = "Theo Điều 24, sinh viên được đăng ký học lại học phần chưa đạt."
    citations = [{"title": "Điều 24. Học lại"}]

    assert ensure_primary_article_anchors(answer, citations) == answer


def test_extracts_article_anchor_from_normalized_parent_section_id() -> None:
    citations = [{"source_section": "K48-K49_QuyCheDaoTao_Chuong1_Dieu3"}]

    assert ensure_primary_article_anchors("Thời gian tối đa là 8 năm.", citations) == (
        "Thời gian tối đa là 8 năm."
    )


def test_uses_only_primary_metadata_not_cross_references_in_content() -> None:
    citations = [
        {
            "title": "Quy định học lại",
            "source_section": "Chương IV",
            "content": "Việc này được dẫn chiếu đến Điều 99.",
        }
    ]

    assert missing_primary_article_anchors("Nội dung trả lời.", citations) == []


def test_replaces_unlabeled_first_three_case_reference() -> None:
    answer = "Đối với các trường hợp tại mục 1, 2, 3: thời gian nghỉ không tính."

    assert normalize_unlabeled_enumeration_references(answer) == (
        "Đối với ba trường hợp đầu nêu trên: thời gian nghỉ không tính."
    )


def test_does_not_duplicate_nêu_trên_when_rewriting_case_reference() -> None:
    answer = "Các trường hợp tại mục 1, 2, 3 nêu trên không tính thời gian nghỉ."

    assert normalize_unlabeled_enumeration_references(answer) == (
        "ba trường hợp đầu nêu trên không tính thời gian nghỉ."
    )
