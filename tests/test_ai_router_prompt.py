from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import src.retrieval.core.ai_router as ai_router_module
from src.retrieval.core.ai_router import (
    AIRouter,
    PLANNER_SYSTEM_PROMPT,
    _RouterCompletion,
    ROUTER_PROMPT_VERSION,
)
from src.retrieval.core.query_plan import (
    QUERY_PLAN_NORMALIZER_VERSION,
    normalize_query_plan,
)
from src.retrieval.core.structured_routing import (
    compact_registry_for_prompt,
    prepare_structured_task,
    validate_structured_task,
)

PLANNER_PROMPT_TEXT = " ".join(PLANNER_SYSTEM_PROMPT.split())


def _router(monkeypatch, tmp_path: Path) -> AIRouter:
    monkeypatch.setenv("OPENAI_API_KEY", "test-router-key")
    return AIRouter(
        cache_enabled=False,
        key_pool_config={"state_path": str(tmp_path / "planner.json")},
    )


def test_compact_registry_omits_prompt_only_noise() -> None:
    prompt_registry = compact_registry_for_prompt()

    assert "examples" not in prompt_registry
    assert "operand_requirements" not in prompt_registry
    assert "required=" in prompt_registry
    assert "values" in prompt_registry
    assert 'formula_type":{"type":"string","values":["scholarship_score","gpa_weighted_average"]}' in prompt_registry
    assert "điểm học bổng từ điểm học tập và rèn luyện=scholarship_score" in prompt_registry
    assert "Điểm học bổng hoặc tên loại học bổng được hỏi" in prompt_registry
    assert '"aspect":{"type":"string"' in prompt_registry
    assert '"values":{"amount":"mức tiền","classification":"xếp loại"}' in prompt_registry
    assert '"secondary_bridge":"liên thông từ trung cấp"' in prompt_registry
    # Self-describing codes keep their code instead of repeating an alias.
    assert '"email":"email"' in prompt_registry
    scholarship_contract = prompt_registry.split("scholarship_classification|", 1)[1].split(
        "\n", 1
    )[0]
    assert "bảng điều kiện xét" in scholarship_contract
    assert "kết luận được cấp học bổng cần quy định RAG" in scholarship_contract
    assert "công thức tiền" in scholarship_contract
    assert "căn cứ học phí" in scholarship_contract
    scoring_contract = prompt_registry.split("scoring|", 1)[1].split("\n", 1)[0]
    assert "tổng điểm rèn luyện" in scoring_contract
    assert "từng tiêu chí thành phần" in scoring_contract
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
def test_supplied_reference_table_selectors_recover_only_their_source_spans(
    query: str,
    lookup_type: str,
    expected_slots: dict[str, str],
) -> None:
    normalized = prepare_structured_task(
        query,
        lookup_type=lookup_type,
        intent="direct_value",
        slots=expected_slots,
        slot_spans={},
        cohort="K51",
    )

    assert normalized["slots"] == expected_slots
    assert set(normalized["slot_spans"]) == set(expected_slots)
    assert validate_structured_task(normalized, query=query) == []


def test_scoring_course_scope_accepts_natural_course_synonym() -> None:
    query = "Môn còn lại của K51 được 5,0 thì có đạt không?"
    normalized = prepare_structured_task(
        query,
        lookup_type="scoring",
        intent="direct_value",
        slots={
                    "operation": "pass_threshold",
                    "score_or_grade": "5.0",
                    "course_scope": "remaining",
                },
        slot_spans={
                    "operation": "có đạt không",
                    "score_or_grade": "5,0",
                    "course_scope": "Môn còn lại",
                },
        cohort="K51",
    )

    assert normalized["slots"]["course_scope"] == "remaining"
    assert normalized["slot_spans"]["course_scope"] == "Môn còn lại"
    assert validate_structured_task(normalized, query=query) == []


def test_reference_table_selector_stays_absent_for_general_question() -> None:
    normalized = prepare_structured_task(
        "Cho tôi thông tin tổng quan về học bổng.",
        lookup_type="scholarship_classification",
        intent="direct_value",
        slots={},
        slot_spans={},
        cohort="K51",
    )

    assert normalized["slots"] == {}
    assert normalized["slot_spans"] == {}


