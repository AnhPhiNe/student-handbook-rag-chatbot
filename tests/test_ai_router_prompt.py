from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.retrieval.core.ai_router as ai_router_module
from src.retrieval.core.ai_router import (
    AIRouter,
    PLANNER_SYSTEM_PROMPT,
    ROUTER_PROMPT_VERSION,
)
from src.retrieval.core.query_plan import QUERY_PLAN_NORMALIZER_VERSION
from src.retrieval.core.structured_routing import (
    compact_registry_for_prompt,
    normalize_router_decision,
    validate_router_decision,
)

PLANNER_PROMPT_TEXT = " ".join(PLANNER_SYSTEM_PROMPT.split())


def _router(monkeypatch, tmp_path: Path, *, model_name: str) -> AIRouter:
    monkeypatch.setenv("GROQ_API_KEYS", "test-router-key")
    return AIRouter(
        model_name=model_name,
        cache_enabled=False,
        key_pool_config={
            "state_path": str(tmp_path / f"{model_name.replace('/', '-')}.json"),
        },
    )


def test_compact_registry_omits_prompt_only_noise() -> None:
    prompt_registry = compact_registry_for_prompt()

    assert "examples" not in prompt_registry
    assert "operand_requirements" not in prompt_registry
    assert "required=" in prompt_registry
    assert "values" in prompt_registry
    assert 'formula_type":{"type":"string","values":["scholarship_score","gpa_weighted_average"]}' in prompt_registry
    assert "điểm học bổng từ điểm học tập và rèn luyện=scholarship_score" in prompt_registry
    assert "Điểm hoặc tên mức xếp loại được hỏi" in prompt_registry
    assert '"aspect":{"type":"string"' in prompt_registry
    assert '"values":["amount","classification"]' in prompt_registry
    scholarship_contract = prompt_registry.split("scholarship_classification|", 1)[1].split(
        "\n", 1
    )[0]
    assert "điều kiện" not in scholarship_contract
    assert "Dịch vụ cần hỗ trợ, không phải tên đơn vị" in prompt_registry


@pytest.mark.parametrize(
    ("query", "lookup_type", "expected_slots"),
    [
        (
            "Mức tiền học bổng Xuất sắc là bao nhiêu?",
            "scholarship_classification",
            {"aspect": "amount"},
        ),
        (
            "Xếp loại học bổng thế nào?",
            "scholarship_classification",
            {"aspect": "classification"},
        ),
        (
            "Thời gian tối đa hệ chính quy là bao lâu?",
            "study_duration",
            {"training_mode": "chinh_quy"},
        ),
    ],
)
def test_reference_table_selectors_are_grounded_from_registry_metadata(
    query: str,
    lookup_type: str,
    expected_slots: dict[str, str],
) -> None:
    normalized = normalize_router_decision(
        {
            "route": "structured",
            "lookup_type": lookup_type,
            "intent": "direct_value",
            "slots": {},
            "slot_spans": {},
        },
        query=query,
        selected_cohort="K51",
    )

    assert normalized["slots"] == expected_slots
    assert set(normalized["slot_spans"]) == set(expected_slots)
    assert validate_router_decision(normalized, query=query) == []


def test_reference_table_selector_stays_absent_for_general_question() -> None:
    normalized = normalize_router_decision(
        {
            "route": "structured",
            "lookup_type": "scholarship_classification",
            "intent": "direct_value",
            "slots": {},
            "slot_spans": {},
        },
        query="Cho tôi thông tin tổng quan về học bổng.",
        selected_cohort="K51",
    )

    assert normalized["slots"] == {}
    assert normalized["slot_spans"] == {}


def test_scholarship_policy_question_does_not_infer_structured_aspect() -> None:
    normalized = normalize_router_decision(
        {
            "route": "structured",
            "lookup_type": "scholarship_classification",
            "intent": "direct_value",
            "slots": {},
            "slot_spans": {},
        },
        query="Điều kiện để được xét học bổng là gì?",
        selected_cohort="K51",
    )

    assert normalized["slots"] == {}
    assert normalized["slot_spans"] == {}


