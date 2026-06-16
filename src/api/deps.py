from __future__ import annotations

import os
import secrets
from functools import lru_cache
from typing import TYPE_CHECKING

from fastapi import Header, HTTPException

if TYPE_CHECKING:
    from src.services import AnswerService


ADMIN_API_KEY_ENV = "STUDENT_RAG_ADMIN_API_KEY"


def verify_admin_api_key(
    x_admin_api_key: str | None = Header(default=None, alias="X-Admin-API-Key"),
) -> None:
    expected_key = os.getenv(ADMIN_API_KEY_ENV, "").strip()
    if not expected_key or not x_admin_api_key:
        raise HTTPException(status_code=403, detail="Admin API key required")
    if not secrets.compare_digest(x_admin_api_key, expected_key):
        raise HTTPException(status_code=403, detail="Admin API key required")


@lru_cache(maxsize=1)
def get_answer_service() -> "AnswerService":
    """Load the shared AnswerService once per API process."""
    from src.services import AnswerService

    return AnswerService()
