from src.retrieval.core.citation_builder import (
    build_citation_from_formula,
    build_citation_from_lookup,
    enrich_citations_with_parent_details,
    sanitize_citation_content,
)


def test_enriches_structured_table_citation_with_parent_article_details():
    citation = {
        "chunk_type": "structured_lookup",
        "title": "Thời gian học tập chuẩn và tối đa",
        "source_parent_id": "K48-K49_Dieu3",
        "content": "Đào tạo đại học cấp bằng thứ nhất",
    }
    parent = {
        "_id": "K48-K49_Dieu3",
        "content": "Nội dung Điều 3 đầy đủ, bao gồm bảng thời gian học tập.",
        "metadata": {
            "article": "Điều 3.",
            "title": "Chương trình đào tạo và thời gian học tập",
            "source_pages": [12, 13],
            "document_id": "so_tay_sinh_vien_khoa_48_49",
            "cohort": "K48-K49",
        },
    }

    result = enrich_citations_with_parent_details(
        [citation],
        {"K48-K49_Dieu3": parent},
    )

    assert result[0]["parent_article"] == "Điều 3."
    assert result[0]["parent_title"] == "Chương trình đào tạo và thời gian học tập"
    assert result[0]["parent_content"] == parent["content"]
    assert result[0]["table_name"] == citation["title"]
    assert result[0]["detail_kind"] == "table"
    assert result[0]["source_pages"] == [12, 13]
    assert result[0]["document_id"] == "so_tay_sinh_vien_khoa_48_49"
    assert result[0]["cohort"] == "K48-K49"


def test_builds_source_backed_structured_table_citation():
    citations = build_citation_from_lookup(
        {
            "lookup_type": "academic_classification",
            "result": {"label": "Giỏi", "range": "3.20-3.59"},
            "table_name": "Xếp loại học lực",
            "source_pages": [42],
            "source_parent_id": "K51_Dieu18",
            "document_id": "so_tay_sinh_vien_khoa_51",
            "cohort": "K51",
        }
    )

    assert len(citations) == 1
    assert citations[0]["chunk_type"] == "structured_lookup"
    assert citations[0]["table_name"] == "Xếp loại học lực"
    assert citations[0]["source_pages"] == [42]
    assert citations[0]["parent_section_id"] == "K51_Dieu18"
    assert citations[0]["document_id"] == "so_tay_sinh_vien_khoa_51"
    assert citations[0]["cohort"] == "K51"
    assert "| Xếp loại | range |" in citations[0]["content"]


def test_builds_program_citation_for_selected_cohort():
    citations = build_citation_from_lookup(
        {
            "lookup_type": "program_directory",
            "result": [
                {
                    "program_name": "Công nghệ Thông tin",
                    "faculty_name": "Khoa Công nghệ Thông tin",
                    "cohort": "K51",
                    "document_id": "so_tay_sinh_vien_khoa_51",
                }
            ],
            "table_name": "Danh sách ngành đào tạo",
            "source_section": "program_directory",
            "document_id": "so_tay_sinh_vien_khoa_51",
            "cohort": "K51",
        }
    )

    assert len(citations) == 1
    assert citations[0]["chunk_type"] == "program_directory"
    assert citations[0]["source_section"] == "program_directory"
    assert citations[0]["document_id"] == "so_tay_sinh_vien_khoa_51"
    assert citations[0]["cohort"] == "K51"
    assert "Công nghệ Thông tin" in citations[0]["content"]


def test_builds_formula_citation_from_regulation_source():
    citations = build_citation_from_formula(
        {
            "rule_name": "Điểm học phần",
            "formula_text": "DHP = 0.4 * QT + 0.6 * CK",
            "source_article": "Điều 16",
            "source_pages": [38],
            "source_section": "K51_Dieu16",
            "document_id": "so_tay_sinh_vien_khoa_51",
            "cohort": "K51",
        }
    )

    assert len(citations) == 1
    assert citations[0]["chunk_type"] == "formula"
    assert citations[0]["source_section"] == "K51_Dieu16"
    assert citations[0]["parent_section_id"] == "K51_Dieu16"
    assert citations[0]["source_pages"] == [38]
    assert "DHP = 0.4 * QT + 0.6 * CK" in citations[0]["content"]


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
