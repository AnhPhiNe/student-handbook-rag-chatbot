from __future__ import annotations

import unittest

from src.extraction.scoring_tables import build_scoring_tables
from src.retrieval.core.structured_lookup import structured_lookup


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


if __name__ == "__main__":
    unittest.main()
