from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import src.retrieval.core.hybrid_pipeline as hybrid_pipeline
import src.services.answer_service as answer_service_module
from src.services.answer_service import AnswerService


def test_answer_service_initializes_pipeline_once_under_concurrency(monkeypatch) -> None:
    calls = 0
    calls_lock = Lock()

    class FakePipeline:
        def __init__(self, **kwargs):
            nonlocal calls
            with calls_lock:
                calls += 1
            time.sleep(0.02)

    monkeypatch.setattr(answer_service_module, "AnswerPipeline", FakePipeline)
    service = AnswerService()

    with ThreadPoolExecutor(max_workers=8) as pool:
        pipelines = list(pool.map(lambda _: service._get_pipeline(), range(16)))

    assert calls == 1
    assert all(pipeline is pipelines[0] for pipeline in pipelines)


def test_global_retriever_initializes_once_under_concurrency(monkeypatch) -> None:
    calls = 0
    calls_lock = Lock()

    class FakeRetriever:
        def __init__(self, *args, **kwargs):
            nonlocal calls
            with calls_lock:
                calls += 1
            time.sleep(0.02)

    monkeypatch.setattr(hybrid_pipeline, "_GLOBAL_RETRIEVER", None)
    monkeypatch.setattr(hybrid_pipeline, "ChildParentHybridRetriever", FakeRetriever)
    monkeypatch.setattr(
        "src.common.env_loader.load_project_env",
        lambda: None,
    )
    monkeypatch.setattr(
        hybrid_pipeline,
        "require_qdrant_collection_name",
        lambda: "student_handbook_semantic_v32",
    )
    monkeypatch.setenv("QDRANT_URL", "https://example.invalid")
    monkeypatch.setenv("QDRANT_API_KEY", "test-key")

    with ThreadPoolExecutor(max_workers=8) as pool:
        retrievers = list(
            pool.map(lambda _: hybrid_pipeline.initialize_hybrid_retriever(), range(16))
        )

    assert calls == 1
    assert all(retriever is retrievers[0] for retriever in retrievers)
