"""Offline instructions and authored-plan plumbing, not live model accuracy.

Questions below are development controls. No expected routing is injected into
the production prompt and no query-keyword repair is introduced in runtime.
"""
import json
from pathlib import Path

import pytest

from src.retrieval.core.ai_router import AIRouter, PLANNER_SYSTEM_PROMPT
from src.retrieval.core.directory_selector import DirectorySelector, render_prompt
from src.retrieval.core.office_lookup import office_lookup
from src.retrieval.core.query_plan import normalize_query_plan
from src.retrieval.core.structured_routing import compact_registry_for_prompt


def test_system_and_tool_use_agree_on_service_versus_complaint_procedure():
    prompt = " ".join(PLANNER_SYSTEM_PROMPT.split())
    use = compact_registry_for_prompt().split("student_service|", 1)[1].split("\n", 1)[0]
    # v59: who handles a task is a directory lookup however it is phrased; a
    # complaint or appeal about a specific result or decision follows its rules.
    # v60 states both sides as concepts; no verbs or wordings taken from cases.
    assert "chọn theo loại đáp án, không theo động từ của câu hỏi" in prompt
    assert "Yêu cầu xem xét lại một kết quả hoặc quyết định đã có (khiếu nại, phúc khảo) theo thủ tục quy chế → RAG" in prompt
    assert "Giữ loại việc trong task.question" in prompt
    assert "Tra đơn vị thực hiện một việc trong danh bạ dịch vụ" in use
    assert "Yêu cầu xem xét lại một kết quả hay quyết định đã có" in use
    for case_word in ("quản lý", "báo sai", "chuẩn đầu ra theo một chứng chỉ"):
        assert case_word not in prompt
    assert "Selector" not in use  # the planner does not know the runtime selector
    for case_text in ("official_det_054", "official_det_098", "official_det_122",
                      "Phòng Quản trị", "phongkhaothi@", "Thanh tra"):
        assert case_text not in prompt and case_text not in use


def test_current_instructions_reach_the_serialized_request_and_cache_identity(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "offline-key")
    router = AIRouter(cache_enabled=False, key_pool_config={"state_path": str(tmp_path / "key.json")})
    system = router._planner_system_prompt()
    request = router._build_plan_prompt("Đơn vị nào quản lý dịch vụ này?", cohort="K50", chat_history=[])
    assert "chọn theo loại đáp án, không theo động từ của câu hỏi" in " ".join(system.split())
    assert "Tra đơn vị thực hiện một việc trong danh bạ dịch vụ" in request
    key = router._cache_key("query", cohort="K50", chat_history=[])
    monkeypatch.setattr("src.retrieval.core.ai_router.ROUTER_PROMPT_VERSION",
                        "structured-regulation-v60-answer-kind-concepts")
    assert router._cache_key("query", cohort="K50", chat_history=[]) != key


