from __future__ import annotations

from src.chunking.regulation_chunker import build_regulation_chunks
from src.chunking.regulation_table_extractor import extract_regulation_tables


def _section(content: str, section_id: str = "article_3_p1_1") -> dict[str, object]:
    return {
        "section_id": section_id,
        "document_title": "Sổ tay sinh viên HCMUE",
        "part": "Phần 1",
        "chapter": "Chương 1",
        "article": "Điều 3",
        "title": "Chương trình đào tạo và thời gian học tập",
        "content_type": "regulation_text",
        "content": content,
        "page_start": 1,
        "page_end": 2,
        "has_table": True,
        "has_formula": False,
        "has_scoring_rule": False,
        "has_thresholds": False,
    }


def test_extract_study_duration_table_from_flattened_text() -> None:
    content = (
        "6. Thời gian học tập chuẩn toàn khóa và thời gian học tập tối đa của CTĐT "
        "Chương trình đào tạo Thời gian học tập chuẩn Thời gian học tập tối đa "
        "Đào tạo đại học cấp bằng thứ nhất 4 năm học 8 năm học "
        "Đào tạo liên thông từ trình độ cao đẳng lên trình độ đại học 2 năm học 4 năm học "
        "Đào tạo liên thông từ trình độ trung cấp lên trình độ đại học 3 năm học 6 năm học "
        "Đào tạo liên thông trình độ đại học đối với người đã có một bằng đại học 2 năm học 4 năm học"
    )

    tables = extract_regulation_tables(_section(content))

    assert [table["table_kind"] for table in tables] == ["study_duration"]
    rows = tables[0]["rows"]
    assert rows[0]["Chương trình đào tạo"] == "Đào tạo đại học cấp bằng thứ nhất"
    assert rows[0]["Thời gian học tập tối đa"] == "8 năm học"
    assert rows[2]["Thời gian học tập chuẩn"] == "3 năm học"


def test_extract_k50_remaining_grade_scale_marks_d_as_not_passed() -> None:
    content = (
        "Thang điểm 10 Thang điểm chữ "
        "Đối với các học phần giáo dục đại cương "
        "Loại Thang điểm 10 Thang điểm chữ Đạt 8,5 - 10 A 7,8 - 8,4 B+ 7,0 - 7,7 B "
        "6,3 - 6,9 C+ 5,5 - 6,2 C 4,8 - 5,4 D+ 4,0 - 4,7 D Không đạt 3,0 - 3,9 F+ 0,0 - 2,9 F "
        "Đối với các học phần còn lại "
        "Loại Thang điểm 10 Thang điểm chữ Đạt 8,5 - 10 A 7,8 - 8,4 B+ 7,0 - 7,7 B "
        "6,3 - 6,9 C+ 5,5 - 6,2 C Không đạt 4,8 - 5,4 D+ 4,0 - 4,7 D 3,0 - 3,9 F+ 0,0 - 2,9 F "
        "b) Các học phần thuộc loại đạt không phân mức"
    )

    tables = extract_regulation_tables(_section(content, "article_10_p16_16"))
    remaining = next(table for table in tables if table["table_id"].endswith("grade_scale_remaining"))

    by_letter = {row["Thang điểm chữ"]: row for row in remaining["rows"]}
    assert by_letter["D+"]["Loại"] == "Không đạt"
    assert by_letter["D"]["Loại"] == "Không đạt"
    assert by_letter["C"]["Loại"] == "Đạt"


def test_regulation_chunker_adds_table_chunks_and_parent_tables() -> None:
    content = (
        "Thang điểm chữ Thang điểm 4 "
        "A 4,0 B+ 3,5 B 3,0 C+ 2,5 C 2,0 D+ 1,5 D 1,0 F+ 0,5 F 0,0 "
        "Xếp loại học lực Xuất sắc Giỏi Khá Trung bình"
    )

    chunks, parents = build_regulation_chunks([_section(content, "article_11_p21_21")])

    table_chunks = [chunk for chunk in chunks if chunk["chunk_type"] == "regulation_table"]
    assert table_chunks
    assert any(chunk["metadata"]["table_kind"] == "letter_to_grade4" for chunk in table_chunks)
    assert parents[0]["tables"]
    assert "BẢNG/DANH SÁCH CHUẨN HÓA TỪ NGUỒN" in parents[0]["content"]
    assert "| Thang điểm chữ | Thang điểm 4 |" in parents[0]["content"]


def test_regulation_chunker_adds_period_schedule_highlight_chunks() -> None:
    content = (
        "Điều 15. Công nhận tốt nghiệp và cấp bằng tốt nghiệp. "
        "5. Sinh viên hết thời gian học tập theo hình thức chính quy được chuyển sang học tập "
        "theo hình thức vừa làm vừa học tại Trường nếu còn trong thời gian học tập. "
        "6. Sinh viên đào tạo theo hình thức chính quy có 03 đợt xét tốt nghiệp chính thức, "
        "thường được tổ chức vào tháng 5, tháng 8 và tháng 11."
    )

    chunks, parents = build_regulation_chunks([_section(content, "article_15_p25_25")])

    highlight_chunks = [
        chunk for chunk in chunks if chunk["chunk_type"] == "regulation_highlight"
    ]
    assert highlight_chunks
    assert highlight_chunks[0]["metadata"]["highlight_kind"] == "period_schedule"
    assert "03 đợt xét tốt nghiệp" in highlight_chunks[0]["content"]
    assert "tháng 5, tháng 8 và tháng 11" in highlight_chunks[0]["content"]
    assert parents[0]["highlights"]
    assert "THÔNG TIN TRỌNG TÂM ĐÃ TÁCH TỪ NGUỒN" in parents[0]["content"]
