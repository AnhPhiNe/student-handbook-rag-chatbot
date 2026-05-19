from typing import Any

from .text_utils import source_page_range


def calculate_gpa(courses: list[dict[str, float]]) -> float:
    total_credits = sum(course["credits"] for course in courses)

    if total_credits <= 0:
        raise ValueError("Total credits must be greater than 0")

    total_weighted_score = sum(
        course["score_4"] * course["credits"]
        for course in courses
    )

    return round(total_weighted_score / total_credits, 2)


def calculate_scholarship_score(
    academic_score_4: float,
    conduct_score_100: float,
) -> float:
    if not 0 <= academic_score_4 <= 4:
        raise ValueError("academic_score_4 must be between 0 and 4")

    if not 0 <= conduct_score_100 <= 100:
        raise ValueError("conduct_score_100 must be between 0 and 100")

    score = (academic_score_4 * 80 + (conduct_score_100 / 25) * 20) / 100

    return round(score, 3)


def extract_formula_rules(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formulas = []

    for section in sections:
        article = section.get("article")
        content = section.get("content", "")
        lower_content = content.lower()
        pages = source_page_range(section["page_start"], section["page_end"])

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
                    "calculator_function": "calculate_gpa",
                    "source_article": article,
                    "source_title": section.get("title"),
                    "source_pages": pages,
                    "review_status": "needs_human_verified",
                    "raw_excerpt": content[:1500],
                }
            )

        if article == "Điều 28." and "điểm học bổng" in lower_content:
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
                    "calculator_function": "calculate_scholarship_score",
                    "source_article": article,
                    "source_title": section.get("title"),
                    "source_pages": pages,
                    "review_status": "needs_human_verified",
                    "raw_excerpt": content[:1800],
                }
            )

    return formulas