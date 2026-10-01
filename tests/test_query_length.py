from pathlib import Path

import pytest
from fastapi import HTTPException

from src.api.chat_controls import max_query_chars, validate_chat_query


@pytest.mark.parametrize("character", ["x", "ế", "🙂"])
def test_default_query_limit_accepts_2000_without_truncation(monkeypatch, character):
    monkeypatch.delenv("STUDENT_RAG_MAX_QUERY_CHARS", raising=False)
    question = character * 2000
    assert max_query_chars() == 2000
    assert validate_chat_query(question) == question
    with pytest.raises(HTTPException) as rejected:
        validate_chat_query(question + character)
    assert rejected.value.status_code == 400
    assert rejected.value.detail == "Query must be at most 2000 characters"


def test_query_limit_preserves_trim_and_explicit_override(monkeypatch):
    monkeypatch.setenv("STUDENT_RAG_MAX_QUERY_CHARS", "10")
    assert validate_chat_query("  " + "ế" * 10 + "  ") == "ế" * 10
    with pytest.raises(HTTPException):
        validate_chat_query("ế" * 11)


def test_env_example_matches_default_query_limit(monkeypatch):
    monkeypatch.delenv("STUDENT_RAG_MAX_QUERY_CHARS", raising=False)
    example = Path(".env.example").read_text(encoding="utf-8")
    assert f"STUDENT_RAG_MAX_QUERY_CHARS={max_query_chars()}" in example
