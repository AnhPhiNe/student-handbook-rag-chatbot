from __future__ import annotations

import unittest

from src.generation.context_allocation import ContextAllocationConfig
from src.generation.amendment_precedence import collect_applicable_amendments
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
        self.assertIn("Không hiển thị quá trình suy luận", prompt)
        self.assertIn("K51", prompt)
        self.assertIn("Chỉ sử dụng STRUCTURED_RESULT và CONTEXT", prompt)
        self.assertIn("nói rằng chưa tìm thấy trong Sổ tay", prompt)

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

        self.assertIn("record có `applicability` phù hợp", prompt)
        self.assertIn("hãy hỏi lại", prompt)

    def test_prompt_ignores_deprecated_answer_scope_contract(self) -> None:
        prompt = build_answer_prompt(
            query="K50 co duoc dong phi thay IELTS khong?",
            retrieval_result={
                "router_decision": {
                    "answer_scope": "abstain_if_no_direct_evidence",
                    "question_specificity": "narrow",
                    "asked_claim": "dong phi thay IELTS",
                    "target_policy": "chuan dau ra ngoai ngu",
                    "requires_direct_evidence": True,
                }
            },
            cohort="K50",
        )

        self.assertNotIn("ANSWER_SCOPE_CONTRACT", prompt)
        self.assertNotIn("abstain_if_no_direct_evidence", prompt)
        self.assertNotIn("requires_direct_evidence", prompt)

    def test_applicable_amendment_is_promoted_for_matching_cohort(self) -> None:
        amendment_note = (
            "5 Điểm này đã được sửa đổi tại khoản 4, Điều 1, Quyết định 4743. "
            "Việc sửa đổi, bổ sung áp dụng từ khoá tuyển sinh năm 2025 trở về sau. "
            "Cụ thể như sau:\n"
            "“Sinh viên học cải thiện được dùng điểm đạt cao nhất làm điểm chính thức.”"
        )
        retrieval_result = {
            "retrieved_items": [
                {
                    "chunk_id": "article-10",
                    "content": "Điểm lần học cuối là điểm chính thức.",
                    "metadata": {"cohort": "K51", "title": "Điều 10"},
                }
            ],
            "related_items": [
                {
                    "chunk_id": "article-11",
                    "content": amendment_note,
                    "metadata": {
                        "cohort": "K51",
                        "title": "Điều 11",
                        "parent_section_id": "article-11",
                    },
                }
            ],
        }

        prompt = build_answer_prompt(
            query="K51 học cải thiện thì lấy điểm nào?",
            retrieval_result=retrieval_result,
            max_context_chars=10000,
            cohort="K51",
            context_allocation=ContextAllocationConfig(
                strategy="full_sources",
                min_chars_per_doc=0,
                max_chars_per_doc=5000,
            ),
        )

        self.assertIn("APPLICABLE AMENDMENTS", prompt)
        self.assertIn("điểm đạt cao nhất", prompt)
        self.assertIn("thứ tự hiệu lực cao hơn", prompt)

    def test_amendment_for_newer_admission_year_is_not_applied_to_k50(self) -> None:
        retrieval_result = {
            "retrieved_items": [
                {
                    "chunk_id": "article-10",
                    "content": (
                        "5 Điểm này được sửa đổi, bổ sung và áp dụng từ khóa tuyển sinh "
                        "năm 2025 trở về sau. Cụ thể như sau: "
                        "“Dùng điểm đạt cao nhất làm điểm chính thức.”"
                    ),
                    "metadata": {"cohort": "K50", "title": "Điều 10"},
                }
            ]
        }

        amendments = collect_applicable_amendments(
            retrieval_result,
            query="Học cải thiện lấy điểm nào?",
            cohort="K50",
        )

        self.assertEqual(amendments, [])

    def test_prompt_sets_semantic_boundary_for_yes_no_inference(self) -> None:
        prompt = build_answer_prompt(
            query="Em có được tự chọn tháng nhận bằng không?",
            retrieval_result={
                "retrieved_items": [
                    {
                        "chunk_id": "graduation-schedule",
                        "content": "Nhà trường xét tốt nghiệp vào tháng 3, 6, 9 và 12.",
                        "metadata": {
                            "cohort": "K51",
                            "title": "Lịch xét tốt nghiệp",
                            "chunk_type": "regulation",
                        },
                    }
                ]
            },
            cohort="K51",
        )

        self.assertIn("không tự chứng minh người dùng có quyền lựa chọn", prompt)
        self.assertIn("chỉ kết luận có hoặc không khi nguồn trực tiếp xác lập", prompt)


if __name__ == "__main__":
    unittest.main()
