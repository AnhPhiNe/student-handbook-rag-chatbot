import re
from typing import Any, Optional


def extract_number(query: str) -> Optional[float]:
    match = re.search(r"\d+(?:[,.]\d+)?", query)
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


def extract_numbers_from_text(text: str) -> list[float]:
    matches = re.finditer(r"\d+(?:[,.]\d+)?", text)
    return [float(match.group(0).replace(",", ".")) for match in matches]


def find_table(tables: list[dict[str, Any]], table_id: str) -> Optional[dict[str, Any]]:
    for table in tables:
        if table.get("table_id") == table_id:
            return table
    return None


def in_range(value: float, range_text: str) -> bool:
    text = range_text.lower().replace(",", ".").strip()
    nums = extract_numbers_from_text(text)

    if "dưới" in text:
        if len(nums) == 1:
            return value < nums[0]
        if len(nums) >= 2:
            return nums[0] <= value < nums[1]

    if "từ" in text and "đến" in text and len(nums) >= 2:
        return nums[0] <= value <= nums[1]

    if "-" in text or "–" in text:
        if len(nums) >= 2:
            return nums[0] <= value <= nums[1]

    return False


def lookup_conduct_classification(query: str, tables: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    value = extract_number(query)
    if value is None:
        return None

    table = find_table(tables, "conduct_classification")
    if not table:
        return None

    for row in table["rows"]:
        if in_range(value, row["range"]):
            return {
                "lookup_type": "conduct_classification",
                "input_value": value,
                "result": row,
                "source_pages": table.get("source_pages", []),
                "table_name": table.get("table_name"),
            }

    return None


def lookup_academic_classification(query: str, tables: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    value = extract_number(query)
    if value is None:
        return None

    table = find_table(tables, "academic_classification")
    if not table:
        return None

    for row in table["rows"]:
        if in_range(value, row["range"]):
            return {
                "lookup_type": "academic_classification",
                "input_value": value,
                "result": row,
                "source_pages": table.get("source_pages", []),
                "table_name": table.get("table_name"),
            }

    return None


def lookup_letter_grade(query: str, tables: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    table = find_table(tables, "letter_to_grade_4")
    if not table:
        return None

    q = query.upper()

    # Ưu tiên match grade dài trước: B+ trước B
    rows = sorted(table["rows"], key=lambda x: len(x["letter_grade"]), reverse=True)

    for row in rows:
        grade = row["letter_grade"].upper()
        if re.search(rf"(?<![A-Z0-9]){re.escape(grade)}(?![A-Z0-9])", q):
            return {
                "lookup_type": "letter_to_grade_4",
                "input_value": grade,
                "result": row,
                "source_pages": table.get("source_pages", []),
                "table_name": table.get("table_name"),
            }

    return None


def should_use_structured_lookup(query: str) -> bool:
    q = query.lower()

    # Những câu này nên đi regulation, không lookup bảng
    regulation_phrases = [
        "qua môn",
        "đạt học phần",
        "rớt môn",
        "học lại",
        "bao nhiêu điểm thì qua",
    ]
    if any(phrase in q for phrase in regulation_phrases):
        return False

    lookup_phrases = [
        "rèn luyện",
        "học lực",
        "gpa",
        "điểm trung bình",
        "quy đổi",
        "thang điểm 4",
        "thang 4",
        "điểm chữ",
        "xếp loại",
        "loại gì",
    ]

    return any(phrase in q for phrase in lookup_phrases)


def structured_lookup(query: str, tables: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not should_use_structured_lookup(query):
        return None

    q = query.lower()

    if "rèn luyện" in q:
        return lookup_conduct_classification(query, tables)

    if any(k in q for k in ["gpa", "học lực", "điểm trung bình"]):
        return lookup_academic_classification(query, tables)

    if any(k in q for k in ["điểm a", "điểm b", "điểm c", "điểm d", "thang điểm 4", "thang 4", "quy đổi", "điểm chữ"]):
        return lookup_letter_grade(query, tables)

    return (
        lookup_letter_grade(query, tables)
        or lookup_conduct_classification(query, tables)
        or lookup_academic_classification(query, tables)
    )