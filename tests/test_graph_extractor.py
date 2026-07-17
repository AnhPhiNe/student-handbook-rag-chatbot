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
