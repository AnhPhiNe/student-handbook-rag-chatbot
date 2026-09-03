from src.generation.answer_formatter import (
    clean_answer,
    format_final_response,
    normalize_unlabeled_enumeration_references,
)


def test_clean_answer_removes_internal_source_packet_labels() -> None:
    answer = "Căn cứ Điều 35 (S1, S6) và Điều 21 (S2/S8), sinh viên bị xử lý."

    assert clean_answer(answer) == "Căn cứ Điều 35 và Điều 21, sinh viên bị xử lý."


def test_clean_answer_removes_dangling_markdown_after_private_source_label() -> None:
    assert clean_answer("Nội dung đúng.\n\n*(S1)") == "Nội dung đúng."


def test_final_response_removes_wrapper_before_generated_sources_section() -> None:
    answer = "Nội dung đúng.\n\n*(Nguồn: Điều 16, Điều 30)"

    assert format_final_response(answer) == "Nội dung đúng."


def test_clean_answer_preserves_balanced_markdown_ending() -> None:
    assert clean_answer("Kết quả là **Tốt**") == "Kết quả là **Tốt**"


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
