from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.generation.answer_guardrails import build_deterministic_answer
from src.extraction.scoring_tables import build_scoring_tables
from src.retrieval.core.office_lookup import office_lookup
from src.retrieval.core.program_lookup import program_lookup
from src.retrieval.core.scholarship_lookup import scholarship_classification_lookup
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

    def test_reference_table_lookup_keeps_all_rows_despite_slots(self) -> None:
        from src.retrieval.core.structured_dispatcher import (
            resolve_structured_decision,
        )

        table = {
            "table_id": "K50_foreign_language_equivalency",
            "table_name": "Bảng quy đổi ngoại ngữ",
            "table_type": "foreign_language",
            "data_category": "regulation_table",
            "cohort": "K50",
            "applicable_cohorts": ["K50", "K51"],
            "rows": [
                {"certificate": "IELTS", "equivalent_level_4": "5.5 - 6.5"},
                {"certificate": "TOEFL iBT", "equivalent_level_4": "46 - 93"},
            ],
            "source_pages": [112],
            "source_parent_id": "K50_Dieu8",
        }
        resolution = resolve_structured_decision(
            {
                "lookup_type": "foreign_language",
                "intent": "direct_value",
                "slots": {"certificate_or_language": "Không có trong bảng"},
            },
            query="IELTS và TOEFL ở K51",
            cohort="K51",
            scoring_tables=[],
            formula_rules=[],
            office_directory=[],
            student_service_directory=[],
            student_faculty_profiles=[],
            foreign_language_tables=[],
            structured_tables_registry=[table],
            program_directory=[],
            probe_other_domains=False,
        )

        self.assertIsNotNone(resolution)
        self.assertEqual(resolution.strategy, "reference_table_lookup")
        self.assertEqual(len(resolution.result["display_rows"]), 2)
        self.assertEqual(resolution.result["cohort"], "K51")
        self.assertEqual(resolution.result["source_cohort"], "K50")

    def test_k51_study_duration_reference_tables_use_amended_values(self) -> None:
        from src.retrieval.core.structured_dispatcher import (
            resolve_structured_decision,
        )

        registry = json.loads(
            Path("data/processed/tables/structured_tables_registry.json").read_text(
                encoding="utf-8"
            )
        )
        resolution = resolve_structured_decision(
            {"lookup_type": "study_duration", "intent": "direct_value"},
            query="Thời gian đào tạo K51",
            cohort="K51",
            scoring_tables=[],
            formula_rules=[],
            office_directory=[],
            student_service_directory=[],
            student_faculty_profiles=[],
            foreign_language_tables=[],
            structured_tables_registry=registry,
            program_directory=[],
            probe_other_domains=False,
        )

        self.assertIsNotNone(resolution)
        leaves = resolution.result["sub_lookups"]
        self.assertEqual(len(leaves), 2)
        rows = [row for leaf in leaves for row in leaf["display_rows"]]
        self.assertEqual(
            {row["Hình thức đào tạo"] for row in rows},
            {"Chính quy", "Vừa làm vừa học"},
        )
        self.assertEqual(
            {row["Thời gian học tập tối đa"] for row in rows},
            {"06 năm học", "7,5 năm học"},
        )
        self.assertTrue(
            all("Quy tắc đối với sinh viên liên thông" in row for row in rows)
        )

        legacy_first_degree_maxima = {}
        for cohort in ("K48-K49", "K50"):
            cohort_rows = [
                row
                for table in registry
                if table.get("table_type") == "study_duration"
                and table.get("cohort") == cohort
                and "chính quy" in str(table.get("applicability") or "").lower()
                for row in table.get("rows") or []
            ]
            first_degree = next(
                row
                for row in cohort_rows
                if row.get("Chương trình đào tạo")
                == "Đào tạo đại học cấp bằng thứ nhất"
            )
            legacy_first_degree_maxima[cohort] = first_degree[
                "Thời gian học tập tối đa"
            ]

        self.assertEqual(
            legacy_first_degree_maxima,
            {"K48-K49": "8 năm học", "K50": "8 năm học"},
        )

    def test_foreign_language_component_requirements_are_data_driven(self) -> None:
        registry = json.loads(
            Path("data/processed/tables/structured_tables_registry.json").read_text(
                encoding="utf-8"
            )
        )
        foreign_table = next(
            table for table in registry if table.get("table_type") == "foreign_language"
        )
        four_component_row = next(
            row
            for row in foreign_table["rows"]
            if (row.get("input_requirements") or {}).get("score_mode")
            == "per_component"
        )

        self.assertEqual(
            four_component_row["input_requirements"]["required_components"],
            ["listening", "reading", "speaking", "writing"],
        )

    def test_foreign_language_scalar_score_requires_declared_components(self) -> None:
        from src.retrieval.core.structured_dispatcher import (
            resolve_structured_decision,
        )

        table = {
            "table_id": "component_certificate",
            "table_name": "Bảng chứng chỉ nhiều kỹ năng",
            "table_type": "foreign_language",
            "data_category": "regulation_table",
            "cohort": "K50",
            "applicable_cohorts": ["K50", "K51"],
            "source_parent_id": "K50_foreign_language_rule",
            "source_pages": [112],
            "rows": [
                {
                    "certificate": "Chứng chỉ ABC (4 kỹ năng)",
                    "input_requirements": {
                        "score_mode": "per_component",
                        "required_components": ["listening", "reading"],
                        "component_slots": {
                            "listening": {
                                "slot": "listening_score",
                                "label": "Nghe",
                            },
                            "reading": {
                                "slot": "reading_score",
                                "label": "Đọc",
                            },
                        },
                    },
                }
            ],
        }
        resolution = resolve_structured_decision(
            {
                "lookup_type": "foreign_language",
                "intent": "direct_value",
                "slots": {
                    "certificate_or_language": "Chứng chỉ ABC",
                    "score_or_level": 650,
                },
            },
            query="Chứng chỉ ABC tổng 650 tương đương bậc nào?",
            cohort="K51",
            scoring_tables=[],
            formula_rules=[],
            office_directory=[],
            student_service_directory=[],
            student_faculty_profiles=[],
            foreign_language_tables=[],
            structured_tables_registry=[table],
            program_directory=[],
            probe_other_domains=False,
        )

        self.assertIsNotNone(resolution)
        self.assertEqual(resolution.result_kind, "clarification")
        self.assertEqual(
            resolution.result["missing_slots"],
            ["listening_score", "reading_score"],
        )
        self.assertIn("Nghe, Đọc", resolution.result["clarification_question"])

    def test_scholarship_policy_schema_is_versioned_by_cohort(self) -> None:
        legacy = next(
            table
            for table in build_scoring_tables("K50")
            if table.get("table_id") == "scholarship_classification"
        )
        amended = next(
            table
            for table in build_scoring_tables("K51")
            if table.get("table_id") == "scholarship_classification"
        )

        self.assertEqual(legacy["schema_variant"], "score_ranges")
        self.assertIn("scholarship_score_range", legacy["rows"][0])
        self.assertEqual(amended["schema_variant"], "classification_matrix")
        self.assertEqual(len(amended["rows"]), 6)
        self.assertEqual(amended["source_pages"], [70, 71, 72])
        self.assertTrue(
            all("scholarship_score_range" not in row for row in amended["rows"])
        )

        registry = json.loads(
            Path("data/processed/tables/structured_tables_registry.json").read_text(
                encoding="utf-8"
            )
        )
        registry_tables = {
            table["cohort"]: table
            for table in registry
            if table.get("table_id") == "scholarship_classification"
        }
        self.assertIn("scholarship_score_range", registry_tables["K50"]["rows"][0])
        self.assertEqual(len(registry_tables["K51"]["rows"]), 6)
        self.assertTrue(
            all(
                "academic_classification" in row
                for row in registry_tables["K51"]["rows"]
            )
        )

    def test_scoring_selector_returns_every_row_of_the_selected_table(self) -> None:
        from src.retrieval.core.structured_dispatcher import (
            resolve_structured_decision,
        )

        registry = json.loads(
            Path("data/processed/tables/structured_tables_registry.json").read_text(
                encoding="utf-8"
            )
        )
        resolution = resolve_structured_decision(
            {
                "lookup_type": "scoring",
                "intent": "direct_value",
                "slots": {
                    "operation": "conduct_classification",
                    "score_or_grade": 85,
                },
            },
            query="85 điểm rèn luyện được xếp loại gì?",
            cohort="K51",
            scoring_tables=[],
            formula_rules=[],
            office_directory=[],
            student_service_directory=[],
            student_faculty_profiles=[],
            foreign_language_tables=[],
            structured_tables_registry=registry,
            program_directory=[],
            probe_other_domains=False,
        )

        self.assertIsNotNone(resolution)
        self.assertEqual(resolution.result["table_subtype"], "conduct_classification")
        self.assertEqual(len(resolution.result["display_rows"]), 6)
        self.assertEqual(
            {row["Xếp loại"] for row in resolution.result["display_rows"]},
            {"Xuất sắc", "Tốt", "Khá", "Trung bình", "Yếu", "Kém"},
        )

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

    def test_multi_entity_program_lookup_all_matched(self):
        programs = [
            {"program_name": "Công nghệ Giáo dục", "faculty_name": "Khoa Công nghệ Thông tin", "cohort": "K51"},
            {"program_name": "Công nghệ Thông tin", "faculty_name": "Khoa Công nghệ Thông tin", "cohort": "K51"},
            {"program_name": "Sư phạm Tin học", "faculty_name": "Khoa Công nghệ Thông tin", "cohort": "K51"},
            {"program_name": "Sư phạm Toán học", "faculty_name": "Khoa Toán - Tin học", "cohort": "K51"},
        ]

        query = "cơ hội việc làm của ngành Công nghệ Giáo dục, Công nghệ Thông tin, Sư phạm Tin học"
        res = program_lookup(
            query,
            programs,
            cohort="K51",
            routing={"content_type": "program_directory", "action": "resolve_faculty", "scope": "school"},
        )
        self.assertIsNotNone(res)
        self.assertEqual(res["program_count"], 3)
        names = {p["program_name"] for p in res["result"]}
        self.assertEqual(names, {"Công nghệ Giáo dục", "Công nghệ Thông tin", "Sư phạm Tin học"})

    def test_program_lookup_subsumption_protection(self):
        programs = [
            {"program_name": "Tin học", "faculty_name": "Khoa CNTT", "cohort": "K51"},
            {"program_name": "Sư phạm Tin học", "faculty_name": "Khoa CNTT", "cohort": "K51"},
        ]
        query = "ngành Sư phạm Tin học"
        res = program_lookup(
            query,
            programs,
            cohort="K51",
            routing={"content_type": "program_directory", "action": "resolve_faculty", "scope": "school"},
        )
        self.assertIsNotNone(res)
    def test_multi_entity_office_and_faculty_lookup_all_matched(self):
        units = [
            {
                "unit_name": "Khoa Công nghệ Thông tin",
                "aliases": ["khoa cntt", "cntt"],
                "emails": ["khoacntt@hcmue.edu.vn"],
                "cohort": "K51",
            },
            {
                "unit_name": "Phòng Công nghệ Thông tin",
                "aliases": ["phong cntt"],
                "emails": ["phongcntt@hcmue.edu.vn"],
                "cohort": "K51",
            },
        ]
        query = "email của khoa cntt và phòng cntt là gì"
        res = office_lookup(
            query,
            units,
            cohort="K51",
            candidate_text=query,
            require_confident_match=True,
        )
        self.assertIsNotNone(res)
        self.assertEqual(len(res["result"]), 2)
        names = {u["unit_name"] for u in res["result"]}
        self.assertEqual(names, {"Khoa Công nghệ Thông tin", "Phòng Công nghệ Thông tin"})

    def test_office_lookup_conjunction_prevents_false_ambiguity(self):
        units = [
            {
                "unit_name": "Phòng Đào tạo",
                "aliases": ["phong dao tao", "phong dt"],
                "emails": ["phongdt@hcmue.edu.vn"],
                "cohort": "K51",
            },
            {
                "unit_name": "Phòng Công tác chính trị và Học sinh, sinh viên",
                "aliases": ["phong cong tac chinh tri hoc sinh sinh vien", "phong ctct hssv"],
                "emails": ["hopthusinhvien@hcmue.edu.vn"],
                "cohort": "K51",
            },
        ]
        query = "email của phòng đào tạo và phòng công tác chính trị học sinh sinh viên"
        res = office_lookup(
            query,
            units,
            cohort="K51",
            candidate_text=query,
            require_confident_match=True,
        )
        self.assertIsNotNone(res)
        self.assertNotEqual(res.get("resolution_status"), "ambiguous")
        self.assertEqual(len(res["result"]), 2)

    def test_multi_entity_scholarship_lookup_all_matched(self):
        tables = [
            {
                "table_id": "scholarship_classification",
                "table_name": "Xếp loại học bổng khuyến khích học tập",
                "cohort": "K51",
                "rows": [
                    {"label": "Khá", "scholarship_score_range": "2.56-3.352"},
                    {"label": "Giỏi", "scholarship_score_range": "3.36-3.832"},
                    {"label": "Xuất sắc", "scholarship_score_range": ">=3.84"},
                ],
            }
        ]
        query = "điểm học bổng loại khá và loại giỏi là bao nhiêu"
        res = scholarship_classification_lookup(query, tables, cohort="K51")
        self.assertIsNotNone(res)
        self.assertEqual(res["result"]["result_count"], 2)
        labels = {r["label"] for r in res["result"]["rows"]}
        self.assertEqual(labels, {"Khá", "Giỏi"})

    def test_inter_table_multi_structured_resolution(self):
        from src.retrieval.core.structured_dispatcher import resolve_structured_decision

        decision = {"lookup_type": "foreign_language", "slots": {}}
        query = "ielts 6.0 quy đổi ra bậc mấy và điểm học bổng loại giỏi là bao nhiêu"
        fl_tables = [
            {
                "table_id": "foreign_language_equivalency_table",
                "table_name": "Bảng tham chiếu quy đổi chứng chỉ ngoại ngữ",
                "table_type": "foreign_language",
                "data_category": "regulation_table",
                "cohort": "K51",
                "applicable_cohorts": ["K51"],
                "rows": [
                    {
                        "language": "Tiếng Anh",
                        "certificate": "IELTS",
                        "level_or_scale": "IELTS",
                        "equivalent_level_3": "4.0 - 5.0",
                        "equivalent_level_4": "5.5 - 6.5",
                    }
                ],
            }
        ]
        scoring_tables = [
            {
                "table_id": "scholarship_classification",
                "table_name": "Xếp loại học bổng khuyến khích học tập",
                "table_type": "scholarship",
                "data_category": "regulation_table",
                "cohort": "K51",
                "rows": [
                    {"label": "Giỏi", "scholarship_score_range": "3.36-3.832"},
                ],
            }
        ]
        res = resolve_structured_decision(
            decision,
            query=query,
            cohort="K51",
            scoring_tables=scoring_tables,
            formula_rules=[],
            office_directory=[],
            student_service_directory=[],
            student_faculty_profiles=[],
            foreign_language_tables=fl_tables,
            structured_tables_registry=fl_tables + scoring_tables,
            program_directory=[],
        )
        self.assertIsNotNone(res)
        self.assertEqual(res.lookup_type, "multi_structured")
        self.assertEqual(res.result.get("lookup_count"), 2)


if __name__ == "__main__":
    unittest.main()
