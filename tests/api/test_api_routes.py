from __future__ import annotations

import unittest

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - exercised only in minimal runtimes.
    TestClient = None

if TestClient is not None:
    from src.api.deps import get_answer_service
    from src.api.main import app


class FakeAnswerService:
    def answer(self, query: str) -> dict:
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


class ApiRoutesTest(unittest.TestCase):
    def setUp(self) -> None:
        if TestClient is None:
            self.skipTest("fastapi is not installed in this runtime")
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
        response = self.client.get("/health/artifacts")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn(payload["status"], {"ok", "missing_artifacts"})
        paths = {item["path"] for item in payload["required_artifacts"]}
        self.assertIn("configs/phase8_answer_generation.yaml", paths)
        self.assertIn("data/vectorstore/chroma", paths)

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


if __name__ == "__main__":
    unittest.main()
