from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
from unittest.mock import Mock, patch

from src.retrieval.core.ai_router import AIRouter
from src.retrieval.core.hybrid_pipeline import (
    ChildParentHybridRetriever,
)
from src.retrieval.runtime_config import load_retrieval_runtime_config
from src.retrieval.core.vector_retriever import load_embedding_model
from src.retrieval.vectorstore.mongo_store import get_mongo_store


def test_retrieval_runtime_config_uses_explicit_file(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("STUDENT_RAG_RETRIEVAL_CONFIG", raising=False)
    config_path = tmp_path / "retrieval.yaml"
    config_path.write_text(
        "embedding:\n  model_name: test/model\nruntime:\n  parent_cache_max_entries: 3\n",
        encoding="utf-8",
    )

    config = load_retrieval_runtime_config(config_path)

    assert config["embedding"]["model_name"] == "test/model"
    assert config["runtime"]["parent_cache_max_entries"] == 3


def test_embedding_model_loader_reuses_one_process_instance() -> None:
    model = object()
    load_embedding_model.cache_clear()
    try:
        with (
            patch(
                "src.retrieval.core.vector_retriever.SentenceTransformer",
                return_value=model,
            ) as model_class,
            patch("src.retrieval.core.vector_retriever.get_device", return_value="cpu"),
        ):
            first = load_embedding_model("test/model")
            second = load_embedding_model("test/model")

        assert first is model
        assert second is model
        model_class.assert_called_once_with("test/model", device="cpu")
    finally:
        load_embedding_model.cache_clear()


def test_mongo_store_uses_database_name_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("MONGODB_PARENT_LOOKUP_ENABLED", "true")
    monkeypatch.setenv("MONGODB_URL", "mongodb://example")
    monkeypatch.setenv("MONGODB_DB_NAME", "student_handbook_test")
    monkeypatch.setenv("MONGODB_TIMEOUT_MS", "1234")
    monkeypatch.setenv("MONGODB_FAILURE_BACKOFF_SECONDS", "7")

    with (
        patch("src.retrieval.vectorstore.mongo_store.load_project_env"),
        patch(
            "src.retrieval.vectorstore.mongo_store.require_mongo_parent_collection_name",
            return_value="parents",
        ),
        patch("src.retrieval.vectorstore.mongo_store.MongoDocStore") as store_class,
    ):
        get_mongo_store()

    store_class.assert_called_once_with(
        uri="mongodb://example",
        db_name="student_handbook_test",
        collection_name="parents",
        timeout_ms=1234,
        failure_backoff_seconds=7,
    )


def test_parent_cache_evicts_oldest_entry_at_configured_limit() -> None:
    retriever = ChildParentHybridRetriever.__new__(ChildParentHybridRetriever)
    retriever.parent_cache = OrderedDict()
    retriever.parent_cache_max_entries = 2
    retriever.mongo_store = Mock()
    retriever.mongo_store.get_document_by_id.side_effect = lambda parent_id: {
        "_id": parent_id
    }

    retriever._get_parent("p1")
    retriever._get_parent("p2")
    retriever._get_parent("p3")

    assert list(retriever.parent_cache) == ["p2", "p3"]


def test_router_output_budget_scales_by_task_and_respects_cap() -> None:
    router = AIRouter.__new__(AIRouter)
    router.max_output_tokens = 768
    router.output_tokens_per_task = 640
    router.hard_max_output_tokens = 1600

    assert router._planner_output_token_limit(None) == 768
    assert router._planner_output_token_limit(2) == 1280
    assert router._planner_output_token_limit(3) == 1600
