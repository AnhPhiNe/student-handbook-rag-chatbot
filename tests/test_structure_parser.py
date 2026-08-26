from __future__ import annotations

from src.preprocessing.structure_parser import reassociate_trailing_amendment_footnotes


def _article(section_id: str, content: str) -> dict:
    return {
        "section_id": section_id,
        "section_level": "article",
        "content_type": "regulation_text",
        "content": content,
    }


def test_footnote_after_next_heading_moves_to_article_with_marker() -> None:
    sections = [
        _article("Dieu11", "Điều 11. Xếp trình độ\nd)6 Sinh viên năm thứ tư"),
        _article(
            "Dieu12",
            "Điều 12. Cảnh báo học tập\n"
            "1. Các điều kiện cảnh báo.\n"
            "6 Điểm này đã được sửa đổi, bổ sung. Cụ thể như sau: "
            "“d) Sinh viên năm thứ tư: M1 + M2 + M3 ≤ N.”\n"
            "2. Buộc thôi học.",
        ),
    ]

    result = reassociate_trailing_amendment_footnotes(sections)

    assert "Cụ thể như sau" in result[0]["content"]
    assert "Cụ thể như sau" not in result[1]["content"]
    assert "2. Buộc thôi học." in result[1]["content"]


def test_footnote_stays_when_marker_is_in_current_article() -> None:
    sections = [
        _article("Dieu9", "Điều 9. Nội dung trước"),
        _article(
            "Dieu10",
            "Điều 10. Đánh giá\nd)2 Học phần tốt nghiệp\n"
            "2 Điểm này đã được sửa đổi, bổ sung. Cụ thể như sau: "
            "“d) Đánh giá học phần tốt nghiệp.”",
        ),
    ]

    result = reassociate_trailing_amendment_footnotes(sections)

    assert "Cụ thể như sau" not in result[0]["content"]
    assert "Cụ thể như sau" in result[1]["content"]
