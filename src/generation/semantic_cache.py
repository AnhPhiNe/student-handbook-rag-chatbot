import time
import uuid
from typing import Any
from pathlib import Path
import chromadb

from src.generation.groq_client import GroqClient


class SemanticCache:
    def __init__(self, config: dict[str, Any], embedding_model: Any):
        self.config = config
        self.enabled = config.get("enabled", False)
        self.max_distance = float(config.get("max_distance", 0.15))
        self.min_query_length = int(config.get("min_query_length", 8))
        self.embedding_model = embedding_model

        if not self.enabled:
            return

        persist_dir = config.get("persist_dir", "data/cache/semantic_cache_chroma")
        collection_name = config.get("collection_name", "semantic_query_cache")

        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        self.chroma_client = chromadb.PersistentClient(
            path=persist_dir, settings=chromadb.Settings(anonymized_telemetry=False)
        )
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name, metadata={"hnsw:space": "cosine"}
        )

        self.verifier_llm = GroqClient(
            model_name=config.get("verifier_model", "llama-3.1-8b-instant"),
            temperature=float(config.get("verifier_temperature", 0.0)),
            max_output_tokens=int(config.get("verifier_max_tokens", 8)),
        )

    def lookup(self, query: str, cohort: str | None = None) -> str | None:
        """Tìm cache_key nếu câu hỏi tương đồng ngữ nghĩa và được LLM phê duyệt."""
        if not self.enabled or len(query.strip()) < self.min_query_length:
            return None

        try:
            # 1. Nhúng câu hỏi
            query_embedding = self.embedding_model.encode(query).tolist()

            # 2. Tìm kiếm trong ChromaDB
            query_kwargs: dict[str, Any] = {
                "query_embeddings": [query_embedding],
                "n_results": 3,
            }
            if cohort:
                query_kwargs["where"] = {"cohort": cohort}

            results = self.collection.query(**query_kwargs)

            if not results["ids"] or not results["ids"][0]:
                return None

            # 3. Duyệt qua các ứng viên
            for idx, distance in enumerate(results["distances"][0]):
                if distance > self.max_distance:
                    continue

                cached_query = results["documents"][0][idx]
                cache_key = results["metadatas"][0][idx].get("cache_key")

                if not cache_key:
                    continue

                # 4. Xác minh bằng LLM
                if self._verify_semantic_match(query, cached_query):
                    print(
                        f"[Semantic Cache] HIT! Distance: {distance:.4f} | New: '{query}' == Cached: '{cached_query}'"
                    )
                    return cache_key

            return None

        except Exception as e:
            print(f"[Semantic Cache] Lookup error: {e}")
            return None

    def store(self, query: str, cache_key: str, cohort: str | None = None) -> None:
        """Lưu vector câu hỏi và cache_key vào ChromaDB."""
        if not self.enabled or len(query.strip()) < self.min_query_length:
            return

        try:
            query_embedding = self.embedding_model.encode(query).tolist()
            metadata = {"cache_key": cache_key, "created_at": time.time()}
            if cohort:
                metadata["cohort"] = cohort

            self.collection.add(
                ids=[str(uuid.uuid4())],
                documents=[query],
                embeddings=[query_embedding],
                metadatas=[metadata],
            )
        except Exception as e:
            print(f"[Semantic Cache] Store error: {e}")

    def _verify_semantic_match(self, new_query: str, cached_query: str) -> bool:
        """Gọi LLM siêu nhỏ để xác minh xem 2 câu hỏi có cùng ý định không."""
        prompt = f"""You are a strict semantic equivalence judge for a university student handbook chatbot.
Are the following two questions asking for the EXACT same information/intent?
If they are slightly different in intent, answer NO.
If you are not 100% sure, answer NO.
Answer with ONLY a single word: YES or NO.

Question 1 (Cached): {cached_query}
Question 2 (New): {new_query}

Answer (YES or NO):"""

        try:
            result = self.verifier_llm.generate(prompt)
            if not result.get("ok"):
                return False

            text = str(result.get("text", "")).strip().upper()
            return text == "YES" or text.startswith("YES")

        except Exception as e:
            print(f"[Semantic Cache] Verification error: {e}")
            return False