def test_scholarship_policy_question_does_not_infer_structured_aspect() -> None:
    normalized = prepare_structured_task(
        "Điều kiện để được xét học bổng là gì?",
        lookup_type="scholarship_classification",
        intent="direct_value",
        slots={},
        slot_spans={},
        cohort="K51",
    )

    assert normalized["slots"] == {}
    assert normalized["slot_spans"] == {}


def test_plan_cache_key_includes_normalizer_version(monkeypatch, tmp_path: Path) -> None:
    router = _router(monkeypatch, tmp_path)
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


def test_strict_planner_prompt_stays_within_budget(monkeypatch, tmp_path: Path) -> None:
    """The production path: OpenAI strict schema, which also carries slot descriptions."""
    router = _router(monkeypatch, tmp_path)
    dynamic_prompt = router._build_plan_prompt(
        "So sánh hai khóa về thời gian học.", cohort="K51", chat_history=[]
    )
    stats = AIRouter._prompt_stats_for_system(
        router._planner_system_prompt(),
        dynamic_prompt,
        router._plan_response_format_payload(),
    )
    # v58 separates answer kinds without changing schema or runtime behavior.
    # Character-based estimates, not provider tokenizer or billing counts.
    assert stats["total_chars"] <= 35500
    assert stats["estimated_input_tokens"] <= 8875
    assert ROUTER_PROMPT_VERSION == "structured-regulation-v58-answer-kind-routing"
    assert "OUTPUT CONTRACT" not in dynamic_prompt
    assert 'COHORT_ADMISSION_YEARS: {"K48-K49":[2022,2023],"K50":[2024],"K51":[2025]}' in dynamic_prompt


def test_dynamic_prompt_preserves_explicit_three_request_count(
    monkeypatch, tmp_path: Path
) -> None:
    router = _router(monkeypatch, tmp_path)
    dynamic_prompt = router._build_plan_prompt(
        "Thứ nhất: hỏi A. Thứ hai: hỏi B. Thứ ba: hỏi C.",
        cohort="K51",
        chat_history=[],
    )

    assert "EXPLICIT_REQUEST_COUNT: 3" in dynamic_prompt


def test_planner_prompt_defines_cohort_independent_task_identity() -> None:
    assert "Cohort không làm tăng số task" in PLANNER_PROMPT_TEXT
    assert "không tạo M×N tasks" in PLANNER_PROMPT_TEXT
    assert "COHORT từ UI chỉ điền cho task vẫn chưa có cohort" in PLANNER_PROMPT_TEXT
    assert "không ghi đè" in PLANNER_PROMPT_TEXT
    assert "So sánh K50 và K51 về thời gian học tối đa" not in PLANNER_PROMPT_TEXT


def test_planner_prompt_keeps_exactly_three_answer_targets() -> None:
    assert "Với 1–3 yêu cầu" in PLANNER_PROMPT_TEXT
    assert "EXPLICIT_REQUEST_COUNT là số marker để rà soát bỏ sót" in PLANNER_PROMPT_TEXT


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
    assert "runtime chịu trách nhiệm chọn bảng và tính kết quả" in PLANNER_PROMPT_TEXT
    assert "không lọc hàng trong bảng đã chọn" not in PLANNER_PROMPT_TEXT


def test_planner_only_clarifies_genuinely_ambiguous_input() -> None:
    assert "tham chiếu thật sự mơ hồ" in PLANNER_PROMPT_TEXT
    assert "như loại cảnh báo" not in PLANNER_PROMPT_TEXT
    # Only data the school holds routes to RAG; values the user knows clarify.
    assert "chỉ hệ thống nhà trường có, không nằm trong Sổ tay" in PLANNER_PROMPT_TEXT
    assert "chưa nêu giá trị họ tự biết" in PLANNER_PROMPT_TEXT
    # "vận hành" also describes student_service, so it must not route to RAG.
    assert "hoặc vận hành mà Sổ tay" not in PLANNER_PROMPT_TEXT
    assert "vì target rõ nhưng nguồn có thể thiếu dữ liệu" in PLANNER_PROMPT_TEXT


