from src.common.legal_reference import article_label_from_heading, normalize_article_label


def test_normalize_article_label_accepts_metadata_and_heading() -> None:
    assert normalize_article_label("16") == "Điều 16"
    assert normalize_article_label("Điều 9. Tổ chức đăng ký học tập") == "Điều 9"
    assert normalize_article_label("K51_QuyCheDaoTao_Dieu3") == "Điều 3"


def test_normalize_article_label_returns_none_without_source_identity() -> None:
    assert normalize_article_label("Quy định chung") is None
    assert article_label_from_heading("Nội dung dẫn chiếu Điều 99.") is None
    assert article_label_from_heading("Điều 16. Nghỉ học tạm thời") == "Điều 16"
