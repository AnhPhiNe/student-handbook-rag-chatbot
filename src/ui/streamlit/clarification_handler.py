from __future__ import annotations

import re
import unicodedata
from typing import Any

from .session_manager import (
    clear_pending_clarification,
    get_pending_clarification,
    set_pending_clarification,
)


def build_pipeline_query(user_query: str) -> tuple[str, bool]:
    """Combine a clarification answer with the previous ambiguous query."""
    pending = get_pending_clarification()
    cleaned_query = user_query.strip()

    if not pending:
        return cleaned_query, False

    previous_query = str(pending.get("original_query") or "").strip()
    clear_pending_clarification()

    if not previous_query:
        return cleaned_query, True

    if _looks_like_new_question(cleaned_query):
        return cleaned_query, False

    return f"{previous_query} {cleaned_query}".strip(), True


def update_clarification_state(pipeline_query: str, result: dict[str, Any]) -> None:
    if _needs_clarification(result):
        set_pending_clarification(
            original_query=pipeline_query,
            question=str(result.get("answer") or "").strip(),
        )
    else:
        clear_pending_clarification()


def _needs_clarification(result: dict[str, Any]) -> bool:
    return (
        result.get("status") == "needs_clarification"
        or result.get("clarification_needed") is True
    )


def _looks_like_new_question(text: str) -> bool:
    ascii_text = _ascii_text(text)
    tokens = re.findall(r"[a-z0-9]+", ascii_text)
    if len(tokens) < 5:
        return False

    question_patterns = [
        "la gi",
        "bao nhieu",
        "nhu the nao",
        "o dau",
        "khi nao",
        "can gi",
        "can mau",
        "cong thuc",
        "dieu kien",
        "quy trinh",
        "thu tuc",
        "email",
        "so dien thoai",
        "gpa",
        "diem ren luyen",
    ]
    if "?" in text:
        return True

    return any(pattern in ascii_text for pattern in question_patterns)


def _ascii_text(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    stripped = re.sub(r"[^a-zA-Z0-9]+", " ", stripped)
    return re.sub(r"\s+", " ", stripped.lower()).strip()
