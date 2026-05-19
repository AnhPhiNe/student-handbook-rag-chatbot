from typing import Any

from .token_utils import count_tokens_approx
from .text_utils import normalize_text


def create_chunk(
    chunk_id: str,
    chunk_type: str,
    index_mode: str,
    content: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    content = normalize_text(content)

    return {
        "chunk_id": chunk_id,
        "chunk_type": chunk_type,
        "index_mode": index_mode,
        "content": content,
        "token_count_approx": count_tokens_approx(content),
        "metadata": metadata,
    }