def test_prompt_clarifies_selectors_without_weakening_grounding() -> None:
    assert "nếu đã xác định rõ giá trị thì phải điền" in PLANNER_PROMPT_TEXT
    assert "Không cung cấp slot khi chưa xác định được" in PLANNER_PROMPT_TEXT
    # One wording for an omitted slot; its encoding belongs to the output rules.
    assert "Để trống" not in PLANNER_PROMPT_TEXT
    assert "Để trống" not in compact_registry_for_prompt()
    assert "cần tên đơn vị/liên hệ cho một dịch vụ" in PLANNER_PROMPT_TEXT
    registry = compact_registry_for_prompt()
    assert "Chọn theo kết quả cần tra, không theo riêng tên loại học bổng" in registry
    assert "unit=tên đơn vị phụ trách; phone=điện thoại kèm số máy nội bộ" in registry
    assert "office=địa chỉ hoặc vị trí làm việc" in registry
    assert "không chỉ theo từ 'phòng'" in registry


def test_contact_intent_description_has_no_benchmark_specific_rule() -> None:
    registry = compact_registry_for_prompt()
    service_contract = registry.split("student_service|", 1)[1].split("\n", 1)[0]
    description = json.loads(service_contract.split("|slots=", 1)[1])[
        "requested_field"
    ]["description"]
    assert "một đơn vị đã nêu tên 'ở đâu' → office" in description
    # Genuinely ambiguous inputs already use the shared clarification rule.
    assert "tham chiếu thật sự mơ hồ" in PLANNER_PROMPT_TEXT
    for benchmark_phrase in ("nhận bằng", "tốt nghiệp", "096", "DeepSeek", "Qwen"):
        assert benchmark_phrase not in description


def test_contact_intent_development_rubrics_preserve_authored_fields() -> None:
    # These are hand-authored plans, not outputs from either live model.
    path = Path(__file__).resolve().parents[1] / "data/eval/development/prompt_v47_contact_intent_cases.yaml"
    bundle = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert bundle["independent_holdout"] is False
    cases = bundle["cases"]
    assert len(cases) == len({case["id"] for case in cases}) == 8
    for case in cases:
        expected = case["expected"]
        decision = prepare_structured_task(
            case["query"], lookup_type=expected["lookup_type"],
            intent=expected["intent"], slots=expected["slots"],
            slot_spans=expected["slot_spans"], cohort=case["cohort"],
        )
        assert validate_structured_task(decision, query=case["query"]) == [], case["id"]
        assert decision["slots"] == expected["slots"], case["id"]
        assert decision["slot_spans"] == expected["slot_spans"], case["id"]
        payload = {
            "schema_version": "v1", "context_mode": "standalone",
            "normalized_query": case["query"], "standalone_query": None,
            "referenced_turns": [], "out_of_domain": False,
            "tasks": [{
                "id": "t1", "question": case["query"], "mode": "structured",
                "intent": expected["intent"], "lookup_type": expected["lookup_type"],
                "slots": expected["slots"], "slot_spans": expected["slot_spans"],
                "cohorts": [case["cohort"]], "clarification_question": None,
            }],
        }
        plan, errors = normalize_query_plan(
            payload, query=case["query"], selected_cohort=case["cohort"],
        )
        assert errors == [], case["id"]
        assert len(plan["tasks"]) == 1, case["id"]
        assert plan["tasks"][0]["mode"] == "structured", case["id"]
        assert plan["tasks"][0]["slots"] == expected["slots"], case["id"]


def test_contact_intent_normalizer_does_not_override_a_present_field() -> None:
    # Improving instructions must not introduce a query-keyword correction.
    query = "Việc mượn sách thư viện do bộ phận nào phụ trách?"
    decision = prepare_structured_task(
        query, lookup_type="student_service", intent="contact",
        slots={"service": "mượn sách thư viện", "requested_field": "office"},
        slot_spans={"service": "mượn sách thư viện", "requested_field": "bộ phận nào"},
        cohort="K50",
    )
    assert decision["slots"]["requested_field"] == "office"
    assert decision["slot_spans"]["requested_field"] == "bộ phận nào"


