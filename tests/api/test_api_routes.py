from __future__ import annotations

import unittest
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - exercised only in minimal runtimes.
    TestClient = None

if TestClient is not None:
    from src.api import chat_controls
    from src.api.deps import get_answer_service
    from src.api.main import app


class FakeAnswerService:
    def answer(self, query: str, chat_history: list | None = None, cohort: str | None = None, langfuse_trace_id: str | None = None) -> dict:
        return {
            "query": query,
            "answer": "Email Phong Dao tao la pdt@example.edu.vn.",
            "status": "answered",
            "intent": "office_query",
            "strategy": "structured_lookup",
            "retrieval_query": query,
            "citations": [{"source": "directory"}],
            "citations_used": [{"source": "directory", "page": 1}],
            "llm_called": False,
            "used_cache": True,
            "clarification_needed": False,
            "context_used": "short context",
            "error_type": None,
            "error_message": None,
        }

    def answer_stream(self, query: str, chat_history: list | None = None, cohort: str | None = None, langfuse_trace_id: str | None = None):
        yield {
            "type": "metadata",
            "status": "answered",
            "intent": "office_query",
            "strategy": "structured_lookup",
            "citations_used": [{"source": "directory", "page": 1}],
            "llm_called": False,
        }
        yield {"type": "token", "text": f"streamed: {query}"}
        yield {"type": "done"}


class ApiRoutesTest(unittest.TestCase):
    def setUp(self) -> None:
        if TestClient is None:
            self.skipTest("fastapi is not installed in this runtime")
        chat_controls._RATE_LIMIT_BUCKETS.clear()
        app.dependency_overrides[get_answer_service] = lambda: FakeAnswerService()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()

    def test_health_does_not_require_answer_service(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "service": "student_handbook_rag",
                "version": "0.1.0",
            },
        )

    def test_artifact_health_reports_required_paths(self) -> None:
        with patch.dict(
            "os.environ",
            {"VECTORDB_PROVIDER": "chroma", "STUDENT_RAG_ADMIN_API_KEY": "secret"},
        ):
            response = self.client.get(
                "/health/artifacts",
                headers={"X-Admin-API-Key": "secret"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn(payload["status"], {"ok", "missing_artifacts"})
        paths = {item["path"] for item in payload["required_artifacts"]}
        self.assertIn("configs/answer_generation.yaml", paths)
        self.assertIn("data/vectorstore/chroma", paths)

    def test_artifact_health_requires_admin_key(self) -> None:
        with patch.dict("os.environ", {"STUDENT_RAG_ADMIN_API_KEY": "secret"}):
            response = self.client.get("/health/artifacts")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Admin API key required")

    def test_artifact_health_uses_qdrant_env_for_cloud_provider(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "VECTORDB_PROVIDER": "qdrant_cloud",
                "QDRANT_URL": "https://example.qdrant.io",
                "QDRANT_API_KEY": "test-key",
                "STUDENT_RAG_ADMIN_API_KEY": "secret",
            },
        ):
            response = self.client.get(
                "/health/artifacts",
                headers={"X-Admin-API-Key": "secret"},
            )

        self.assertEqual(response.status_code, 200)
        paths = {item["path"] for item in response.json()["required_artifacts"]}
        self.assertIn("QDRANT_URL", paths)
        self.assertIn("QDRANT_API_KEY", paths)
        self.assertNotIn("data/vectorstore/chroma", paths)

    def test_chat_maps_answer_service_response_without_debug(self) -> None:
        response = self.client.post(
            "/chat",
            json={"query": "Email Phong Dao tao la gi?"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "answered")
        self.assertEqual(payload["intent"], "office_query")
        self.assertEqual(payload["strategy"], "structured_lookup")
        self.assertEqual(payload["citations_used"], [{"source": "directory", "page": 1}])
        self.assertFalse(payload["llm_called"])
        self.assertTrue(payload["used_cache"])
        self.assertIsInstance(payload["request_id"], str)
        self.assertIsInstance(payload["latency_ms"], float)
        self.assertIsNone(payload["debug"])

    def test_chat_includes_limited_debug_when_requested(self) -> None:
        with patch.dict("os.environ", {"STUDENT_RAG_SHOW_DEBUG": "true"}):
            response = self.client.post(
                "/chat",
                json={"query": "Email Phong Dao tao la gi?", "include_debug": True},
            )

        self.assertEqual(response.status_code, 200)
        debug = response.json()["debug"]
        self.assertEqual(debug["retrieval_query"], "Email Phong Dao tao la gi?")
        self.assertEqual(debug["context_used_length"], len("short context"))
        self.assertEqual(debug["citations_count"], 1)
        self.assertEqual(debug["citations_used_count"], 1)
        self.assertIsInstance(debug["request_id"], str)
        self.assertIsInstance(debug["latency_ms"], float)
        self.assertNotIn("context_used", debug)

    def test_chat_rejects_empty_query(self) -> None:
        response = self.client.post("/chat", json={"query": "   "})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Query must not be empty")

    def test_chat_rejects_query_over_configured_length(self) -> None:
        with patch.dict("os.environ", {"STUDENT_RAG_MAX_QUERY_CHARS": "10"}):
            response = self.client.post("/chat", json={"query": "x" * 11})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "Query must be at most 10 characters",
        )

    def test_chat_applies_optional_rate_limit(self) -> None:
        with patch.dict("os.environ", {"STUDENT_RAG_RATE_LIMIT_PER_MINUTE": "1"}):
            first = self.client.post("/chat", json={"query": "Email phong dao tao?"})
            second = self.client.post("/chat", json={"query": "Email phong dao tao?"})

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()["detail"], "Rate limit exceeded")

    def test_chat_returns_busy_when_capacity_is_full(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "STUDENT_RAG_MAX_CONCURRENT_CHAT": "1",
                "STUDENT_RAG_MAX_QUEUE_SIZE": "0",
            },
        ):
            with chat_controls.chat_capacity_slot():
                response = self.client.post(
                    "/chat",
                    json={"query": "Email phong dao tao?"},
                )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"],
            "Hệ thống đang bận, bạn thử lại sau vài giây nhé.",
        )

    def test_chat_capacity_settings_defaults_are_beta_safe(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(chat_controls.chat_capacity_settings(), (3, 10, 15.0))

    def test_chat_rate_limit_defaults_to_10(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(chat_controls.rate_limit_per_minute(), 10)

    def test_chat_stream_rejects_empty_query(self) -> None:
        response = self.client.post("/chat/stream", json={"query": "   "})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Query must not be empty")

    def test_chat_stream_rejects_query_over_configured_length(self) -> None:
        with patch.dict("os.environ", {"STUDENT_RAG_MAX_QUERY_CHARS": "10"}):
            response = self.client.post("/chat/stream", json={"query": "x" * 11})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json()["detail"],
            "Query must be at most 10 characters",
        )

    def test_chat_and_stream_share_rate_limit(self) -> None:
        with patch.dict("os.environ", {"STUDENT_RAG_RATE_LIMIT_PER_MINUTE": "1"}):
            first = self.client.post("/chat", json={"query": "Email phong dao tao?"})
            second = self.client.post(
                "/chat/stream",
                json={"query": "Email phong dao tao?"},
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()["detail"], "Rate limit exceeded")


if __name__ == "__main__":
    unittest.main()
