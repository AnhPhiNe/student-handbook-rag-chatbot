from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services import AnswerService


@lru_cache(maxsize=1)
def get_answer_service() -> "AnswerService":
    """Load the shared AnswerService once per API process."""
    from src.services import AnswerService

    return AnswerService()
