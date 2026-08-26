from src.ingestion.pdf_loader import clean_text


def test_clean_text_removes_repeated_headers_for_all_handbooks() -> None:
    raw = "\n".join(
        [
            "Sổ tay Sinh viên năm học 2022 – 2023",
            "Nội dung K48-K49",
            "SỔ TAY SINH VIÊN KHÓA 50 189",
            "Nội dung K50",
            "174 SỔ TAY SINH VIÊN KHÓA 50",
            "SỔ TAY SINH VIÊN KHÓA 51",
            "Nội dung K51",
            "190",
        ]
    )

    assert clean_text(raw) == "Nội dung K48-K49\nNội dung K50\nNội dung K51"


def test_clean_text_preserves_non_header_sentence() -> None:
    sentence = "Nguồn tham khảo là Sổ tay Sinh viên khóa 51 của Trường."
    assert clean_text(sentence) == sentence
