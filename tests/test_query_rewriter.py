from __future__ import annotations

import unittest
import os
from types import SimpleNamespace
from unittest.mock import patch

os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_API_KEY"] = ""
os.environ["LANGCHAIN_API_KEY"] = ""

from src.generation.query_rewriter import QueryRewriter


class FakeRewriteClient:
    """Fake đúng interface Groq: client.chat.completions.create(...)."""

    def __init__(self, text: str | list[str]) -> None:
        self.responses = [text] if isinstance(text, str) else list(text)
        self.prompts: list[str] = []
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create_completion)
        )

    def _create_completion(self, **kwargs):
        self.calls.append(kwargs)
        self.prompts.append(kwargs["messages"][0]["content"])
        if not self.responses:
            raise AssertionError("FakeRewriteClient has no response left")
        message = SimpleNamespace(content=self.responses.pop(0))
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])


class QueryRewriterTest(unittest.TestCase):
    def test_disabled_rewriter_keeps_original_query(self) -> None:
        rewriter = QueryRewriter(enabled=False)

        result = rewriter.rewrite("email phong dao tao la gi")

        self.assertEqual(result.effective_query, "email phong dao tao la gi")
        self.assertFalse(result.llm_called)
        self.assertEqual(result.reason, "disabled")

    @patch("src.generation.query_rewriter.load_project_env")
    def test_enabled_without_api_key_skips_rewrite(self, mock_load_env) -> None:
        with patch.dict("os.environ", {}, clear=True):
            rewriter = QueryRewriter(enabled=True, api_key_env_var="QUERY_REWRITER_API_KEY")
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
        with patch.dict("os.environ", {"QUERY_REWRITER_API_KEY": "test-key"}):
            rewriter = QueryRewriter(enabled=True, client=client)
            result = rewriter.rewrite("email phong dao tao la gi")

        self.assertEqual(result.effective_query, "Email Phòng Đào tạo là gì?")
        self.assertEqual(result.rewritten_query, "Email Phòng Đào tạo là gì?")
        self.assertTrue(result.changed)
        self.assertTrue(result.llm_called)
        self.assertEqual(len(client.prompts), 1)

    def test_preserves_user_meaning_for_casual_accentless_query(self) -> None:
        client = FakeRewriteClient(
            '{"normalized_query":"Cậu biết Khoa Tiếng Trung ở đâu không?",'
            '"needs_clarification":false,'
            '"clarification_question":null,'
            '"confidence":"high",'
            '"reason":"accent_restoration"}'
        )
        with patch.dict("os.environ", {"QUERY_REWRITER_API_KEY": "test-key"}):
            rewriter = QueryRewriter(enabled=True, client=client)
            result = rewriter.rewrite("cau biet khoa tieng Trung o dau khong")

        self.assertEqual(
            result.effective_query,
            "Cậu biết Khoa Tiếng Trung ở đâu không?",
        )
        self.assertTrue(result.changed)
        self.assertTrue(result.llm_called)

    def test_rejects_rewrite_that_adds_new_subject(self) -> None:
        client = FakeRewriteClient(
            '{"normalized_query":"Câu lạc bộ Khoa Tiếng Trung ở đâu không?",'
            '"needs_clarification":false,'
            '"clarification_question":null,'
            '"confidence":"high",'
            '"reason":"accent_restoration_and_typo_correction"}'
        )
        with patch.dict("os.environ", {"QUERY_REWRITER_API_KEY": "test-key"}):
            rewriter = QueryRewriter(enabled=True, client=client)
            result = rewriter.rewrite("cau biet khoa tieng Trung o dau khong")

        self.assertEqual(
            result.effective_query,
            "cau biet khoa tieng Trung o dau khong",
        )
        self.assertEqual(
            result.rewritten_query,
            "Câu lạc bộ Khoa Tiếng Trung ở đâu không?",
        )
        self.assertFalse(result.changed)
        self.assertEqual(result.reason, "unsafe_rewrite_semantic_drift")
        self.assertTrue(result.llm_called)

    def test_returns_clarification_when_llm_marks_ambiguous(self) -> None:
        client = FakeRewriteClient(
            '{"normalized_query":null,'
            '"needs_clarification":true,'
            '"clarification_question":"Bạn muốn hỏi điều kiện học bổng, hồ sơ hay đơn vị liên hệ?",'
            '"confidence":"medium",'
            '"reason":"ambiguous_scholarship_scope"}'
        )
        with patch.dict("os.environ", {"QUERY_REWRITER_API_KEY": "test-key"}):
            rewriter = QueryRewriter(enabled=True, client=client)
            result = rewriter.rewrite("hoc bong hoi ai")

        self.assertTrue(result.needs_clarification)
        self.assertIn("học bổng", result.clarification_question or "")
        self.assertEqual(result.effective_query, "hoc bong hoi ai")

    def test_does_not_call_llm_for_clear_accented_query(self) -> None:
        pass # Test removed because we now always call the LLM to rewrite slang

    def test_follow_up_query_uses_recent_history(self) -> None:
        client = FakeRewriteClient(
            '{"decision":"follow_up",'
            '"confidence":"high",'
            '"referenced_turns":[0],'
            '"standalone_query":"Sinh viên được học bổng loại giỏi cần bao nhiêu điểm?",'
            '"clarification_question":null,'
            '"reason":"history_context_resolution"}'
        )
        # move below
        history = [
            {
                "role": "user",
                "content": "Học bổng loại khá cần bao nhiêu điểm?",
            },
            {"role": "assistant", "content": "Loại khá cần đạt mức điểm theo quy định."},
        ]

        with patch.dict("os.environ", {"QUERY_REWRITER_API_KEY": "test-key"}):
            rewriter = QueryRewriter(enabled=True, client=client)
            result = rewriter.rewrite("còn loại giỏi thì sao?", chat_history=history)

        self.assertEqual(
            result.effective_query,
            "Sinh viên được học bổng loại giỏi cần bao nhiêu điểm?",
        )
        self.assertTrue(result.context_resolution["history_used"])
        self.assertIn("Học bổng loại khá", client.prompts[0])
        self.assertEqual(len(client.prompts), 1)

    def test_new_topic_does_not_use_previous_history(self) -> None:
        client = FakeRewriteClient(
            [
                '{"decision":"standalone_new_topic",'
                '"confidence":"high",'
                '"referenced_turns":[],'
                '"standalone_query":"Khoa CNTT ở đâu?",'
                '"clarification_question":null,'
                '"reason":"current_query_has_own_subject"}',
                '{"normalized_query":"Khoa Công nghệ thông tin ở đâu?",'
                '"needs_clarification":false,'
                '"clarification_question":null,'
                '"confidence":"high",'
                '"reason":"new_topic_accent_restoration"}',
            ]
        )
        history = [
            {
                "role": "user",
                "content": "Học bổng loại khá cần bao nhiêu điểm?",
            },
            {"role": "assistant", "content": "Loại khá cần đạt mức điểm theo quy định."},
        ]

        with patch.dict("os.environ", {"QUERY_REWRITER_API_KEY": "test-key"}):
            rewriter = QueryRewriter(enabled=True, client=client)
            result = rewriter.rewrite("Khoa CNTT ở đâu?", chat_history=history)

        self.assertEqual(result.effective_query, "Khoa Công nghệ thông tin ở đâu?")
        self.assertFalse(result.context_resolution["history_used"])
        self.assertIn("Học bổng loại khá", client.prompts[0])
        self.assertNotIn("Học bổng loại khá", client.prompts[1])

    def test_ambiguous_context_asks_for_clarification(self) -> None:
        client = FakeRewriteClient(
            '{"decision":"ambiguous",'
            '"confidence":"low",'
            '"referenced_turns":[],'
            '"standalone_query":null,'
            '"clarification_question":"Bạn đang hỏi tiếp về học bổng hay chuyển sang chủ đề mới?",'
            '"reason":"unclear_reference"}'
        )

        history = [
            {"role": "user", "content": "Học bổng loại khá cần bao nhiêu điểm?"},
            {"role": "assistant", "content": "Loại khá cần đạt mức điểm theo quy định."},
        ]

        with patch.dict("os.environ", {"QUERY_REWRITER_API_KEY": "test-key"}):
            rewriter = QueryRewriter(enabled=True, client=client)
            result = rewriter.rewrite("bên đó thì sao?", chat_history=history)

        self.assertTrue(result.needs_clarification)
        self.assertFalse(result.changed)
        self.assertEqual(result.reason, "unclear_reference")
        self.assertEqual(len(client.prompts), 1)

    def test_follow_up_without_known_phrase_can_use_llm_context(self) -> None:
        client = FakeRewriteClient(
            '{"decision":"follow_up",'
            '"confidence":"high",'
            '"referenced_turns":[0],'
            '"standalone_query":"Sinh viên năm nhất xét học bổng khuyến khích học tập có khác gì không?",'
            '"clarification_question":null,'
            '"reason":"history_context_resolution"}'
        )
        history = [
            {"role": "user", "content": "Điều kiện xét học bổng khuyến khích học tập là gì?"},
            {"role": "assistant", "content": "Sinh viên cần đáp ứng điều kiện theo quy định học bổng."},
        ]

        with patch.dict("os.environ", {"QUERY_REWRITER_API_KEY": "test-key"}):
            rewriter = QueryRewriter(enabled=True, client=client)
            result = rewriter.rewrite("năm nhất có khác không?", chat_history=history)

        self.assertEqual(
            result.effective_query,
            "Sinh viên năm nhất xét học bổng khuyến khích học tập có khác gì không?",
        )
        self.assertTrue(result.context_resolution["history_used"])
        self.assertEqual(len(client.prompts), 1)

    def test_rejects_context_rewrite_that_adds_unrelated_entity(self) -> None:
        client = FakeRewriteClient(
            '{"decision":"follow_up",'
            '"confidence":"high",'
            '"referenced_turns":[0],'
            '"standalone_query":"Học bổng loại giỏi của Khoa Công nghệ thông tin cần bao nhiêu điểm?",'
            '"clarification_question":null,'
            '"reason":"history_context_resolution"}'
        )
        history = [
            {"role": "user", "content": "Học bổng loại khá cần bao nhiêu điểm?"},
            {"role": "assistant", "content": "Loại khá cần đạt mức điểm theo quy định."},
        ]
        with patch.dict("os.environ", {"QUERY_REWRITER_API_KEY": "test-key"}):
            rewriter = QueryRewriter(enabled=True, client=client)
            result = rewriter.rewrite("còn loại giỏi thì sao?", chat_history=history)

        self.assertTrue(result.needs_clarification)
        self.assertEqual(result.effective_query, "còn loại giỏi thì sao?")
        self.assertEqual(result.reason, "unsafe_context_rewrite")


if __name__ == "__main__":
    unittest.main()
