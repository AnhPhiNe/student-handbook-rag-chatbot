import torch
from sentence_transformers import SentenceTransformer


def get_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def load_embedding_model(model_name: str) -> SentenceTransformer:
    device = get_device()
    model = SentenceTransformer(model_name, device=device)
    return model


def encode_texts(
    model: SentenceTransformer,
    texts: list[str],
    batch_size: int = 8,
    normalize_embeddings: bool = True,
) -> list[list[float]]:
    embeddings = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=normalize_embeddings,
        show_progress_bar=True,
    )

    return embeddings.tolist()