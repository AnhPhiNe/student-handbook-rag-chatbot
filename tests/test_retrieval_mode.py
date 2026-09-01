from __future__ import annotations

import pytest

from src.retrieval.core.retrieval_mode import (
    DEFAULT_RETRIEVAL_MODE,
    resolve_retrieval_mode,
)


def test_production_retrieval_mode_defaults_to_vector_graph_contract(
    monkeypatch,
) -> None:
    monkeypatch.delenv("STUDENT_RAG_RETRIEVAL_MODE", raising=False)
    monkeypatch.delenv("STUDENT_RAG_EVAL_RETRIEVAL_MODE", raising=False)
    monkeypatch.delenv("STUDENT_RAG_ALLOW_RETRIEVAL_ABLATION", raising=False)

    assert resolve_retrieval_mode() == DEFAULT_RETRIEVAL_MODE


def test_ablation_mode_requires_explicit_guard(monkeypatch) -> None:
    monkeypatch.setenv("STUDENT_RAG_RETRIEVAL_MODE", "full")
    monkeypatch.delenv("STUDENT_RAG_ALLOW_RETRIEVAL_ABLATION", raising=False)

    with pytest.raises(ValueError, match="evaluation-only"):
        resolve_retrieval_mode()

    monkeypatch.setenv("STUDENT_RAG_ALLOW_RETRIEVAL_ABLATION", "1")
    assert resolve_retrieval_mode() == "full"


def test_runtime_mode_takes_precedence_over_legacy_eval_alias(monkeypatch) -> None:
    monkeypatch.setenv(
        "STUDENT_RAG_RETRIEVAL_MODE",
        DEFAULT_RETRIEVAL_MODE,
    )
    monkeypatch.setenv("STUDENT_RAG_EVAL_RETRIEVAL_MODE", "full")

    assert resolve_retrieval_mode() == DEFAULT_RETRIEVAL_MODE
