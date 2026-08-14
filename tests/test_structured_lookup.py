from __future__ import annotations

import unittest

from src.generation.answer_guardrails import build_deterministic_answer
from src.extraction.scoring_tables import build_scoring_tables
from src.retrieval.core.program_lookup import program_lookup
from src.retrieval.core.structured_lookup import (
    structured_lookup,
    structured_lookup_from_slots,
)


class StructuredLookupTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tables = build_scoring_tables()

    def test_letter_grade_with_plus_is_not_downgraded_to_base_grade(self) -> None:
        cases = {
            "Điểm B+ quy đổi sang hệ 4 bao nhiêu?": ("B+", 3.5),
            "Điểm C+ quy đổi sang thang 4 là bao nhiêu?": ("C+", 2.5),
        }

        for query, (expected_grade, expected_score) in cases.items():
            with self.subTest(query=query):
                result = structured_lookup(query, self.tables)

                self.assertIsNotNone(result)
                row = result["result"]
                self.assertEqual(row["letter_grade"], expected_grade)
                self.assertEqual(row["score_4"], expected_score)

    def test_numeric_grade_10_maps_to_letter_grade(self) -> None:
        result = structured_lookup("Điểm 8.5 tương ứng điểm chữ nào?", self.tables)

        self.assertIsNotNone(result)
        self.assertEqual(result["lookup_type"], "grade_10_to_letter")
        self.assertIsInstance(result["result"], list)
        self.assertTrue(result["result"])

        first = result["result"][0]
        self.assertEqual(first["row"]["letter_grade"], "A")

    def test_numeric_grade_answer_mentions_letter_grade(self) -> None:
        result = structured_lookup("Điểm 8.5 tương ứng điểm chữ nào?", self.tables)
        self.assertIsNotNone(result)

        answer = build_deterministic_answer(
            "Điểm 8.5 tương ứng điểm chữ nào?",
            {
                "structured_result": result,
                "retrieved_items": [],
                "tool_result": None,
                "formula_result": None,
            },
        )
        self.assertIn("điểm chữ A", answer)


    def test_conduct_label_maps_back_to_score_range(self) -> None:
        tables = [
            {
                "table_id": "conduct_classification",
                "cohort": "K50",
                "document_id": "handbook",
                "source_section": "conduct_article",
                "source_pages": [1],
                "table_name": "Phan loai ket qua ren luyen",
                "rows": [
                    {"range": "80-duoi 90", "label": "Tot"},
                    {"range": "90-100", "label": "Xuat sac"},
                ],
            }
        ]

        result = structured_lookup_from_slots(
            {"operation": "conduct_classification", "score_or_grade": "Tot"},
            tables,
            cohort="K50",
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["lookup_type"], "conduct_classification")
        self.assertEqual(result["result"]["range"], "80-duoi 90")

    def test_program_topic_faculty_lookup_lists_matching_programs(self) -> None:
        programs = [
            {
                "program_name": "Su pham Tin hoc",
                "faculty_name": "Khoa Cong nghe Thong tin",
                "cohort": "K50",
                "document_id": "handbook",
                "source_section": "program_directory",
            },
            {
                "program_name": "Cong nghe Thong tin",
                "faculty_name": "Khoa Cong nghe Thong tin",
                "cohort": "K50",
                "document_id": "handbook",
                "source_section": "program_directory",
            },
        ]

        result = program_lookup(
            "cac nganh su pham do khoa nao quan ly",
            programs,
            cohort="K50",
            routing={
                "content_type": "program_directory",
                "action": "list",
                "scope": "faculty",
            },
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["lookup_scope"], "program_topic_faculty")
        self.assertEqual(result["source_lookup_type"], "faculty")
        self.assertEqual(result["program_count"], 1)
        self.assertEqual(result["result"][0]["program_name"], "Su pham Tin hoc")

    def test_program_lookup_accepts_shared_directory_for_selected_cohort(self) -> None:
        programs = [
            {
                "program_name": "Cong nghe Thong tin",
                "faculty_name": "Khoa Cong nghe Thong tin",
                "cohort": "all",
                "document_id": "program-directory",
                "source_section": "program_directory",
                "source_pages": [207],
            }
        ]

        result = program_lookup(
            "nganh cong nghe thong tin o khoa nao",
            programs,
            cohort="K51",
            routing={
                "content_type": "program_directory",
                "action": "resolve_faculty",
                "scope": "school",
            },
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["lookup_scope"], "program")
        self.assertEqual(result["program_count"], 1)
        self.assertEqual(
            result["result"][0]["faculty_name"],
            "Khoa Cong nghe Thong tin",
        )

    def test_is_cohort_applicable_and_foreign_language_inheritance(self) -> None:
        from src.common.cohort import is_cohort_applicable
        from src.retrieval.core.foreign_language_lookup import foreign_language_lookup

        table = {
            "table_id": "K50_foreign_language_equivalency_dieu8",
            "cohort": "K50",
            "applicable_cohorts": ["K48-K49", "K50", "K51"],
            "applicability": "Điều 1 áp dụng cho sinh viên từ khóa 2022 trở đi.",
            "rows": [
                {
                    "language": "Tiếng Anh",
                    "certificate": "IELTS",
                    "equivalent_level_3": "4.0 - 5.0",
                    "equivalent_level_4": "5.5 - 6.5",
                }
            ],
            "source_pages": [112],
            "document_id": "so_tay_sinh_vien_khoa_50",
        }

        self.assertTrue(is_cohort_applicable(table, "K48-K49"))
        self.assertTrue(is_cohort_applicable(table, "K50"))
        self.assertTrue(is_cohort_applicable(table, "K51"))
        self.assertFalse(is_cohort_applicable(table, "K47"))

        # Test lookup for K51 and K48-K49 queries
        for cohort in ["K48-K49", "K50", "K51"]:
            res = foreign_language_lookup("IELTS 6.0 quy đổi bậc mấy", [table], cohort=cohort)
            self.assertIsNotNone(res, f"Expected match for cohort {cohort}")
            self.assertEqual(res["result"]["matched_level"], "bac_4")
            self.assertEqual(res["cohort"], cohort)
            self.assertEqual(res["source_cohort"], "K50")

    def test_program_lookup_faculty_programs_per_cohort_counts(self) -> None:
        programs = [
            {
                "program_name": "Công nghệ Thông tin",
                "faculty_name": "Khoa Công nghệ Thông tin",
                "cohort": "K48-K49",
                "document_id": "so_tay_sinh_vien_khoa_48_49",
            },
            {
                "program_name": "Sư phạm Tin học",
                "faculty_name": "Khoa Công nghệ Thông tin",
                "cohort": "K48-K49",
                "document_id": "so_tay_sinh_vien_khoa_48_49",
            },
            {
                "program_name": "Công nghệ Giáo dục",
                "faculty_name": "Khoa Công nghệ Thông tin",
                "cohort": "K51",
                "document_id": "so_tay_sinh_vien_khoa_51",
            },
            {
                "program_name": "Công nghệ Thông tin",
                "faculty_name": "Khoa Công nghệ Thông tin",
                "cohort": "K51",
                "document_id": "so_tay_sinh_vien_khoa_51",
            },
            {
                "program_name": "Sư phạm Tin học",
                "faculty_name": "Khoa Công nghệ Thông tin",
                "cohort": "K51",
                "document_id": "so_tay_sinh_vien_khoa_51",
            },
        ]

        res_k49 = program_lookup(
            "Khoa Công nghệ Thông tin",
            programs,
            cohort="K48-K49",
            routing={"content_type": "program_directory", "action": "list", "scope": "faculty"},
        )
        self.assertIsNotNone(res_k49)
        self.assertEqual(res_k49["program_count"], 2)
        names_k49 = {p["program_name"] for p in res_k49["result"]}
        self.assertEqual(names_k49, {"Công nghệ Thông tin", "Sư phạm Tin học"})

        res_k51 = program_lookup(
            "Khoa Công nghệ Thông tin",
            programs,
            cohort="K51",
            routing={"content_type": "program_directory", "action": "list", "scope": "faculty"},
        )
        self.assertIsNotNone(res_k51)
        self.assertEqual(res_k51["program_count"], 3)
        names_k51 = {p["program_name"] for p in res_k51["result"]}
        self.assertEqual(names_k51, {"Công nghệ Giáo dục", "Công nghệ Thông tin", "Sư phạm Tin học"})


if __name__ == "__main__":
    unittest.main()
