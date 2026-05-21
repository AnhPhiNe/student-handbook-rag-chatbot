from __future__ import annotations

import unittest

from src.retrieval.core.entity_linker import detect_entities, normalize_query_with_entities


class EntityLinkerTest(unittest.TestCase):
    def test_detects_accentless_faculty_alias(self) -> None:
        registry = [
            {
                "canonical_name": "Khoa Ngữ văn",
                "entity_type": "faculty",
                "aliases": ["khoa ngữ văn", "khoa văn học", "văn học"],
            }
        ]

        detected = detect_entities("cau biet khoa van hoc o dau khong?", registry)

        self.assertEqual(len(detected), 1)
        self.assertEqual(detected[0]["canonical_name"], "Khoa Ngữ văn")
        self.assertIn(
            "Khoa Ngữ văn",
            normalize_query_with_entities("cau biet khoa van hoc o dau khong?", detected),
        )

    def test_detects_light_typo_when_alias_is_long_enough(self) -> None:
        registry = [
            {
                "canonical_name": "Khoa Ngữ văn",
                "entity_type": "faculty",
                "aliases": ["khoa ngữ văn"],
            }
        ]

        detected = detect_entities("khoa ngu vna o dau?", registry)

        self.assertEqual(len(detected), 1)
        self.assertEqual(detected[0]["canonical_name"], "Khoa Ngữ văn")


if __name__ == "__main__":
    unittest.main()
