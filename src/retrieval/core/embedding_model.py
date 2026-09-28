"""BGE-M3 embeddings from DeepInfra's OpenAI-compatible API.

The service returns the same vectors as the local sentence-transformers
BGE-M3 (cosine 1.00000 on handbook text, measured 2026-09-29), so collections
built before the switch stay valid. Running the model locally cost the HF
Space its RAM and CPU; the API costs about 1-2 s per query instead.

A query uses a short timeout and one retry; when it still fails the retriever
falls back to BM25. Documents (the index build) go in parallel batches with
more retries, since nobody waits on them.
"""
from __future__ import annotations

import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from typing import Any

import requests


class EmbeddingClient:
    def __init__(self, config: dict[str, Any], post=requests.post) -> None:
        self.model_name = str(config["model_name"])
        self.api_url = str(config["api_url"])
        key_env = str(config.get("api_key_env_var") or "DEEPINFRA_API_KEY")
        self.api_key = (os.environ.get(key_env) or "").strip()
        if not self.api_key:
            raise RuntimeError(f"{key_env} must be set to embed with {self.model_name}.")
        self.normalize = bool(config.get("normalize_embeddings", True))
        self.query_timeout = float(config.get("query_timeout_seconds", 5))
        self.query_retries = int(config.get("query_retries", 1))
        self.batch_size = int(config.get("document_batch_size", 64))
        self.concurrency = int(config.get("document_concurrency", 8))
        self._post = post

    def embed_query(self, text: str) -> list[float]:
        return self._request([text], timeout=self.query_timeout, retries=self.query_retries)[0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        batches = [texts[i:i + self.batch_size] for i in range(0, len(texts), self.batch_size)]
        with ThreadPoolExecutor(self.concurrency) as pool:
            results = pool.map(lambda batch: self._request(batch, timeout=180, retries=4), batches)
            return [vector for batch in results for vector in batch]

    def _request(self, texts: list[str], *, timeout: float, retries: int) -> list[list[float]]:
        for attempt in range(retries + 1):
            try:
                response = self._post(
                    self.api_url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"model": self.model_name, "input": texts, "encoding_format": "float"},
                    timeout=timeout,
                )
                response.raise_for_status()
                data = sorted(response.json()["data"], key=lambda item: item["index"])
                vectors = [list(map(float, item["embedding"])) for item in data]
                if len(vectors) != len(texts):
                    raise ValueError("Embedding response does not match its input.")
                return [self._normalized(v) for v in vectors] if self.normalize else vectors
            except (requests.RequestException, KeyError, ValueError):
                if attempt == retries:
                    raise
                time.sleep(min(2 ** attempt, 8))
        raise AssertionError("unreachable")

    @staticmethod
    def _normalized(vector: list[float]) -> list[float]:
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


@lru_cache(maxsize=4)
def _cached_client(frozen_config: tuple[tuple[str, Any], ...]) -> EmbeddingClient:
    return EmbeddingClient(dict(frozen_config))


def load_embedding_client(config: dict[str, Any]) -> EmbeddingClient:
    """One process-wide client per embedding configuration."""
    return _cached_client(tuple(sorted(config.items())))
