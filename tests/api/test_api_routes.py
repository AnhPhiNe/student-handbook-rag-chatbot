from __future__ import annotations

import json
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
    from src.api.schemas import ArtifactHealthResponse


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
            "query_plan": {
                "schema_version": "v1",
                "context_mode": "standalone",
                "tasks": [
                    {
                        "id": "t1",
                        "question": query,
                        "mode": "structured",
                        "lookup_type": "office",
                        "intent": "direct_value",
                        "cohorts": [cohort or "K51"],
                    }
                ],
            },
            "task_results": [
                {
                    "task_id": "t1",
                    "coverage": "covered",
                    "coverage_by_cohort": {cohort or "K51": "covered"},
                    "evidence": [{"lookup_type": "office"}],
                    "citation_count": 1,
                }
            ],
            "coverage_by_task": {"t1": "covered"},
        }
        yield {"type": "token", "text": f"streamed: {query}"}
        yield {
            "type": "done",
            "citations_used": [{"source": "final", "page": 2}],
        }


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
            {"STUDENT_RAG_ADMIN_API_KEY": "secret"},
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
        self.assertIn("data/processed/amendments/amendments.json", paths)
        self.assertIn("QDRANT_URL", paths)
        self.assertIn("QDRANT_API_KEY", paths)
        self.assertIn("QDRANT_COLLECTION_NAME", paths)

    def test_artifact_health_requires_admin_key(self) -> None:
        with patch.dict("os.environ", {"STUDENT_RAG_ADMIN_API_KEY": "secret"}):
            response = self.client.get("/health/artifacts")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Admin API key required")

    def test_readiness_is_public_and_reports_degraded_without_required_env(self) -> None:
        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "src.api.routes.health.get_bm25_runtime_status",
                return_value={
                    "status": "degraded",
                    "attempts": 3,
                    "error_type": "TimeoutError",
                },
            ),
        ):
            response = self.client.get("/health/readiness")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["service"], "student_handbook_rag")
        self.assertIn(payload["status"], {"ok", "degraded"})
        self.assertIsInstance(payload["ready"], bool)
        self.assertGreaterEqual(payload["missing_count"], 0)
        self.assertEqual(payload["qdrant"]["status"], "not_configured")
        self.assertEqual(payload["mongodb"]["status"], "not_configured")
        self.assertEqual(
            payload["retrieval_mode"],
            "vector_primary_graph_supplement",
        )
        self.assertEqual(
            payload["bm25"],
            {
                "status": "degraded",
                "attempts": 3,
                "error_type": "TimeoutError",
            },
        )

    def test_readiness_stays_ready_when_only_bm25_is_degraded(self) -> None:
        artifact_status = ArtifactHealthResponse(status="ok", required_artifacts=[])
        with (
            patch(
                "src.api.routes.health._artifact_health_response",
                return_value=artifact_status,
            ),
            patch(
                "src.api.routes.health.get_bm25_runtime_status",
                return_value={
                    "status": "degraded",
                    "attempts": 3,
                    "error_type": "TimeoutError",
                },
            ),
            patch(
                "src.api.routes.health.get_dependency_runtime_statuses",
                return_value={
                    "qdrant": {
                        "status": "ready",
                        "error_type": None,
                        "latency_ms": 1.0,
                    },
                    "mongodb": {
                        "status": "ready",
                        "error_type": None,
                        "latency_ms": 1.0,
                    },
                },
            ),
        ):
            response = self.client.get("/health/readiness")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ready"])
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["bm25"]["status"], "degraded")

    def test_readiness_is_not_ready_when_primary_store_probe_fails(self) -> None:
        artifact_status = ArtifactHealthResponse(status="ok", required_artifacts=[])
        with (
            patch(
                "src.api.routes.health._artifact_health_response",
                return_value=artifact_status,
            ),
            patch(
                "src.api.routes.health.get_bm25_runtime_status",
                return_value={
                    "status": "ready",
                    "attempts": 1,
                    "error_type": None,
                },
            ),
            patch(
                "src.api.routes.health.get_dependency_runtime_statuses",
                return_value={
                    "qdrant": {
                        "status": "degraded",
                        "error_type": "TimeoutError",
                        "latency_ms": 1500.0,
                    },
                    "mongodb": {
                        "status": "ready",
                        "error_type": None,
                        "latency_ms": 2.0,
                    },
                },
            ),
        ):
            response = self.client.get("/health/readiness")

        payload = response.json()
        self.assertFalse(payload["ready"])
        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["qdrant"]["error_type"], "TimeoutError")

    def test_artifact_health_uses_qdrant_environment(self) -> None:
        with patch.dict(
            "os.environ",
            {
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

    def test_stream_traces_internal_plan_while_public_metadata_stays_redacted(self) -> None:
        captured_source: dict = {}

        def capture_trace_source(source, **kwargs):
            del kwargs
            captured_source.update(source)
            return {"model": "gemini-3.1-flash-lite"}

        with patch(
            "src.api.routes.chat_stream.build_trace_metadata",
            side_effect=capture_trace_source,
        ):
            response = self.client.post(
                "/chat/stream",
                json={"query": "Email Phòng Đào tạo?", "cohort": "K51"},
            )

        assert response.status_code == 200
        assert "query_plan" not in response.text
        assert "task_results" not in response.text
        assert captured_source["query_plan"]["tasks"][0]["lookup_type"] == "office"
        assert captured_source["coverage_by_task"] == {"t1": "covered"}

    def test_stream_done_exposes_final_citation_order(self) -> None:
        response = self.client.post(
            "/chat/stream",
            json={"query": "Email Phòng Đào tạo?", "cohort": "K51"},
        )

        assert response.status_code == 200
        done_block = next(
            block
            for block in response.text.split("\n\n")
            if block.startswith("event: done")
        )
        done_payload = json.loads(
            next(
                line.removeprefix("data: ")
                for line in done_block.splitlines()
                if line.startswith("data: ")
            )
        )
        assert done_payload["citations_used"] == [{"source": "final", "page": 2}]

    def test_stream_done_uses_terminal_error_status(self) -> None:
        class ErrorStreamService:
            def answer_stream(self, *args, **kwargs):
                yield {"type": "metadata", "status": "streaming"}
                yield {"type": "token", "text": "fallback"}
                yield {
                    "type": "metadata",
                    "status": "api_error",
                    "fallback_reason": "api_error",
                }
                yield {
                    "type": "done",
                    "status": "api_error",
                    "error_type": "RuntimeError",
                    "citations_used": [],
                }

        app.dependency_overrides[get_answer_service] = lambda: ErrorStreamService()
        response = self.client.post(
            "/chat/stream",
            json={"query": "Câu hỏi hợp lệ", "cohort": "K51"},
        )

        done_block = next(
            block
            for block in response.text.split("\n\n")
            if block.startswith("event: done")
        )
        done_payload = json.loads(
            next(
                line.removeprefix("data: ")
                for line in done_block.splitlines()
                if line.startswith("data: ")
            )
        )
        assert done_payload["status"] == "api_error"
        assert done_payload["error_type"] == "RuntimeError"


if __name__ == "__main__":
    unittest.main()
