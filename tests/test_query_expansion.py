import unittest

from src.retrieval.core.query_expansion import expand_query


class QueryExpansionTest(unittest.TestCase):
    def test_expands_academic_registration_terms(self):
        rules = [
            {
                "trigger": ["học vượt", "học kỳ phụ", "đăng ký học phần"],
                "expand_to": [
                    "đăng ký học phần",
                    "khối lượng học tập tối đa",
                    "học kỳ chính",
                    "học kỳ phụ",
                ],
            }
        ]

        expanded = expand_query(
            "Muốn học vượt thì cần điều kiện gì?",
            rules,
        )

        self.assertIn("đăng ký học phần", expanded)
        self.assertIn("khối lượng học tập tối đa", expanded)
        self.assertIn("học kỳ phụ", expanded)


if __name__ == "__main__":
    unittest.main()
