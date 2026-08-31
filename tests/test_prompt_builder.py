from __future__ import annotations

from src.generation.amendment_precedence import (
    ApplicableAmendment,
    collect_applicable_amendments,
    strip_misattached_amendment_notes,
)
from src.generation.prompt_builder import (
    ANSWER_PROMPT_VERSION,
    _amendment_evidence,
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
                    "metadata": {
                        "title": "Điều 12",
                        "cohort": "K51",
                        "dense_score": 0.88,
                    },
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


def test_prompt_requires_complete_cited_markdown_and_preserves_scope() -> None:
    prompt = build_answer_prompt(
        query="Năm nhất có được xin nghỉ học tạm thời?",
        retrieval_result={
            "citations": [
                {
                    "chunk_id": "K51_Dieu16",
                    "title": "Nghỉ học tạm thời",
                    "content": (
                        "Điều 16. Sinh viên có nhiều trường hợp nghỉ học tạm thời; "
                        "điều kiện học tối thiểu một học kỳ chỉ áp dụng cho lý do cá nhân."
                    ),
                    "cohort": "K51",
                }
            ]
        },
        cohort="K51",
    )

    assert "không tự ý rút gọn đến mức gây hiểu lầm" in prompt
    assert "phải giữ đúng phạm vi ngữ nghĩa mà nguồn trực tiếp xác lập" in prompt
    assert "đối tượng, hành vi, kết quả được áp dụng, điều kiện và hệ quả" in prompt
    assert "Không coi hai khái niệm là tương đương" in prompt
    assert "kể cả khi đặt trong ngoặc" in prompt
    assert "gọi tên và trình bày riêng từng phần" in prompt
    assert "Chỉ kết luận dứt khoát đối với từng ý" in prompt
    assert "Nếu kết quả phụ thuộc thông tin câu hỏi chưa cung cấp" in prompt
    assert "không tự đoán hoặc trả lời có/không tuyệt đối" in prompt
    assert "Mở đầu bằng câu trả lời trực tiếp" not in prompt
    assert "chỉ được trả lời có/không khi evidence trực tiếp" in prompt
    assert "việc nguồn không nói \"được phép\"" in prompt
    assert "nêu đúng article_label" in prompt
    assert "in đậm kết luận chính" in prompt
    assert "Với đơn vị mode=structured" in prompt
    assert "không sao chép toàn bộ bảng" in prompt
    assert "structured evidence có resolved_result" in prompt
    assert 'không suy "Sổ tay không quy định"' in prompt
    assert "role=target" in prompt
    assert "bao quát đủ các khoản/ý trực tiếp của target" in prompt
    assert "không biến mục gần nghĩa thành target mới" in prompt
    assert "Nguồn hiện có chưa trực tiếp xác lập" in prompt
    assert "Sổ tay chưa nêu trực tiếp" not in prompt
    assert "evidence đã được cấp cho đơn vị" in prompt
    assert "không tính lại, nội suy hoặc mượn số liệu từ đơn vị khác" in prompt
    assert '"article_label": "Điều 16"' in prompt


def test_resolved_structured_result_is_explicit_in_authorized_packet() -> None:
    resolved_result = {
        "result": {
            "certificate": "IELTS",
            "matched_level": "bac_4",
            "matched_value": 6.0,
        }
    }
    citation = {
        "chunk_id": "K50_Dieu8",
        "source_parent_id": "K50_Dieu8",
        "cohort": "K51",
        "source_cohort": "K50",
        "applicable_cohorts": ["K51"],
        "applicability_validated": True,
        "supports_task_ids": ["t1"],
        "content": '{"rows":[{"certificate":"IELTS"}]}',
        "resolved_result": resolved_result,
    }
    packet = build_authorized_evidence_packet(
        query="IELTS 6.0 tương đương bậc mấy?",
        retrieval_result={
            "query_plan": {
                "tasks": [
                    {
                        "id": "t1",
                        "question": "IELTS 6.0 tương đương bậc mấy?",
                        "mode": "structured",
                        "cohorts": ["K51"],
                    }
                ]
            },
            "task_results": [{"task_id": "t1", "coverage": "covered"}],
            "coverage_by_task": {"t1": "covered"},
            "evidence_citations": [citation],
        },
        selected_citations=[citation],
        max_context_chars=10000,
        fallback_cohort="K51",
    )

    assert packet["units"][0]["primary_evidence"][0]["resolved_result"] == resolved_result


def test_prompt_separates_distinct_scopes_without_case_specific_rules() -> None:
    prompt = build_answer_prompt(
        query="Quy định này áp dụng thế nào?",
        retrieval_result={
            "citations": [
                {
                    "chunk_id": "K51_Dieu1",
                    "title": "Phạm vi áp dụng",
                    "content": (
                        "Điều 1. Mỗi đối tượng và trường hợp có điều kiện, "
                        "kết quả áp dụng riêng."
                    ),
                    "cohort": "K51",
                }
            ]
        },
        cohort="K51",
    )

    assert "khái niệm gần nghĩa" in prompt
    assert "coi chúng là cùng một cơ chế" in prompt
    assert "giữ đúng điều kiện và ngoại lệ tương ứng" in prompt
    assert "bảo lưu kết quả học tập" not in prompt
    assert "nghỉ học tạm thời" not in prompt


def test_packet_does_not_promote_cross_reference_to_source_article() -> None:
    packet = build_authorized_evidence_packet(
        query="Quy định hiện hành là gì?",
        retrieval_result={"citations": []},
        selected_citations=[
            {
                "chunk_id": "source-without-article",
                "title": "Quy định chung",
                "content": "Nội dung này dẫn chiếu Điều 99 ở đoạn sau.",
                "cohort": "K51",
            }
        ],
        fallback_cohort="K51",
        max_context_chars=10000,
    )

    assert packet["units"][0]["primary_evidence"][0]["article_label"] is None


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


def test_packet_binds_runtime_clarification_to_exact_cohort() -> None:
    first_question = "Sinh viên K48-K49 cần tra cứu chứng chỉ nào?"
    second_question = "Sinh viên K50 cần tra cứu chứng chỉ nào?"
    packet = build_authorized_evidence_packet(
        query="So sánh yêu cầu ngoại ngữ giữa các khóa",
        retrieval_result={
            "query_plan": {
                "tasks": [
                    {
                        **_task(
                            "t1",
                            "Yêu cầu ngoại ngữ?",
                            ["K48-K49", "K50", "K51"],
                        ),
                        "mode": "structured",
                        "clarification_question": "Không dùng câu hỏi chung của task.",
                    },
                    {
                        **_task("t2", "Yêu cầu chứng chỉ?", ["K51"]),
                        "mode": "structured",
                        "clarification_question": "Không dùng câu hỏi task khác.",
                    },
                ]
            },
            "task_results": [
                {
                    "task_id": "t1",
                    "coverage": "needs_clarification",
                    "coverage_by_cohort": {
                        "K48-K49": "needs_clarification",
                        "K50": "needs_clarification",
                        "K51": "covered",
                    },
                    "clarification_by_cohort": {
                        "K48-K49": first_question,
                        "K50": second_question,
                        "K51": "Không dùng câu hỏi cũ cho khóa đã đủ nguồn.",
                    },
                    "clarification_question": "Không dùng câu hỏi chung của result.",
                },
                {
                    "task_id": "t2",
                    "coverage": "needs_clarification",
                    "coverage_by_cohort": {"K51": "needs_clarification"},
                    "clarification_by_cohort": {},
                    "clarification_question": "Không dùng câu hỏi result khác.",
                },
            ],
            "clarification_question": "Không dùng câu hỏi toàn cục.",
        },
        selected_citations=[
            {
                "chunk_id": "language-k51",
                "content": "Yêu cầu ngoại ngữ K51",
                "supports_task_ids": ["t1"],
                "cohort": "K51",
            }
        ],
        fallback_cohort=None,
        max_context_chars=10000,
    )

    units = {
        (unit["task_id"], unit["cohort"]): unit for unit in packet["units"]
    }
    assert units[("t1", "K48-K49")]["clarification_question"] == first_question
    assert units[("t1", "K50")]["clarification_question"] == second_question
    assert units[("t1", "K51")]["clarification_question"] is None
    assert units[("t2", "K51")]["clarification_question"] is None
    for key in (("t1", "K48-K49"), ("t1", "K50"), ("t2", "K51")):
        assert units[key]["coverage"] == "needs_clarification"
        assert units[key]["allowed_source_refs"] == []
        assert units[key]["primary_evidence"] == []
    assert units[("t1", "K51")]["coverage"] == "covered"
    assert units[("t1", "K51")]["allowed_source_refs"] == ["S1"]


def test_packet_preserves_legacy_task_and_result_clarification_questions() -> None:
    task_question = "Bạn muốn tra cứu quy định nào?"
    result_question = "Bạn muốn tra cứu chứng chỉ nào?"
    packet = build_authorized_evidence_packet(
        query="Hai yêu cầu cần làm rõ",
        retrieval_result={
            "query_plan": {
                "tasks": [
                    {
                        **_task("t1", "Quy định?", ["K51"]),
                        "mode": "clarify",
                        "clarification_question": task_question,
                    },
                    {
                        **_task("t2", "Yêu cầu ngoại ngữ?", ["K51"]),
                        "mode": "structured",
                    },
                ]
            },
            "task_results": [
                {
                    "task_id": "t1",
                    "coverage": "needs_clarification",
                    "clarification_question": "Câu hỏi task được ưu tiên.",
                },
                {
                    "task_id": "t2",
                    "coverage": "needs_clarification",
                    "clarification_by_cohort": None,
                    "clarification_question": result_question,
                },
            ],
            "clarification_question": "Không dùng câu hỏi toàn cục.",
        },
        selected_citations=[],
        fallback_cohort="K51",
        max_context_chars=10000,
    )

    first, second = packet["units"]
    assert first["clarification_question"] == task_question
    assert second["clarification_question"] == result_question
    assert first["allowed_source_refs"] == second["allowed_source_refs"] == []


def test_shared_source_uses_table_for_structured_and_parent_text_for_rag() -> None:
    structured_task = {
        **_task("t1", "Điểm học bổng loại Giỏi?", ["K51"]),
        "mode": "structured",
        "lookup_type": "scholarship_classification",
    }
    packet = build_authorized_evidence_packet(
        query="Điểm loại Giỏi và điều kiện xét học bổng?",
        retrieval_result={
            "query_plan": {
                "tasks": [
                    structured_task,
                    _task("t2", "Điều kiện xét học bổng?", ["K51"]),
                ]
            },
            "task_results": [
                {"task_id": "t1", "coverage": "covered"},
                {"task_id": "t2", "coverage": "covered"},
            ],
        },
        selected_citations=[
            {
                "source_parent_id": "K51_Dieu27",
                "content": '{"scholarship_level":"Giỏi"}',
                "parent_content": "Điều kiện gồm đủ tín chỉ và không bị kỷ luật.",
                "supports_task_ids": ["t1", "t2"],
                "cohort": "K51",
            }
        ],
        fallback_cohort="K51",
        max_context_chars=10000,
    )

    assert packet["units"][0]["primary_evidence"][0]["content"] == (
        '{"scholarship_level":"Giỏi"}'
    )
    assert packet["units"][1]["primary_evidence"][0]["content"] == (
        "Điều kiện gồm đủ tín chỉ và không bị kỷ luật."
    )


def test_misattached_amendment_is_removed_using_authoritative_target() -> None:
    note = (
        "Điểm này đã được sửa đổi, bổ sung. Cụ thể như sau: "
        "“d) Quy tắc thuộc điều trước.”"
    )
    registry = (
        {
            "target_parent_id": "Dieu11",
            "replacement_text": "d) Quy tắc thuộc điều trước.",
        },
    )

    assert strip_misattached_amendment_notes(
        f"Điều 12. Nội dung hiện tại\n{note}\n2. Nội dung tiếp theo",
        source_parent_id="Dieu12",
        registry=registry,
    ) == "Điều 12. Nội dung hiện tại\n\n2. Nội dung tiếp theo"
    assert note in strip_misattached_amendment_notes(
        f"Điều 11. Nội dung\n{note}",
        source_parent_id="Dieu11",
        registry=registry,
    )


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
                "source_cohort": "K50",
                "applicable_cohorts": ["K50"],
            },
            {
                "chunk_id": "p51",
                "content": "Quy định K51",
                "supports_task_ids": ["t1"],
                "source_cohort": "K51",
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
                {"chunk_id": "allowed", "content": "Được chọn", "cohort": "K51"},
                {
                    "chunk_id": "not-selected",
                    "content": "Không được chọn",
                    "cohort": "K51",
                },
            ]
        },
        selected_citations=[
            {"chunk_id": "allowed", "content": "Được chọn", "cohort": "K51"}
        ],
        fallback_cohort="K51",
        max_context_chars=10000,
    )

    evidence = packet["units"][0]["primary_evidence"]
    assert [source["source_id"] for source in evidence] == ["allowed"]


