from __future__ import annotations

from src.generation.amendment_precedence import collect_applicable_amendments
from src.generation.prompt_builder import (
    ANSWER_PROMPT_VERSION,
    build_answer_prompt,
    build_authorized_evidence_packet,
)


def _task(task_id: str, question: str, cohorts: list[str]) -> dict:
    return {
        "id": task_id,
        "question": question,
        "mode": "rag",
        "intent": "open_question",
        "lookup_type": None,
        "cohorts": cohorts,
    }


def test_prompt_is_compact_and_places_final_task_after_evidence() -> None:
    prompt = build_answer_prompt(
        query="Điều kiện xét học bổng là gì?",
        retrieval_result={
            "effective_query": "Điều kiện xét học bổng là gì?",
            "retrieval_query": "telemetry query must stay hidden",
            "strategy": "hybrid_rrf",
            "retrieved_items": [
                {
                    "chunk_id": "p1",
                    "content": "Có ba điều kiện xét học bổng.",
                    "score": 0.91,
                    "metadata": {"title": "Điều 12", "dense_score": 0.88},
                }
            ],
        },
        cohort="K51",
    )

    assert ANSWER_PROMPT_VERSION in prompt
    assert "AUTHORIZED_EVIDENCE_BY_UNIT" in prompt
    assert "Có ba điều kiện xét học bổng." in prompt
    assert prompt.index("AUTHORIZED_EVIDENCE_BY_UNIT") < prompt.index("FINAL_INSTRUCTIONS")
    assert "Câu hỏi gốc: Điều kiện xét học bổng là gì?" in prompt
    assert "retrieval_query" not in prompt
    assert "dense_score" not in prompt
    assert "hybrid_rrf" not in prompt
    assert "QUERY_PLAN:" not in prompt
    assert "TASK_RESULTS:" not in prompt
    assert "STRUCTURED_RESULT:" not in prompt
    assert "RETRIEVAL_METADATA:" not in prompt
    assert "product_" not in prompt


def test_packet_binds_sources_to_their_tasks() -> None:
    plan = {
        "tasks": [
            _task("t1", "Quy định học bổng?", ["K51"]),
            _task("t2", "Thủ tục bảo lưu?", ["K51"]),
        ]
    }
    packet = build_authorized_evidence_packet(
        query="hai yêu cầu",
        retrieval_result={
            "query_plan": plan,
            "task_results": [
                {"task_id": "t1", "coverage": "covered"},
                {"task_id": "t2", "coverage": "covered"},
            ],
            "coverage_by_task": {"t1": "covered", "t2": "covered"},
        },
        selected_citations=[
            {
                "chunk_id": "scholarship",
                "content": "Nguồn học bổng",
                "supports_task_ids": ["t1"],
                "cohort": "K51",
            },
            {
                "chunk_id": "leave",
                "content": "Nguồn bảo lưu",
                "supports_task_ids": ["t2"],
                "cohort": "K51",
            },
        ],
        fallback_cohort="K51",
        max_context_chars=10000,
    )

    first, second = packet["units"]
    assert first["allowed_source_refs"] == ["S1"]
    assert [source["content"] for source in first["primary_evidence"]] == ["Nguồn học bổng"]
    assert second["allowed_source_refs"] == ["S2"]
    assert [source["content"] for source in second["primary_evidence"]] == ["Nguồn bảo lưu"]


def test_packet_binds_explicit_applicability_per_cohort() -> None:
    plan = {"tasks": [_task("t1", "So sánh quy định", ["K50", "K51"])]}
    packet = build_authorized_evidence_packet(
        query="So sánh quy định K50 và K51",
        retrieval_result={
            "query_plan": plan,
            "task_results": [
                {
                    "task_id": "t1",
                    "coverage": "covered",
                    "coverage_by_cohort": {"K50": "covered", "K51": "covered"},
                }
            ],
        },
        selected_citations=[
            {
                "chunk_id": "p50",
                "content": "Quy định K50",
                "supports_task_ids": ["t1"],
                "applicable_cohorts": ["K50"],
            },
            {
                "chunk_id": "p51",
                "content": "Quy định K51",
                "supports_task_ids": ["t1"],
                "applicable_cohorts": ["K51"],
            },
        ],
        fallback_cohort=None,
        max_context_chars=10000,
    )

    assert packet["units"][0]["allowed_source_refs"] == ["S1"]
    assert packet["units"][1]["allowed_source_refs"] == ["S2"]


