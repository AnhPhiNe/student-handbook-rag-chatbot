from __future__ import annotations

import re
import unicodedata
from typing import Any


GRADE_RANGES = [
    ("8,5 - 10", "A"),
    ("7,8 - 8,4", "B+"),
    ("7,0 - 7,7", "B"),
    ("6,3 - 6,9", "C+"),
    ("5,5 - 6,2", "C"),
    ("4,8 - 5,4", "D+"),
    ("4,0 - 4,7", "D"),
    ("3,0 - 3,9", "F+"),
    ("0,0 - 2,9", "F"),
]

GRADE4_ROWS = [
    ("A", "4,0"),
    ("B+", "3,5"),
    ("B", "3,0"),
    ("C+", "2,5"),
    ("C", "2,0"),
    ("D+", "1,5"),
    ("D", "1,0"),
    ("F+", "0,5"),
    ("F", "0,0"),
]


def extract_regulation_tables(section: dict[str, Any]) -> list[dict[str, Any]]:
    """Trích các bảng quy định bị flatten thành cấu trúc dễ đọc cho RAG."""

    # Chuẩn hóa Unicode ngay từ đầu để tránh lỗi tiếng Việt trong PDF (NFC vs NFD)
    raw_content = str(section.get("content") or "")
    if not raw_content:
        return []
    content = unicodedata.normalize("NFC", raw_content)

    source_pages = list(
        range(int(section["page_start"]), int(section["page_end"]) + 1)
    )
    tables: list[dict[str, Any]] = []
    tables.extend(_extract_study_duration_tables(section, content, source_pages))
    tables.extend(_extract_grade_scale_tables(section, content, source_pages))
    pass_fail_table = extract_pass_fail_ungraded_table(section, content, source_pages)
    if pass_fail_table is not None:
        tables.append(pass_fail_table)
    tables.extend(_extract_grade4_tables(section, content, source_pages))
    tables.extend(_extract_academic_classification_tables(section, content, source_pages))
    tables.extend(_extract_conduct_tables(section, content, source_pages))
    return tables


def format_tables_for_parent(tables: list[dict[str, Any]]) -> str:
    if not tables:
        return ""

    blocks: list[str] = ["BẢNG/DANH SÁCH CHUẨN HÓA TỪ NGUỒN:"]
    for table in tables:
        blocks.append("")
        blocks.append(f"Bảng: {table['table_name']}")
        applicability = table.get("applicability")
        if applicability:
            blocks.append(f"Phạm vi áp dụng: {applicability}")
        blocks.append(_rows_to_markdown(table["columns"], table["rows"]))
    return "\n".join(blocks).strip()


def build_regulation_table_chunk_content(
    section: dict[str, Any],
    table: dict[str, Any],
) -> str:
    parts = [
        f"Tài liệu: {section.get('document_title') or ''}",
        f"Điều: {section.get('article') or ''}",
        f"Tiêu đề: {section.get('title') or ''}",
        f"Bảng: {table['table_name']}",
    ]
    if table.get("applicability"):
        parts.append(f"Phạm vi áp dụng: {table['applicability']}")
    parts.extend(
        [
            "Nội dung bảng:",
            _rows_to_markdown(table["columns"], table["rows"]),
        ]
    )
    return "\n".join(part for part in parts if part and part.strip())


def table_metadata_payload(table: dict[str, Any]) -> dict[str, Any]:
    return {
        "table_id": table["table_id"],
        "table_name": table["table_name"],
        "table_kind": table["table_kind"],
        "applicability": table.get("applicability"),
        "columns": table["columns"],
        "rows": table["rows"],
    }


