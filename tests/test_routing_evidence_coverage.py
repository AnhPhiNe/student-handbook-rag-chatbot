"""General contracts for selectors, bounded fallback and policy evidence; no providers."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.generation.plan_executor import PlanExecutor, StructuredCatalogs
from src.generation.answer_pipeline import AnswerPipeline
from src.generation.prompt_builder import build_answer_prompt_bundle, build_authorized_evidence_packet
from src.retrieval.core.structured_dispatcher import StructuredResolution, resolve_structured_task
from src.retrieval.core.directory_selector import Selection, NONE


def catalogs():
    def read(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return StructuredCatalogs(
        read("data/processed/tables/formula_rules.json"),
        read("data/processed/directories/student_office_profiles.json"),
        read("data/processed/directories/student_service_directory.json"),
        read("data/processed/directories/student_faculty_profiles.json"),
        read("data/processed/tables/structured_tables_registry.json"),
        read("data/processed/directories/program_directory.json"),
    )


def task(query="K51 điểm B sang thang 4", **slots):
    return {"id": "t1", "question": query, "mode": "structured", "intent": "direct_value",
            "lookup_type": "scoring", "cohorts": ["K51"], "slots": slots,
            "slot_spans": {"score_or_grade": "B", "course_scope": "môn tính GPA"}}


def executor(plan_task, cats=None):
    return PlanExecutor(router=SimpleNamespace(plan=lambda *a, **kw: {
        "tasks": [plan_task], "out_of_domain": False, "context_mode": "standalone"}),
        slang_normalizer=SimpleNamespace(normalize_for_retrieval=lambda text: text),
        catalogs=cats or catalogs(), parent_sources_by_id={}, top_k=5, public_source_limit=5,
        graph=SimpleNamespace(expand_context=lambda *a, **kw: []))


@pytest.mark.parametrize("cohort", ["K48-K49", "K50", "K51"])
@pytest.mark.parametrize("scope", ["graded", "foundation", "remaining"])
def test_scope_does_not_remove_letter_conversion(cohort, scope):
    phrase = {"graded": "môn tính GPA", "foundation": "học phần nền tảng", "remaining": "học phần còn lại"}[scope]
    t = task(f"{cohort} {phrase} điểm B sang thang 4", operation="letter_to_grade_4",
             score_or_grade="B", course_scope=scope)
    t["slot_spans"]["course_scope"] = phrase
    result = executor(t)._execute_planned_structured_task(task=t, task_id="t1", cohort=cohort)
    lock = result["structured_result"]["resolved_result"]
    assert lock["result"] == {"letter_grade": "B", "score_4": 3.0}


def test_operation_union_keeps_noncourse_table_with_course_scope():
    t = task("K51 học phần còn lại đổi điểm chữ và thang 4", operation=["grade_10_to_letter", "letter_to_grade_4"],
             course_scope="remaining")
    result = executor(t)._execute_planned_structured_task(task=t, task_id="t1", cohort="K51")
    tables = result["structured_result"]["sub_lookups"]
    assert {item["table_subtype"] for item in tables} == {"grade_scale", "letter_to_grade4"}
    assert all("remaining" in item["table_id"] for item in tables if item["table_subtype"] == "grade_scale")


def test_selector_conflict_stays_visible_and_does_not_fallback(monkeypatch):
    t = task("K51 6,1 điểm", operation="grade_10_to_letter", score_or_grade=6.1,
             course_scope="pass_fail_ungraded")
    monkeypatch.setattr("src.generation.plan_executor.run_hybrid_retrieval_pipeline",
                        lambda **kw: pytest.fail("selector bug must not be hidden by RAG"))
    result = executor(t)._execute_planned_structured_task(task=t, task_id="t1", cohort="K51")
    assert result["coverage"] == "uncovered"
    assert result["structured_failure_reason"] == "selector_conflict"


def test_missing_source_fallback_once_keeps_plan_and_cohort(monkeypatch):
    cats = catalogs()
    # A valid corpus can lack this family for one cohort; no table is synthesized.
    only_older = [t for t in cats.structured_tables_registry if t["cohort"] != "K51"]
    cats = StructuredCatalogs(**{**vars(cats), "structured_tables_registry": only_older})
    t = task(operation="letter_to_grade_4", score_or_grade="B")
    calls = []
    def rag(**kw):
        calls.append(kw)
        return {"retrieved_items": [{"chunk_id": "p", "content": "Nguồn K51", "metadata": {"cohort": "K51"}}],
                "citations": [{"chunk_id": "p", "content": "Nguồn K51", "cohort": "K51"}]}
    monkeypatch.setattr("src.generation.plan_executor.run_hybrid_retrieval_pipeline", rag)
    result = executor(t, cats).run(query=t["question"], cohort="K51", chat_history=[])
    assert len(calls) == 1 and calls[0]["cohort"] == "K51"
    assert result["query_plan"]["tasks"][0]["mode"] == "structured"
    assert result["execution_mode"] == "rag"
    assert result["structured_result"] is None
    assert result["task_results"][0]["retrieval_fallback_by_cohort"] == {"K51": "no_source"}
    packet = build_authorized_evidence_packet(query=t["question"], retrieval_result=result,
        selected_citations=result["citations"], fallback_cohort="K51", max_context_chars=10000)
    assert packet["units"][0]["mode"] == "rag"
    assert "resolved_result" not in packet["units"][0]["primary_evidence"][0]


@pytest.mark.parametrize("kind,reason", [(None, None), ("clarification", None),
                                        ("unavailable", "invalid_input"), ("unavailable", "selector_conflict")])
def test_unknown_missing_or_ambiguous_inputs_never_fallback(monkeypatch, kind, reason):
    result = None if kind is None else StructuredResolution("scoring", "test", kind,
        {"needs_clarification": kind == "clarification", "clarification_question": "Điểm của bạn?",
         "unavailable_reason": reason}, [])
    monkeypatch.setattr("src.retrieval.core.structured_dispatcher.resolve_structured_task", lambda *a, **kw: result)
    monkeypatch.setattr("src.generation.plan_executor.run_hybrid_retrieval_pipeline",
                        lambda **kw: pytest.fail("unclassified/clarify/error does not permit RAG"))
    executor(task())._execute_planned_structured_task(task=task(), task_id="t1", cohort="K51")


def test_system_exception_is_not_converted_to_fallback(monkeypatch):
    def broken(*args, **kw):
        raise RuntimeError("fixture failure")
    monkeypatch.setattr("src.retrieval.core.structured_dispatcher.resolve_structured_task", broken)
    with pytest.raises(RuntimeError):
        executor(task())._execute_planned_structured_task(task=task(), task_id="t1", cohort="K51")


@pytest.mark.parametrize("chunk_type,has_context", [("structured_lookup", True), ("formula_rule", True),
                                                   ("program_directory", False), ("student_faculty_profile", False)])
def test_source_context_is_same_source_budgeted_and_not_directory(chunk_type, has_context):
    t = task()
    citation = {"chunk_id": "parent", "source_parent_id": "parent", "chunk_type": chunk_type,
                "cohort": "K51", "supports_task_ids": ["t1"], "content": "TABLE",
                "parent_content": "Điều kiện: kết quả toàn khóa không vượt quá Tốt. " * 100,
                "resolved_result": {"cohort": "K51", "result": {"label": "Xuất sắc"}}}
    original = copy.deepcopy(citation)
    _, context = build_answer_prompt_bundle("Tra bảng", {"query_plan": {"tasks": [t]},
        "task_results": [{"task_id": "t1", "coverage": "covered"}]}, [citation], 1000, "K51")
    source = json.loads(context)["units"][0]["primary_evidence"][0]
    assert ("source_context" in source) == has_context
    assert len(source["content"]) + len(source.get("source_context", "")) <= 750
    assert source["resolved_result"]["result"]["label"] == "Xuất sắc"
    assert citation == original


def test_one_rag_task_can_receive_policy_and_table_for_shared_source():
    docs = {p["_id"]: p for p in json.loads(Path("data/processed/chunks/all_docstore_items.json").read_text(encoding="utf-8"))}
    ids = ["K50_QuyDinhChuanDauRaNgoaiNgu_KhongCoChuong_Dieu4",
           "K50_QuyDinhChuanDauRaNgoaiNgu_KhongCoChuong_Dieu8"]
    citations = [{**docs[i]["metadata"], "chunk_id": i, "content": docs[i]["content"],
                  "source_cohort": "K50", "supports_task_ids": ["t1"]} for i in ids]
    t = {**task(), "mode": "rag", "cohorts": ["K48-K49"]}
    packet = build_authorized_evidence_packet(query="TOEIC để tốt nghiệp", retrieval_result={
        "query_plan": {"tasks": [t]}, "task_results": [{"task_id": "t1", "coverage": "covered"}]},
        selected_citations=citations, fallback_cohort="K48-K49", max_context_chars=160000)
    sources = packet["units"][0]["primary_evidence"]
    assert len(packet["units"]) == 1 and len(sources) == 2
    assert any("bậc 3/6" in s["content"] for s in sources)
    assert any("TOEIC" in s["content"] and "275" in s["content"] for s in sources)


def test_selector_registry_blank_does_not_authorize_fallback():
    t = task(operation="letter_to_grade_4", score_or_grade="B")
    result = resolve_structured_task(t, query=t["question"], cohort="K51", formula_rules=[],
        office_directory=[], student_service_directory=[], student_faculty_profiles=[],
        structured_tables_registry=[], program_directory=[])
    assert result is None


def test_empty_scoped_rows_are_corrupt_not_an_absent_cohort(monkeypatch):
    cats = catalogs()
    tables = [t for t in cats.structured_tables_registry if t["cohort"] != "K51"]
    tables.append({"table_id": "broken", "table_type": "scoring", "data_category": "regulation_table",
                   "cohort": "K51", "document_id": "doc", "rows": []})
    cats = StructuredCatalogs(**{**vars(cats), "structured_tables_registry": tables})
    monkeypatch.setattr("src.generation.plan_executor.run_hybrid_retrieval_pipeline",
                        lambda **kw: pytest.fail("malformed scoped rows cannot disappear before classification"))
    t = task(operation="letter_to_grade_4", score_or_grade="B")
    result = executor(t, cats)._execute_planned_structured_task(task=t, task_id="t1", cohort="K51")
    assert result["structured_failure_reason"] == "invalid_catalog"


@pytest.mark.parametrize("tool,catalog_field,bad_record,slots", [
    ("scoring", "structured_tables_registry", {"data_category": "regulation_table",
     "table_type": "scoring", "rows": [{}]}, {"operation": "letter_to_grade_4", "score_or_grade": "B"}),
    ("scoring", "structured_tables_registry", {"data_category": "regulation_table",
     "table_type": "scoring", "table_id": "old", "cohort": "K50", "document_id": "doc",
     "rows": [{"Thang điểm chữ": "B"}, {}]}, {"operation": "letter_to_grade_4", "score_or_grade": "B"}),
    ("formula", "formula_rules", {"rule_id": "broken"}, {"formula_type": "gpa_weighted_average"}),
    ("formula", "formula_rules", {"rule_id": "broken", "cohort": "K50", "document_id": "doc"},
     {"formula_type": "gpa_weighted_average"}),
    ("formula", "formula_rules", {"rule_id": "broken", "cohort": "INVALID", "document_id": "doc",
     "formula_text": "A = B"}, {"formula_type": "gpa_weighted_average"}),
    ("program", "program_directory", {"cohort": "K50"}, {"program_or_faculty": "Foo"}),
])
def test_malformed_nonempty_catalog_never_proves_missing_source(tool, catalog_field, bad_record, slots):
    kwargs = {"formula_rules": [], "office_directory": [], "student_service_directory": [],
              "student_faculty_profiles": [], "structured_tables_registry": [], "program_directory": [],
              catalog_field: [bad_record], "directory_selector": SimpleNamespace()}
    t = {**task(), "lookup_type": tool, "slots": slots,
         "intent": "exists" if tool == "program" else "formula" if tool == "formula" else "direct_value"}
    result = resolve_structured_task(t, query=t["question"], cohort="K51", **kwargs)
    assert result.result_kind == "unavailable"
    assert result.result["unavailable_reason"] == "invalid_catalog"


def test_missing_directory_source_uses_original_grounding_not_rewrite():
    query = "K51 Sư phạm Dược thuộc khoa nào?"
    original = "K51 SP Dược thuộc khoa nào?"
    t = {**task(query), "lookup_type": "program", "slots": {
        "program_or_faculty": "SP Dược", "requested_field": "faculty"},
        "slot_spans": {"program_or_faculty": "SP Dược"}}
    cats = catalogs()
    result = resolve_structured_task(t, query=query, grounding=original, cohort="K51",
        **vars(cats), directory_selector=SimpleNamespace(select=lambda *a, **kw: Selection(NONE)))
    assert result.result["unavailable_reason"] == "no_source"


@pytest.mark.parametrize("transport", ["sync", "stream"])
def test_final_answer_path_keeps_table_value_and_policy(transport, monkeypatch):
    query = "K51, 92 điểm rèn luyện, bị cảnh cáo thì xếp loại toàn khóa thế nào?"
    t = task(query, operation="conduct_classification", score_or_grade=92)
    t["slot_spans"] = {"score_or_grade": "92"}
    run = executor(t)
    parents = json.loads(Path("data/processed/chunks/all_docstore_items.json").read_text(encoding="utf-8"))
    run.parent_sources_by_id = {parent["_id"]: parent for parent in parents}
    retrieval = run.run(query=query, cohort="K51", chat_history=[])
    pipeline = AnswerPipeline.__new__(AnswerPipeline)
    pipeline.max_context_chars = 160000
    pipeline.config = {"planning": {}, "citations": {"public_max_sources": 5}}
    pipeline.llm_config = {"model_name": "fixture"}
    pipeline._run_retrieval = lambda *a, **kw: retrieval
    expected = "Tra bảng: Xuất sắc. Khi xét toàn khóa bị cảnh cáo, xếp loại không vượt quá Tốt."

    class Composer:
        def check(self, prompt):
            assert '"source_context"' in prompt
            assert "không được vượt quá loại tốt" in prompt.lower()
            assert "Xuất sắc" in prompt and "resolved_result" in prompt

        def generate(self, prompt):
            self.check(prompt)
            return {"ok": True, "text": expected, "model_used": "fixture", "usage": {}}

        def generate_stream(self, prompt):
            self.check(prompt)
            yield expected
            return {"model_used": "fixture", "usage": {}}

    pipeline._get_llm_client = lambda: Composer()
    monkeypatch.setattr("src.generation.answer_pipeline.resolve_cohort_from_query", lambda q, c: c)
    if transport == "sync":
        result = pipeline.answer(query, cohort="K51")
        assert result["status"] == "answered" and result["answer"] == expected
    else:
        events = list(pipeline.answer_stream(query, cohort="K51"))
        assert "".join(e.get("text", "") for e in events if e["type"] == "token") == expected
        assert events[-1]["status"] == "answered"
