import re
from typing import Any


def normalize_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def join_non_empty(parts: list[str], sep: str = "\n") -> str:
    return sep.join([part.strip() for part in parts if part and part.strip()])


def format_source_pages(pages: list[int]) -> str:
    if not pages:
        return "Không rõ trang"

    if len(pages) == 1:
        return f"Trang {pages[0]}"

    return f"Trang {min(pages)}-{max(pages)}"


def source_page_range(start: int, end: int) -> list[int]:
    return list(range(start, end + 1))


def get_source_pages_from_item(item: dict[str, Any]) -> list[int]:
    if "source_pages" in item and item["source_pages"]:
        return item["source_pages"]

    if "page_start" in item and "page_end" in item:
        return source_page_range(item["page_start"], item["page_end"])

    return []