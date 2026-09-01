import re
from typing import Any

from .text_utils import source_page_range


def extract_formula_rules(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Trích xuất các quy tắc công thức tính toán từ các phần của tài liệu.

    Hàm này duyệt qua một danh sách các phần (sections) của một tài liệu
    (ví dụ: các điều khoản trong một quy chế). Nó tìm kiếm các từ khóa và
    số điều cụ thể để xác định và trích xuất thông tin về các công thức
    tính điểm trung bình chung (GPA) và điểm học bổng.

    Args:
        sections: Một danh sách các dictionary, mỗi dictionary đại diện cho
            một phần của tài liệu. Mỗi phần cần có các khóa như "article"
            (số điều), "content" (nội dung văn bản), "page_start" (trang bắt đầu),
            "page_end" (trang kết thúc) và "title" (tiêu đề của phần).

    Returns:
        Một danh sách các dictionary. Mỗi dictionary mô tả một công thức
        được tìm thấy, bao gồm:
        - "rule_id": Mã định danh duy nhất của quy tắc.
        - "rule_name": Tên của quy tắc (ví dụ: "Công thức tính điểm trung bình chung").
        - "rule_type": Loại quy tắc (luôn là "formula" trong trường hợp này).
        - "calculation_type": Loại tính toán (ví dụ: "weighted_average").
        - "formula_text": Văn bản mô tả công thức.
        - "variables": Một dictionary giải thích các biến trong công thức.
        - "source_article": Điều khoản nguồn.
        - "source_title": Tiêu đề của phần nguồn.
        - "source_pages": Phạm vi trang nguồn.
        - "review_status": Trạng thái xem xét (ví dụ: "needs_human_verified").
        - "raw_excerpt": Đoạn trích nội dung gốc từ tài liệu.
    """
    formulas = []

    for section in sections:
        article = section.get("article")
        content = section.get("content", "")
        lower_content = content.lower()
        pages = source_page_range(section["page_start"], section["page_end"])

        source_parent_id = section.get("section_id")

        if article == "Điều 11." and "điểm trung bình" in lower_content:
            formulas.append(
                {
                    "rule_id": "gpa_weighted_average",
                    "rule_name": "Công thức tính điểm trung bình chung",
                    "rule_type": "formula",
                    "calculation_type": "weighted_average",
                    "formula_text": "A = Σ(ai × ni) / Σ(ni)",
                    "variables": {
                        "A": "Điểm trung bình chung học kỳ, năm học hoặc điểm trung bình chung tích lũy",
                        "ai": "Điểm của học phần thứ i",
                        "ni": "Số tín chỉ của học phần thứ i",
                    },
                    "source_article": article,
                    "source_title": section.get("title"),
                    "source_pages": pages,
                    "source_parent_id": source_parent_id,
                    "review_status": "needs_human_verified",
                    "raw_excerpt": content[:1500],
                }
            )

        scholarship_formula_present = (
            "điểm học bổng" in lower_content
            and re.search(r"điểm\s+học\s+bổng\s*=", lower_content) is not None
            and all(token in lower_content for token in ("80", "25", "20", "100"))
        )
        if scholarship_formula_present:
            formulas.append(
                {
                    "rule_id": "scholarship_score",
                    "rule_name": "Công thức tính điểm học bổng",
                    "rule_type": "formula",
                    "calculation_type": "weighted_score",
                    "formula_text": "Điểm học bổng = (Điểm học tập × 80 + Điểm rèn luyện / 25 × 20) / 100",
                    "variables": {
                        "diem_hoc_tap": "Điểm học tập theo thang điểm 4",
                        "diem_ren_luyen": "Điểm rèn luyện theo thang điểm 100",
                    },
                    "source_article": article,
                    "source_title": section.get("title"),
                    "source_pages": pages,
                    "source_parent_id": source_parent_id,
                    "review_status": "needs_human_verified",
                    "raw_excerpt": content[:1800],
                }
            )

    return formulas
