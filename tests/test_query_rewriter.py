from __future__ import annotations

import unittest
from unittest.mock import patch

from src.generation.query_rewriter import QueryRewriter


class FakeRewriteClient:
    def __init__(self, text: str) -> None:
        self.text = text
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> dict:
        self.prompts.append(prompt)
        return {"ok": True, "text": self.text}


class QueryRewriterTest(unittest.TestCase):
    def test_disabled_rewriter_keeps_original_query(self) -> None:
        rewriter = QueryRewriter(enabled=False)

        result = rewriter.rewrite("email phong dao tao la gi")

        self.assertEqual(result.effective_query, "email phong dao tao la gi")
        self.assertFalse(result.llm_called)
        self.assertEqual(result.reason, "disabled")

    def test_enabled_without_api_key_skips_rewrite(self) -> None:
        rewriter = QueryRewriter(enabled=True, api_key_env_var="QUERY_REWRITER_API_KEY")

        with patch.dict("os.environ", {}, clear=True):
            result = rewriter.rewrite("email phong dao tao la gi")

        self.assertEqual(result.effective_query, "email phong dao tao la gi")
        self.assertFalse(result.llm_called)
        self.assertEqual(result.reason, "missing_QUERY_REWRITER_API_KEY")

    def test_rewrites_accentless_query_when_confident(self) -> None:
        client = FakeRewriteClient(
            '{"normalized_query":"Email Phòng Đào tạo là gì?",'
            '"needs_clarification":false,'
            '"clarification_question":null,'
            '"confidence":"high",'
            '"reason":"accent_restoration"}'
        )
        rewriter = QueryRewriter(enabled=True, client=client)

        with patch.dict("os.environ", {"QUERY_REWRITER_API_KEY": "test-key"}):
            result = rewriter.rewrite("email phong dao tao la gi")

        self.assertEqual(result.effective_query, "Email Phòng Đào tạo là gì?")
        self.assertEqual(result.rewritten_query, "Email Phòng Đào tạo là gì?")
        self.assertTrue(result.changed)
        self.assertTrue(result.llm_called)
        self.assertEqual(len(client.prompts), 1)

    def test_returns_clarification_when_llm_marks_ambiguous(self) -> None:
        client = FakeRewriteClient(
            '{"normalized_query":null,'
            '"needs_clarification":true,'
            '"clarification_question":"Bạn muốn hỏi điều kiện học bổng, hồ sơ hay đơn vị liên hệ?",'
            '"confidence":"medium",'
            '"reason":"ambiguous_scholarship_scope"}'
        )
        rewriter = QueryRewriter(enabled=True, client=client)

        with patch.dict("os.environ", {"QUERY_REWRITER_API_KEY": "test-key"}):
            result = rewriter.rewrite("hoc bong hoi ai")

        self.assertTrue(result.needs_clarification)
        self.assertIn("học bổng", result.clarification_question or "")
        self.assertEqual(result.effective_query, "hoc bong hoi ai")

    def test_does_not_call_llm_for_clear_accented_query(self) -> None:
        client = FakeRewriteClient("{}")
        rewriter = QueryRewriter(enabled=True, client=client)

        with patch.dict("os.environ", {"QUERY_REWRITER_API_KEY": "test-key"}):
            result = rewriter.rewrite("Email Phòng Đào tạo là gì?")

        self.assertEqual(result.reason, "not_triggered")
        self.assertFalse(result.llm_called)
        self.assertEqual(len(client.prompts), 0)


if __name__ == "__main__":
    unittest.main()
