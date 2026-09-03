import transformers
from sentence_transformers import CrossEncoder

# Tắt cảnh báo "overflowing tokens are not returned" của Tokenizer
transformers.logging.set_verbosity_error()


class LocalReranker:
    _instance = None

    def __new__(cls, model_name: str = "itdainb/PhoRanker"):
        if cls._instance is None:
            cls._instance = super(LocalReranker, cls).__new__(cls)
            cls._instance._init(model_name)
        return cls._instance

    def _init(self, model_name: str):
        print(f"[Reranker] Loading local Cross-Encoder model: {model_name}...")
        self.model = CrossEncoder(model_name, max_length=256)
        print("[Reranker] Model loaded successfully.")

def get_local_reranker() -> LocalReranker:
    return LocalReranker()
