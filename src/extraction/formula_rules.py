import re
from typing import Any

from .text_utils import source_page_range


def extract_formula_rules(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract configured calculation rules from structured document sections."""
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