def test_plan_cache_key_includes_normalizer_version(monkeypatch, tmp_path: Path) -> None:
    router = _router(monkeypatch, tmp_path, model_name="qwen/qwen3.8-27b")
    key = router._cache_key(
        "So sánh K50 và K51",
        cohort="K51",
        chat_history=[],
    )

    monkeypatch.setattr(
        ai_router_module,
        "QUERY_PLAN_NORMALIZER_VERSION",
        QUERY_PLAN_NORMALIZER_VERSION + "-changed",
    )
    changed_key = router._cache_key(
        "So sánh K50 và K51",
        cohort="K51",
        chat_history=[],
    )

    assert changed_key != key


def test_planner_prompt_stays_within_budget(monkeypatch, tmp_path: Path) -> None:
    router = _router(monkeypatch, tmp_path, model_name="qwen/qwen3.8-27b")
    dynamic_prompt = router._build_plan_prompt(
        "So sánh hai khóa về thời gian học và một quy định học vụ.",
        cohort="K51",
        chat_history=[],
    )
    stats = AIRouter._prompt_stats_for_system(
        PLANNER_SYSTEM_PROMPT,
        dynamic_prompt,
        router._plan_response_format_payload(),
    )

    assert stats["total_chars"] <= 10700
    assert stats["estimated_input_tokens"] <= 2700
    assert ROUTER_PROMPT_VERSION == "structured-regulation-v39-reference-table-selector"
    assert "OUTPUT CONTRACT" not in dynamic_prompt
    assert "native JSON Schema" in dynamic_prompt
    assert 'COHORT_ADMISSION_YEARS: {"K48-K49":[2022,2023],"K50":[2024],"K51":[2025]}' in dynamic_prompt


def test_planner_prompt_defines_cohort_independent_task_identity() -> None:
    assert "TASK IDENTITY không phụ thuộc cohort" in PLANNER_PROMPT_TEXT
    assert "không tạo M×N tasks" in PLANNER_PROMPT_TEXT
    assert "COHORT từ UI chỉ điền cho task vẫn chưa có cohort" in PLANNER_PROMPT_TEXT
    assert "không ghi đè" in PLANNER_PROMPT_TEXT
    assert "So sánh K50 và K51 về thời gian học tối đa" not in PLANNER_PROMPT_TEXT


def test_planner_prompt_keeps_exactly_three_answer_targets() -> None:
    assert "Với 1–3 yêu cầu" in PLANNER_PROMPT_TEXT
    assert "Đúng 3 yêu cầu" in PLANNER_PROMPT_TEXT


def test_planner_prompt_routes_named_unit_contacts_to_directory() -> None:
    assert "Đơn vị nêu đích danh" in PLANNER_PROMPT_TEXT
    assert "directory office/faculty" in PLANNER_PROMPT_TEXT
    assert "student_service chỉ dùng" in PLANNER_PROMPT_TEXT


def test_planner_prompt_treats_compare_as_presentation_and_slots_as_grounded() -> None:
    assert "So sánh là yêu cầu trình bày" in PLANNER_PROMPT_TEXT
    assert "Không dùng intent=compare" in PLANNER_PROMPT_TEXT
    assert "điền đủ required slots" in PLANNER_PROMPT_TEXT
    assert "Optional slots chỉ xuất khi có căn cứ" in PLANNER_PROMPT_TEXT
    assert "Trích xuất mọi dữ kiện có căn cứ" in PLANNER_PROMPT_TEXT
    assert "runtime chịu trách nhiệm chọn bảng và giải quyết kết quả" in PLANNER_PROMPT_TEXT
    assert "không lọc hàng trong bảng đã chọn" not in PLANNER_PROMPT_TEXT


def test_planner_only_clarifies_genuinely_ambiguous_input() -> None:
    assert "tham chiếu thật sự mơ hồ" in PLANNER_PROMPT_TEXT
    assert "như loại cảnh báo" not in PLANNER_PROMPT_TEXT


def test_planner_prompt_splits_independent_answer_targets() -> None:
    assert "Mỗi task.question chứa một yêu cầu độc lập" in PLANNER_PROMPT_TEXT
    assert "Chỉ gộp các khía cạnh bổ sung" in PLANNER_PROMPT_TEXT
    assert "Tách task khi các phần hỏi về đối tượng/chủ đề độc lập" in PLANNER_PROMPT_TEXT
    assert "Từ nối \"và\" hoặc \"so sánh\" không tự quyết định" in PLANNER_PROMPT_TEXT
    assert "Nhiều entity dùng cùng một structured lookup" in PLANNER_PROMPT_TEXT
    assert "Mỗi task chỉ có một mode" in PLANNER_PROMPT_TEXT
    assert "mỗi yêu cầu độc lập xuất hiện đúng một lần" in PLANNER_PROMPT_TEXT
    assert "composer mới kết hợp" in PLANNER_PROMPT_TEXT


