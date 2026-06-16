import json
import re
from pathlib import Path
from typing import Any, Optional

import yaml


CONFIG_PATH = Path("configs/structure_parser.yaml")

NO_CHAPTER = "__NO_CHAPTER__"
MAX_NON_ARTICLE_CHARS = 1200


PART_PATTERN = re.compile(r"^PHẦN\s+[IVXLCDM]+", re.IGNORECASE)
CHAPTER_PATTERN = re.compile(r"^Chương\s+[IVXLCDM]+", re.IGNORECASE)
ARTICLE_PATTERN = re.compile(r"^Điều\s+(\d+)\.\s*(.*)", re.IGNORECASE)
CLAUSE_PATTERN = re.compile(r"^\d+\.\s+")
POINT_PATTERN = re.compile(r"^[a-zđ]\)\s+", re.IGNORECASE)


DOCUMENT_TITLE_PATTERNS = [
    re.compile(r"^QUYẾT ĐỊNH\b", re.IGNORECASE),
    re.compile(r"^QUY CHẾ\b", re.IGNORECASE),
    re.compile(r"^QUY ĐỊNH\b", re.IGNORECASE),
    re.compile(r"^PHỤ LỤC\b", re.IGNORECASE),
    re.compile(r"^HƯỚNG DẪN\b", re.IGNORECASE),
]


def load_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing config file: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def normalize_line(line: str) -> str:
    line = line.strip()
    line = re.sub(r"\s+", " ", line)
    return line


def is_heading_like(line: str) -> bool:
    if len(line) > 140:
        return False

    letters = [ch for ch in line if ch.isalpha()]
    if not letters:
        return False

    uppercase_letters = [ch for ch in letters if ch.isupper()]
    uppercase_ratio = len(uppercase_letters) / max(len(letters), 1)

    return uppercase_ratio >= 0.55


def classify_line(line: str) -> str:
    line = normalize_line(line)

    if not line:
        return "empty"

    if PART_PATTERN.match(line):
        return "part"

    if CHAPTER_PATTERN.match(line):
        return "chapter"

    if ARTICLE_PATTERN.match(line):
        return "article"

    if CLAUSE_PATTERN.match(line):
        return "clause"

    if POINT_PATTERN.match(line):
        return "point"

    if is_heading_like(line):
        for pattern in DOCUMENT_TITLE_PATTERNS:
            if pattern.search(line):
                return "document_title"

    return "normal_text"


def pages_to_line_records(
    pages: list[dict[str, Any]],
    target_content_types: list[str],
) -> list[dict[str, Any]]:
    line_records = []

    for page in pages:
        content_type = page.get("content_type")

        if content_type not in target_content_types:
            continue

        page_number = page["page_number"]
        text = page.get("text", "")

        for line_index, line in enumerate(text.splitlines(), start=1):
            clean_line = normalize_line(line)

            if not clean_line:
                continue

            line_records.append(
                {
                    "page_number": page_number,
                    "line_index": line_index,
                    "content_type": content_type,
                    "line": clean_line,
                    "line_type": classify_line(clean_line),
                }
            )

    return line_records


def extract_article_info(line: str) -> tuple[str, str, int]:
    match = ARTICLE_PATTERN.match(line)

    if not match:
        raise ValueError(f"Invalid article line: {line}")

    article_number = int(match.group(1))
    article = f"Điều {article_number}."
    title = line

    return article, title, article_number


def slugify_text(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"\s+", "_", text)
    return text.strip("_")


def make_section_id(
    section_level: str,
    page_start: int,
    index: int,
    article_number: Optional[int] = None,
    content_type: Optional[str] = None,
) -> str:
    if article_number is not None:
        return f"article_{article_number}_p{page_start}_{index}"

    prefix = content_type or section_level
    prefix = slugify_text(prefix)

    return f"{prefix}_p{page_start}_{index}"


def detect_has_table(content: str) -> bool:
    lower = content.lower()

    table_patterns = [
        r"loại\s+thang điểm\s+10\s+thang điểm chữ",
        r"thang điểm chữ\s+thang điểm\s+4",
        r"tt\s+khung điểm\s+xếp loại",
        r"nội dung đánh giá\s+khung điểm\s+điểm đánh giá",
        r"chương trình đào tạo\s+thời gian\s+học tập chuẩn\s+thời gian\s+học tập tối đa",
        r"tổng cộng:\s*đạt loại rèn luyện",
    ]

    return any(re.search(pattern, lower) for pattern in table_patterns)


def detect_has_formula(content: str) -> bool:
    lower = content.lower()

    formula_patterns = [
        r"điểm học bổng\s*=",
        r"\ba\s+là\s+điểm trung bình",
        r"\b[a-zA-Z]\s*=\s*",
        r"\(.+\s*[+\-*/x]\s*.+\)",
        r"\d+\s*[x*/]\s*\d+",
        r"/\s*\d+",
    ]

    return any(re.search(pattern, lower) for pattern in formula_patterns)


