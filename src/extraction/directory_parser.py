import re
from typing import Any, Optional

from src.ingestion.pdf_loader import clean_text

from .text_utils import get_pages_by_type, normalize_text


OFFICE_HEADING_PATTERN = re.compile(
    (
        r"^\s*(\d+)\.\s+"
        r"(Phòng|Ban|Trung tâm|Thư viện|Ký túc xá|Tạp chí|Trạm|Trường|"
        r"Nhà xuất bản|Viện|Đoàn|Phân hiệu)\b"
    ),
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
    """Return whether a line is a directory section title."""

    line = line.strip()
    return any(pattern.search(line) for pattern in SECTION_TITLE_PATTERNS)


def is_office_heading(line: str) -> bool:
    """Return whether a line starts an office record."""

    return bool(OFFICE_HEADING_PATTERN.match(line.strip()))


def is_faculty_heading(line: str) -> bool:
    """Return whether a line starts a faculty record."""

    return bool(FACULTY_HEADING_PATTERN.match(line.strip()))


def clean_heading_name(line: str) -> str:
    """Preserve the source ordinal and unit name for traceability."""
    return normalize_text(line)


def should_skip_line(line: str) -> bool:
    """Reject empty lines and overview titles that are not directory records."""
    clean_line = line.strip()

    if not clean_line:
        return True

    if is_section_title(clean_line):
        return True

    return False


def split_page_to_lines(text: str) -> list[str]:
    """Normalize extracted page text into non-empty lines."""
    text = normalize_text(clean_text(text))
    return [line.strip() for line in text.splitlines() if line.strip()]


def close_current_record(
    current_record: Optional[dict[str, Any]],
    records: list[dict[str, Any]],
) -> None:
    """Finalize the open directory record and append it when valid."""

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
    """Flag records whose description is absent or unusually short."""
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
    """Append a description line to the currently open record."""

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
    """Create a normalized directory record from one heading."""

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
    """Parse office or faculty records while carrying descriptions across pages."""

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

            # No new heading: continue the current record when one exists.
            # Descriptions and bullets belong to the open record.
            if current_record is not None:
                append_line_to_current_record(current_record, line, page_number)
                continue

            # Ignore leading page text until the first valid record appears.
            # This includes overview headings and extraction noise.
            # Never create a record from a bullet or description alone.
            continue

    close_current_record(current_record, records)

    return records


def extract_office_directory(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract office records from handbook pages."""

    return extract_directory_by_heading(
        pages=pages,
        content_type="office_directory",
        heading_type="office",
    )


def extract_faculty_program_directory(
    pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract faculty and program directory records from handbook pages."""

    return extract_directory_by_heading(
        pages=pages,
        content_type="faculty_program_directory",
        heading_type="faculty",
    )


def extract_reference_directory(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Preserve non-core reference directories by page to avoid false parsing."""
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
