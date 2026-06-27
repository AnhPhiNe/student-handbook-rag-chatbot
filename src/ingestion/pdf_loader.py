import json
import os
import re
from pathlib import Path
from typing import Any

import fitz
import yaml


PDF_PATH = Path(os.environ.get("PDF_PATH", "data/raw/so-tay-sinh-vien-khoa-48.pdf"))
CONFIG_PATH = Path(os.environ.get("CONFIG_PATH", "configs/document_sections.yaml"))
OUTPUT_DIR = Path("data/processed/metadata")


def load_yaml_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def clean_text(text: str) -> str:
    """
    Làm sạch text cơ bản.
    Mục tiêu: bỏ header/footer, số trang, khoảng trắng dư.
    """

    lines = text.splitlines()
    cleaned_lines = []

    for line in lines:
        line = line.strip()

        if not line:
            continue

        # Bỏ header/footer lặp lại
        if "Sổ tay Sinh viên năm học 2022" in line:
            continue

        # Bỏ dòng chỉ có số trang
        if re.fullmatch(r"\d{1,3}", line):
            continue

        cleaned_lines.append(line)

    cleaned_text = "\n".join(cleaned_lines)

    # Chuẩn hóa khoảng trắng
    cleaned_text = re.sub(r"[ \t]+", " ", cleaned_text)
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text)

    return cleaned_text.strip()


def detect_by_page_range(page_number: int, config: dict[str, Any]) -> tuple[str, str]:
    """
    Gắn content_type theo config page range.
    Không hardcode trong code, muốn đổi chỉ sửa YAML.
    """

    for section in config.get("sections", []):
        if section["page_start"] <= page_number <= section["page_end"]:
            return section["content_type"], section.get("description", "")

    return "unknown", ""


def detect_by_pattern(text: str) -> list[str]:
    """
    Nhận diện bằng pattern để kiểm tra lại page range.
    Một trang có thể khớp nhiều pattern.
    """

    lower_text = text.lower()
    matched = []

    if re.search(r"\bchương\s+[ivxlcdm]+", lower_text) or re.search(
        r"\bđiều\s+\d+", lower_text
    ):
        matched.append("regulation_text")

    if "quy ước viết tắt" in lower_text:
        matched.append("abbreviation")

    if (
        "thang điểm" in lower_text
        or "xếp loại" in lower_text
        or "khung điểm" in lower_text
    ):
        matched.append("scoring_table")

    if "nội dung đánh giá" in lower_text and "điểm đánh giá" in lower_text:
        matched.append("scoring_table")

    if "phiếu đánh giá kết quả rèn luyện sinh viên" in lower_text:
        matched.append("form_template")

    if (
        "kính gửi" in lower_text
        or "người làm đơn" in lower_text
        or "đơn xin" in lower_text
    ):
        matched.append("form_template")

    if "phòng đào tạo" in lower_text or "phòng công tác chính trị" in lower_text:
        matched.append("office_directory")

    if "khoa" in lower_text and ("ngành" in lower_text or "chuyên ngành" in lower_text):
        matched.append("faculty_program_directory")

    if "mục lục" in lower_text:
        matched.append("toc_or_index")

    return matched


def estimate_confidence(
    range_type: str, pattern_types: list[str], char_count: int
) -> tuple[float, bool, str]:
    """
    Tính confidence đơn giản:
    - Config và pattern trùng nhau: tin cao.
    - Trang ít chữ: cần review hoặc bỏ.
    - Config có nhưng pattern chưa confirm: tin vừa.
    """

    if char_count < 100:
        return 0.95, False, "low_text_page"

    if range_type in pattern_types:
        return 0.95, False, "config+pattern"

    if range_type != "unknown":
        return 0.75, False, "config_only"

    if pattern_types:
        return 0.70, True, "pattern_only"

    return 0.40, True, "unknown"


def has_table_hint(text: str, pattern_types: list[str]) -> bool:
    table_keywords = [
        "thang điểm",
        "xếp loại",
        "khung điểm",
        "nội dung đánh giá",
        "điểm đánh giá",
        "tổng cộng",
    ]

    lower_text = text.lower()

    return "scoring_table" in pattern_types or any(
        keyword in lower_text for keyword in table_keywords
    )