def detect_has_scoring_rule(content: str) -> bool:
    lower = content.lower()

    scoring_keywords = [
        "thang điểm",
        "điểm thành phần",
        "điểm học phần",
        "điểm học bổng",
        "điểm rèn luyện",
        "điểm trung bình",
        "xếp loại",
        "khung điểm",
        "học bổng loại",
    ]

    return any(keyword in lower for keyword in scoring_keywords)


def detect_has_thresholds(content: str) -> bool:
    lower = content.lower()

    threshold_patterns = [
        r"từ\s+\d+([,.]\d+)?\s+đến",
        r"dưới\s+\d+([,.]\d+)?",
        r"trở lên",
        r">=\s*\d+([,.]\d+)?",
        r"\d+([,.]\d+)?\s*[-–]\s*\d+([,.]\d+)?",
        r"không vượt quá\s+\d+",
        r"ít nhất\s+\d+",
        r"tối đa\s+\d+",
        r"tối thiểu\s+\d+",
    ]

    return any(re.search(pattern, lower) for pattern in threshold_patterns)


def detect_needs_structured_extraction(content: str, content_type: str) -> bool:
    return (
        content_type == "scoring_form_table"
        or detect_has_table(content)
        or detect_has_formula(content)
        or detect_has_thresholds(content)
    )


def resolve_chapter(chapter: Optional[str]) -> str:
    return chapter if chapter else NO_CHAPTER


def create_section(
    section_level: str,
    page_number: int,
    content_type: str,
    index: int,
    document_title: Optional[str],
    part: Optional[str],
    chapter: Optional[str],
    article: Optional[str],
    title: str,
    article_number: Optional[int] = None,
) -> dict[str, Any]:
    return {
        "section_id": make_section_id(
            section_level=section_level,
            page_start=page_number,
            index=index,
            article_number=article_number,
            content_type=content_type,
        ),
        "section_level": section_level,
        "document_title": document_title,
        "part": part,
        "chapter": resolve_chapter(chapter),
        "article": article,
        "title": title,
        "content_type": content_type,
        "page_start": page_number,
        "page_end": page_number,
        "content_lines": [],
        "pages": [],
    }


def close_section(
    current_section: Optional[dict[str, Any]],
    sections: list[dict[str, Any]],
) -> None:
    if current_section is None:
        return

    content_lines = current_section.get("content_lines", [])
    content = "\n".join(content_lines).strip()

    if not content:
        return

    pages = current_section.get("pages", [])

    current_section["content"] = content
    current_section["page_end"] = max(pages) if pages else current_section["page_start"]

    current_section["has_table"] = detect_has_table(content)
    current_section["has_formula"] = detect_has_formula(content)
    current_section["has_scoring_rule"] = detect_has_scoring_rule(content)
    current_section["has_thresholds"] = detect_has_thresholds(content)
    current_section["needs_structured_extraction"] = detect_needs_structured_extraction(
        content=content,
        content_type=current_section["content_type"],
    )

    current_section.pop("content_lines", None)
    current_section.pop("pages", None)

    sections.append(current_section)


def should_close_on_content_type_change(
    current_section: Optional[dict[str, Any]],
    new_content_type: str,
) -> bool:
    if current_section is None:
        return False

    return current_section.get("content_type") != new_content_type


def should_split_long_non_article_section(
    current_section: Optional[dict[str, Any]],
) -> bool:
    if current_section is None:
        return False

    if current_section.get("section_level") != "non_article":
        return False

    current_content = "\n".join(current_section.get("content_lines", []))

    return len(current_content) >= MAX_NON_ARTICLE_CHARS


