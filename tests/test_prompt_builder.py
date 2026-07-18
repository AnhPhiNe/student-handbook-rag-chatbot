from __future__ import annotations

import unittest

from src.generation.context_allocation import ContextAllocationConfig
from src.generation.prompt_builder import build_answer_prompt


class PromptBuilderTest(unittest.TestCase):
    def test_prompt_is_gemini_oriented_without_visible_thinking(self) -> None:
        prompt = build_answer_prompt(
            query="Em được nghỉ học tạm thời bao lâu?",
            retrieval_result={
                "retrieved_items": [
                    {
                        "chunk_id": "section-1",
                        "content": "Quy định về nghỉ học tạm thời.",
                        "metadata": {
                            "title": "Điều 1",
                            "chunk_type": "regulation",
                            "source_pages": [1],
                        },
                    }
                ],
            },
            max_context_chars=5000,
            cohort="K51",
        )

        self.assertNotIn("<thinking>", prompt)
        self.assertNotIn("CITATIONS", prompt)
        self.assertIn("không xuất checklist", prompt)
        self.assertIn("K51", prompt)
        self.assertIn("DIRECT ANSWER FIRST", prompt)
        self.assertIn("required facts", prompt)

    def test_structured_result_no_longer_forces_1500_char_context_cap(self) -> None:
        long_content = ("nội dung dài " * 160) + "TAIL_MARKER_CONTEXT_VAN_CON"
        prompt = build_answer_prompt(
            query="Điều kiện xét học bổng là gì?",
            retrieval_result={
                "structured_result": {"kind": "table", "rows": [{"name": "học bổng"}]},
                "retrieved_items": [
                    {
                        "chunk_id": "scholarship",
                        "content": long_content,
                        "metadata": {
                            "title": "Điều học bổng",
                            "chunk_type": "regulation",
                            "source_pages": [10],
                        },
                        "score": 0.9,
                    }
                ],
            },
            max_context_chars=5000,
            context_allocation=ContextAllocationConfig(
                strategy="full_sources",
                min_chars_per_doc=0,
                max_chars_per_doc=50000,
                sentence_boundary=True,
            ),
        )

        self.assertIn("TAIL_MARKER_CONTEXT_VAN_CON", prompt)

    def test_structured_prompt_keeps_full_table_scope_for_gemini(self) -> None:
        prompt = build_answer_prompt(
            query="K50 hệ chính quy học tối đa bao lâu?",
            retrieval_result={
                "execution_mode": "structured",
                "structured_result": {
                    "source_lookup_type": "study_duration",
                    "cohort": "K50",
                    "items": [
                        {
                            "table_id": "K50_study_duration_chinh_quy",
                            "applicability": "Áp dụng cho hình thức đào tạo chính quy.",
                            "selection_method": "full_table",
                            "rows": [
                                {
                                    "Chương trình đào tạo": "Đào tạo đại học cấp bằng thứ nhất",
                                    "Thời gian học tập tối đa": "8 năm học",
                                }
                            ],
                        }
                    ],
                },
                "citations": [{"source_parent_id": "K50_Dieu3"}],
            },
            cohort="K50",
        )

        self.assertIn("Áp dụng cho hình thức đào tạo chính quy", prompt)
        self.assertIn("8 năm học", prompt)
        self.assertIn('"selection_method": "full_table"', prompt)

    def test_prompt_requires_applicability_check_for_overlapping_tables(self) -> None:
        prompt = build_answer_prompt(
            query="K51 được 5 điểm có đạt không?",
            retrieval_result={
                "structured_result": {
                    "items": [
                        {
                            "table_name": "Học phần nền tảng",
                            "applicability": "Học phần chung thuộc nhóm nền tảng",
                        },
                        {
                            "table_name": "Học phần đạt không phân mức",
                            "applicability": "Không tính vào điểm trung bình học tập",
                        },
                    ]
                }
            },
            cohort="K51",
        )

        self.assertIn("đối chiếu trường `applicability`", prompt)
        self.assertIn("không tự chọn bảng", prompt)


if __name__ == "__main__":
    unittest.main()
