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
    def answer(self, query: str, chat_history: list | None = None, cohort: str | None = None, trace_id: str | None = None) -> dict:
        return {
            "query": query,
            "answer": "Email Phong Dao tao la pdt@example.edu.vn.",
            "status": "answered",
            "intent": "office_query",
            "strategy": "structured_lookup",
            "retrieval_query": query,
            "citations": [{"source": "directory"}],
            "citations_used": [{"source": "directory", "page": 1}],
            "related_references": [{"id": "R1", "title": "Điều 3"}],
            "llm_called": False,
            "used_cache": True,
            "clarification_needed": False,
            "context_used": "short context",
            "error_type": None,
            "error_message": None,
        }

    def answer_stream(self, query: str, chat_history: list | None = None, cohort: str | None = None, trace_id: str | None = None):
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
        self.assertIn("data/processed/retrieval/bm25_index.json", paths)
        self.assertIn("data/vectorstore/chroma", paths)

    def test_artifact_health_requires_admin_key(self) -> None:
        with patch.dict("os.environ", {"STUDENT_RAG_ADMIN_API_KEY": "secret"}):
            response = self.client.get("/health/artifacts")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Admin API key required")

    def test_readiness_is_public_and_reports_degraded_without_required_env(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            response = self.client.get("/health/readiness")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["service"], "student_handbook_rag")
        self.assertIn(payload["status"], {"ok", "degraded"})
        self.assertIsInstance(payload["ready"], bool)
        self.assertGreaterEqual(payload["missing_count"], 0)

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

    def test_artifact_health_uses_qdrant_env_for_qdrant_provider(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "VECTORDB_PROVIDER": "qdrant",
                "QDRANT_URL": "https://example.qdrant.io",
                "QDRANT_API_KEY": "test-key",
                "QDRANT_COLLECTION_NAME": "student_handbook_semantic_v9_candidate",
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
        self.assertIn("QDRANT_COLLECTION_NAME", paths)
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
        self.assertEqual(payload["related_references"], [{"id": "R1", "title": "Điều 3"}])
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
        self.assertIsNone(debug["retrieval_query"])
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
        self.assertEqual(second.headers["Retry-After"], "60")

    def test_chat_rate_limit_separates_browsers_on_the_same_ip(self) -> None:
        first_client = "00000000-0000-4000-8000-000000000001"
        second_client = "00000000-0000-4000-8000-000000000002"
        env = {
            "STUDENT_RAG_RATE_LIMIT_PER_MINUTE": "1",
            "STUDENT_RAG_IP_RATE_LIMIT_PER_MINUTE": "10",
        }
        with patch.dict("os.environ", env):
            first = self.client.post(
                "/chat",
                headers={"X-Client-ID": first_client},
                json={"query": "Email phong dao tao?"},
            )
            second = self.client.post(
                "/chat",
                headers={"X-Client-ID": second_client},
                json={"query": "Email phong dao tao?"},
            )
            repeated = self.client.post(
                "/chat",
                headers={"X-Client-ID": first_client},
                json={"query": "Email phong dao tao?"},
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(repeated.status_code, 429)

    def test_chat_keeps_public_ip_abuse_guard(self) -> None:
        env = {
            "STUDENT_RAG_RATE_LIMIT_PER_MINUTE": "10",
            "STUDENT_RAG_IP_RATE_LIMIT_PER_MINUTE": "2",
        }
        with patch.dict("os.environ", env):
            responses = [
                self.client.post(
                    "/chat",
                    headers={
                        "X-Client-ID": f"00000000-0000-4000-8000-{index:012d}",
                    },
                    json={"query": "Email phong dao tao?"},
                )
                for index in range(1, 4)
            ]

        self.assertEqual([response.status_code for response in responses], [200, 200, 429])

    def test_rate_limit_ignores_forwarded_for_by_default(self) -> None:
        env = {
            "STUDENT_RAG_RATE_LIMIT_PER_MINUTE": "10",
            "STUDENT_RAG_IP_RATE_LIMIT_PER_MINUTE": "1",
        }
        with patch.dict("os.environ", env, clear=False):
            first = self.client.post(
                "/chat",
                headers={
                    "X-Client-ID": "00000000-0000-4000-8000-000000000001",
                    "X-Forwarded-For": "203.0.113.10",
                },
                json={"query": "Email phong dao tao?"},
            )
            second = self.client.post(
                "/chat",
                headers={
                    "X-Client-ID": "00000000-0000-4000-8000-000000000002",
                    "X-Forwarded-For": "203.0.113.11",
                },
                json={"query": "Email phong dao tao?"},
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)

    def test_rate_limit_can_trust_forwarded_for_when_enabled(self) -> None:
        env = {
            "STUDENT_RAG_RATE_LIMIT_PER_MINUTE": "10",
            "STUDENT_RAG_IP_RATE_LIMIT_PER_MINUTE": "1",
            "STUDENT_RAG_TRUST_PROXY_HEADERS": "true",
        }
        with patch.dict("os.environ", env, clear=False):
            first = self.client.post(
                "/chat",
                headers={
                    "X-Client-ID": "00000000-0000-4000-8000-000000000001",
                    "X-Forwarded-For": "203.0.113.10, 10.16.0.1",
                },
                json={"query": "Email phong dao tao?"},
            )
            second = self.client.post(
                "/chat",
                headers={
                    "X-Client-ID": "00000000-0000-4000-8000-000000000002",
                    "X-Forwarded-For": "203.0.113.11, 10.16.0.1",
                },
                json={"query": "Email phong dao tao?"},
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)

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

    def test_chat_rate_limit_defaults_to_5(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(chat_controls.rate_limit_per_minute(), 5)
            self.assertEqual(chat_controls.ip_rate_limit_per_minute(), 120)

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
        client_id = "00000000-0000-4000-8000-000000000003"
        with patch.dict("os.environ", {"STUDENT_RAG_RATE_LIMIT_PER_MINUTE": "1"}):
            first = self.client.post(
                "/chat",
                headers={"X-Client-ID": client_id},
                json={"query": "Email phong dao tao?"},
            )
            second = self.client.post(
                "/chat/stream",
                headers={"X-Client-ID": client_id},
                json={"query": "Email phong dao tao?"},
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)
        self.assertEqual(second.json()["detail"], "Rate limit exceeded")


if __name__ == "__main__":
    unittest.main()
