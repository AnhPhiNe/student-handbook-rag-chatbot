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

    def test_short_trigger_must_match_as_standalone_term(self):
        rules = [
            {
                "trigger": ["it"],
                "expand_to": ["khoa công nghệ thông tin"],
            }
        ]

        self.assertIn(
            "khoa công nghệ thông tin",
            expand_query("ngành it học gì?", rules),
        )
        self.assertEqual(
            "credit học phí là gì?",
            expand_query("credit học phí là gì?", rules),
        )

    def test_hyphenated_trigger_still_matches(self):
        rules = [
            {
                "trigger": ["ctct-hssv"],
                "expand_to": ["phòng công tác chính trị và học sinh, sinh viên"],
            }
        ]

        expanded = expand_query("liên hệ ctct-hssv ở đâu?", rules)

        self.assertIn("phòng công tác chính trị và học sinh, sinh viên", expanded)


if __name__ == "__main__":
    unittest.main()