def test_prompt_development_rubrics_are_valid_but_not_holdout() -> None:
    # Validate authored intent fixtures only. This is NOT a model-quality test.
    path = Path(__file__).resolve().parents[1] / "data/eval/development/prompt_v44_cases.yaml"
    bundle = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert bundle["independent_holdout"] is False
    cases = bundle["cases"]
    assert len(cases) == len({case["id"] for case in cases}) == 10
    for case in cases:
        expected = case["expected"]
        assert expected["mode"] in {"structured", "rag", "clarify"}
        if expected["mode"] != "structured":
            continue
        decision = prepare_structured_task(
            case["query"], lookup_type=expected["lookup_type"],
            intent=expected["intent"], slots=expected["slots"],
            slot_spans=expected.get("slot_spans", {}), cohort=case["cohort"],
        )
        assert validate_structured_task(decision, query=case["query"]) == [], case["id"]
        assert decision["slots"] == expected["slots"], case["id"]


def test_planner_prompt_keeps_merge_and_rag_as_only_if_conditions() -> None:
    """Merging and RAG are restricted exceptions, not sufficient conditions.

    A readability rewrite once turned "Chỉ gộp ... khi" into "Một task khi" and
    "Chỉ chọn RAG khi" into "rag: khi", which licensed merging two regulation
    questions on one topic and routing table questions to RAG.
    """
    assert "Chỉ gộp các khía cạnh bổ sung khi chúng cùng đối tượng, mode, lookup và phạm vi nguồn để tạo một answer target" in PLANNER_PROMPT_TEXT
    assert "Mặc định mỗi yêu cầu là một task" in PLANNER_PROMPT_TEXT
    assert "Hai yêu cầu cần hai đáp án khác nhau là hai task" in PLANNER_PROMPT_TEXT
    assert "chỉ chọn RAG khi cần đọc quy định" in PLANNER_PROMPT_TEXT
    assert "bảng tham chiếu không tự xác lập mức nào là bắt buộc" in PLANNER_PROMPT_TEXT
    assert "Một task khi các phần" not in PLANNER_PROMPT_TEXT
    assert "cần đạt điều kiện gì là hỏi chính sách" not in PLANNER_PROMPT_TEXT


def test_planner_prompt_splits_independent_answer_targets() -> None:
    assert "Mỗi task.question chứa một yêu cầu độc lập" in PLANNER_PROMPT_TEXT
    assert "Nhiều trường của cùng một đối tượng" in PLANNER_PROMPT_TEXT
    assert "Tách task khi các phần hỏi về đối tượng/chủ đề độc lập" in PLANNER_PROMPT_TEXT
    assert "Từ nối \"và\" hoặc \"so sánh\" không tự quyết định" in PLANNER_PROMPT_TEXT
    assert "hỗ trợ danh sách → một task với danh sách entity" in PLANNER_PROMPT_TEXT
    assert "tách task để giữ từng cặp entity–dữ kiện" in PLANNER_PROMPT_TEXT
    assert "Mỗi entity đi kèm giá trị đầu vào riêng do người hỏi nêu, hoặc mỗi entity hỏi một trường khác nhau → tách task" in PLANNER_PROMPT_TEXT
    assert "không kèm giá trị riêng, trong cùng lookup hỗ trợ danh sách → một task" in PLANNER_PROMPT_TEXT
    assert "không phải phụ thuộc giữa task: runtime tự nối sang liên hệ, nên dùng một task" in PLANNER_PROMPT_TEXT
    # The runtime joins to a contact only from a single source item.
    assert "mỗi ngành/dịch vụ một task, vì runtime chỉ nối sang liên hệ từ đúng một mục" in PLANNER_PROMPT_TEXT
    assert "Khoa/đơn vị đã nêu tên trực tiếp thì vẫn tra chung một task" in PLANNER_PROMPT_TEXT
    assert "Mỗi task chỉ có một mode" in PLANNER_PROMPT_TEXT
    assert "mỗi yêu cầu độc lập xuất hiện đúng một lần" in PLANNER_PROMPT_TEXT
    assert "composer mới kết hợp" in PLANNER_PROMPT_TEXT


