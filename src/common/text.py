"""Accent-insensitive text folding shared by the routing and lookup layers."""

import re
import unicodedata
from typing import Any


def fold_text(value: Any, keep: str = "") -> str:
    """Lowercase, drop Vietnamese diacritics (đ -> d) and collapse every run of
    characters outside ``[a-z0-9]`` and ``keep`` into one space."""

    text = str(value or "").lower().replace("đ", "d")
    text = "".join(
        char
        for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )
    return re.sub(rf"[^a-z0-9{re.escape(keep)}]+", " ", text).strip()


def slot_values(value: Any) -> list[Any]:
    """Return supplied slot choices without collapsing a list to one value."""

    if isinstance(value, list):
        return [item for item in value if item is not None and str(item).strip()]
    if value is None or not str(value).strip():
        return []
    return [value]
