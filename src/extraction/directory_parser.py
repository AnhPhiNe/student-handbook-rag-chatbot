import re
from typing import Any, Optional

from .text_utils import get_pages_by_type, normalize_text


OFFICE_HEADING_PATTERN = re.compile(
    r"^\s*(\d+)\.\s+(Phòng|Ban|Trung tâm|Thư viện|Ký túc xá|Tạp chí)\b",
    re.IGNORECASE,
)

FACULTY_HEADING_PATTERN = re.compile(
    r"^\s*(\d+)\.\s+(Khoa|Tổ)\b",
    re.IGNORECASE,
)

BULLET_PATTERN = re.compile(r"^\s*[-–−+•]\s+")

SECTION_TITLE_PATTERNS = [
    re.compile(r"^CÁC PHÒNG, BAN", re.IGNORECASE),
    re.compile(r"^CÁC KHOA VÀ TỔ", re.IGNORECASE),
]


def is_section_title(line: str) -> bool:
    line = line.strip()
    return any(pattern.search(line) for pattern in SECTION_TITLE_PATTERNS)


def is_bullet_line(line: str) -> bool:
    return bool(BULLET_PATTERN.match(line.strip()))


def is_office_heading(line: str) -> bool:
    return bool(OFFICE_HEADING_PATTERN.match(line.strip()))


def is_faculty_heading(line: str) -> bool:
    return bool(FACULTY_HEADING_PATTERN.match(line.strip()))


def clean_heading_name(line: str) -> str:
    """
    Giữ nguyên số thứ tự + tên đơn vị để dễ trace source.
    Ví dụ: '3. Phòng Đào tạo'
    """
    return normalize_text(line)


def should_skip_line(line: str) -> bool:
    """
    Bỏ những dòng rỗng hoặc title tổng quan, không phải record.
    """
    clean_line = line.strip()

    if not clean_line:
        return True

    if is_section_title(clean_line):
        return True

    return False


def split_page_to_lines(text: str) -> list[str]:
    """
    Chuẩn hóa text page thành lines.
    """
    text = normalize_text(text)
    return [line.strip() for line in text.splitlines() if line.strip()]


def close_current_record(
    current_record: Optional[dict[str, Any]],
    records: list[dict[str, Any]],
) -> None:
    if not current_record:
        return

    raw_lines = current_record.get("_raw_lines", [])
    raw_text = normalize_text("\n".join(raw_lines))

    if not raw_text:
        return

    current_record["raw_text"] = raw_text
    current_record["needs_manual_review"] = detect_needs_manual_review(current_record)

    current_record.pop("_raw_lines", None)

    records.append(current_record)


def detect_needs_manual_review(record: dict[str, Any]) -> bool:
    """
    Flag review nếu record quá ngắn hoặc không có mô tả.
    """
    raw_text = record.get("raw_text", "")
    source_pages = record.get("source_pages", [])

    if len(raw_text) < 80:
        return True

    if not source_pages:
        return True

    return False


def append_line_to_current_record(
    current_record: dict[str, Any],
    line: str,
    page_number: int,
) -> None:
    current_record["_raw_lines"].append(line)

    if page_number not in current_record["source_pages"]:
        current_record["source_pages"].append(page_number)


def create_directory_record(
    record_id: str,
    content_type: str,
    name_field: str,
    name_value: str,
    page_number: int,
    heading_line: str,
) -> dict[str, Any]:
    return {
        "record_id": record_id,
        "content_type": content_type,
        name_field: name_value,
        "source_pages": [page_number],
        "_raw_lines": [heading_line],
    }


def extract_directory_by_heading(
    pages: list[dict[str, Any]],
    content_type: str,
    heading_type: str,
) -> list[dict[str, Any]]:
    """
    Parser chung cho office/faculty.

    Logic:
    - Chỉ mở record mới khi gặp heading thật:
      + office: '1. Phòng...', '2. Trung tâm...'
      + faculty: '1. Khoa...', '2. Tổ...'
    - Dòng bullet/mô tả sẽ append vào record hiện tại.
    - Nội dung tiếp qua trang mới vẫn append vào record trước cho đến khi gặp heading mới.
    """

    if heading_type not in {"office", "faculty"}:
        raise ValueError("heading_type must be 'office' or 'faculty'")

    target_pages = get_pages_by_type(pages, content_type)
    records: list[dict[str, Any]] = []
    current_record: Optional[dict[str, Any]] = None
    record_counter = 1

    for page in target_pages:
        page_number = page["page_number"]
        lines = split_page_to_lines(page.get("text", ""))

        for line in lines:
            if should_skip_line(line):
                continue

            if heading_type == "office":
                is_new_heading = is_office_heading(line)
                name_field = "unit_name"
                record_prefix = "office"
            else:
                is_new_heading = is_faculty_heading(line)
                name_field = "faculty_or_unit_name"
                record_prefix = "faculty"

            if is_new_heading:
                close_current_record(current_record, records)

                name_value = clean_heading_name(line)

                current_record = create_directory_record(
                    record_id=f"{record_prefix}_{record_counter}",
                    content_type=content_type,
                    name_field=name_field,
                    name_value=name_value,
                    page_number=page_number,
                    heading_line=line,
                )

                record_counter += 1
                continue

            # Không có heading mới:
            # Nếu đã có record thì append mô tả/bullet vào record hiện tại.
            if current_record is not None:
                append_line_to_current_record(current_record, line, page_number)
                continue

            # Nếu chưa có record mà gặp dòng mô tả đầu trang thì bỏ qua.
            # Ví dụ: heading tổng quan hoặc dòng rác trước đơn vị đầu tiên.
            # Không tạo record mới bằng bullet/mô tả.
            continue

    close_current_record(current_record, records)

    return records


def extract_office_directory(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return extract_directory_by_heading(
        pages=pages,
        content_type="office_directory",
        heading_type="office",
    )


def extract_faculty_program_directory(
    pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return extract_directory_by_heading(
        pages=pages,
        content_type="faculty_program_directory",
        heading_type="faculty",
    )


def extract_reference_directory(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Reference directory không cố tách từng item vì nhóm này không phải core QA.
    Giữ theo page để tránh parse sai.
    """
    reference_pages = get_pages_by_type(pages, "reference_directory")
    records = []

    for page in reference_pages:
        page_number = page["page_number"]
        text = normalize_text(page.get("text", ""))

        if not text:
            continue

        records.append(
            {
                "record_id": f"reference_p{page_number}",
                "content_type": "reference_directory",
                "name": f"Tài liệu tham khảo/trang tra cứu {page_number}",
                "source_pages": [page_number],
                "raw_text": text,
                "needs_manual_review": False,
            }
        )

    return records
