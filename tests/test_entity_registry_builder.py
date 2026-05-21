from __future__ import annotations

import unittest

from src.retrieval.core.build_entity_registry import (
    extract_program_names,
    make_program_aliases,
)


class EntityRegistryBuilderTest(unittest.TestCase):
    def test_extracts_program_names_from_faculty_raw_text(self) -> None:
        raw_text = """
6. Khoa Ngữ văn
NGÀNH SƯ PHẠM NGỮ VĂN
Cơ hội nghề nghiệp sau khi tốt nghiệp:
NGÀNH VĂN HỌC
Cơ hội nghề nghiệp sau khi tốt nghiệp:
TIẾNG VIỆT VÀ VĂN HÓA VIỆT NAM (DÀNH CHO SINH
VIÊN NƯỚC NGOÀI)
Cơ hội nghề nghiệp sau khi tốt nghiệp:
"""

        names = extract_program_names(raw_text)

        self.assertIn("Sư Phạm Ngữ Văn", names)
        self.assertIn("Văn Học", names)
        self.assertIn(
            "Tiếng Việt Và Văn Hóa Việt Nam (Dành Cho Sinh Viên Nước Ngoài)",
            names,
        )

    def test_program_aliases_include_accentless_faculty_style_aliases(self) -> None:
        aliases = make_program_aliases(["Văn Học", "Sư Phạm Tin Học"])

        self.assertIn("khoa văn học", aliases)
        self.assertIn("khoa van hoc", aliases)
        self.assertNotIn("tin hoc", aliases)
        self.assertIn("ngành sư phạm tin học", aliases)


if __name__ == "__main__":
    unittest.main()