def _extract_study_duration_tables(
    section: dict[str, Any],
    content: str,
    source_pages: list[int],
) -> list[dict[str, Any]]:
    lowered = content.lower()
    if "thời gian học tập chuẩn" not in lowered or "thời gian học tập tối đa" not in lowered:
        return []

    normalized = _collapse_space(content)
    
    blocks = []
    # Phân tách block chính quy và vừa làm vừa học nếu có
    idx_chinh_quy = lowered.find("hình thức đào tạo chính quy")
    idx_vua_lam = lowered.find("hình thức đào tạo vừa làm vừa học")
    
    if idx_chinh_quy != -1 and idx_vua_lam != -1:
        if idx_chinh_quy < idx_vua_lam:
            blocks.append(("chinh_quy", normalized[idx_chinh_quy:idx_vua_lam], "Áp dụng cho hình thức đào tạo chính quy."))
            blocks.append(("vua_lam_vua_hoc", normalized[idx_vua_lam:], "Áp dụng cho hình thức đào tạo vừa làm vừa học."))
        else:
            blocks.append(("vua_lam_vua_hoc", normalized[idx_vua_lam:idx_chinh_quy], "Áp dụng cho hình thức đào tạo vừa làm vừa học."))
            blocks.append(("chinh_quy", normalized[idx_chinh_quy:], "Áp dụng cho hình thức đào tạo chính quy."))
    else:
        blocks.append(("chung", normalized, "Theo hình thức đào tạo được nêu trong điều khoản nguồn."))

    row_patterns = [
        r"(Đào tạo đại học cấp bằng thứ nhất)\s+([0-9,\.]+\s*năm học)\s+([0-9,\.]+\s*năm học)",
        r"(Đào tạo cao đẳng chính quy)\s+([0-9,\.]+\s*năm học)\s+([0-9,\.]+\s*năm học)",
        r"(Đào tạo cao đẳng vừa làm vừa học)\s+([0-9,\.]+\s*năm học)\s+([0-9,\.]+\s*năm học)",
        r"(Đào tạo liên thông từ trình độ cao đẳng lên trình độ đại học)\s+([0-9,\.]+\s*năm học)\s+([0-9,\.]+\s*năm học)",
        r"(Đào tạo liên thông từ trình độ trung cấp lên trình độ đại học)\s+([0-9,\.]+\s*năm học)\s+([0-9,\.]+\s*năm học)",
        r"(Đào tạo liên thông trình độ đại học đối với người đã có một bằng đại học)\s+([0-9,\.]+\s*năm học)\s+([0-9,\.]+\s*năm học)",
    ]
    
    tables = []
    for suffix, block_text, applicability in blocks:
        rows = []
        for pattern in row_patterns:
            for match in re.finditer(pattern, block_text, flags=re.IGNORECASE):
                rows.append(
                    {
                        "Chương trình đào tạo": match.group(1).strip(),
                        "Thời gian học tập chuẩn": match.group(2).strip(),
                        "Thời gian học tập tối đa": match.group(3).strip(),
                    }
                )
        if rows:
            tables.append(
                _make_table(
                    section,
                    suffix=f"study_duration_{suffix}",
                    table_name="Thời gian học tập chuẩn và tối đa",
                    table_kind="study_duration",
                    columns=[
                        "Chương trình đào tạo",
                        "Thời gian học tập chuẩn",
                        "Thời gian học tập tối đa",
                    ],
                    rows=rows,
                    source_pages=source_pages,
                    applicability=applicability,
                )
            )
    return tables


def _extract_grade_scale_tables(
    section: dict[str, Any],
    content: str,
    source_pages: list[int],
) -> list[dict[str, Any]]:
    lowered = content.lower()
    if "thang điểm 10" not in lowered or "thang điểm chữ" not in lowered:
        return []

    compact = _collapse_space(content)
    blocks: list[tuple[str, str, str]] = []
    
    if "giáo dục đại cương" in lowered or "nền tảng" in lowered:
        # Cố gắng tìm phần nền tảng
        foundation_idx = lowered.find("giáo dục đại cương")
        if foundation_idx == -1:
            foundation_idx = lowered.find("nền tảng")
            
        remaining_idx = lowered.find("còn lại")
        if remaining_idx == -1:
            remaining_idx = lowered.find("còn lại") # NFD 'ò' in some PDFs
            
        end_idx = lowered.find("đạt không phân mức")
        if end_idx == -1:
            end_idx = len(compact)
            
        if foundation_idx != -1 and remaining_idx != -1:
            foundation = compact[foundation_idx:remaining_idx]
            remaining = compact[remaining_idx:end_idx]
            blocks.extend(
                [
                    (
                        "grade_scale_foundation",
                        "Bảng quy đổi điểm học phần nhóm nền tảng",
                        foundation,
                    ),
                    (
                        "grade_scale_remaining",
                        "Bảng quy đổi điểm học phần còn lại",
                        remaining,
                    ),
                ]
            )
        else:
            blocks.append(
                (
                    "grade_scale_general",
                    "Bảng quy đổi thang điểm 10 sang điểm chữ",
                    compact,
                )
            )
    else:
        blocks.append(
            (
                "grade_scale_general",
                "Bảng quy đổi thang điểm 10 sang điểm chữ",
                compact,
            )
        )

    tables: list[dict[str, Any]] = []
    for suffix, table_name, block in blocks:
        rows = _grade_scale_rows(block, remaining=("remaining" in suffix))
        if not rows:
            continue
        applicability = None
        if "foundation" in suffix:
            applicability = "Áp dụng cho học phần giáo dục đại cương/học phần chung thuộc nhóm nền tảng."
        elif "remaining" in suffix:
            applicability = "Áp dụng cho các học phần còn lại."
        tables.append(
            _make_table(
                section,
                suffix=suffix,
                table_name=table_name,
                table_kind="grade_scale",
                columns=["Loại", "Thang điểm 10", "Thang điểm chữ"],
                rows=rows,
                source_pages=source_pages,
                applicability=applicability,
            )
        )
    return tables