def test_planner_prompt_defines_registry_grounded_cohort_conflict() -> None:
    assert "COHORT_ADMISSION_YEARS là metadata xác thực từ registry" in PLANNER_PROMPT_TEXT
    assert "khóa và năm tuyển sinh cho cùng một đối tượng" in PLANNER_PROMPT_TEXT
    assert "nêu đúng hai giá trị cần xác nhận" in PLANNER_PROMPT_TEXT
    assert "Không áp dụng cho câu so sánh nhiều khóa" in PLANNER_PROMPT_TEXT


def test_planner_limits_tool_contract_to_structured_tasks() -> None:
    assert "Với structured, chỉ dùng lookup_type, intent và slots" in PLANNER_PROMPT_TEXT
    assert "RAG và clarify tuân theo quy tắc riêng ở phần MODE" in PLANNER_PROMPT_TEXT
    assert "Chỉ dùng lookup_type, intent, slots khai báo trong TOOLS" not in PLANNER_PROMPT_TEXT


def test_planner_prompt_requires_grounded_slots_for_structured_mode() -> None:
    assert "Mỗi slot_span phải chính là cụm nguyên văn" in PLANNER_PROMPT_TEXT
    assert "control value được chuẩn hóa" in PLANNER_PROMPT_TEXT
    assert "không phải toàn bộ câu hỏi" in PLANNER_PROMPT_TEXT
    assert "Không chọn structured chỉ vì trùng từ chủ đề" in PLANNER_PROMPT_TEXT
    assert "dù QUERY không" in PLANNER_PROMPT_TEXT
    assert "Chỉ clarify task bị thiếu thông tin" in PLANNER_PROMPT_TEXT


def test_planner_prompt_defines_context_and_hint_precedence_once() -> None:
    assert "standalone_query" in PLANNER_PROMPT_TEXT
    assert "referenced_turns" in PLANNER_PROMPT_TEXT
    assert "CATALOG_HINT là metadata đã được grounding" in PLANNER_PROMPT_TEXT
    assert PLANNER_PROMPT_TEXT.count("hơn 3 yêu cầu") == 2
    assert "xuất đúng một clarify task" in PLANNER_PROMPT_TEXT
    assert "không thực thi một phần" in PLANNER_PROMPT_TEXT


def test_planner_prompt_matches_global_context_and_rag_contract() -> None:
    assert "context_mode=ambiguous chỉ khi toàn QUERY mơ hồ hoặc có hơn 3" in PLANNER_PROMPT_TEXT
    assert "clarify cho riêng task đó" in PLANNER_PROMPT_TEXT
    assert "Mọi RAG task dùng intent=open_question" in PLANNER_PROMPT_TEXT
    assert "Chỉ đặt out_of_domain=true khi toàn bộ QUERY" in PLANNER_PROMPT_TEXT
    assert "khi đó tasks=[]" in PLANNER_PROMPT_TEXT
    assert "giữ các target trong phạm vi" in PLANNER_PROMPT_TEXT
    assert "thiếu evidence" not in PLANNER_PROMPT_TEXT


def test_json_object_planner_keeps_embedded_output_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    router = _router(monkeypatch, tmp_path, model_name="qwen/qwen3.6-27b")

    dynamic_prompt = router._build_plan_prompt(
        "K50 học gì?",
        cohort="K50",
        chat_history=[],
    )

    assert "OUTPUT CONTRACT" in dynamic_prompt
    assert "native JSON Schema" not in dynamic_prompt


def test_planner_prompt_protects_normalized_query_semantics() -> None:
    assert "normalized_query chỉ sửa dấu, chính tả nhẹ" in PLANNER_PROMPT_TEXT
    for protected_value in ("entity", "cohort", "số liệu", "phủ định", "chủ đề", "ý định"):
        assert protected_value in PLANNER_PROMPT_TEXT


