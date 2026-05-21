from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.retrieval.core.entity_linker import detect_entities
from src.retrieval.core.query_router import route_query


ENTITY_REGISTRY_PATH = Path("data/processed/entities/entity_registry.json")


class ProductionQueryBehaviorsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.entity_registry = json.loads(
            ENTITY_REGISTRY_PATH.read_text(encoding="utf-8")
        )

    def test_core_router_behaviors_do_not_regress(self) -> None:
        cases = {
            "email phong dao tao la gi": ("office_query", "semantic_filtered_rerank"),
            "khoa van hoc o dau": ("faculty_query", "semantic_filtered_rerank"),
            "diem tb tinh kieu j": ("formula_query", "formula_lookup"),
            "xin giay tam hoan nghia vu quan su": (
                "form_query",
                "semantic_filtered_rerank",
            ),
        }

        for query, (expected_intent, expected_strategy) in cases.items():
            with self.subTest(query=query):
                route = route_query(query)
                self.assertEqual(route["intent"], expected_intent)
                self.assertEqual(route["strategy"], expected_strategy)

    def test_program_aliases_resolve_to_parent_faculty(self) -> None:
        cases = {
            "khoa van hoc o dau": "Khoa Ngữ văn",
            "nganh giao duc hoc lien he ai": "Khoa Khoa học Giáo dục",
            "nganh su pham cong nghe o dau": "Khoa Vật lí",
            "khoa ngu vna o dau": "Khoa Ngữ văn",
        }

        for query, expected_entity in cases.items():
            with self.subTest(query=query):
                names = [
                    entity["canonical_name"]
                    for entity in detect_entities(query, self.entity_registry)
                ]
                self.assertIn(expected_entity, names)


if __name__ == "__main__":
    unittest.main()
