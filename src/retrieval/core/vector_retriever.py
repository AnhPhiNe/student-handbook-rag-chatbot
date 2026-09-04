import torch
from sentence_transformers import SentenceTransformer


def get_device() -> str:
    """Select the best available embedding inference device."""

    return "cuda" if torch.cuda.is_available() else "cpu"


def load_embedding_model(model_name: str) -> SentenceTransformer:
    """Load and configure the sentence embedding model."""

    return SentenceTransformer(model_name, device=get_device())