def test_packet_fails_closed_when_source_cohort_is_missing() -> None:
    packet = build_authorized_evidence_packet(
        query="Quy định K51 là gì?",
        retrieval_result={},
        selected_citations=[{"chunk_id": "unknown", "content": "Không rõ khóa."}],
        fallback_cohort="K51",
        max_context_chars=10000,
    )

    assert packet["units"][0]["primary_evidence"] == []
    assert packet["units"][0]["allowed_source_refs"] == []


def test_packet_only_allows_validated_cross_cohort_applicability() -> None:
    base_source = {
        "chunk_id": "K50-policy",
        "content": "Quy định áp dụng từ khóa tuyển sinh 2022 trở về sau.",
        "source_cohort": "K50",
        "applicable_cohorts": ["K51"],
    }
    denied = build_authorized_evidence_packet(
        query="Quy định K51 là gì?",
        retrieval_result={},
        selected_citations=[base_source],
        fallback_cohort="K51",
        max_context_chars=10000,
    )
    allowed = build_authorized_evidence_packet(
        query="Quy định K51 là gì?",
        retrieval_result={},
        selected_citations=[{**base_source, "applicability_validated": True}],
        fallback_cohort="K51",
        max_context_chars=10000,
    )

    assert denied["units"][0]["primary_evidence"] == []
    assert [source["source_id"] for source in allowed["units"][0]["primary_evidence"]] == [
        "K50-policy"
    ]