def test_prompt_keeps_unscaled_scores_and_whole_table_comparisons():
    # A missing scale is not missing input; the operation decides the scale.
    assert "Khi người dùng không nêu thang điểm, điền đúng con số" in PLANNER_PROMPT_TEXT
    # The value is a parseable score; the literal wording stays in the span.
    assert 'không kèm chữ như "điểm"' in PLANNER_PROMPT_TEXT
    assert "khoa đào tạo" in PLANNER_PROMPT_TEXT
    assert "Không hỏi thêm chi tiết mà lookup không cần" in PLANNER_PROMPT_TEXT
    assert "không clarify chỉ vì thiếu thang" in PLANNER_PROMPT_TEXT
    # A comparison over values the table holds is answered with every row.
    assert "bảng trả được mọi cách hiểu, nên không clarify" in PLANNER_PROMPT_TEXT
    assert "để runtime trả đủ các hàng" in PLANNER_PROMPT_TEXT


def test_prompt_preserves_explicit_score_scale_and_grounded_history():
    assert '"3,6/4" hoặc "3,6/10"' in PLANNER_PROMPT_TEXT
    assert "không rút thành số 3.6" in PLANNER_PROMPT_TEXT
    assert "không cắt mẫu số khỏi span" in PLANNER_PROMPT_TEXT
    assert "không tự quy đổi điểm sang thang khác" in PLANNER_PROMPT_TEXT
    assert "không thêm thông tin không có căn cứ trong QUERY hoặc history hợp lệ" in PLANNER_PROMPT_TEXT


def test_planner_prompt_defines_registry_grounded_cohort_conflict() -> None:
    assert "COHORT_ADMISSION_YEARS: năm tuyển sinh của từng khóa, là metadata xác thực từ registry" in PLANNER_PROMPT_TEXT
    assert "khóa và năm tuyển sinh cho cùng một đối tượng" in PLANNER_PROMPT_TEXT
    assert "nêu đúng hai giá trị cần xác nhận" in PLANNER_PROMPT_TEXT
    assert "Không áp dụng cho câu so sánh nhiều khóa" in PLANNER_PROMPT_TEXT


def test_planner_limits_tool_contract_to_structured_tasks() -> None:
    assert "Chỉ dùng lookup_type, intent, slots khai báo trong TOOLS" not in PLANNER_PROMPT_TEXT


def test_planner_prompt_requires_grounded_slots_for_structured_mode() -> None:
    assert "Mỗi slot_span phải chính là cụm nguyên văn" in PLANNER_PROMPT_TEXT
    assert "control value được chuẩn hóa" in PLANNER_PROMPT_TEXT
    assert "không phải toàn bộ câu hỏi" in PLANNER_PROMPT_TEXT
    assert "Không chọn structured chỉ vì trùng từ chủ đề" in PLANNER_PROMPT_TEXT
    assert "dù QUERY không" in PLANNER_PROMPT_TEXT
    assert "Chỉ clarify task bị thiếu thông tin" in PLANNER_PROMPT_TEXT


def test_planner_prompt_defines_context_precedence_once() -> None:
    assert "standalone_query" in PLANNER_PROMPT_TEXT
    assert "referenced_turns" in PLANNER_PROMPT_TEXT
    assert "CATALOG_HINT" not in PLANNER_PROMPT_TEXT
    assert PLANNER_PROMPT_TEXT.count("hơn 3 yêu cầu") == 2
    assert "xuất đúng một clarify task" in PLANNER_PROMPT_TEXT
    assert "không thực thi một phần" in PLANNER_PROMPT_TEXT


def test_planner_prompt_matches_global_context_and_rag_contract() -> None:
    assert "context_mode=ambiguous chỉ khi toàn QUERY mơ hồ hoặc có hơn 3" in PLANNER_PROMPT_TEXT
    assert "clarify cho riêng task đó" in PLANNER_PROMPT_TEXT
    assert "chỉ đặt out_of_domain=true khi toàn bộ QUERY" in PLANNER_PROMPT_TEXT
    assert "khi đó tasks=[]" in PLANNER_PROMPT_TEXT
    assert "giữ các target trong phạm vi" in PLANNER_PROMPT_TEXT
    assert "thiếu evidence" not in PLANNER_PROMPT_TEXT


def test_planner_prompt_protects_normalized_query_semantics() -> None:
    assert "normalized_query chỉ sửa dấu, chính tả nhẹ" in PLANNER_PROMPT_TEXT
    for protected_value in ("entity", "cohort", "số liệu", "phủ định", "chủ đề", "ý định"):
        assert protected_value in PLANNER_PROMPT_TEXT