def extract_pdf_pages(pdf_path: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    doc = fitz.open(pdf_path)
    pages = []

    for page_index, page in enumerate(doc):
        page_number = page_index + 1

        raw_text = page.get_text("text")
        cleaned_text = clean_text(raw_text)

        range_type, section_description = detect_by_page_range(page_number, config)
        pattern_types = detect_by_pattern(cleaned_text)

        confidence, needs_review, detection_source = estimate_confidence(
            range_type=range_type,
            pattern_types=pattern_types,
            char_count=len(cleaned_text),
        )

        final_content_type = range_type
        if final_content_type == "unknown" and pattern_types:
            final_content_type = pattern_types[0]

        page_data = {
            "document_id": config.get("document_id"),
            "file_name": config.get("file_name"),
            "page_number": page_number,
            "content_type": final_content_type,
            "section_description": section_description,
            "pattern_detected_types": pattern_types,
            "detection_source": detection_source,
            "confidence": confidence,
            "needs_review": needs_review,
            "has_table_hint": has_table_hint(cleaned_text, pattern_types),
            "raw_char_count": len(raw_text.strip()),
            "cleaned_char_count": len(cleaned_text),
            "text": cleaned_text,
        }

        pages.append(page_data)

    return pages


def build_document_profile(
    pages: list[dict[str, Any]], config: dict[str, Any]
) -> dict[str, Any]:
    content_type_count = {}
    low_text_pages = []
    possible_table_pages = []
    review_pages = []

    for page in pages:
        content_type = page["content_type"]
        content_type_count[content_type] = content_type_count.get(content_type, 0) + 1

        if page["content_type"] == "low_text_or_blank":
            low_text_pages.append(page["page_number"])

        if page["has_table_hint"]:
            possible_table_pages.append(page["page_number"])

        if page["needs_review"]:
            review_pages.append(page["page_number"])

    return {
        "document_id": config.get("document_id"),
        "file_name": config.get("file_name"),
        "document_type": config.get("document_type"),
        "language": config.get("language"),
        "academic_year": config.get("academic_year"),
        "total_pages": len(pages),
        "content_type_count": content_type_count,
        "low_text_pages": low_text_pages,
        "possible_table_pages": possible_table_pages,
        "pages_need_review": review_pages,
        "configured_sections": config.get("sections", []),
    }


def build_extraction_report(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Report để debug nhanh bước PDF extraction.
    """

    return {
        "total_pages": len(pages),
        "low_text_pages": [
            p["page_number"] for p in pages if p["content_type"] == "low_text_or_blank"
        ],
        "possible_table_pages": [
            p["page_number"] for p in pages if p["has_table_hint"]
        ],
        "form_template_pages": [
            p["page_number"] for p in pages if p["content_type"] == "form_template"
        ],
        "office_directory_pages": [
            p["page_number"] for p in pages if p["content_type"] == "office_directory"
        ],
        "faculty_program_directory_pages": [
            p["page_number"]
            for p in pages
            if p["content_type"] == "faculty_program_directory"
        ],
        "toc_or_index_pages": [
            p["page_number"] for p in pages if p["content_type"] == "toc_or_index"
        ],
        "pages_need_review": [
            {
                "page_number": p["page_number"],
                "content_type": p["content_type"],
                "pattern_detected_types": p["pattern_detected_types"],
                "confidence": p["confidence"],
            }
            for p in pages
            if p["needs_review"]
        ],
    }


def save_json(data: Any, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    cohort = os.environ.get("COHORT", "UNKNOWN")
    if cohort == "K50-K51":
        config = load_yaml_config(Path("configs/document_sections_k50_k51.yaml"))
    else:
        config = load_yaml_config(CONFIG_PATH)

    pages = extract_pdf_pages(PDF_PATH, config)
    document_profile = build_document_profile(pages, config)
    extraction_report = build_extraction_report(pages)

    save_json(pages, OUTPUT_DIR / "pages.json")
    save_json(document_profile, OUTPUT_DIR / "document_profile.json")
    save_json(extraction_report, OUTPUT_DIR / "extraction_report.json")

    print("PDF extraction completed.")
    print(f"Total pages: {document_profile['total_pages']}")
    print(f"Saved: {OUTPUT_DIR / 'pages.json'}")
    print(f"Saved: {OUTPUT_DIR / 'document_profile.json'}")
    print(f"Saved: {OUTPUT_DIR / 'extraction_report.json'}")


if __name__ == "__main__":
    main()
