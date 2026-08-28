import unittest

from src.ingestion.graph_extractor import extract_rule_edges, extract_references


def _item(
    section_id: str,
    content: str,
    *,
    cohort: str = "K50",
    document_id: str = "so_tay_sinh_vien_khoa_50",
    document_title: str = "Quy chế đào tạo",
    article: str | None = None,
) -> dict:
    if article is None:
        article_number = section_id.rsplit("Dieu", 1)[-1]
        article = f"Điều {article_number}."
    return {
        "_id": section_id,
        "content": content,
        "cohort": cohort,
        "document_id": document_id,
        "metadata": {
            "cohort": cohort,
            "document_id": document_id,
            "document_title": document_title,
            "article": article,
            "content_type": "regulation_text",
        },
    }


class RuleGraphExtractorTest(unittest.TestCase):
    def test_extracts_single_article_reference(self) -> None:
        items = [
            _item(
                "K50_QuyCheDaoTao_Chuong4_Dieu17",
                "Điều 17. Nghỉ học tạm thời. Thời gian nghỉ học thực hiện theo quy định tại Điều 16.",
            ),
            _item("K50_QuyCheDaoTao_Chuong4_Dieu16", "Điều 16. Nghỉ học tạm thời."),
        ]

        edges, report = extract_rule_edges(items)

        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["source"], "K50_QuyCheDaoTao_Chuong4_Dieu17")
        self.assertEqual(edges[0]["target"], "K50_QuyCheDaoTao_Chuong4_Dieu16")
        self.assertEqual(edges[0]["relation"], "LIEN_QUAN_TOI")
        self.assertEqual(edges[0]["method"], "rule")
        self.assertEqual(report["validation"]["graph_nodes_missing_in_docstore"], 0)

    def test_extracts_multiple_article_references(self) -> None:
        items = [
            _item("K50_QuyCheDaoTao_Chuong3_Dieu10", "Điều 10. Căn cứ Điều 3 và theo Điều 4."),
            _item("K50_QuyCheDaoTao_Chuong1_Dieu3", "Điều 3. Thời gian đào tạo."),
            _item("K50_QuyCheDaoTao_Chuong1_Dieu4", "Điều 4. Học lại."),
        ]

        edges, _ = extract_rule_edges(items)

        self.assertEqual({edge["target"] for edge in edges}, {
            "K50_QuyCheDaoTao_Chuong1_Dieu3",
            "K50_QuyCheDaoTao_Chuong1_Dieu4",
        })

    def test_self_reference_dieu_nay_does_not_create_edge(self) -> None:
        items = [
            _item("K50_QuyCheDaoTao_Chuong4_Dieu16", "Điều 16. Các trường hợp tại khoản 1 Điều này."),
        ]

        edges, report = extract_rule_edges(items)

        self.assertEqual(edges, [])
        self.assertEqual(report["skip_counts"]["self_reference"], 1)

    def test_clause_and_point_are_edge_metadata_only(self) -> None:
        items = [
            _item(
                "K50_QuyCheDaoTao_Chuong4_Dieu17",
                "Điều 17. Sinh viên được xem xét căn cứ điểm a khoản 1 Điều 16.",
            ),
            _item("K50_QuyCheDaoTao_Chuong4_Dieu16", "Điều 16. Nghỉ học tạm thời."),
        ]

        edges, _ = extract_rule_edges(items)

        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["target"], "K50_QuyCheDaoTao_Chuong4_Dieu16")
        self.assertEqual(edges[0]["reference_article"], 16)
        self.assertEqual(edges[0]["reference_clause"], "1")
        self.assertEqual(edges[0]["reference_point"], "a")

    def test_same_article_in_different_cohort_is_not_cross_mapped(self) -> None:
        items = [
            _item("K50_QuyCheDaoTao_Chuong4_Dieu17", "Điều 17. Theo Điều 16.", cohort="K50"),
            _item("K51_QuyCheDaoTao_Chuong4_Dieu16", "Điều 16. Nghỉ học.", cohort="K51"),
        ]

        edges, report = extract_rule_edges(items)

        self.assertEqual(edges, [])
        self.assertEqual(report["skip_counts"]["unresolved_target"], 1)

    def test_same_article_in_different_document_title_is_not_cross_mapped(self) -> None:
        items = [
            _item(
                "K50_QuyCheDaoTao_Chuong4_Dieu17",
                "Điều 17. Theo Điều 16.",
                document_title="Quy chế đào tạo",
            ),
            _item(
                "K50_QuyCheCongTacSinhVien_Chuong4_Dieu16",
                "Điều 16. Công tác sinh viên.",
                document_title="Quy chế công tác sinh viên",
            ),
        ]

        edges, report = extract_rule_edges(items)

        self.assertEqual(edges, [])
        self.assertEqual(report["skip_counts"]["unresolved_target"], 1)

    def test_explicit_cross_document_reference_uses_named_regulation(self) -> None:
        items = [
            _item(
                "K50_QuyCheCongTacSinhVien_Chuong5_Dieu30",
                (
                    "Điều 30. Nghỉ học tạm thời. Được quy định tại khoản 1 Điều 16 "
                    "Quy chế đào tạo trình độ đại học chính quy tại Trường."
                ),
                document_title="Quy chế công tác sinh viên",
            ),
            _item(
                "K50_QuyCheCongTacSinhVien_Chuong4_Dieu16",
                "Điều 16. Phòng Hợp tác Quốc tế.",
                document_title="Quy chế công tác sinh viên",
            ),
            _item(
                "K50_QuyCheDaoTao_Chuong4_Dieu16",
                "Điều 16. Nghỉ học tạm thời, tiếp nhận trở lại học và cho thôi học.",
                document_title="Quy chế đào tạo trình độ đại học tại Trường",
            ),
        ]

        edges, report = extract_rule_edges(items)

        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["target"], "K50_QuyCheDaoTao_Chuong4_Dieu16")
        self.assertEqual(edges[0]["resolution_mode"], "explicit_cross_document")
        self.assertEqual(edges[0]["target_document_title"], "Quy chế đào tạo trình độ đại học tại Trường")
        self.assertEqual(report["resolution_counts"]["explicit_cross_document"], 1)

    def test_explicit_external_document_does_not_fallback_to_same_number(self) -> None:
        items = [
            _item(
                "K51_QuyCheDaoTao_Chuong1_Dieu3",
                (
                    "Điều 3. Thời gian đào tạo. Khoản này được sửa đổi tại khoản 1 Điều 1 "
                    "Quyết định số 4743/QĐ-ĐHSP."
                ),
                document_title="Quy chế đào tạo trình độ đại học",
            ),
            _item(
                "K51_QuyCheDaoTao_Chuong1_Dieu1",
                "Điều 1. Phạm vi điều chỉnh.",
                document_title="Quy chế đào tạo trình độ đại học",
            ),
        ]

        edges, report = extract_rule_edges(items)

        self.assertEqual(edges, [])
        self.assertEqual(report["skip_counts"]["unresolved_external_document"], 1)
        unresolved = next(
            item for item in report["skipped"] if item["issue"] == "unresolved_external_document"
        )
        self.assertIn("Quyết định số 4743", unresolved["target_document_hint"])

    def test_explicit_missing_study_level_document_does_not_map_to_other_level(self) -> None:
        items = [
            _item(
                "K50_QuyCheCongTacSinhVien_Chuong5_Dieu30",
                "Điều 30. Thực hiện theo khoản 1 Điều 16 Quy chế đào tạo trình độ cao đẳng.",
                document_title="Quy chế công tác sinh viên",
            ),
            _item(
                "K50_QuyCheDaoTao_Chuong4_Dieu16",
                "Điều 16. Nghỉ học tạm thời.",
                document_title="Quy chế đào tạo trình độ đại học",
            ),
        ]

        edges, report = extract_rule_edges(items)

        self.assertEqual(edges, [])
        self.assertEqual(report["skip_counts"]["unresolved_external_document"], 1)

    def test_repeated_legal_number_becomes_document_alias(self) -> None:
        title = "Nghị định quy định chính sách hỗ trợ sinh viên sư phạm"
        items = [
            _item(
                "K51_NghiDinhHoTro_Chuong2_Dieu8",
                "Điều 8. Bồi hoàn theo khoản 1 Điều 6 Nghị định 116.",
                document_title=title,
            ),
            _item(
                "K51_NghiDinhHoTro_Chuong2_Dieu6",
                "Điều 6. Các trường hợp bồi hoàn theo Nghị định 116.",
                document_title=title,
            ),
        ]

        edges, _ = extract_rule_edges(items)

        self.assertEqual(len(edges), 1)
        self.assertEqual(edges[0]["target"], "K51_NghiDinhHoTro_Chuong2_Dieu6")
        self.assertEqual(edges[0]["resolution_mode"], "same_document")

    def test_external_numbered_decree_is_not_mapped_to_current_decree(self) -> None:
        title = "Nghị định quy định chính sách hỗ trợ sinh viên sư phạm"
        items = [
            _item(
                "K51_NghiDinhHoTro_Chuong4_Dieu14",
                "Điều 14. Thực hiện theo Điều 6 của Nghị định số 86/2015/NĐ-CP.",
                document_title=title,
            ),
            _item(
                "K51_NghiDinhHoTro_Chuong2_Dieu6",
                "Điều 6. Các trường hợp bồi hoàn theo Nghị định 116.",
                document_title=title,
            ),
            _item(
                "K51_NghiDinhHoTro_Chuong2_Dieu8",
                "Điều 8. Bồi hoàn theo Điều 6 Nghị định 116.",
                document_title=title,
            ),
        ]

        edges, report = extract_rule_edges(items)

        targets_by_source = {edge["source"]: edge["target"] for edge in edges}
        self.assertNotIn("K51_NghiDinhHoTro_Chuong4_Dieu14", targets_by_source)
        self.assertEqual(report["skip_counts"]["unresolved_external_document"], 1)

    def test_report_contains_machine_auditable_edge_fields(self) -> None:
        items = [
            _item("K50_QuyCheDaoTao_Chuong4_Dieu17", "Điều 17. Theo Điều 16."),
            _item("K50_QuyCheDaoTao_Chuong4_Dieu16", "Điều 16. Nghỉ học tạm thời."),
        ]

        _, report = extract_rule_edges(items)

        audit = report["edge_audit"][0]
        self.assertEqual(audit["source_cohort"], "K50")
        self.assertEqual(audit["target_cohort"], "K50")
        self.assertEqual(audit["source_article"], 17)
        self.assertEqual(audit["target_article"], 16)
        self.assertEqual(audit["resolution_mode"], "same_document")
        self.assertIn("reference_reason", audit)

    def test_duplicate_edges_are_deduplicated(self) -> None:
        items = [
            _item(
                "K50_QuyCheDaoTao_Chuong4_Dieu17",
                "Điều 17. Theo Điều 16. Thực hiện theo quy định tại Điều 16.",
            ),
            _item("K50_QuyCheDaoTao_Chuong4_Dieu16", "Điều 16. Nghỉ học tạm thời."),
        ]

        edges, report = extract_rule_edges(items)

        self.assertEqual(len(edges), 1)
        self.assertEqual(report["skip_counts"]["duplicate_edge"], 1)

    def test_reference_parser_ignores_dieu_nay_without_number(self) -> None:
        references = extract_references("Nội dung tại khoản 1 Điều này được áp dụng.")

        self.assertEqual(references, [])


if __name__ == "__main__":
    unittest.main()
