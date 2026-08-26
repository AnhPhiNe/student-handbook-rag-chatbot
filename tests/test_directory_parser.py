from src.extraction.directory_parser import extract_office_directory


def test_office_directory_drops_repeated_pdf_headers() -> None:
    records = extract_office_directory(
        [
            {
                "page_number": 196,
                "content_type": "office_directory",
                "text": (
                    "2. Phòng Công tác sinh viên\n"
                    "Công tác giáo dục pháp luật\n"
                    "196 SỔ TAY SINH VIÊN KHÓA 51\n"
                    "Tiếp nhận phản ánh của sinh viên"
                ),
            }
        ]
    )

    assert len(records) == 1
    assert "SỔ TAY SINH VIÊN" not in records[0]["raw_text"]
    assert "Công tác giáo dục pháp luật" in records[0]["raw_text"]
    assert "Tiếp nhận phản ánh của sinh viên" in records[0]["raw_text"]
