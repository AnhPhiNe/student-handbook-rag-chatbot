import os
import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture(autouse=True)
def mock_env_vars():
    """Mock essential environment variables for testing isolation."""
    env_vars = {
        "STUDENT_RAG_ROUTER_MODEL": "qwen/qwen3.6-27b",
        "STUDENT_RAG_ROUTER_REASONING_EFFORT": "none",
        "STUDENT_RAG_ROUTER_MAX_OUTPUT_TOKENS": "384",
        "GROQ_API_KEY": "test_groq_key",
        "GEMINI_API_KEY": "test_gemini_key",
        "MONGO_URI": "mongodb://localhost:27017/",
        "QDRANT_URL": "http://localhost:6333",
        "LANGFUSE_PUBLIC_KEY": "test_public",
        "LANGFUSE_SECRET_KEY": "test_secret",
        "LANGFUSE_HOST": "https://us.cloud.langfuse.com",
    }
    with patch.dict(os.environ, env_vars):
        yield

@pytest.fixture(autouse=True)
def mock_langfuse():
    """Mock Langfuse client to prevent telemetry emission during tests."""
    with patch("langfuse.Langfuse", autospec=True) as mock_lf:
        mock_instance = MagicMock()
        mock_lf.return_value = mock_instance
        yield mock_instance