def test_model_defaults_select_supported_reasoning_and_format(
    monkeypatch,
    tmp_path: Path,
) -> None:
    qwen_36 = _router(monkeypatch, tmp_path, model_name="qwen/qwen3.6-27b")
    qwen_38 = _router(monkeypatch, tmp_path, model_name="qwen/qwen3.8-27b")
    gpt_oss = _router(monkeypatch, tmp_path, model_name="openai/gpt-oss-20b")

    assert qwen_36._resolved_reasoning_effort() == "none"
    assert qwen_36._plan_response_format_payload() == {"type": "json_object"}
    assert qwen_38._resolved_reasoning_effort() == "low"
    assert qwen_38._plan_response_format_payload()["type"] == "json_schema"
    assert gpt_oss._resolved_reasoning_effort() == "low"
    assert gpt_oss._plan_response_format_payload()["type"] == "json_schema"


def test_router_treats_upstream_disconnect_as_transient() -> None:
    error = RuntimeError("Server disconnected without sending a response.")

    assert AIRouter._classify_error(error) == "transient_error"


def _mock_plan_response(monkeypatch, tasks: list) -> None:
    payload = {
        "schema_version": "v1",
        "context_mode": "standalone",
        "out_of_domain": False,
        "tasks": tasks,
    }

    class _FakeGroq:
        def __init__(self, **_kwargs) -> None:
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kwargs: SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(
                            content=json.dumps(payload, ensure_ascii=False),
                        ))],
                        usage=None,
                    ),
                ),
            )

    monkeypatch.setattr(ai_router_module, "Groq", _FakeGroq)


def _valid_plan_task() -> dict:
    return {
        "question": "IELTS 6.0 tương đương bậc mấy?",
        "mode": "structured",
        "lookup_type": "foreign_language",
        "intent": "direct_value",
        "slots": {"certificate_or_language": "IELTS", "score_or_level": "6.0"},
        "slot_spans": {"certificate_or_language": "IELTS", "score_or_level": "6.0"},
        "cohorts": ["K51"],
    }


@pytest.mark.parametrize(
    ("raw_mode", "lookup_type", "expected_mode", "error_marker"),
    [
        ("structured", "nonexistent_tool", "clarify", "unknown_lookup_type"),
        ("rag", "foreign_language", "rag", "rag_must_not_select_lookup"),
        ("invalid-mode", None, "rag", "invalid_mode"),
    ],
)
def test_planner_preserves_siblings_after_safe_task_repair(
    monkeypatch, tmp_path, raw_mode, lookup_type, expected_mode, error_marker,
) -> None:
    _mock_plan_response(monkeypatch, [
        _valid_plan_task(),
        {
            "question": "Quy định học vụ thế nào?",
            "mode": raw_mode,
            "lookup_type": lookup_type,
            "intent": "open_question",
            "cohorts": ["K51"],
        },
    ])
    router = _router(monkeypatch, tmp_path, model_name="qwen/qwen3.8-27b")
    plan = router.plan(
        "IELTS 6.0 tương đương bậc mấy và quy định học vụ thế nào?", cohort="K51",
    )

    assert [task["mode"] for task in plan["tasks"]] == ["structured", expected_mode]
    assert plan["tasks"][0]["slots"]["score_or_level"] == "6.0"
    assert plan["tasks"][1]["lookup_type"] is None
    assert not plan.get("planner_fallback")
    assert any(error_marker in error for error in plan["planner_validation_errors"])


def test_planner_does_not_execute_partial_plan_after_unreadable_task(monkeypatch, tmp_path) -> None:
    _mock_plan_response(monkeypatch, [_valid_plan_task(), "not a task object"])
    router = _router(monkeypatch, tmp_path, model_name="qwen/qwen3.8-27b")
    plan = router.plan("IELTS 6.0 tương đương bậc mấy và quy định học vụ thế nào?", cohort="K51")

    assert plan["planner_fallback"] == "safe_rag"
    assert [task["mode"] for task in plan["tasks"]] == ["rag"]
    assert any("invalid_object" in error for error in plan["planner_validation_errors"])