def extract_pass_fail_ungraded_table(
    section: dict[str, Any],
    content: str,
    source_pages: list[int],
) -> dict[str, Any] | None:
    """Extract the K51 pass/fail-only course rule without mixing it with GPA scales."""

    compact = _collapse_space(unicodedata.normalize("NFC", content))
    if "đạt không phân mức" not in compact.lower():
        return None

    match = re.search(
        r"yêu cầu đạt\s+(\d+(?:[,.]\d+)?)\s+trở lên.*?"
        r"điểm chữ là\s+([A-Z])\b",
        compact,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None

    threshold = match.group(1)
    letter_grade = match.group(2).upper()
    return _make_table(
        section,
        suffix="pass_fail_ungraded",
        table_name="Bảng đánh giá học phần đạt/không đạt không phân mức",
        table_kind="pass_fail_ungraded",
        columns=[
            "Kết quả",
            "Thang điểm 10",
            "Điểm chữ",
            "Tính vào điểm trung bình học tập",
        ],
        rows=[
            {
                "Kết quả": "Đạt",
                "Thang điểm 10": f"Từ {threshold} trở lên",
                "Điểm chữ": letter_grade,
                "Tính vào điểm trung bình học tập": "Không",
            },
            {
                "Kết quả": "Chưa đạt",
                "Thang điểm 10": f"Dưới {threshold}",
                "Điểm chữ": "Không quy đổi thành P",
                "Tính vào điểm trung bình học tập": "Không",
            },
        ],
        source_pages=source_pages,
        applicability=(
            "Áp dụng cho học phần chỉ yêu cầu đạt, không phân mức và không tính "
            "vào điểm trung bình học tập."
        ),
    )


def _extract_grade4_tables(
    section: dict[str, Any],
    content: str,
    source_pages: list[int],
) -> list[dict[str, Any]]:
    lowered = content.lower()
    if "thang điểm chữ" not in lowered or "thang điểm 4" not in lowered:
        return []

    compact = _collapse_space(content)
    # Tìm xem ít nhất có chữ A và F không
    if not ("A" in compact and "F" in compact):
        return []

    rows = []
    for letter, point in GRADE4_ROWS:
        # Cho phép match các dạng 'A 4,0', 'A: 4.0'
        if re.search(rf"{re.escape(letter)}\s*[:]?\s*{re.escape(point)}", compact, flags=re.IGNORECASE) or \
           re.search(rf"{re.escape(letter)}\s*[:]?\s*{point.replace(',', '.')}", compact, flags=re.IGNORECASE):
            rows.append({"Thang điểm chữ": letter, "Thang điểm 4": point})
    
    if not rows:
        return []

    return [
        _make_table(
            section,
            suffix="letter_to_grade4",
            table_name="Bảng quy đổi điểm chữ sang thang điểm 4",
            table_kind="letter_to_grade4",
            columns=["Thang điểm chữ", "Thang điểm 4"],
            rows=rows,
            source_pages=source_pages,
        )
    ]


def _extract_academic_classification_tables(
    section: dict[str, Any],
    content: str,
    source_pages: list[int],
) -> list[dict[str, Any]]:
    lowered = content.lower()
    if "xếp loại" not in lowered or "thang điểm 4" not in lowered:
        return []

    compact = _collapse_space(content)
    row_patterns = [
        (r"Xuất sắc\s+Từ 3[,.]6 đến 4[,.]0", "Xuất sắc", "Từ 3,6 đến 4,0"),
        (r"Giỏi\s+Từ 3[,.]2 đến dưới 3[,.]6", "Giỏi", "Từ 3,2 đến dưới 3,6"),
        (r"Khá\s+Từ 2[,.]5 đến dưới 3[,.]2", "Khá", "Từ 2,5 đến dưới 3,2"),
        (r"Trung bình\s+Từ 2[,.]0 đến dưới 2[,.]5", "Trung bình", "Từ 2,0 đến dưới 2,5"),
        (r"Yếu\s+Từ 1[,.]0 đến dưới 2[,.]0", "Yếu", "Từ 1,0 đến dưới 2,0"),
        (r"Kém\s+Dưới 1[,.]0", "Kém", "Dưới 1,0"),
    ]
    rows = []
    for pattern, label, score_range in row_patterns:
        if re.search(pattern, compact, flags=re.IGNORECASE):
            rows.append({"Xếp loại": label, "Thang điểm 4": score_range})

    if not rows:
        return []

    return [
        _make_table(
            section,
            suffix="academic_classification",
            table_name="Bảng xếp loại học lực theo thang điểm 4",
            table_kind="academic_classification",
            columns=["Xếp loại", "Thang điểm 4"],
            rows=rows,
            source_pages=source_pages,
        )
    ]


def _extract_conduct_tables(
    section: dict[str, Any],
    content: str,
    source_pages: list[int],
) -> list[dict[str, Any]]:
    lowered = content.lower()
    if "khung điểm" not in lowered or "xếp loại" not in lowered:
        return []

    compact = _collapse_space(content)
    row_patterns = [
        (r"Từ 90 đến 100 điểm\s+Xuất sắc", "Từ 90 đến 100 điểm", "Xuất sắc"),
        (r"Từ 80 đến dưới 90 điểm\s+Tốt", "Từ 80 đến dưới 90 điểm", "Tốt"),
        (r"Từ 65 đến dưới 80 điểm\s+Khá", "Từ 65 đến dưới 80 điểm", "Khá"),
        (r"Từ 50 đến dưới 65 điểm\s+Trung bình", "Từ 50 đến dưới 65 điểm", "Trung bình"),
        (r"Từ 35 đến dưới 50 điểm\s+Yếu", "Từ 35 đến dưới 50 điểm", "Yếu"),
        (r"Dưới 35 điểm\s+Kém", "Dưới 35 điểm", "Kém"),
    ]
    rows = []
    for pattern, score_range, label in row_patterns:
        if re.search(pattern, compact, flags=re.IGNORECASE):
            rows.append({"Khung điểm": score_range, "Xếp loại": label})

    if not rows:
        return []

    return [
        _make_table(
            section,
            suffix="conduct_classification",
            table_name="Bảng phân loại kết quả rèn luyện",
            table_kind="conduct_classification",
            columns=["Khung điểm", "Xếp loại"],
            rows=rows,
            source_pages=source_pages,
        )
    ]


def _grade_scale_rows(block: str, *, remaining: bool) -> list[dict[str, str]]:
    if not block:
        return []

    rows: list[dict[str, str]] = []
    for score_range, letter in GRADE_RANGES:
        range_pattern = score_range.replace(" - ", r"\s*[–-]\s*")
        if not re.search(rf"{range_pattern}\s+{re.escape(letter)}(?=\s|$)", block):
            continue
        is_fail = letter in {"F+", "F"} or (remaining and letter in {"D+", "D"})
        rows.append(
            {
                "Loại": "Không đạt" if is_fail else "Đạt",
                "Thang điểm 10": score_range,
                "Thang điểm chữ": letter,
            }
        )
    return rows


def _make_table(
    section: dict[str, Any],
    *,
    suffix: str,
    table_name: str,
    table_kind: str,
    columns: list[str],
    rows: list[dict[str, str]],
    source_pages: list[int],
    applicability: str | None = None,
) -> dict[str, Any]:
    table_id = f"{section['section_id']}_{suffix}"
    return {
        "table_id": table_id,
        "table_name": table_name,
        "table_kind": table_kind,
        "columns": columns,
        "rows": rows,
        "source_pages": source_pages,
        "source_section": section.get("title") or section.get("article"),
        "applicability": applicability,
    }


def _rows_to_markdown(columns: list[str], rows: list[dict[str, Any]]) -> str:
    header = "| " + " | ".join(columns) + " |"
    divider = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| " + " | ".join(str(row.get(column, "")) for column in columns) + " |"
        for row in rows
    ]
    return "\n".join([header, divider, *body])


def _between(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        return ""
    start += len(start_marker)
    end = text.find(end_marker, start)
    if end < 0:
        return text[start:]
    return text[start:end]


def _collapse_space(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()