def test_router_treats_upstream_disconnect_as_transient() -> None:
    error = RuntimeError("Server disconnected without sending a response.")

    assert AIRouter._classify_error(error) == "transient_error"


def _completion(payload: dict) -> _RouterCompletion:
    return _RouterCompletion(json.dumps(payload, ensure_ascii=False),
                             {"input": 0, "output": 0, "total": 0}, "stop")


def _mock_plan_response(monkeypatch, tasks: list) -> None:
    payload = {
        "schema_version": "v1",
        "context_mode": "standalone",
        "out_of_domain": False,
        "tasks": tasks,
    }
    monkeypatch.setattr(AIRouter, "_chat_completion",
                        lambda self, **_kwargs: _completion(payload))


def _mock_plan_response_sequence(monkeypatch, task_sequences: list[list]) -> list[dict]:
    """Serve one plan per planner request and record each request's arguments."""
    calls: list[dict] = []
    payloads = [
        {
            "schema_version": "v1",
            "context_mode": "standalone",
            "out_of_domain": False,
            "tasks": tasks,
        }
        for tasks in task_sequences
    ]

    def request(self, **kwargs):
        calls.append(kwargs)
        return _completion(payloads[min(len(calls) - 1, len(payloads) - 1)])

    monkeypatch.setattr(AIRouter, "_chat_completion", request)
    return calls


def _rag_task(question: str) -> dict:
    return {
        "question": question,
        "mode": "rag",
        "lookup_type": None,
        "intent": "open_question",
        "slots": {},
        "slot_spans": {},
        "cohorts": ["K51"],
    }


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
    router = _router(monkeypatch, tmp_path)
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
    router = _router(monkeypatch, tmp_path)
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
    router = _router(monkeypatch, tmp_path)
    plan = router.plan("IELTS 6.0 tương đương bậc mấy?", cohort="K51")

    assert plan["planner_fallback"] == "safe_rag"
    assert [task["mode"] for task in plan["tasks"]] == ["rag"]


def test_router_falls_back_to_regulation_rag_after_provider_error(
    monkeypatch,
    tmp_path: Path,
) -> None:
    def unavailable(self, **_kwargs):
        raise RuntimeError("Service temporarily unavailable.")

    monkeypatch.setattr(AIRouter, "_chat_completion", unavailable)
    router = _router(monkeypatch, tmp_path)

    decision = router.plan(
        "K48-K49: co duoc xin nang diem ren luyen neu thieu minh chung khong?",
        cohort="K48-K49",
    )

    assert [task["mode"] for task in decision["tasks"]] == ["rag"]
    assert decision["planner_error_type"] == "transient_error"
    assert decision["planner_fallback"] == "safe_rag"


