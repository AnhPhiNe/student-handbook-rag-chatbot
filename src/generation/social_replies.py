"""Fixed replies for social and out-of-domain queries (configs/social_replies.yaml)."""
from __future__ import annotations

import random
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPLIES_PATH = ROOT / "configs" / "social_replies.yaml"
COHORT_MARK = "{khóa}"


@lru_cache(maxsize=2)
def load_replies(path: str | Path = DEFAULT_REPLIES_PATH) -> dict[str, list[str]]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    replies = {str(kind): [str(text) for text in texts or []] for kind, texts in data.items()}
    for kind, texts in replies.items():
        # Every kind must still have a reply when no cohort is selected.
        if not any(COHORT_MARK not in text for text in texts):
            raise ValueError(f"social reply '{kind}' needs a variant without {COHORT_MARK}")
    return replies


def reply_for(
    kind: str,
    cohort: str | None = None,
    *,
    rng: random.Random | None = None,
    path: str | Path = DEFAULT_REPLIES_PATH,
) -> str:
    """One variant of ``kind``, with the cohort filled in where it is marked."""

    texts = load_replies(path)[kind]
    if not cohort:
        texts = [text for text in texts if COHORT_MARK not in text]
    text = (rng or random).choice(texts)
    return text.replace(COHORT_MARK, cohort or "")
