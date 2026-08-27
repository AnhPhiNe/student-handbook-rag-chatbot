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
    assert "trình bày riêng mọi nhánh có evidence trực tiếp" in prompt
    assert "Không lấy điều kiện của một nhánh" in prompt
    assert "Không suy ra một điều kiện đã hoặc chưa được đáp ứng" in prompt
    assert "không tự biến việc diễn giải tiêu chí thành lệnh cấm hoặc cho phép" in prompt
    assert "nêu đúng article_label" in prompt
    assert "in đậm kết luận chính" in prompt
    assert '"article_label": "Điều 16"' in prompt


def test_packet_does_not_promote_cross_reference_to_source_article() -> None:
    packet = build_authorized_evidence_packet(
        query="Quy định hiện hành là gì?",
        retrieval_result={"citations": []},
        selected_citations=[
            {
                "chunk_id": "source-without-article",
                "title": "Quy định chung",
                "content": "Nội dung này dẫn chiếu Điều 99 ở đoạn sau.",
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


def test_prompt_distinguishes_external_referral_from_direct_answer() -> None:
    prompt = build_answer_prompt(
        query="Ai thuộc diện miễn giảm học phí?",
        retrieval_result={"retrieved_items": []},
    )

    assert "Mở đầu bằng câu trả lời trực tiếp cho đúng từ hỏi" in prompt
    assert "nguồn chỉ dẫn chiếu sang văn bản khác" in prompt
    assert "không trình bày câu dẫn chiếu như thể đã trả lời danh sách" in prompt
