"""The BGE-M3 embedding client, with the HTTP call replaced by a fake."""
from unittest.mock import Mock

import pytest
import requests

from src.retrieval.core.embedding_model import EmbeddingClient

CONFIG = {
    "model_name": "BAAI/bge-m3",
    "api_url": "https://api.example.test/embeddings",
    "api_key_env_var": "TEST_EMBEDDING_KEY",
    "normalize_embeddings": True,
    "query_timeout_seconds": 5,
    "query_retries": 1,
    "document_batch_size": 2,
    "document_concurrency": 2,
}


def _response(vectors: list[list[float]], *, reversed_order: bool = False) -> Mock:
    data = [{"index": i, "embedding": v} for i, v in enumerate(vectors)]
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"data": list(reversed(data)) if reversed_order else data}
    return response


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("TEST_EMBEDDING_KEY", "test-key")


def test_query_vector_is_normalized_and_sent_with_the_short_timeout() -> None:
    post = Mock(return_value=_response([[3.0, 4.0]]))
    client = EmbeddingClient(CONFIG, post=post)

    assert client.embed_query("câu hỏi") == pytest.approx([0.6, 0.8])
    kwargs = post.call_args.kwargs
    assert kwargs["timeout"] == 5
    assert kwargs["json"] == {"model": "BAAI/bge-m3", "input": ["câu hỏi"], "encoding_format": "float"}
    assert kwargs["headers"] == {"Authorization": "Bearer test-key"}


def test_documents_keep_their_order_across_batches_and_response_order() -> None:
    def post(url, *, headers, json, timeout):
        return _response([[float(len(text)), 0.0] for text in json["input"]], reversed_order=True)

    client = EmbeddingClient({**CONFIG, "normalize_embeddings": False}, post=post)
    texts = ["a", "bb", "ccc", "dddd", "eeeee"]

    assert [v[0] for v in client.embed_documents(texts)] == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_query_retries_once_then_raises_for_the_bm25_fallback(monkeypatch) -> None:
    monkeypatch.setattr("src.retrieval.core.embedding_model.time.sleep", lambda _: None)
    post = Mock(side_effect=requests.Timeout("slow"))
    client = EmbeddingClient(CONFIG, post=post)

    with pytest.raises(requests.Timeout):
        client.embed_query("câu hỏi")
    assert post.call_count == 2


def test_missing_key_fails_at_construction(monkeypatch) -> None:
    monkeypatch.delenv("TEST_EMBEDDING_KEY")
    with pytest.raises(RuntimeError, match="TEST_EMBEDDING_KEY"):
        EmbeddingClient(CONFIG, post=Mock())