def test_planner_still_blocks_unrepaired_structured_contract_errors(monkeypatch, tmp_path) -> None:
    task = {**_valid_plan_task(), "validation_errors": ["missing_slot_span:score_or_level"]}
    _mock_plan_response(monkeypatch, [task])
    monkeypatch.setattr(
        ai_router_module, "normalize_query_plan",
        lambda *args, **kwargs: ({"tasks": [task]}, ["t1:missing_slot_span:score_or_level"]),
    )
    router = _router(monkeypatch, tmp_path, model_name="qwen/qwen3.8-27b")
    plan = router.plan("IELTS 6.0 tương đương bậc mấy?", cohort="K51")

    assert plan["planner_fallback"] == "safe_rag"
    assert [task["mode"] for task in plan["tasks"]] == ["rag"]


def test_router_treats_provider_json_validation_failure_as_transient() -> None:
    error = RuntimeError("json_validate_failed: Failed to generate JSON.")

    assert AIRouter._classify_error(error) == "transient_error"


def test_router_falls_back_to_regulation_rag_after_provider_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    class _Completions:
        @staticmethod
        def create(**_kwargs):
            raise RuntimeError("json_validate_failed: Failed to generate JSON.")

    class _FakeGroq:
        def __init__(self, **_kwargs) -> None:
            self.chat = SimpleNamespace(completions=_Completions())

    monkeypatch.setattr(ai_router_module, "Groq", _FakeGroq)
    router = _router(monkeypatch, tmp_path, model_name="qwen/qwen3.8-27b")

    decision = router.plan(
        "K48-K49: co duoc xin nang diem ren luyen neu thieu minh chung khong?",
        cohort="K48-K49",
    )

    assert [task["mode"] for task in decision["tasks"]] == ["rag"]
    assert decision["planner_error_type"] == "transient_error"
    assert decision["planner_fallback"] == "safe_rag"


