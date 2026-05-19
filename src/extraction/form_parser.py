import re
from typing import Any, Optional

from .text_utils import get_pages_by_type, normalize_text


FORM_TITLE_PATTERNS = [
    r"^ĐƠN\s+(XIN|ĐỀ NGHỊ)",
    r"^PHIẾU\s+",
    r"^BIÊN BẢN\s+",
    r"^BẢNG\s+KẾT QUẢ",
    r"^BẢN\s+CAM KẾT",
    r"^GIẤY\s+XÁC NHẬN",
    r"^CÁC MẪU ĐƠN",
]


def is_new_form_title(line: str) -> bool:
    line = line.strip()
    upper = line.upper()

    if len(upper) > 180:
        return False

    # Tránh bắt nhầm dòng ghi chú có chữ "đơn xin"
    banned_phrases = [
        "SINH VIÊN CÓ ĐƠN XIN",
        "CÓ ĐƠN XIN KHÔNG",
        "ĐƠN XIN KHÔNG ĐÁNH",
    ]

    if any(phrase in upper for phrase in banned_phrases):
        return False

    return any(re.search(pattern, upper) for pattern in FORM_TITLE_PATTERNS)


def extract_form_title(text: str) -> Optional[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for line in lines:
        if is_new_form_title(line):
            return line

    return None


def extract_required_fields(text: str) -> list[str]:
    fields = [
        "Họ tên",
        "Họ và tên",
        "MSSV",
        "Mã số sinh viên",
        "Lớp",
        "Lớp SV",
        "Khóa",
        "Khoá",
        "Khoa",
        "Ngành",
        "Ngày sinh",
        "Ngày tháng năm sinh",
        "Số điện thoại",
        "Điện thoại",
        "Email",
        "Địa chỉ email",
        "Lý do",
        "Lí do",
        "Nội dung",
        "Thời gian",
        "Kính gửi",
        "Địa chỉ",
        "Hộ khẩu thường trú",
        "CMND",
        "CCCD",
    ]

    found = []
    lower_text = text.lower()

    for field in fields:
        if field.lower() in lower_text:
            found.append(field)

    # Chuẩn hóa field trùng nghĩa
    normalize_map = {
        "Họ và tên": "Họ tên",
        "Mã số sinh viên": "MSSV",
        "Lớp SV": "Lớp",
        "Khoá": "Khóa",
        "Ngày tháng năm sinh": "Ngày sinh",
        "Điện thoại": "Số điện thoại",
        "Địa chỉ email": "Email",
        "Lí do": "Lý do",
    }

    normalized = []
    for item in found:
        normalized.append(normalize_map.get(item, item))

    return sorted(set(normalized))


def should_skip_form_page(text: str, page_number: int) -> bool:
    """
    Bỏ trang rỗng hoặc trang không có nội dung thật.
    """
    if not text.strip():
        return True

    if len(text.strip()) < 30:
        return True

    return False


def extract_form_templates(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    form_pages = get_pages_by_type(pages, "form_template")

    forms = []
    current_form = None

    for page in form_pages:
        page_number = page["page_number"]
        text = normalize_text(page.get("text", ""))

        if should_skip_form_page(text, page_number):
            continue

        title = extract_form_title(text)

        if title:
            if current_form:
                forms.append(current_form)

            current_form = {
                "form_id": f"form_p{page_number}",
                "form_name": title,
                "content_type": "form_template",
                "source_pages": [page_number],
                "raw_text": text,
                "review_status": "auto_grouped",
            }

        else:
            if current_form:
                current_form["source_pages"].append(page_number)
                current_form["raw_text"] += "\n\n" + text
            else:
                current_form = {
                    "form_id": f"form_p{page_number}",
                    "form_name": f"Biểu mẫu trang {page_number}",
                    "content_type": "form_template",
                    "source_pages": [page_number],
                    "raw_text": text,
                    "review_status": "needs_manual_review",
                }

    if current_form:
        forms.append(current_form)

    for form in forms:
        form["raw_text"] = normalize_text(form["raw_text"])
        form["required_fields_detected"] = extract_required_fields(form["raw_text"])

    return forms