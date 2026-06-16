from __future__ import annotations

import time
import unittest

from src.generation.gemini_client import GeminiClient


class _SlowStreamModels:
    def generate_content_stream(self, **kwargs):
        time.sleep(0.05)
        yield type("Chunk", (), {"text": "late"})()


class _FakeClient:
    models = _SlowStreamModels()


class GeminiClientTest(unittest.TestCase):
    def test_streaming_call_times_out_without_chunks(self) -> None:
        client = object.__new__(GeminiClient)
        client._client = _FakeClient()
        client._config = object()
        client.model_name = "fake-model"
        client.request_timeout_seconds = 0.01

        with self.assertRaises(TimeoutError):
            list(client._generate_stream_once("prompt"))


if __name__ == "__main__":
    unittest.main()