def test_from_config_accepts_model_environment_override(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("GROQ_API_KEYS", "test-router-key")
    monkeypatch.setenv("STUDENT_RAG_ROUTER_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("STUDENT_RAG_ROUTER_MAX_OUTPUT_TOKENS", "1024")
    config_path = tmp_path / "router.yaml"
    state_path = tmp_path / "router-state.json"
    config_path.write_text(
        "\n".join(
            (
                "model_name: qwen/qwen3.8-27b",
                "reasoning_effort: auto",
                "response_format: auto",
                "cache_enabled: false",
                "key_pool:",
                f"  state_path: {json.dumps(str(state_path))}",
            )
        ),
        encoding="utf-8",
    )

    router = AIRouter.from_config(config_path)

    assert router.model_name == "openai/gpt-oss-20b"
    assert router._resolved_reasoning_effort() == "low"
    assert router.max_output_tokens == 1024


def test_router_normalization_infers_explicit_jlpt_level_slot() -> None:
    query = "K50 JLPT N3 tương đương bậc mấy?"
    decision = normalize_router_decision(
        {
            "route": "structured",
            "execution_mode": "structured",
            "intent": "direct_value",
            "lookup_type": "foreign_language",
            "cohort": "K50",
            "slots": {"certificate_or_language": "JLPT"},
            "slot_spans": {"certificate_or_language": "JLPT"},
        },
        query=query,
        selected_cohort="K50",
    )

    assert decision["slots"]["score_or_level"] == "N3"
    assert validate_router_decision(
        decision,
        query=query,
        selected_cohort="K50",
    ) == []


def test_router_normalization_grounds_literals_for_another_registry_tool() -> None:
    query = "K51 hệ vừa làm vừa học văn bằng hai tối đa bao lâu?"
    decision = normalize_router_decision(
        {
            "route": "structured",
            "execution_mode": "structured",
            "intent": "direct_value",
            "lookup_type": "study_duration",
            "cohort": "K51",
            "slots": {},
            "slot_spans": {},
        },
        query=query,
        selected_cohort="K51",
    )

    assert decision["slots"] == {
        "training_mode": "vua_lam_vua_hoc",
        "program_type": "second_degree",
    }
    assert decision["slot_spans"] == {
        "training_mode": "vừa làm vừa học",
        "program_type": "văn bằng hai",
    }


def test_router_normalization_does_not_choose_between_two_declared_literals() -> None:
    decision = normalize_router_decision(
        {
            "route": "structured",
            "execution_mode": "structured",
            "intent": "direct_value",
            "lookup_type": "foreign_language",
            "cohort": "K51",
            "slots": {},
            "slot_spans": {},
        },
        query="So sánh IELTS và TOEFL ở K51.",
        selected_cohort="K51",
    )

    assert "certificate_or_language" not in decision["slots"]


def test_router_normalization_grounds_requested_field_from_registry() -> None:
    query = "Tài khoản sinh viên bị lỗi thì đơn vị nào hỗ trợ?"
    decision = normalize_router_decision(
        {
            "route": "structured",
            "execution_mode": "structured",
            "intent": "contact",
            "lookup_type": "student_service",
            "slots": {"service": "Tài khoản sinh viên bị lỗi"},
            "slot_spans": {"service": "Tài khoản sinh viên bị lỗi"},
        },
        query=query,
        selected_cohort="K51",
    )

    assert decision["slots"]["requested_field"] == "unit"
    assert decision["slot_spans"]["requested_field"] == "đơn vị"


def test_router_normalization_infers_program_list_scope_from_faculty_query() -> None:
    query = "Khoa Công nghệ Thông tin có những ngành nào?"
    decision = normalize_router_decision(
        {
            "route": "structured",
            "execution_mode": "structured",
            "intent": "list_items",
            "lookup_type": "program",
            "cohort": "K51",
            "slots": {},
            "slot_spans": {},
        },
        query=query,
        selected_cohort="K51",
    )

    assert decision["slots"]["scope"] == "faculty"


def test_router_normalization_grounds_student_service_in_full_query() -> None:
    query = "Tài khoản sinh viên bị lỗi thì đơn vị nào hỗ trợ?"
    decision = normalize_router_decision(
        {
            "route": "structured",
            "execution_mode": "structured",
            "intent": "contact",
            "lookup_type": "student_service",
            "slots": {
                "service": "hỗ trợ lỗi tài khoản",
                "requested_field": "unit",
            },
            "slot_spans": {"service": "hỗ trợ lỗi tài khoản"},
        },
        query=query,
        selected_cohort="K48-K49",
    )

    assert decision["slots"]["service"] == query
    assert decision["slot_spans"]["service"] == query
    assert decision["slots"]["requested_field"] == "unit"
    assert validate_router_decision(
        decision,
        query=query,
        selected_cohort="K51",
    ) == []


def test_router_normalization_preserves_grounded_student_service_span() -> None:
    query = "Muốn mượn phòng học thì hỏi đơn vị nào; cho tôi website Khoa Hóa học."
    decision = normalize_router_decision(
        {
            "route": "structured",
            "execution_mode": "structured",
            "intent": "contact",
            "lookup_type": "student_service",
            "cohort": "K51",
            "slots": {
                "service": "mượn phòng học",
                "requested_field": "unit",
            },
            "slot_spans": {"service": "mượn phòng học"},
        },
        query=query,
        selected_cohort="K51",
    )

    assert decision["slots"]["service"] == "mượn phòng học"
    assert decision["slot_spans"]["service"] == "mượn phòng học"
    assert validate_router_decision(
        decision,
        query=query,
        selected_cohort="K51",
    ) == []


def test_router_normalization_handles_multi_cohort_comparison() -> None:
    query = "K50 và K51 thì mấy điểm mới qua môn?"
    decision = normalize_router_decision(
        {
            "route": "rag",
            "execution_mode": "regulation",
            "intent": "regulation",
            "lookup_type": None,
            "cohort": "K50",
            "cohorts": ["K50", "K51"],
            "is_multi_cohort": True,
            "slots": {},
            "slot_spans": {},
        },
        query=query,
        selected_cohort="K50",
    )

    assert decision["is_multi_cohort"] is True
    assert decision["cohorts"] == ["K50", "K51"]
    assert decision["cohort"] == "K50"


def test_structured_normalization_preserves_single_cohort() -> None:
    query = "K50 mấy điểm qua môn?"
    decision = normalize_router_decision(
        {
            "route": "rag",
            "execution_mode": "regulation",
            "intent": "regulation",
            "lookup_type": None,
            "cohort": "K50",
            "cohorts": ["K50"],
            "is_multi_cohort": False,
            "slots": {},
            "slot_spans": {},
        },
        query=query,
        selected_cohort="K50",
    )

    assert decision["is_multi_cohort"] is False
    assert decision["cohorts"] == ["K50"]
    assert decision["cohort"] == "K50"

