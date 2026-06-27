import re
from typing import Any, Optional


def calculate_gpa(courses: list[dict[str, float]]) -> float:
    total_credits = sum(course["credits"] for course in courses)
    if total_credits <= 0:
        raise ValueError("Total credits must be greater than 0")

    total_weighted_score = sum(
        course["score_4"] * course["credits"] for course in courses
    )
    return round(total_weighted_score / total_credits, 2)


def calculate_scholarship_score(
    academic_score_4: float, conduct_score_100: float
) -> float:
    if not 0 <= academic_score_4 <= 4:
        raise ValueError("academic_score_4 must be between 0 and 4")

    if not 0 <= conduct_score_100 <= 100:
        raise ValueError("conduct_score_100 must be between 0 and 100")

    score = (academic_score_4 * 80 + (conduct_score_100 / 25) * 20) / 100
    return round(score, 3)


def extract_numbers(query: str) -> list[float]:
    nums = re.findall(r"\d+(?:[,.]\d+)?", query)
    return [float(n.replace(",", ".")) for n in nums]


def try_calculation(query: str) -> Optional[dict[str, Any]]:
    q = query.lower()
    numbers = extract_numbers(query)

    if "điểm học bổng" in q and len(numbers) >= 2:
        academic_score = numbers[0]
        conduct_score = numbers[1]

        result = calculate_scholarship_score(
            academic_score_4=academic_score,
            conduct_score_100=conduct_score,
        )

        return {
            "tool_name": "calculate_scholarship_score",
            "inputs": {
                "academic_score_4": academic_score,
                "conduct_score_100": conduct_score,
            },
            "result": result,
            "note": "Công thức: (Điểm học tập × 80 + Điểm rèn luyện / 25 × 20) / 100",
        }

    return None
