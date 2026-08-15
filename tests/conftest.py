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
        "LANGCHAIN_API_KEY": "test_langsmith_key",
        "LANGCHAIN_TRACING_V2": "true",
        "LANGCHAIN_PROJECT": "test-hcmue-student-handbook-rag",
    }
    with patch.dict(os.environ, env_vars):
        yield

@pytest.fixture(autouse=True)
def mock_langsmith():
    """Mock LangSmith helpers to prevent telemetry emission during tests."""
    with patch("src.api.langsmith_helper.push_trace_to_langsmith") as mock_push, \
         patch("src.api.langsmith_helper.push_feedback_to_langsmith") as mock_feedback, \
         patch("src.api.langsmith_helper.get_langsmith_client") as mock_client:
        mock_client.return_value = None
        yield {
            "push": mock_push,
            "feedback": mock_feedback,
            "client": mock_client,
        }
