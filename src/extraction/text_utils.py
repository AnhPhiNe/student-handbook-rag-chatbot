import re
import unicodedata
from typing import Any


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def get_pages_by_type(
    pages: list[dict[str, Any]],
    content_type: str,
) -> list[dict[str, Any]]:
    return [page for page in pages if page.get("content_type") == content_type]


def source_page_range(start: int, end: int) -> list[int]:
    return list(range(start, end + 1))


def extract_first_line(block: str) -> str:
    for line in block.splitlines():
        line = line.strip()
        if line:
            return line

    return "Unknown"