@pytest.mark.parametrize("query,mode,lookup,slots,spans", [
    ("Phòng nào quản lý thiết bị trình chiếu trong lớp học?", "structured", "student_service",
     {"service": "thiết bị trình chiếu", "requested_field": "unit"},
     {"service": "thiết bị trình chiếu", "requested_field": "Phòng nào"}),
    ("Giấy chứng nhận điểm do đơn vị nào cấp, và em gửi email cho đơn vị đó ở địa chỉ nào?",
     "structured", "student_service", {"service": "Giấy chứng nhận điểm", "requested_field": ["unit", "email"]},
     {"service": "Giấy chứng nhận điểm", "requested_field": "đơn vị nào cấp, và em gửi email"}),
    ("Học bổng xuất sắc cần học tập và rèn luyện loại gì?", "structured", "scholarship_classification",
     {"aspect": "classification", "score_or_label": "xuất sắc"},
     {"aspect": "loại gì", "score_or_label": "xuất sắc"}),
    ("Theo quy chế, Hội đồng nào giải quyết khiếu nại điểm rèn luyện?", "rag", None, {}, {}),
    ("Quy trình và thời hạn giải quyết khiếu nại điểm là gì?", "rag", None, {}, {}),
    ("Bị kỷ luật thì em có đủ điều kiện nhận học bổng không?", "rag", None, {}, {}),
])
def test_authored_answer_kind_plans_remain_executable_without_keyword_override(query, mode, lookup, slots, spans):
    raw = {"schema_version": "v1", "context_mode": "standalone", "out_of_domain": False,
           "normalized_query": query, "standalone_query": None, "referenced_turns": [],
           "tasks": [{"id": "t1", "question": query, "mode": mode,
                      "lookup_type": lookup, "intent": "open_question" if mode == "rag" else
                      "contact" if lookup == "student_service" else "direct_value",
                      "slots": slots, "slot_spans": spans, "cohorts": ["K50"],
                      "clarification_question": None}]}
    plan, errors = normalize_query_plan(raw, query=query, selected_cohort="K50")
    assert errors == []
    assert plan["tasks"][0]["mode"] == mode
    assert plan["tasks"][0]["lookup_type"] == lookup
    assert plan["tasks"][0]["slots"] == slots


@pytest.mark.parametrize("needle", ["trình chiếu", "chứng nhận điểm"])
def test_real_catalog_service_identity_contacts_and_provenance_stay_intact(needle):
    records = json.loads(Path("data/processed/directories/student_service_directory.json").read_text(encoding="utf-8"))
    source, = [row for row in records if row["cohort"] == "K50" and needle in row["service"]]

    class NoCalls:
        def generate(self, *args, **kwargs):
            pytest.fail("An exact catalog service must not require inference")

    result = office_lookup(source["service"], records, candidate_text=source["service"],
                           lookup_type="student_service", cohort="K50", requested_field=["unit", "email"],
                           selector=DirectorySelector(NoCalls(), NoCalls()))
    assert result["selection_method"] == "catalog_exact"
    record, = result["result"]
    assert record["unit_name"] == source["unit_name"]
    assert record["emails"] == source["emails"]
    assert record["record_id"] == source["service_id"]
    assert record["cohort"] == "K50"
    assert record["source_pages"] == source["source_pages"]


def test_service_selector_retains_specialized_scope_guard():
    prompt, _ = render_prompt("student_service", "khiếu nại", [],
                             question="Hội đồng nào giải quyết khiếu nại điểm rèn luyện?",
                             requested_field="unit")
    assert "Hội đồng nào" in prompt
    assert "thẩm quyền xử lý mọi tình huống chuyên biệt" in prompt
    assert "Thiếu căn cứ thì chọn none" in prompt


def test_scoring_operations_say_what_each_lookup_returns():
    scoring = compact_registry_for_prompt().split("scoring|", 1)[1].split("\n", 1)[0]
    assert "grade_10_to_letter trả điểm chữ kèm Đạt/Không đạt" in scoring
    assert "hỏi cả hai vẫn một task" in scoring
    assert "pass_fail_ungraded chỉ cho môn chấm đạt/không đạt, không tính GPA" in scoring
    prompt = " ".join(PLANNER_SYSTEM_PROMPT.split())
    assert "hoặc của cùng một hàng kết quả" in prompt


def test_policy_questions_that_need_a_reference_table_also_look_it_up():
    # RAG alone often misses an appendix table, so the lookup is not optional.
    prompt = " ".join(PLANNER_SYSTEM_PROMPT.split())
    assert "kết luận mà bảng không chứa (mức bắt buộc, quyền hưởng) → task structured tra bảng" in prompt
    assert "Hỏi giá trị/hàng bảng có sẵn chỉ là một task structured" in prompt
    assert "có thể là một RAG task tự đủ nghĩa" not in prompt
    use = compact_registry_for_prompt().split("foreign_language|", 1)[1].split("\n", 1)[0]
    assert "cần bảng này cùng quy định qua RAG" in use
