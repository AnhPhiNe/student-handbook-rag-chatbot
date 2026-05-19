import unittest

from src.generation.answer_guardrails import detect_ambiguous_query


def _item(chunk_type: str, score: float, entity_type: str = "") -> dict:
    metadata = {"chunk_type": chunk_type}
    if entity_type:
        metadata["entity_type"] = entity_type
    return {
        "metadata": metadata,
        "rerank": {"final_score": score},
    }


def _retrieval(
    *,
    detected_entities: list[dict] | None = None,
    retrieved_items: list[dict] | None = None,
    intent: str = "office_query",
) -> dict:
    return {
        "intent": intent,
        "detected_entities": detected_entities or [],
        "retrieved_items": retrieved_items or [],
        "context_for_llm": "synthetic context",
    }


CNTT_CONFLICT_ENTITIES = [
    {
        "canonical_name": "Phòng Công nghệ Thông tin",
        "entity_type": "office",
        "aliases": ["cntt", "công nghệ thông tin", "it"],
    },
    {
        "canonical_name": "Khoa Công nghệ - Thông tin",
        "entity_type": "faculty",
        "aliases": ["cntt", "công nghệ thông tin", "it"],
    },
]


class Phase8AmbiguityTest(unittest.TestCase):
    def test_cntt_without_scope_needs_clarification(self) -> None:
        retrieval = _retrieval(
            detected_entities=CNTT_CONFLICT_ENTITIES,
            retrieved_items=[
                _item("office_directory", 0.82, "office"),
                _item("faculty_program_directory", 0.79, "faculty"),
            ],
        )

        self.assertTrue(detect_ambiguous_query("CNTT ở đâu?", retrieval))

    def test_explicit_cntt_scope_does_not_need_clarification(self) -> None:
        retrieval = _retrieval(
            detected_entities=CNTT_CONFLICT_ENTITIES,
            retrieved_items=[
                _item("office_directory", 0.82, "office"),
                _item("faculty_program_directory", 0.79, "faculty"),
            ],
        )

        self.assertFalse(detect_ambiguous_query("Phòng CNTT ở đâu?", retrieval))
        self.assertFalse(detect_ambiguous_query("Khoa CNTT ở đâu?", retrieval))

    def test_generic_academic_affairs_and_documents_need_clarification(self) -> None:
        self.assertTrue(
            detect_ambiguous_query(
                "Học vụ liên hệ ai?",
                _retrieval(retrieved_items=[_item("office_directory", 0.76)]),
            )
        )
        self.assertTrue(
            detect_ambiguous_query(
                "Giấy tờ sinh viên làm ở đâu?",
                _retrieval(retrieved_items=[_item("form", 0.77), _item("procedure", 0.73)]),
            )
        )

    def test_specific_regression_queries_do_not_need_clarification(self) -> None:
        clear_regulation = _retrieval(
            intent="regulation_query",
            retrieved_items=[_item("regulation", 0.81), _item("regulation", 0.76)],
        )
        clear_form = _retrieval(
            intent="form_query",
            retrieved_items=[_item("form", 0.81), _item("procedure", 0.78)],
        )
        deterministic_score = {
            "structured_result": {
                "table_name": "Điểm rèn luyện",
                "input_value": 85,
                "result": {"label": "Tốt"},
            }
        }

        self.assertFalse(
            detect_ambiguous_query("Có thể học vượt để ra trường sớm không?", clear_regulation)
        )
        self.assertFalse(
            detect_ambiguous_query("Có giới hạn số lần học lại một môn không?", clear_regulation)
        )
        self.assertFalse(
            detect_ambiguous_query("Muốn tạm nghỉ học cần mẫu đơn nào?", clear_form)
        )
        self.assertFalse(
            detect_ambiguous_query("Điểm rèn luyện 85 là loại gì?", deterministic_score)
        )

    def test_close_retrieval_conflict_only_triggers_for_under_specified_query(self) -> None:
        mixed_retrieval = _retrieval(
            intent="mixed_query",
            retrieved_items=[_item("form", 0.80), _item("office_directory", 0.75)],
        )

        self.assertTrue(detect_ambiguous_query("Giấy tờ", mixed_retrieval))
        self.assertFalse(
            detect_ambiguous_query(
                "Muốn xin giấy xác nhận sinh viên cần mẫu đơn nào?",
                mixed_retrieval,
            )
        )


if __name__ == "__main__":
    unittest.main()