def build_structured_sections(
    line_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []

    current_document_title: Optional[str] = None
    current_part: Optional[str] = None
    current_chapter: Optional[str] = None
    current_section: Optional[dict[str, Any]] = None

    section_index = 1

    for record in line_records:
        line = record["line"]
        line_type = record["line_type"]
        page_number = record["page_number"]
        content_type = record["content_type"]

        if should_close_on_content_type_change(current_section, content_type):
            close_section(current_section, sections)
            current_section = None

        if line_type == "document_title":
            close_section(current_section, sections)
            current_section = None

            current_document_title = line
            current_part = None
            current_chapter = None
            continue

        if line_type == "part":
            close_section(current_section, sections)
            current_section = None

            current_part = line
            current_chapter = None
            continue

        if line_type == "chapter":
            close_section(current_section, sections)
            current_section = None

            current_chapter = line
            continue

        if line_type == "article":
            close_section(current_section, sections)

            article, title, article_number = extract_article_info(line)

            current_section = create_section(
                section_level="article",
                page_number=page_number,
                content_type=content_type,
                index=section_index,
                document_title=current_document_title,
                part=current_part,
                chapter=current_chapter,
                article=article,
                title=title,
                article_number=article_number,
            )

            current_section["content_lines"].append(line)
            current_section["pages"].append(page_number)

            section_index += 1
            continue

        if current_section is None:
            title = (
                current_chapter
                or current_part
                or current_document_title
                or f"Section page {page_number}"
            )

            current_section = create_section(
                section_level="non_article",
                page_number=page_number,
                content_type=content_type,
                index=section_index,
                document_title=current_document_title,
                part=current_part,
                chapter=current_chapter,
                article=None,
                title=title,
            )

            section_index += 1

        current_section["content_lines"].append(line)
        current_section["pages"].append(page_number)

        if should_split_long_non_article_section(current_section):
            close_section(current_section, sections)
            current_section = None

    close_section(current_section, sections)

    return sections


def validate_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    issues = []
    seen_ids = set()

    for section in sections:
        section_id = section["section_id"]

        if section_id in seen_ids:
            issues.append(
                {
                    "section_id": section_id,
                    "issue": "duplicate_section_id",
                    "severity": "high",
                }
            )

        seen_ids.add(section_id)

        if section["page_end"] < section["page_start"]:
            issues.append(
                {
                    "section_id": section_id,
                    "issue": "page_end_before_page_start",
                    "severity": "high",
                }
            )

        if (
            section["content_type"] == "regulation_text"
            and section["section_level"] == "non_article"
            and len(section["content"]) > MAX_NON_ARTICLE_CHARS + 300
        ):
            issues.append(
                {
                    "section_id": section_id,
                    "issue": "long_non_article_regulation_section",
                    "severity": "medium",
                    "page_start": section["page_start"],
                    "page_end": section["page_end"],
                    "content_length": len(section["content"]),
                }
            )

    return issues


def build_structure_report(sections: list[dict[str, Any]]) -> dict[str, Any]:
    content_type_count: dict[str, int] = {}
    section_level_count: dict[str, int] = {}

    for section in sections:
        content_type = section["content_type"]
        section_level = section["section_level"]

        content_type_count[content_type] = content_type_count.get(content_type, 0) + 1
        section_level_count[section_level] = section_level_count.get(section_level, 0) + 1

    validation_issues = validate_sections(sections)

    return {
        "total_sections": len(sections),
        "total_article_sections": sum(
            1 for s in sections if s["section_level"] == "article"
        ),
        "total_non_article_sections": sum(
            1 for s in sections if s["section_level"] == "non_article"
        ),
        "content_type_count": content_type_count,
        "section_level_count": section_level_count,
        "sections_with_tables": [
            {
                "section_id": s["section_id"],
                "title": s["title"],
                "page_start": s["page_start"],
                "page_end": s["page_end"],
            }
            for s in sections
            if s["has_table"]
        ],
        "sections_with_formulas": [
            {
                "section_id": s["section_id"],
                "title": s["title"],
                "page_start": s["page_start"],
                "page_end": s["page_end"],
            }
            for s in sections
            if s["has_formula"]
        ],
        "sections_with_scoring_rules": [
            {
                "section_id": s["section_id"],
                "title": s["title"],
                "page_start": s["page_start"],
                "page_end": s["page_end"],
            }
            for s in sections
            if s["has_scoring_rule"]
        ],
        "sections_with_thresholds": [
            {
                "section_id": s["section_id"],
                "title": s["title"],
                "page_start": s["page_start"],
                "page_end": s["page_end"],
            }
            for s in sections
            if s["has_thresholds"]
        ],
        "sections_need_structured_extraction": [
            {
                "section_id": s["section_id"],
                "title": s["title"],
                "content_type": s["content_type"],
                "page_start": s["page_start"],
                "page_end": s["page_end"],
            }
            for s in sections
            if s["needs_structured_extraction"]
        ],
        "validation_issues": validation_issues,
    }


def main() -> None:
    config = load_yaml(CONFIG_PATH)

    pages_path = Path(config["input"]["pages"])
    pages = load_json(pages_path)

    target_content_types = config["target_content_types"]

    line_records = pages_to_line_records(
        pages=pages,
        target_content_types=target_content_types,
    )

    structured_sections = build_structured_sections(line_records)
    structure_report = build_structure_report(structured_sections)

    save_json(line_records, Path(config["output"]["line_records"]))
    save_json(structured_sections, Path(config["output"]["structured_sections"]))
    save_json(structure_report, Path(config["output"]["structure_report"]))

    print("Structure parsing completed.")
    print(f"Line records: {len(line_records)}")
    print(f"Structured sections: {structure_report['total_sections']}")
    print(f"Article sections: {structure_report['total_article_sections']}")
    print(f"Non-article sections: {structure_report['total_non_article_sections']}")
    print(f"Validation issues: {len(structure_report['validation_issues'])}")


if __name__ == "__main__":
    main()