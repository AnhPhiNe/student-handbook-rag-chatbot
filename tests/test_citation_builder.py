from src.retrieval.core.citation_builder import (
    build_citations_from_vector_results,
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
        },
    }

    result = enrich_citations_with_parent_details(
        [citation],
        {"K48-K49_Dieu3": parent},
    )

    assert result[0]["parent_article"] == "Điều 3"
    assert result[0]["article_label"] == "Điều 3"
    assert result[0]["parent_title"] == "Chương trình đào tạo và thời gian học tập"
    assert result[0]["parent_content"] == parent["content"]
    assert result[0]["table_name"] == citation["title"]
    assert result[0]["detail_kind"] == "table"


def test_vector_citation_exposes_canonical_article_label_from_source_heading():
    citations = build_citations_from_vector_results(
        [
            {
                "chunk_id": "K51_Dieu16",
                "content": "Điều 16. Nghỉ học tạm thời\nNội dung quy định.",
                "metadata": {
                    "title": "Nghỉ học tạm thời",
                    "cohort": "K51",
                },
            }
        ]
    )

    assert citations[0]["article_label"] == "Điều 16"


def test_vector_citation_preserves_validated_cross_cohort_applicability():
    citations = build_citations_from_vector_results(
        [
            {
                "chunk_id": "foreign-language-policy",
                "content": "Điều 4. Chuẩn đầu ra ngoại ngữ",
                "metadata": {
                    "cohort": "K50",
                    "source_cohort": "K50",
                    "applicable_cohorts": ["K48-K49", "K50", "K51"],
                    "applicability_validated": True,
                    "applicability_basis_parent_id": "K50_Dieu1",
                    "chunk_type": "regulation",
                    "title": "Chuẩn đầu ra ngoại ngữ",
                },
            }
        ]
    )

    assert citations[0]["source_cohort"] == "K50"
    assert citations[0]["applicable_cohorts"] == ["K48-K49", "K50", "K51"]
    assert citations[0]["applicability_validated"] is True
    assert citations[0]["applicability_basis_parent_id"] == "K50_Dieu1"


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