def test_from_config_accepts_environment_overrides(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-router-key")
    monkeypatch.setenv("STUDENT_RAG_ROUTER_REASONING_EFFORT", "low")
    monkeypatch.setenv("STUDENT_RAG_ROUTER_MAX_OUTPUT_TOKENS", "1024")
    config_path = tmp_path / "router.yaml"
    state_path = tmp_path / "router-state.json"
    config_path.write_text(
        "\n".join(
            (
                "model_name: gpt-6-luna",
                "reasoning_effort: medium",
                "cache_enabled: false",
                "key_pool:",
                f"  state_path: {json.dumps(str(state_path))}",
            )
        ),
        encoding="utf-8",
    )

    router = AIRouter.from_config(config_path)

    assert router.model_name == "gpt-6-luna"
    assert router.reasoning_effort == "low"
    assert router.max_output_tokens == 1024
    # A stale model override is rejected rather than sent an untested prompt.
    monkeypatch.setenv("STUDENT_RAG_ROUTER_MODEL", "qwen/qwen3.8-27b")
    with pytest.raises(ValueError):
        AIRouter.from_config(config_path)


def test_router_normalization_does_not_infer_missing_jlpt_level_slot() -> None:
    query = "K50 JLPT N3 tương đương bậc mấy?"
    decision = prepare_structured_task(
        query,
        lookup_type="foreign_language",
        intent="direct_value",
        slots={"certificate_or_language": "JLPT"},
        slot_spans={"certificate_or_language": "JLPT"},
        cohort="K50",
    )

    assert "score_or_level" not in decision["slots"]
    assert validate_structured_task(decision, query=query) == []


def test_router_normalization_leaves_missing_duration_inputs_absent() -> None:
    query = "K51 hệ vừa làm vừa học văn bằng hai tối đa bao lâu?"
    decision = prepare_structured_task(
        query,
        lookup_type="study_duration",
        intent="direct_value",
        slots={},
        slot_spans={},
        cohort="K51",
    )

    assert decision["slots"] == {}
    assert decision["slot_spans"] == {}


def test_router_normalization_does_not_choose_between_two_declared_literals() -> None:
    decision = prepare_structured_task(
        "So sánh IELTS và TOEFL ở K51.",
        lookup_type="foreign_language",
        intent="direct_value",
        slots={},
        slot_spans={},
        cohort="K51",
    )

    assert "certificate_or_language" not in decision["slots"]


def test_router_normalization_does_not_infer_missing_requested_field() -> None:
    query = "Tài khoản sinh viên bị lỗi thì đơn vị nào hỗ trợ?"
    decision = prepare_structured_task(
        query,
        lookup_type="student_service",
        intent="contact",
        slots={"service": "Tài khoản sinh viên bị lỗi"},
        slot_spans={"service": "Tài khoản sinh viên bị lỗi"},
        cohort="K51",
    )

    assert "requested_field" not in decision["slots"]
    assert "requested_field" not in decision["slot_spans"]


def test_router_normalization_does_not_infer_program_list_scope() -> None:
    query = "Khoa Công nghệ Thông tin có những ngành nào?"
    decision = prepare_structured_task(
        query,
        lookup_type="program",
        intent="list_items",
        slots={},
        slot_spans={},
        cohort="K51",
    )

    assert "scope" not in decision["slots"]


def test_router_normalization_does_not_rewrite_student_service_from_query() -> None:
    query = "Tài khoản sinh viên bị lỗi thì đơn vị nào hỗ trợ?"
    decision = prepare_structured_task(
        query,
        lookup_type="student_service",
        intent="contact",
        slots={
                    "service": "hỗ trợ lỗi tài khoản",
                    "requested_field": "unit",
                },
        slot_spans={"service": "hỗ trợ lỗi tài khoản"},
        cohort="K48-K49",
    )

    assert decision["slots"]["service"] == "hỗ trợ lỗi tài khoản"
    assert decision["slot_spans"]["service"] == "hỗ trợ lỗi tài khoản"
    assert decision["slots"]["requested_field"] == "unit"
    assert validate_structured_task(decision, query=query) == ["ungrounded_slot:service"]


def test_router_normalization_preserves_grounded_student_service_span() -> None:
    query = "Muốn mượn phòng học thì hỏi đơn vị nào; cho tôi website Khoa Hóa học."
    decision = prepare_structured_task(
        query,
        lookup_type="student_service",
        intent="contact",
        slots={
                    "service": "mượn phòng học",
                    "requested_field": "unit",
                },
        slot_spans={"service": "mượn phòng học"},
        cohort="K51",
    )

    assert decision["slots"]["service"] == "mượn phòng học"
    assert decision["slot_spans"]["service"] == "mượn phòng học"
    assert validate_structured_task(decision, query=query) == []


def test_rejected_key_is_not_retried() -> None:
    error = RuntimeError(
        "Error code: 401 - {'error': {'message': 'Authentication Fails, "
        "Your api key: ****833c is invalid', 'type': 'authentication_error'}}"
    )

    assert AIRouter._classify_error(error) == "auth_error"


def test_unit_and_office_semantics_reach_the_model_in_the_schema(monkeypatch, tmp_path: Path) -> None:
    router = _router(monkeypatch, tmp_path)
    schema = json.dumps(router._plan_response_format_payload(), ensure_ascii=False)
    for rule in ("phụ trách hoặc hỗ trợ một việc → unit", "tòa nhà/tầng/số phòng",
                 "một đơn vị đã nêu tên 'ở đâu' → office"):
        assert rule in schema
