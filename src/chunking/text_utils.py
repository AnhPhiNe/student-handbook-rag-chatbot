import re


def normalize_text(text: str) -> str:
    """Normalize non-breaking spaces, horizontal whitespace, and blank lines."""
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def join_non_empty(parts: list[str], sep: str = "\n") -> str:
    """Strip, discard empty strings, and join the remaining parts."""
    return sep.join([part.strip() for part in parts if part and part.strip()])


def source_page_range(start: int, end: int) -> list[int]:
    """Return an inclusive page-number range."""
    return list(range(start, end + 1))