def test_selected_citations_are_the_only_primary_evidence() -> None:
    packet = build_authorized_evidence_packet(
        query="Câu hỏi",
        retrieval_result={
            "citations": [
                {"chunk_id": "allowed", "content": "Được chọn"},
                {"chunk_id": "not-selected", "content": "Không được chọn"},
            ]
        },
        selected_citations=[{"chunk_id": "allowed", "content": "Được chọn"}],
        fallback_cohort="K51",
        max_context_chars=10000,
    )

    evidence = packet["units"][0]["primary_evidence"]
    assert [source["source_id"] for source in evidence] == ["allowed"]


def test_structured_legacy_fallback_preserves_full_table() -> None:
    prompt = build_answer_prompt(
        query="K50 hệ chính quy học tối đa bao lâu?",
        retrieval_result={
            "structured_result": {
                "table_name": "Thời gian đào tạo",
                "cohort": "K50",
                "items": [
                    {
                        "applicability": "Áp dụng cho hình thức đào tạo chính quy",
                        "selection_method": "full_table",
                        "rows": [{"Thời gian học tập tối đa": "8 năm học"}],
                    }
                ],
            },
            "citations": [{"source_parent_id": "K50_Dieu3"}],
        },
        cohort="K50",
    )

    assert "Áp dụng cho hình thức đào tạo chính quy" in prompt
    assert "8 năm học" in prompt
    assert "full_table" in prompt


def test_applicable_amendment_is_kept_in_the_unit() -> None:
    amendment_note = (
        "Điểm này đã được sửa đổi tại Quyết định 4743. "
        "Việc sửa đổi, bổ sung áp dụng từ khoá tuyển sinh năm 2025 trở về sau. "
        "Cụ thể như sau:\n"
        "“Sinh viên học cải thiện được dùng điểm đạt cao nhất làm điểm chính thức.”"
    )
    prompt = build_answer_prompt(
        query="K51 học cải thiện thì lấy điểm nào?",
        retrieval_result={
            "retrieved_items": [
                {
                    "chunk_id": "article-10",
                    "content": "Điểm lần học cuối là điểm chính thức.",
                    "metadata": {"cohort": "K51", "title": "Điều 10"},
                }
            ],
            "related_items": [
                {
                    "chunk_id": "article-11",
                    "content": amendment_note,
                    "metadata": {"cohort": "K51", "title": "Điều 11"},
                }
            ],
        },
        cohort="K51",
    )

    assert '"applicable_amendments"' in prompt
    assert "điểm đạt cao nhất" in prompt
    assert "áp dụng nội dung mới nhất" in prompt


def test_newer_amendment_is_not_applied_to_k50() -> None:
    result = {
        "retrieved_items": [
            {
                "chunk_id": "article-10",
                "content": (
                    "Điểm này được sửa đổi, bổ sung và áp dụng từ khóa tuyển sinh "
                    "năm 2025 trở về sau. Cụ thể như sau: "
                    "“Dùng điểm đạt cao nhất làm điểm chính thức.”"
                ),
                "metadata": {"cohort": "K50", "title": "Điều 10"},
            }
        ]
    }
    assert collect_applicable_amendments(
        result,
        query="Học cải thiện lấy điểm nào?",
        cohort="K50",
    ) == []


def test_long_primary_source_uses_request_budget_not_legacy_1500_cap() -> None:
    long_content = ("nội dung dài " * 160) + "TAIL_MARKER_CONTEXT_VAN_CON"
    prompt = build_answer_prompt(
        query="Điều kiện là gì?",
        retrieval_result={
            "retrieved_items": [
                {
                    "chunk_id": "long-source",
                    "content": long_content,
                    "metadata": {"title": "Điều quy định"},
                }
            ]
        },
        max_context_chars=5000,
    )
    assert "TAIL_MARKER_CONTEXT_VAN_CON" in prompt