def test_packet_does_not_treat_title_substrings_as_authority() -> None:
    packet = build_authorized_evidence_packet(
        query=(
            "Sinh viên cần lưu ý gì về Chi phí bồi hoàn và cách tính "
            "chi phí bồi hoàn?"
        ),
        retrieval_result={},
        selected_citations=[
            {
                "chunk_id": "related-first",
                "title": "Thu hồi chi phí bồi hoàn",
                "content": "Nguồn liên quan đứng hạng đầu.",
                "cohort": "K50",
            },
            {
                "chunk_id": "exact-second",
                "title": "Chi phí bồi hoàn và cách tính chi phí bồi hoàn",
                "content": "Nguồn đích danh đứng hạng hai.",
                "cohort": "K50",
            },
            {
                "chunk_id": "generic-third",
                "title": "Sinh viên",
                "content": "Tiêu đề ngắn cũng xuất hiện trong câu hỏi.",
                "cohort": "K50",
            },
        ],
        fallback_cohort="K50",
        max_context_chars=10000,
    )

    evidence = packet["units"][0]["primary_evidence"]
    assert [(source["source_id"], source["role"]) for source in evidence] == [
        ("related-first", "candidate"),
        ("exact-second", "candidate"),
        ("generic-third", "candidate"),
    ]


