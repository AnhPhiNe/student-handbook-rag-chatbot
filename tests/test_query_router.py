import unittest

from src.retrieval.core.query_router import route_query


class QueryRouterTest(unittest.TestCase):
    def test_core_portfolio_routes(self) -> None:
        cases = {
            "Email phòng Đào tạo là gì?": ("office_query", "semantic_filtered_rerank"),
            "Khoa CNTT ở đâu?": ("faculty_query", "semantic_filtered_rerank"),
            "Muốn tạm nghỉ học cần mẫu đơn nào?": ("form_query", "semantic_filtered_rerank"),
            "Điểm rèn luyện 85 là loại gì?": ("score_lookup_query", "structured_lookup"),
            "Tính điểm học bổng nếu GPA 3.2 và rèn luyện 90": (
                "calculation_query",
                "calculator_tool",
            ),
            "Quy trình vào ký túc xá như thế nào?": (
                "procedure_query",
                "semantic_filtered_rerank",
            ),
        }

        for query, (expected_intent, expected_strategy) in cases.items():
            with self.subTest(query=query):
                route = route_query(query)
                self.assertEqual(route["intent"], expected_intent)
                self.assertEqual(route["strategy"], expected_strategy)


if __name__ == "__main__":
    unittest.main()
