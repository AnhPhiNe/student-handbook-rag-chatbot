from src.retrieval.core.citation_builder import sanitize_citation_content


def test_sanitize_citation_content_removes_internal_focus_block_and_joins_pdf_lines():
    raw = """Tài liệu: QUY CHẾ
Tiêu đề: Điều 15. Công nhận tốt nghiệp và cấp bằng tốt nghiệp
Nội dung:
Điều 15. Công nhận tốt nghiệp và cấp bằng tốt nghiệp
6. Sinh viên đào tạo theo hình thức chính quy có 03 đợt xét tốt nghiệp
chính thức, thường được tổ chức vào tháng 5, tháng 8 và tháng
10. Thời gian cụ thể được quy định trong kế hoạch năm học.
THÔNG TIN TRỌNG TÂM ĐÃ TÁCH TỪ NGUỒN:
- Lịch/đợt thực hiện theo quy định: 6. Sinh viên đào tạo theo hình thức chính quy...
"""

    cleaned = sanitize_citation_content(raw)

    assert "THÔNG TIN TRỌNG TÂM" not in cleaned
    assert "tháng 5, tháng 8 và tháng 10." in cleaned
    assert "03 đợt xét tốt nghiệp chính thức" in cleaned


def test_sanitize_citation_content_keeps_numbered_and_lettered_items_readable():
    raw = """Nội dung:
1. Sinh viên được xét và công nhận tốt nghiệp khi có đủ các điều
kiện sau:
a) Tích lũy đủ học phần, số tín chỉ và hoàn thành các nội dung bắt
buộc khác theo yêu cầu của CTĐT;
b) Điểm trung bình tích lũy của toàn khóa học đạt từ trung bình
trở lên;"""

    cleaned = sanitize_citation_content(raw)

    assert "các điều kiện sau:" in cleaned
    assert "a) Tích lũy đủ học phần" in cleaned
    assert "b) Điểm trung bình tích lũy" in cleaned
    assert "\n\na)" in cleaned
    assert "\n\nb)" in cleaned
