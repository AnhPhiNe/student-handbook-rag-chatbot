from __future__ import annotations

from src.generation.answer_guardrails import build_scope_abstention_answer


def test_scope_abstention_blocks_unsupported_high_risk_policy_claim() -> None:
    retrieval_result = {
        "retrieved_items": [
            {
                "content": "Sinh viên sư phạm được xét hỗ trợ học phí theo quy định.",
                "metadata": {
                    "title": "Điều 29. Hỗ trợ chi phí học tập",
                    "document_id": "K51_student_handbook",
                    "source_section": "Điều 29",
                },
            }
        ],
        "context_for_llm": "Điều 29 quy định về học bổng và hỗ trợ chi phí học tập.",
    }

    answer = build_scope_abstention_answer(
        "K51 có chính sách cấp laptop miễn phí cho mọi sinh viên không?",
        retrieval_result,
    )

    assert answer is not None
    assert "chưa thấy căn cứ trực tiếp" in answer.casefold()


def test_scope_abstention_allows_directly_supported_policy_question() -> None:
    retrieval_result = {
        "retrieved_items": [
            {
                "content": (
                    "Sinh viên có thể được nghỉ học tạm thời trong các trường hợp "
                    "được quy định tại Điều 15."
                ),
                "metadata": {
                    "title": "Điều 15. Nghỉ học tạm thời",
                    "document_id": "K51_student_handbook",
                    "source_section": "Điều 15",
                },
            }
        ],
        "context_for_llm": "Điều 15. Nghỉ học tạm thời.",
    }

    assert (
        build_scope_abstention_answer(
            "Sinh viên có được nghỉ học tạm thời không?",
            retrieval_result,
        )
        is None
    )