def test_packet_keeps_ambiguous_article_sources_as_candidates() -> None:
    packet = build_authorized_evidence_packet(
        query="Điều 16 quy định gì?",
        retrieval_result={},
        selected_citations=[
            {
                "chunk_id": "doc-a-16",
                "title": "Nghỉ học tạm thời",
                "article_label": "Điều 16",
                "content": "Quy chế A.",
                "cohort": "K50",
            },
            {
                "chunk_id": "doc-b-16",
                "title": "Phòng Hợp tác Quốc tế",
                "article_label": "Điều 16",
                "content": "Quy chế B.",
                "cohort": "K50",
            },
        ],
        fallback_cohort="K50",
        max_context_chars=10000,
    )

    assert [
        (source["source_id"], source["role"])
        for source in packet["units"][0]["primary_evidence"]
    ] == [("doc-a-16", "candidate"), ("doc-b-16", "candidate")]


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


def test_curated_registry_applies_without_parseable_pdf_footnote() -> None:
    registry = (
        {
            "target_parent_id": "K51_Dieu10",
            "replacement_text": (
                "Thang điểm học phần đại cương: D+ từ 4,8 đến 5,4 là đạt."
            ),
            "applicability": {"kind": "min_admission_year", "year": 2025},
            "cohort": "K51",
            "importance": "substantive",
            "source_document_id": "4743/QĐ-ĐHSP",
            "source_locator": "khoản 3, Điều 1",
            "source_handbook_id": "so_tay_sinh_vien_khoa_51",
            "source_handbook_title": "Sổ tay sinh viên khóa 51",
            "source_pages": [18],
        },
    )
    result = {
        "retrieved_items": [
            {
                "chunk_id": "K51_Dieu10",
                "content": "Nội dung PDF bị mất dấu ngoặc kép đóng.",
                "metadata": {"cohort": "K51", "title": "Điều 10"},
            }
        ]
    }

    amendments = collect_applicable_amendments(
        result,
        query="Thang điểm D+ của học phần đại cương?",
        cohort="K51",
        registry=registry,
    )

    assert len(amendments) == 1
    assert amendments[0].source_parent_id == "K51_Dieu10"
    assert "D+ từ 4,8 đến 5,4" in amendments[0].replacement_text
    assert amendments[0].source_document_id == "4743/QĐ-ĐHSP"
    assert amendments[0].source_locator == "khoản 3, Điều 1"
    assert amendments[0].source_handbook_title == "Sổ tay sinh viên khóa 51"
    assert amendments[0].source_pages == (18,)


