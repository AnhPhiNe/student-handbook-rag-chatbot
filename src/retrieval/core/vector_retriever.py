from functools import lru_cache

import torch
from sentence_transformers import SentenceTransformer


def get_device() -> str:
    """Select the best available embedding inference device."""

    return "cuda" if torch.cuda.is_available() else "cpu"


@lru_cache(maxsize=4)
def load_embedding_model(model_name: str) -> SentenceTransformer:
    """Return one process-wide embedding model instance per model name."""

    return SentenceTransformer(model_name, device=get_device())
