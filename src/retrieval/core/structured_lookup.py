import re
import unicodedata
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


def normalize_text(text: Any) -> str:
    value = str(text or "").lower()
    value = value.replace("đ", "d").replace("Đ", "D")
    value = unicodedata.normalize("NFD", value)
    value = "".join(char for char in value if unicodedata.category(char) != "Mn")
    value = re.sub(r"[^a-z0-9+]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _metadata_from_tables(tables: list[dict[str, Any]]) -> dict[str, Any]:
    cohorts = {table.get("cohort") for table in tables if table.get("cohort")}
    document_ids = {
        table.get("document_id") for table in tables if table.get("document_id")
    }
    source_sections = {
        table.get("source_section") for table in tables if table.get("source_section")
    }
    return {
        "cohort": next(iter(cohorts)) if len(cohorts) == 1 else None,
        "document_id": next(iter(document_ids)) if len(document_ids) == 1 else None,
        "source_section": next(iter(source_sections))
        if len(source_sections) == 1
        else "scoring_table",
        "content_type": "structured_lookup",
    }


def _with_metadata(
    result: dict[str, Any],
    tables: list[dict[str, Any]],
) -> dict[str, Any]:
    return result | _metadata_from_tables(tables)


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
            } | _metadata_from_tables([table])

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
            } | _metadata_from_tables([table])

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
            } | _metadata_from_tables([table])

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

    requested_grade = _requested_letter_grade(query, tables)
    requested_grade_rows = _matching_grade_rows(requested_grade, matching_tables)
    letter_grade_4 = lookup_letter_grade(query, tables)

    return _with_metadata({
        "lookup_type": "grade_10_to_letter",
        "input_value": query,
        "result": [t for t in matching_tables],
        "source_pages": list(
            set(p for t in matching_tables for p in t.get("source_pages", []))
        ),
        "table_name": table_name,
        "requested_letter_grade": requested_grade,
        "requested_grade_rows": requested_grade_rows,
        "letter_grade_4": letter_grade_4.get("result") if letter_grade_4 else None,
    }, matching_tables)


def _requested_letter_grade(query: str, tables: list[dict[str, Any]]) -> str | None:
    table = find_table(tables, "letter_to_grade_4")
    if not table:
        return None

    q = query.upper()
    rows = sorted(table["rows"], key=lambda x: len(x["letter_grade"]), reverse=True)
    for row in rows:
        grade = row["letter_grade"].upper()
        if _contains_letter_grade(q, grade):
            return grade
    return None


def _matching_grade_rows(
    grade: str | None,
    tables: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not grade:
        return []

    matches = []
    for table in tables:
        for row in table.get("rows") or []:
            if str(row.get("letter_grade") or "").upper() == grade:
                matches.append(
                    {
                        "table_id": table.get("table_id"),
                        "table_name": table.get("table_name"),
                        "applicability": table.get("applicability"),
                        "pass_threshold": table.get("pass_threshold"),
                        "row": row,
                    }
                )
    return matches


def _contains_letter_grade(text: str, grade: str) -> bool:
    # Diem chu co dau "+" khong hop voi \b word-boundary, nen can chan
    # ky tu chu/so va dau "+" bang lookaround de B+ khong bi match thanh B.
    normalized_text = normalize_text(text).upper()
    normalized_grade = normalize_text(grade).upper()
    pattern = rf"(?<![A-Z0-9]){re.escape(normalized_grade)}(?![A-Z0-9+])"
    return re.search(pattern, normalized_text) is not None


def should_use_structured_lookup(query: str) -> bool:
    q = query.lower()
    ascii_q = normalize_text(query)
    ascii_lookup_phrases = [
        "ren luyen",
        "hoc luc",
        "gpa",
        "diem trung binh",
        "quy doi",
        "thang diem 4",
        "thang 4",
        "diem chu",
        "xep loai",
        "loai gi",
        "qua mon",
        "qua hoc phan",
        "rot mon",
        "diem d",
        "diem d+",
        "d+",
        "diem f",
        "bi f",
        "he thong tinh",
        "tinh nhu the nao",
        "tinh the nao",
        "bao nhieu diem",
        "may diem",
        "dat",
        "khong dat",
    ]
    if any(phrase in ascii_q for phrase in ascii_lookup_phrases):
        return True

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
    ascii_q = normalize_text(query)

    if "ren luyen" in ascii_q:
        return lookup_conduct_classification(query, tables)

    if any(k in ascii_q for k in ["gpa", "hoc luc", "diem trung binh"]):
        return lookup_academic_classification(query, tables)

    asks_pass_status = any(
        k in ascii_q
        for k in [
            "qua mon",
            "qua hoc phan",
            "rot mon",
            "dat",
            "khong dat",
            "may diem",
            "bao nhieu diem",
        ]
    )
    asks_scale_4 = any(k in ascii_q for k in ["he 4", "thang 4"])

    if asks_pass_status:
        return lookup_grade_10_to_letter(query, tables)

    if asks_scale_4:
        return lookup_letter_grade(query, tables)

    if any(k in ascii_q for k in ["he thong tinh", "tinh nhu the nao", "tinh the nao"]):
        return lookup_letter_grade(query, tables)

    if re.search(r"\d+(?:[,.]\d+)?", query) and any(
        k in ascii_q for k in ["diem chu", "tuong ung", "quy doi"]
    ):
        return lookup_grade_10_to_letter(query, tables)

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
