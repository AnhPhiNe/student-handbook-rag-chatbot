from __future__ import annotations

import re
from typing import Any


_ARTICLE_LABEL_PATTERN = re.compile(
    r"(?<![A-Za-zÀ-ỹ])(?:Điều|Dieu)[\s_-]*(\d+[a-z]?)\b",
    re.IGNORECASE,
)
_ARTICLE_HEADING_PATTERN = re.compile(
    r"^\s*(?:Điều|Dieu)[\s_-]*(\d+[a-z]?)\b",
    re.IGNORECASE,
)
_BARE_ARTICLE_NUMBER_PATTERN = re.compile(r"^\s*(\d+[a-z]?)\s*$", re.IGNORECASE)


def normalize_article_label(*values: Any) -> str | None:
    """Return a canonical article label from authoritative source metadata.

    Callers should pass source-owned fields such as ``article``, ``title`` or
    the source heading. Full body text is intentionally not scanned because a
    cross-reference inside an article must not become that source's identity.
    """

    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        bare_match = _BARE_ARTICLE_NUMBER_PATTERN.fullmatch(text)
        match = bare_match or _ARTICLE_LABEL_PATTERN.search(text)
        if match:
            return f"Điều {match.group(1).lower()}"
    return None


def article_label_from_heading(value: Any) -> str | None:
    """Extract an article label only when a source heading starts with it."""

    match = _ARTICLE_HEADING_PATTERN.search(str(value or ""))
    if not match:
        return None
    return f"Điều {match.group(1).lower()}"
