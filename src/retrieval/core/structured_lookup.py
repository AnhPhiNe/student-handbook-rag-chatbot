import re
from typing import Any, Optional

from src.common.cohort import normalize_cohort


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

    # Cac range trong so tay co the viet "duoi 3.2" hoac "2.5-duoi 3.2".
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


def lookup_conduct_classification(
    query: str, tables: list[dict[str, Any]]
) -> Optional[dict[str, Any]]:
    # Tra bang diem ren luyen: input la mot so diem, output la xep loai.
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


def lookup_academic_classification(
    query: str, tables: list[dict[str, Any]]
) -> Optional[dict[str, Any]]:
    # Tra bang hoc luc theo GPA/thang 4.
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


def lookup_letter_grade(
    query: str, tables: list[dict[str, Any]]
) -> Optional[dict[str, Any]]:
    # Tra diem chu sang thang 4, vi day la bang co ket qua deterministic.
    table = find_table(tables, "letter_to_grade_4")
    if not table:
        return None

    q = query.upper()

    # Ưu tiên match grade dài trước: B+ trước B
    rows = sorted(table["rows"], key=lambda x: len(x["letter_grade"]), reverse=True)

    for row in rows:
        grade = row["letter_grade"].upper()
        if _contains_letter_grade(q, grade):
            return {
                "lookup_type": "letter_to_grade_4",
                "input_value": grade,
                "result": row,
                "source_pages": table.get("source_pages", []),
                "table_name": table.get("table_name"),
            }

    return None


def lookup_grade_10_to_letter(
    query: str, tables: list[dict[str, Any]]
) -> Optional[dict[str, Any]]:
    matching_tables = [
        t
        for t in tables
        if t.get("lookup_group") == "grade_10_to_letter"
        or "grade_10_to_letter" in t.get("table_id", "")
    ]
    if not matching_tables:
        return None

    # Return all matching tables (general and major if split) so LLM can read them
    if len(matching_tables) == 1:
        table_name = matching_tables[0].get("table_name", "Quy đổi thang điểm 10")
    else:
        table_name = "Các bảng: " + " | ".join(
            t.get("table_name", "Bảng quy đổi") for t in matching_tables
        )

    return {
        "lookup_type": "grade_10_to_letter",
        "input_value": query,
        "result": [t for t in matching_tables],
        "source_pages": list(
            set(p for t in matching_tables for p in t.get("source_pages", []))
        ),
        "table_name": table_name,
    }


def _contains_letter_grade(text: str, grade: str) -> bool:
    # Diem chu co dau "+" khong hop voi \b word-boundary, nen can chan
    # ky tu chu/so va dau "+" bang lookaround de B+ khong bi match thanh B.
    pattern = rf"(?<![A-Z0-9]){re.escape(grade)}(?![A-Z0-9+])"
    return re.search(pattern, text) is not None


def should_use_structured_lookup(query: str) -> bool:
    q = query.lower()

    # Cau hoi ve quy trinh (hoc lai, huy mon) thi la regulation.
    # Nhung neu hoi "may diem thi rot/qua" thi cho phep tra bang.
    regulation_phrases = [
        "học lại",
        "hủy môn",
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
        "qua môn",
        "rớt môn",
        "bao nhiêu điểm",
        "mấy điểm",
    ]

    return any(phrase in q for phrase in lookup_phrases)


def structured_lookup(
    query: str, tables: list[dict[str, Any]], cohort: str | None = None
) -> Optional[dict[str, Any]]:
    if not should_use_structured_lookup(query):
        return None

    cohort = normalize_cohort(cohort)
    if cohort:
        tables = [t for t in tables if t.get("cohort") == cohort]

    q = query.lower()

    # Thu tu uu tien giup query co keyword ro di vao dung bang truoc.
    if "rèn luyện" in q:
        return lookup_conduct_classification(query, tables)

    if any(k in q for k in ["gpa", "học lực", "điểm trung bình"]):
        return lookup_academic_classification(query, tables)

    if any(
        k in q
        for k in [
            "điểm a",
            "điểm b",
            "điểm c",
            "điểm d",
            "thang điểm 4",
            "thang 4",
            "quy đổi",
            "điểm chữ",
        ]
    ):
        return lookup_letter_grade(query, tables)

    if any(
        k in q
        for k in ["qua môn", "rớt môn", "bao nhiêu điểm", "mấy điểm", "thang điểm 10"]
    ):
        return lookup_grade_10_to_letter(query, tables)

    # Neu keyword khong ro, thu lan luot cac bang deterministic truoc khi fallback vector.
    return (
        lookup_letter_grade(query, tables)
        or lookup_grade_10_to_letter(query, tables)
        or lookup_conduct_classification(query, tables)
        or lookup_academic_classification(query, tables)
    )