def test_amendment_evidence_exposes_only_simple_provenance_fields() -> None:
    amendment = ApplicableAmendment(
        source_parent_id="K51_Dieu10",
        source_role="primary",
        source_title="Điều 10",
        effective_rule="khóa tuyển sinh từ năm 2025 trở về sau",
        replacement_text="Nội dung thay thế.",
        relevance_score=2,
        source_document_id="4743/QĐ-ĐHSP",
        source_locator="khoản 3, Điều 1, Quyết định số 4743/QĐ-ĐHSP",
        source_handbook_id="so_tay_sinh_vien_khoa_51",
        source_handbook_title="Sổ tay sinh viên khóa 51",
        source_pages=(18,),
    )

    assert _amendment_evidence(amendment) == {
        "amendment_source": "khoản 3, Điều 1, Quyết định số 4743/QĐ-ĐHSP",
        "citation_source": "Sổ tay sinh viên khóa 51",
        "citation_pages": [18],
        "effective_rule": "khóa tuyển sinh từ năm 2025 trở về sau",
        "replacement_text": "Nội dung thay thế.",
    }


def test_non_substantive_registry_note_is_not_promoted() -> None:
    registry = (
        {
            "target_parent_id": "K51_Dieu10",
            "replacement_text": "Ghi chú trình bày thang điểm.",
            "cohort": "K51",
            "importance": "non_substantive",
        },
    )
    result = {
        "retrieved_items": [
            {
                "chunk_id": "K51_Dieu10",
                "content": "Điều 10",
                "metadata": {"cohort": "K51"},
            }
        ]
    }

    assert collect_applicable_amendments(
        result,
        query="Ghi chú thang điểm",
        cohort="K51",
        registry=registry,
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


def test_unit_budget_is_computed_after_task_cohort_and_target_filtering() -> None:
    tasks = [
        _task(f"t{task_index}", f"Quy định task {task_index}?", ["K48-K49", "K50", "K51"])
        for task_index in range(1, 4)
    ]
    tasks[0]["question"] = "Điều 27 quy định gì?"
    long_target = ("nội dung Điều khoản đích danh " * 240) + "TARGET_TAIL_PRESERVED"
    citations = []
    for task_index in range(1, 4):
        for cohort in ("K48-K49", "K50", "K51"):
            for source_index in range(1, 6):
                is_target = task_index == 1 and source_index == 1
                citations.append(
                    {
                        "chunk_id": f"t{task_index}-{cohort}-{source_index}",
                        "title": (
                            "Điều khoản đích danh"
                            if is_target
                            else f"Nguồn liên quan {task_index} {source_index}"
                        ),
                        "article_label": "Điều 27" if is_target else None,
                        "content": long_target if is_target else "Nội dung liên quan.",
                        "cohort": cohort,
                        "supports_task_ids": [f"t{task_index}"],
                    }
                )

    packet = build_authorized_evidence_packet(
        query="Điều 27 quy định gì?",
        retrieval_result={
            "query_plan": {"tasks": tasks},
            "task_results": [
                {
                    "task_id": task["id"],
                    "coverage": "covered",
                    "coverage_by_cohort": {
                        "K48-K49": "covered",
                        "K50": "covered",
                        "K51": "covered",
                    },
                }
                for task in tasks
            ],
        },
        selected_citations=citations,
        fallback_cohort=None,
        max_context_chars=160000,
    )

    target_unit = next(
        unit
        for unit in packet["units"]
        if unit["task_id"] == "t1" and unit["cohort"] == "K51"
    )
    assert len(citations) == 45
    assert len(target_unit["primary_evidence"]) == 5
    assert [source["role"] for source in target_unit["primary_evidence"]] == [
        "target",
        "candidate",
        "candidate",
        "candidate",
        "candidate",
    ]
    assert "TARGET_TAIL_PRESERVED" in target_unit["primary_evidence"][0]["content"]


def test_global_evidence_cap_truncates_only_oversized_candidate_workload() -> None:
    tasks = [
        _task(f"t{task_index}", f"Câu hỏi rộng task {task_index}?", ["K48-K49", "K50", "K51"])
        for task_index in range(1, 4)
    ]
    citations = [
        {
            "chunk_id": f"t{task_index}-{cohort}-{source_index}",
            "title": f"Nguồn candidate {task_index} {source_index}",
            "content": ("candidate dài " * 650) + "CANDIDATE_TAIL",
            "cohort": cohort,
            "supports_task_ids": [f"t{task_index}"],
        }
        for task_index in range(1, 4)
        for cohort in ("K48-K49", "K50", "K51")
        for source_index in range(1, 6)
    ]
    packet = build_authorized_evidence_packet(
        query="Một câu hỏi rộng không đích danh Điều hoặc tiêu đề",
        retrieval_result={
            "query_plan": {"tasks": tasks},
            "task_results": [
                {
                    "task_id": task["id"],
                    "coverage": "covered",
                    "coverage_by_cohort": {
                        "K48-K49": "covered",
                        "K50": "covered",
                        "K51": "covered",
                    },
                }
                for task in tasks
            ],
        },
        selected_citations=citations,
        fallback_cohort=None,
        max_context_chars=160000,
    )

    evidence = [
        source
        for unit in packet["units"]
        for source in unit["primary_evidence"]
    ]
    assert len(evidence) == 45
    assert sum(len(source["content"]) for source in evidence) <= 120000
    assert all(source["role"] == "candidate" for source in evidence)
    assert any("[Evidence đã được rút gọn.]" in source["content"] for source in evidence)


def test_candidate_budget_is_split_by_unit_before_sources() -> None:
    tasks = [
        _task("t1", "Câu hỏi rộng thứ nhất?", ["K51"]),
        _task("t2", "Câu hỏi rộng thứ hai?", ["K51"]),
    ]
    citations = [
        {
            "chunk_id": "t1-only-source",
            "title": "Nguồn chung thứ nhất",
            "content": "A" * 1000,
            "cohort": "K51",
            "supports_task_ids": ["t1"],
        },
        *[
            {
                "chunk_id": f"t2-source-{index}",
                "title": f"Nguồn chung thứ hai {index}",
                "content": "B" * 1000,
                "cohort": "K51",
                "supports_task_ids": ["t2"],
            }
            for index in range(1, 6)
        ],
    ]
    packet = build_authorized_evidence_packet(
        query="Hai câu hỏi rộng không đích danh Điều hoặc tiêu đề",
        retrieval_result={
            "query_plan": {"tasks": tasks},
            "task_results": [
                {
                    "task_id": task["id"],
                    "coverage": "covered",
                    "coverage_by_cohort": {"K51": "covered"},
                }
                for task in tasks
            ],
        },
        selected_citations=citations,
        fallback_cohort="K51",
        max_context_chars=400,
    )

    content_by_task = {
        unit["task_id"]: sum(
            len(source["content"]) for source in unit["primary_evidence"]
        )
        for unit in packet["units"]
    }
    assert content_by_task == {"t1": 150, "t2": 150}


def test_prompt_distinguishes_external_referral_from_direct_answer() -> None:
    prompt = build_answer_prompt(
        query="Ai thuộc diện miễn giảm học phí?",
        retrieval_result={"retrieved_items": []},
    )

    assert "Chỉ kết luận dứt khoát đối với từng ý" in prompt
    assert "Nếu kết quả phụ thuộc thông tin câu hỏi chưa cung cấp" in prompt
    assert "nguồn chỉ dẫn chiếu sang văn bản khác" in prompt
    assert "không trình bày câu dẫn chiếu như thể đã trả lời danh sách" in prompt
