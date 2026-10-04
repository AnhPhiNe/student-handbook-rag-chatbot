"""Task-local contradictions are not valid merely because inputs occur globally."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.generation.answer_pipeline import AnswerPipeline
from src.generation.plan_executor import PlanExecutor, StructuredCatalogs
from src.generation.prompt_builder import build_authorized_evidence_packet
from src.retrieval.core.query_plan import normalize_query_plan


def task(question, cohort="K51", *, mode="rag", value=None, scope=None):
    result = {"question": question, "mode": mode, "intent": "open_question" if mode == "rag" else "direct_value",
              "lookup_type": None if mode == "rag" else "scoring", "cohorts": [cohort], "slots": {}, "slot_spans": {}}
    if mode == "structured":
        result["slots"] = {"operation": "grade_10_to_letter", "score_or_grade": value}
        result["slot_spans"] = {"score_or_grade": value}
        if scope:
            result["slots"]["course_scope"] = scope
            result["slot_spans"]["course_scope"] = "môn nền tảng" if scope == "foundation" else "môn còn lại"
    return result


def normalize(tasks, query=None, **kwargs):
    query = query or " và ".join(t["question"] for t in tasks)
    raw = {"schema_version": "v1", "context_mode": "standalone", "out_of_domain": False, "tasks": copy.deepcopy(tasks)}
    raw.update(kwargs.pop("payload", {}))
    return normalize_query_plan(raw, query=query, selected_cohort=kwargs.pop("selected_cohort", "K51"), **kwargs)


@pytest.mark.parametrize("mode", ["rag", "structured"])
@pytest.mark.parametrize("cohorts", [["K50"], ["K50", "K51"]])
def test_wrong_or_extra_cohort_clarifies_only_the_conflicting_task(mode, cohorts):
    first = task("K50 môn A 5.2 đổi điểm chữ?", "K50", mode=mode, value="5.2")
    first["cohorts"] = cohorts if cohorts != ["K50"] else ["K51"]
    second = task("K51 môn B 7.6 đổi điểm chữ?", mode=mode, value="7.6")
    plan, errors = normalize([first, second])
    assert "t1:task_cohort_conflict" in errors
    assert [t["mode"] for t in plan["tasks"]] == ["clarify", mode]
    assert plan["tasks"][1]["cohorts"] == ["K51"]


@pytest.mark.parametrize("mode", ["rag", "structured"])
@pytest.mark.parametrize("query", ["So sánh K50 và K51 với điểm 5.2?", "Đối chiếu K50 với K51 ở điểm 5.2?"])
def test_one_explicit_comparison_cannot_silently_omit_a_cohort(mode, query):
    first = task(query, "K50", mode=mode, value="5.2")
    plan, errors = normalize([first], query=query)
    assert "t1:task_cohort_conflict" in errors
    assert plan["tasks"][0]["mode"] == "clarify"


@pytest.mark.parametrize("mode", ["rag", "structured"])
def test_correct_comparison_keeps_both_cohorts_over_ui_default(mode):
    question = "So sánh K50 và K51 với điểm 5.2?"
    first = task(question, mode=mode, value="5.2")
    first["cohorts"] = ["K50", "K51"]
    plan, errors = normalize([first], selected_cohort="K48-K49")
    assert not errors
    assert plan["tasks"][0]["cohorts"] == ["K50", "K51"]
    assert plan["tasks"][0]["mode"] == mode


def test_existing_single_explicit_cohort_override_is_preserved():
    original = "K50 nghỉ học tạm thời thế nào?"
    plan, errors = normalize([task("K51 nghỉ học thế nào?")], query=original)
    assert not errors and plan["tasks"][0]["mode"] == "rag"
    assert plan["tasks"][0]["question"] == original
    assert plan["tasks"][0]["cohorts"] == ["K50"]


def test_task_without_explicit_scope_keeps_populated_cohort():
    plan, errors = normalize([task("Quy định nghỉ học?")], selected_cohort="K50")
    assert not errors and plan["tasks"][0]["cohorts"] == ["K51"]


def test_two_correct_scopes_are_never_overwritten_from_whole_query():
    plan, errors = normalize([task("K50 bảo lưu thế nào?", "K50"), task("K51 học phí thế nào?")])
    assert not errors and [t["cohorts"] for t in plan["tasks"]] == [["K50"], ["K51"]]


@pytest.mark.parametrize("reverse", [False, True])
def test_cohort_conflict_is_checked_before_rag_cohort_copies_can_merge(reverse):
    tasks = [task("K50 bảo lưu thế nào?", "K51"), task("K51 bảo lưu thế nào?", "K50")]
    if reverse:
        tasks.reverse()
    plan, errors = normalize(tasks)
    assert len(errors) == 2 and len(plan["tasks"]) == 2
    assert all(t["mode"] == "clarify" for t in plan["tasks"])


@pytest.mark.parametrize("reverse", [False, True])
def test_swapped_numeric_inputs_do_not_reach_structured_execution(reverse):
    tasks = [task("K51 môn nền tảng 5,2 đổi điểm chữ?", mode="structured", value="7,6", scope="foundation"),
             task("K51 môn còn lại 7,6 đổi điểm chữ?", mode="structured", value="5,2", scope="remaining")]
    if reverse:
        tasks.reverse()
    plan, errors = normalize(tasks)
    assert len(errors) == 2 and all("task_operand_conflict:score_or_grade" in e for e in errors)
    assert all(t["mode"] == "clarify" and not t["slots"] for t in plan["tasks"])


@pytest.mark.parametrize("first,second", [("5,2", "7,6"), ("5.2/10", "7.6/10"), ("-5.2/10", "+5.2/10")])
def test_correct_numeric_pairs_and_signed_scales_are_preserved(first, second):
    tasks = [task(f"K51 môn nền tảng {first} đổi điểm chữ?", mode="structured", value=first, scope="foundation"),
             task(f"K51 môn còn lại {second} đổi điểm chữ?", mode="structured", value=second, scope="remaining")]
    plan, errors = normalize(tasks)
    assert not errors and all(t["mode"] == "structured" for t in plan["tasks"])
    assert [t["slots"]["score_or_grade"] for t in plan["tasks"]] == [first, second]


def test_scalar_slot_cannot_borrow_a_denominator_from_another_task():
    first = task("K51 GPA 3,6/4 xếp loại gì?", mode="structured", value=3.6)
    first["slots"]["operation"] = "academic_classification"
    first["slot_spans"]["score_or_grade"] = "3,6/10"
    second = task("K51 môn A 3,6/10 đổi điểm chữ?", mode="structured", value="3,6/10")
    plan, errors = normalize([first, second])
    assert "t1:task_operand_conflict:score_or_grade" in errors
    assert plan["tasks"][0]["mode"] == "clarify"
    assert plan["tasks"][1]["mode"] == "structured"


def test_missing_numeric_text_in_paraphrase_alone_is_not_a_contradiction():
    first = task("Môn A đổi ra điểm chữ gì?", mode="structured", value="5.2")
    second = task("Môn B đổi ra điểm chữ gì?", mode="structured", value="7.6")
    plan, errors = normalize([first, second], query="K51 môn A 5.2, môn B 7.6 đổi điểm chữ thế nào?")
    assert not errors and all(t["mode"] == "structured" for t in plan["tasks"])


def test_unrelated_article_and_cohort_digits_are_not_competing_operands():
    first = task("K51 Điều 10 đổi điểm chữ thế nào?", mode="structured", value="5.2")
    second = task("K51 môn B 7.6 đổi điểm chữ?", mode="structured", value="7.6")
    plan, errors = normalize([first, second], query="K51 Điều 10: môn A 5.2 đổi điểm chữ; môn B 7.6 đổi điểm chữ?")
    assert not errors and all(t["mode"] == "structured" for t in plan["tasks"])


@pytest.mark.parametrize("number", ["3", "3.0"])
@pytest.mark.parametrize("anchored", [False, True])
def test_course_credits_are_not_a_sibling_gpa_operand(number, anchored):
    first_question = f"K51 môn A {number} tín chỉ đổi sang điểm chữ?"
    first = task(first_question, mode="structured", value="5.2")
    second = task("K51 GPA 3.0 xếp loại gì?", mode="structured", value="3.0")
    second["slots"]["operation"] = "academic_classification"
    query = (f"K51 được 5.2 điểm; {first_question} {second['question']}" if anchored else
             f"K51 môn A {number} tín chỉ được 5.2 điểm đổi sang chữ gì? {second['question']}")
    plan, errors = normalize([first, second], query=query)
    assert not errors and all(t["mode"] == "structured" for t in plan["tasks"])


def test_unanchored_paraphrase_condition_is_not_a_sibling_operand():
    first = task("K51 môn A cần ngưỡng 7.6 để xếp loại thế nào?", mode="structured", value="5.2")
    second = task("K51 môn B 7.6 đổi điểm chữ?", mode="structured", value="7.6")
    plan, errors = normalize([first, second], query="K51 môn A được 5.2, môn B được 7.6 đổi điểm chữ thế nào?")
    assert not errors and all(t["mode"] == "structured" for t in plan["tasks"])


@pytest.mark.parametrize("locator", ["được in trong sổ tay K50", "in trong sổ tay sinh viên khóa K50", "in ở sổ tay K50"])
def test_source_handbook_edition_is_not_execution_scope(locator):
    question = f"IELTS 5.5 quy đổi theo bảng {locator}?"
    foreign = {**task(question), "mode": "structured", "intent": "direct_value", "lookup_type": "foreign_language",
               "slots": {"certificate_or_language": "IELTS", "score_or_level": "5.5"},
               "slot_spans": {"certificate_or_language": "IELTS", "score_or_level": "5.5"}}
    plan, errors = normalize([foreign, task("K51 nghỉ học thế nào?")],
                            query=f"Em K51; {question} K51 nghỉ học thế nào?")
    assert not errors and plan["tasks"][0]["cohorts"] == ["K51"]
    assert plan["tasks"][0]["mode"] == "structured"


def test_plain_handbook_comparison_remains_an_explicit_cohort_request():
    question = "So sánh sổ tay K50 và sổ tay K51 về nghỉ học?"
    plan, errors = normalize([task(question, "K50")], query=question)
    assert "t1:task_cohort_conflict" in errors
    assert plan["tasks"][0]["mode"] == "clarify"


def test_follow_up_comparison_uses_standalone_scope_not_current_turn_alone():
    first = task("So sánh K50 và K51 về bảo lưu?", "K50")
    first["cohorts"] = ["K50", "K51"]
    plan, errors = normalize([first], query="Còn K51 so với khóa đó?", visible_history={0: "K50 bảo lưu?"},
        payload={"context_mode": "follow_up", "standalone_query": first["question"], "referenced_turns": [0]})
    assert not errors and plan["tasks"][0]["cohorts"] == ["K50", "K51"]


def test_follow_up_can_ground_inputs_only_in_referenced_history():
    questions = ["K50 môn A 5.2 đổi điểm chữ?", "K51 môn B 7.6 đổi điểm chữ?"]
    tasks = [task(q, cohort, mode="structured", value=value)
             for q, cohort, value in zip(questions, ["K50", "K51"], ["5.2", "7.6"])]
    plan, errors = normalize(tasks, query="Tính lại hai môn đó?", visible_history={0: " và ".join(questions)},
        payload={"context_mode": "follow_up", "standalone_query": " và ".join(questions), "referenced_turns": [0]})
    assert not errors and all(t["mode"] == "structured" for t in plan["tasks"])


@pytest.mark.parametrize("streaming", [False, True])
def test_contradictory_task_cannot_produce_evidence_but_valid_sibling_can(streaming):
    # The plan is normalized before it crosses the real executor interface.
    root = Path(__file__).resolve().parents[1]
    tables = json.loads((root / "data/processed/tables/structured_tables_registry.json").read_text(encoding="utf-8"))
    tasks = [task("K50 môn A 5.2 đổi điểm chữ?", "K51", mode="structured", value="5.2"),
             task("K51 môn còn lại 7.6 đổi điểm chữ?", mode="structured", value="7.6", scope="remaining")]
    query = " và ".join(t["question"] for t in tasks)
    plan, errors = normalize(tasks, query)
    assert "t1:task_cohort_conflict" in errors
    executor = PlanExecutor(router=SimpleNamespace(plan=lambda *a, **kw: plan),
        slang_normalizer=SimpleNamespace(normalize_for_retrieval=lambda q: q),
        catalogs=StructuredCatalogs([], [], [], [], tables, []), parent_sources_by_id={},
        top_k=5, public_source_limit=10, graph=SimpleNamespace(expand_context=lambda *a, **kw: []))
    result = executor.run(query=query, cohort="K51", chat_history=[])
    packet = build_authorized_evidence_packet(query=query, retrieval_result=result,
        selected_citations=result["evidence_citations"], fallback_cohort="K51", max_context_chars=160000)
    assert packet["units"][0]["coverage"] == "needs_clarification"
    assert not packet["units"][0]["primary_evidence"]
    assert packet["units"][1]["primary_evidence"][0]["resolved_result"]["input_value"] == 7.6
    prompts = []

    class Composer:
        def generate(self, prompt):
            prompts.append(prompt)
            return {"ok": True, "text": "Một phần cần làm rõ.", "model_used": "fake", "usage": {}}

        def generate_stream(self, prompt):
            prompts.append(prompt)
            yield "Một phần cần làm rõ."
            return {"model_used": "fake", "usage": {}}

    pipeline = AnswerPipeline(llm_client=Composer())
    pipeline._run_retrieval = lambda *a, **kw: result
    output = list(pipeline.answer_stream(query, cohort="K51"))[-1] if streaming else pipeline.answer(query, cohort="K51")
    assert output["status"] == "answered" and len(prompts) == 1
    context, _ = json.JSONDecoder().raw_decode(prompts[0].split("\nAUTHORIZED_EVIDENCE_BY_UNIT\n", 1)[1])
    assert not context["units"][0]["primary_evidence"]


def test_binding_validation_does_not_mutate_planner_payload():
    tasks = [task("K50 điểm trung bình?"), task("K51 nghỉ học?")]
    before = copy.deepcopy(tasks)
    normalize(tasks)
    assert tasks == before
