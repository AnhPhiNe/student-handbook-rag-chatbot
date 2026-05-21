import unittest

from src.retrieval.core.query_router import route_query


class QueryRouterTest(unittest.TestCase):
    def test_core_portfolio_routes(self) -> None:
        cases = {
            "Email phong Dao tao la gi?": ("office_query", "semantic_filtered_rerank"),
            "Khoa CNTT o dau?": ("faculty_query", "semantic_filtered_rerank"),
            "Muon tam nghi hoc can mau don nao?": (
                "form_query",
                "semantic_filtered_rerank",
            ),
            "Diem ren luyen 85 la loai gi?": (
                "score_lookup_query",
                "structured_lookup",
            ),
            "Tinh diem hoc bong neu GPA 3.2 va ren luyen 90": (
                "calculation_query",
                "calculator_tool",
            ),
            "Cong thuc tinh diem GPA la gi?": (
                "formula_query",
                "formula_lookup",
            ),
            "diem tb tinh kieu j": (
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


if __name__ == "__main__":
    unittest.main()
