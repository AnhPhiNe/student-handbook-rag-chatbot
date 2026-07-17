import unittest

from src.retrieval.core.query_router import route_query


class QueryRouterTest(unittest.TestCase):
    def test_core_portfolio_routes(self) -> None:
        cases = {
            "email phong dao tao la gi": ("office_query", "office_lookup"),
            "thông tin Khoa CNTT": ("faculty_query", "semantic_filtered_rerank"),
            "diem tb tinh kieu j": ("formula_query", "formula_lookup"),
            "Muon tam nghi hoc can mau don nao?": (
                "form_query",
                "form_lookup",
            ),
            "Diem ren luyen 85 la loai gi?": (
                "score_lookup_query",
                "structured_lookup",
            ),
            "Tinh diem hoc bong neu GPA 3.2 va ren luyen 90": (
                "formula_query",
                "formula_lookup",
            ),
            "Cong thuc tinh diem GPA la gi?": (
                "formula_query",
                "formula_lookup",
            ),
            "Quy trinh vao ky tuc xa nhu the nao?": (
                "procedure_query",
                "semantic_filtered_rerank",
            ),
        }

        for query, (expected_intent, expected_strategy) in cases.items():
            with self.subTest(query=query):
                route = route_query(query)
                self.assertEqual(route["intent"], expected_intent)
                self.assertEqual(route["strategy"], expected_strategy)

    def test_policy_and_procedure_shapes_never_take_direct_lookup(self) -> None:
        cases = {
            "Quy trình nộp hồ sơ học bổng cho K51 ra sao?": "procedure_query",
            "Sau khi nộp mẫu xin nghỉ học thì quy trình xét thế nào?": "procedure_query",
            "Nộp biểu mẫu trễ có được giải quyết ngoại lệ không?": "regulation_query",
            "Có được khiếu nại cách tính điểm học bổng không?": "regulation_query",
        }

        for query, expected_intent in cases.items():
            with self.subTest(query=query):
                route = route_query(query)
                self.assertEqual(route["intent"], expected_intent)
                self.assertNotIn(
                    route["strategy"],
                    {
                        "form_lookup",
                        "formula_lookup",
                        "scholarship_classification_lookup",
                        "student_service_lookup",
                    },
                )

    def test_unresolved_reference_requests_clarification(self) -> None:
        route = route_query("Trường hợp đó thì em liên hệ ai?")

        self.assertEqual(route["intent"], "needs_clarification")
        self.assertTrue(route["needs_clarification"])

    def test_clear_external_topic_is_rejected(self) -> None:
        for query in (
            "Giá Bitcoin hôm nay bao nhiêu?",
            "Dịch câu này sang tiếng Pháp giúp em.",
            "Máy tính bị xanh màn hình sửa sao?",
        ):
            with self.subTest(query=query):
                route = route_query(query)
                self.assertEqual(route["intent"], "out_of_domain")
                self.assertEqual(route["strategy"], "none")


if __name__ == "__main__":
    unittest.main()
