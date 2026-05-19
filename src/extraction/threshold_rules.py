import re
from typing import Any

from .text_utils import source_page_range


THRESHOLD_PATTERNS = [
    r"từ\s+\d+([,.]\d+)?\s+đến",
    r"dưới\s+\d+([,.]\d+)?",
    r"trở lên",
    r">=\s*\d+([,.]\d+)?",
    r"tối thiểu",
    r"tối đa",
    r"ít nhất",
    r"không vượt quá",
    r"\d+([,.]\d+)?\s*[-–]\s*\d+([,.]\d+)?",
]


def classify_threshold_priority(
    section: dict[str, Any],
    lines: list[str],
) -> str:
    text = (section.get("title", "") + "\n" + "\n".join(lines)).lower()

    high_keywords = [
        "học bổng",
        "cảnh báo",
        "buộc thôi học",
        "tốt nghiệp",
        "điểm rèn luyện",
        "xếp loại",
        "điểm trung bình",
    ]

    medium_keywords = [
        "thời hạn",
        "hồ sơ",
        "nghỉ học",
        "chuyển ngành",
        "ký túc xá",
        "đăng ký học phần",
    ]

    if any(keyword in text for keyword in high_keywords):
        return "high"

    if any(keyword in text for keyword in medium_keywords):
        return "medium"

    return "low"


def extract_threshold_rules(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rules = []

    for section in sections:
        content = section.get("content", "")
        matched_lines = []

        for line in content.splitlines():
            lower = line.lower()

            if any(re.search(pattern, lower) for pattern in THRESHOLD_PATTERNS):
                matched_lines.append(line)

        if not matched_lines:
            continue

        priority = classify_threshold_priority(section, matched_lines)

        rules.append(
            {
                "rule_id": f"threshold_{section['section_id']}",
                "rule_type": "threshold_rule",
                "priority": priority,
                "source_article": section.get("article"),
                "source_title": section.get("title"),
                "source_pages": source_page_range(
                    section["page_start"],
                    section["page_end"],
                ),
                "threshold_lines": matched_lines,
                "review_status": "auto_extracted",
            }
        )

    return rules