"""Task-bound raw tables and amendments: real catalogs, no model/store calls."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.generation.amendment_precedence import collect_applicable_amendments
from src.generation.plan_executor import PlanExecutor, StructuredCatalogs
from src.generation.answer_pipeline import AnswerPipeline
from src.generation.prompt_builder import build_authorized_evidence_packet
from src.generation.citation_formatter import deduplicate_citations


@pytest.fixture
def sources():
    def read(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))
    return (read("data/processed/tables/structured_tables_registry.json"),
            {p["_id"]: p for p in read("data/processed/chunks/all_docstore_items.json")})


def rag_evidence(parent, task_id, table=None):
    context = {} if table is None else {"raw_table_context": json.dumps({"tables": [
        {k: table.get(k) for k in ("table_id", "table_name", "cohort", "applicability", "columns", "rows")}
    ]}, ensure_ascii=False)}
    item = {**parent, "chunk_id": parent["_id"], "supports_task_ids": [task_id],
            "metadata": {**parent["metadata"], "parent_section_id": parent["_id"],
                         "supports_task_ids": [task_id], **context}}
    citation = {**parent["metadata"], "chunk_id": parent["_id"], "source_parent_id": parent["_id"],
                "cohort": parent["cohort"], "content": parent["content"], "document": parent["content"],
                "supports_task_ids": [task_id], **context}
    return item, citation


def packet(tasks, items, citations, budget=160000):
    return build_authorized_evidence_packet(query="Các yêu cầu độc lập", retrieval_result={
        "query_plan": {"tasks": tasks}, "retrieved_items": items,
        "coverage_by_task": {t["id"]: "covered" for t in tasks},
    }, selected_citations=citations, fallback_cohort="K51", max_context_chars=budget)


def task(task_id, question, mode="rag", cohort="K51"):
    return {"id": task_id, "question": question, "mode": mode, "cohorts": [cohort]}


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("family", ["study_duration", "grade_scale"])
def test_same_parent_tables_remain_bound_to_their_task_through_composition(sources, reverse, family):
    tables, parents = sources
    siblings = [t for t in tables if t["cohort"] == "K51" and t["table_subtype"] == family]
    assert len(siblings) == 2 and siblings[0]["source_parent_id"] == siblings[1]["source_parent_id"]
    parent = parents[siblings[0]["source_parent_id"]]
    evidence = [rag_evidence(parent, f"t{i}", t) for i, t in enumerate(siblings, 1)]
    if reverse:
        evidence.reverse()
    items, citations = map(list, zip(*evidence))
    before = copy.deepcopy((items, citations))
    merged_items = PlanExecutor._merge_task_items(items)
    merged_citations = PlanExecutor._merge_task_citations(citations)
    assert len(merged_items) == len(merged_citations) == 2
    result = packet([task(f"t{i}", t["table_name"]) for i, t in enumerate(siblings, 1)], merged_items, merged_citations)
    for unit in result["units"]:
        expected = siblings[int(unit["task_id"][1:]) - 1]
        assert len(unit["primary_evidence"]) == 1
        source = unit["primary_evidence"][0]
        raw = json.loads(source["content"])["tables"]
        assert len(raw) == 1 and raw[0]["table_id"] == expected["table_id"]
        assert raw[0]["rows"] == expected["rows"] and raw[0]["applicability"] == expected.get("applicability")
        assert "resolved_result" not in source  # RAG does not acquire a fact lock.
    assert (items, citations) == before
    assert len(deduplicate_citations(merged_citations)) == 1  # Public parent still deduplicates.


def test_table_handle_cannot_replace_plain_parent_evidence_of_another_task(sources):
    tables, parents = sources
    table = next(t for t in tables if t["cohort"] == "K51" and t["table_subtype"] == "conduct_classification")
    parent = parents[table["source_parent_id"]]
    evidence = [rag_evidence(parent, "t1", table), rag_evidence(parent, "t2")]
    items, citations = map(list, zip(*evidence))
    result = packet([task("t1", "Tra bảng"), task("t2", "Quy định kỷ luật")],
                    PlanExecutor._merge_task_items(items), PlanExecutor._merge_task_citations(citations))
    assert json.loads(result["units"][0]["primary_evidence"][0]["content"])["tables"][0]["rows"] == table["rows"]
    plain = result["units"][1]["primary_evidence"][0]["content"]
    assert plain == parent["content"].strip() and '"tables":' not in plain


def test_structured_fact_lock_and_rag_table_of_same_parent_remain_separate(sources):
    tables, parents = sources
    table = next(t for t in tables if t["cohort"] == "K51" and t["table_subtype"] == "conduct_classification")
    item, rag = rag_evidence(parents[table["source_parent_id"]], "t2", table)
    structured = {"chunk_id": item["chunk_id"], "source_parent_id": item["chunk_id"], "cohort": "K51",
                  "evidence_kind": "structured_result", "chunk_type": "structured_lookup", "supports_task_ids": ["t1"],
                  "content": json.dumps({"rows": [{"score": 82, "result": "Tốt"}]}),
                  "resolved_result": {"cohort": "K51", "input_value": 82, "result": {"classification": "Tốt"}}}
    result = packet([task("t1", "82 điểm được loại gì?", "structured"), task("t2", "Bảng rèn luyện")], [item],
                    PlanExecutor._merge_task_citations([structured, rag]))
    locked, reference = [u["primary_evidence"][0] for u in result["units"]]
    assert locked["resolved_result"]["input_value"] == 82
    assert "resolved_result" not in reference and json.loads(reference["content"])["tables"][0]["rows"] == table["rows"]


def test_raw_table_identity_does_not_broaden_cross_cohort_authorization(sources):
    tables, parents = sources
    table = next(t for t in tables if t["cohort"] == "K51" and t["table_subtype"] == "conduct_classification")
    item, citation = rag_evidence(parents[table["source_parent_id"]], "t1", table)
    citation["supports_task_ids"] = ["t1", "t2"]
    result = packet([task("t1", "Bảng K51"), task("t2", "Bảng K50", cohort="K50")], [item], [citation])
    assert result["units"][0]["primary_evidence"]
    assert result["units"][1]["primary_evidence"] == []


def test_plain_shared_parent_amendment_is_available_to_both_authorized_tasks(sources):
    _, parents = sources
    parent = parents["K51_QuyCheDaoTao_Chuong3_Dieu10"]
    items, citations = map(list, zip(rag_evidence(parent, "t1"), rag_evidence(parent, "t2")))
    result = packet([task("t1", "Quy định học lại học phần?"), task("t2", "Điểm học lại?")],
                    PlanExecutor._merge_task_items(items), PlanExecutor._merge_task_citations(citations))
    assert all(u["applicable_amendments"] for u in result["units"])


def test_raw_table_budget_failure_is_local_to_each_task(sources):
    tables, parents = sources
    siblings = [t for t in tables if t["cohort"] == "K51" and t["table_subtype"] == "study_duration"]
    evidence = [rag_evidence(parents[t["source_parent_id"]], f"t{i}", t) for i, t in enumerate(siblings, 1)]
    items, citations = map(list, zip(*evidence))
    result = packet([task("t1", "Phạm vi A"), task("t2", "Phạm vi B")],
                    PlanExecutor._merge_task_items(items), PlanExecutor._merge_task_citations(citations), budget=600)
    for unit in result["units"]:
        source = unit["primary_evidence"][0]
        assert source["table_context_unavailable"] == "context_budget"
        assert '"tables":' not in source["content"]


def test_plain_shared_source_fusion_and_same_task_duplicates_are_unchanged(sources):
    _, parents = sources
    parent = next(p for p in parents.values() if p["cohort"] == "K51")
    items, citations = map(list, zip(rag_evidence(parent, "t1"), rag_evidence(parent, "t2")))
    assert len(PlanExecutor._merge_task_items(items)) == 1
    merged = PlanExecutor._merge_task_citations(citations)
    assert len(merged) == 1 and merged[0]["supports_task_ids"] == ["t1", "t2"]
    duplicate = copy.deepcopy(citations[0])
    duplicate["raw_table_context"] = '{"tables":[{"table_id":"arbitrary","rows":[{"v":1}]}]}'
    assert len(PlanExecutor._merge_task_citations([duplicate, copy.deepcopy(duplicate)])) == 1


def test_executor_aggregates_source_support_without_overwriting_a_task(sources, monkeypatch):
    tables, parents = sources
    siblings = [t for t in tables if t["cohort"] == "K51" and t["table_subtype"] == "study_duration"]
    def retrieval(**kwargs):
        table = next(t for t in siblings if t["table_name"] + t["table_id"] == kwargs["query"])
        item, citation = rag_evidence(parents[table["source_parent_id"]], "unused", table)
        return {"retrieved_items": [item], "citations": [citation]}
    monkeypatch.setattr("src.generation.plan_executor.run_hybrid_retrieval_pipeline", retrieval)
    tasks = [task(f"t{i}", t["table_name"] + t["table_id"]) for i, t in enumerate(siblings, 1)]
    executor = PlanExecutor(router=SimpleNamespace(plan=lambda *a, **kw: {"tasks": tasks}),
        slang_normalizer=SimpleNamespace(normalize_for_retrieval=lambda text: text),
        catalogs=StructuredCatalogs([], [], [], [], [], []), parent_sources_by_id=parents,
        top_k=5, public_source_limit=10)
    result = executor.run(query="Tra hai phạm vi", cohort="K51", chat_history=[])
    assert len(result["evidence_citations"]) == len(result["retrieved_items"]) == 2
    assert result["supports_task_ids"][siblings[0]["source_parent_id"]] == ["t1", "t2"]


@pytest.mark.parametrize("streaming", [False, True])
def test_sync_and_stream_composers_receive_the_same_task_local_tables(sources, streaming):
    tables, parents = sources
    siblings = [t for t in tables if t["cohort"] == "K51" and t["table_subtype"] == "study_duration"]
    items, citations = map(list, zip(*(rag_evidence(parents[t["source_parent_id"]], f"t{i}", t)
                                     for i, t in enumerate(siblings, 1))))
    tasks = [task(f"t{i}", t["table_name"]) for i, t in enumerate(siblings, 1)]
    result = {"query_plan": {"tasks": tasks}, "coverage_by_task": {"t1": "covered", "t2": "covered"},
              "citations": PlanExecutor._merge_task_citations(citations),
              "evidence_citations": PlanExecutor._merge_task_citations(citations),
              "retrieved_items": PlanExecutor._merge_task_items(items), "needs_llm_answer": True}
    answer = "Hai phạm vi được giữ riêng."
    prompts = []
    class Composer:
        def generate(self, prompt):
            prompts.append(prompt)
            return {"ok": True, "text": answer, "model_used": "fake", "usage": {}}

        def generate_stream(self, prompt):
            prompts.append(prompt)
            yield answer
            return {"model_used": "fake", "usage": {}}
    pipeline = AnswerPipeline(llm_client=Composer())
    pipeline._run_retrieval = lambda *a, **kw: result
    if streaming:
        events = list(pipeline.answer_stream("Tra hai phạm vi", cohort="K51"))
        assert events[-1]["status"] == "answered"
        assert "".join(e.get("text", "") for e in events if e["type"] == "token") == answer
    else:
        output = pipeline.answer("Tra hai phạm vi", cohort="K51")
        assert output["status"] == "answered" and output["answer"] == answer
    assert len(prompts) == 1
    context, _ = json.JSONDecoder().raw_decode(prompts[0].split("\nAUTHORIZED_EVIDENCE_BY_UNIT\n", 1)[1])
    for i, unit in enumerate(context["units"]):
        assert json.loads(unit["primary_evidence"][0]["content"])["tables"][0]["table_id"] == siblings[i]["table_id"]


@pytest.mark.parametrize("mode", ["rag", "structured"])
def test_real_amendments_cannot_cross_task_boundaries(sources, mode):
    _, parents = sources
    conduct = parents["K51_QuyCheDanhGiaRenLuyen_Chuong3_Dieu9"]
    training = parents["K51_QuyCheDaoTao_Chuong3_Dieu10"]
    items, citations = map(list, zip(rag_evidence(conduct, "t1"), rag_evidence(training, "t2")))
    result = packet([task("t1", "Điểm rèn luyện có bao nhiêu loại?", mode),
                     task("t2", "Quy định học lại học phần?")], items, citations)
    assert result["units"][0]["applicable_amendments"] == []
    assert result["units"][1]["applicable_amendments"]
    assert result["units"][0]["allowed_source_refs"] == ["S1"]


def test_real_pure_structured_executor_retains_canonical_lock_and_source_context(sources):
    tables, parents = sources
    question = "K51 học phần còn lại 5,2/10 được điểm chữ gì?"
    planned = {**task("t1", question, "structured"), "intent": "direct_value", "lookup_type": "scoring",
               "slots": {"operation": "grade_10_to_letter", "course_scope": "remaining", "score_or_grade": "5.2/10"},
               "slot_spans": {"course_scope": "học phần còn lại", "score_or_grade": "5,2/10"}}
    executor = PlanExecutor(router=SimpleNamespace(plan=lambda *a, **kw: {"tasks": [planned], "context_mode": "standalone"}),
        slang_normalizer=SimpleNamespace(normalize_for_retrieval=lambda text: text),
        catalogs=StructuredCatalogs([], [], [], [], tables, []), parent_sources_by_id=parents,
        top_k=5, public_source_limit=10, graph=SimpleNamespace(expand_context=lambda *a, **kw: []))
    result = executor.run(query=question, cohort="K51", chat_history=[])
    assert result["retrieved_items"] == []  # This exercises the real structured path, not RAG-shaped fixtures.
    composed = build_authorized_evidence_packet(query=question, retrieval_result=result,
        selected_citations=result["evidence_citations"], fallback_cohort="K51", max_context_chars=160000)
    source = composed["units"][0]["primary_evidence"][0]
    lock = source["resolved_result"]
    assert lock["input_value"] == 5.2 and lock["cohort"] == "K51"
    assert lock["result"][0]["row"] == {"status": "Không đạt", "score_10_range": "4,8 - 5,4", "letter_grade": "D+"}
    assert "Các học phần còn lại" in source["source_context"] or "các học phần còn lại" in source["source_context"]


def test_amendment_authorization_precedes_relevance_and_item_budget():
    registry = tuple({"target_parent_id": "other", "replacement_text": f"Điểm học phần rèn luyện học lại quy định {i}",
                      "cohort": "K51", "importance": "substantive"} for i in range(6)) + (
        {"target_parent_id": "allowed", "replacement_text": "Điểm đúng phạm vi.", "cohort": "K51"},)
    retrieved = {"retrieved_items": [{"chunk_id": p, "content": "Nguồn", "metadata": {"cohort": "K51"}}
                                     for p in ("other", "allowed")]}
    amendments = collect_applicable_amendments(retrieved, query="Điểm học phần rèn luyện học lại quy định", cohort="K51",
        registry=registry, max_items=1, allowed_primary_parent_ids={"allowed"})
    assert len(amendments) == 1 and amendments[0].source_parent_id == "allowed"


@pytest.mark.parametrize("target", ["allowed", "other", None])
def test_related_footnote_must_amend_an_authorized_primary_parent(target):
    replacement = "Điểm học lại dùng điểm cao nhất."
    registry = () if target is None else ({"target_parent_id": target, "replacement_text": replacement,
                                           "cohort": "K51"},)
    retrieved = {"retrieved_items": [{"chunk_id": p, "content": "Nguồn", "metadata": {"cohort": "K51"}}
                                     for p in ("allowed", "other")],
                 "related_items": [{"chunk_id": "physical", "metadata": {"cohort": "K51"},
                    "content": "Điểm này được sửa đổi, áp dụng từ năm 2025 trở về sau. Cụ thể như sau: “" + replacement + "”"}]}
    amendments = collect_applicable_amendments(retrieved, query="Điểm học lại", cohort="K51",
        registry=registry, allowed_primary_parent_ids={"allowed"})
    assert bool(amendments) == (target == "allowed")
    assert all(a.source_parent_id == "allowed" for a in amendments)


@pytest.mark.parametrize("cohort", ["K48-K49", "K50"])
def test_authorized_parent_does_not_bypass_amendment_cohort_or_year(cohort):
    amendments = collect_applicable_amendments({"retrieved_items": [{"chunk_id": "allowed", "content": "Nguồn",
        "metadata": {"cohort": cohort}}]}, query="Điểm học lại", cohort=cohort,
        registry=({"target_parent_id": "allowed", "replacement_text": "Điểm học lại", "cohort": "K51",
                   "applicability": {"kind": "min_admission_year", "year": 2025}},),
        allowed_primary_parent_ids={"allowed"})
    assert amendments == []
