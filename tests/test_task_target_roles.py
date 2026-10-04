"""Target roles are scoped by logical task before evidence-budget allocation."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.generation.answer_pipeline import AnswerPipeline
from src.generation.plan_executor import PlanExecutor, StructuredCatalogs
from src.generation.prompt_builder import build_authorized_evidence_packet, build_answer_prompt_bundle
from src.retrieval.core.citation_builder import build_citations_from_vector_results
from src.retrieval.core.query_plan import normalize_query_plan


@pytest.fixture(scope="module")
def parents():
    root = Path(__file__).resolve().parents[1]
    return {p["_id"]: p for p in json.loads((root / "data/processed/chunks/all_docstore_items.json").read_text(encoding="utf-8"))}


def task(task_id, question, cohort="K51", mode="rag"):
    return {"id": task_id, "question": question, "mode": mode, "intent": "open_question",
            "lookup_type": None, "slots": {}, "slot_spans": {}, "cohorts": [cohort]}


def source(parents, article, task_id, cohort="K51"):
    parent = next(p for key, p in parents.items() if key.startswith(f"{cohort}_QuyCheDaoTao_") and key.endswith(f"_Dieu{article}"))
    item = {**parent, "chunk_id": parent["_id"]}
    citation = build_citations_from_vector_results([item])[0]
    return {**citation, "supports_task_ids": [task_id]}


def packet(tasks, sources, *, query=None, budget=160000):
    query = query or " và ".join(t["question"] for t in tasks)
    return build_authorized_evidence_packet(query=query, retrieval_result={
        "query_plan": {"tasks": tasks}, "coverage_by_task": {t["id"]: "covered" for t in tasks},
    }, selected_citations=sources, fallback_cohort="K51", max_context_chars=budget)


def roles(unit):
    return {s["article_label"]: s["role"] for s in unit["primary_evidence"]}


@pytest.mark.parametrize("first_mode", ["rag", "structured"])
@pytest.mark.parametrize("reverse", [False, True])
def test_sibling_article_cannot_promote_an_unnamed_source(parents, first_mode, reverse):
    tasks = [task("t1", "K51 điểm trung bình được tính thế nào?", mode=first_mode),
             task("t2", "Điều 16 Quy chế đào tạo K51 quy định nghỉ học thế nào?")]
    citations = [source(parents, 11, "t1"), source(parents, 16, "t1"), source(parents, 16, "t2")]
    original = copy.deepcopy(citations)
    if reverse:
        tasks.reverse()
        citations.reverse()
    result = packet(tasks, citations)
    units = {u["task_id"]: u for u in result["units"]}
    assert roles(units["t1"]) == {"Điều 11": "candidate", "Điều 16": "candidate"}
    assert roles(units["t2"]) == {"Điều 16": "target"}
    assert sorted(citations, key=lambda c: (c["source_parent_id"], c["supports_task_ids"])) == sorted(
        original, key=lambda c: (c["source_parent_id"], c["supports_task_ids"]))


@pytest.mark.parametrize("cohort", ["K50", "K51"])
@pytest.mark.parametrize("reverse", [False, True])
def test_each_named_task_keeps_its_own_target_when_query_names_other_articles(parents, cohort, reverse):
    tasks = [task("t1", f"Điều 11 Quy chế đào tạo {cohort} tính điểm trung bình thế nào?", cohort),
             task("t2", f"Điều 16 Quy chế đào tạo {cohort} quy định nghỉ học thế nào?", cohort)]
    citations = [source(parents, 11, "t1", cohort), source(parents, 16, "t1", cohort), source(parents, 16, "t2", cohort)]
    if reverse:
        tasks.reverse()
        citations.reverse()
    result = packet(tasks, citations)
    units = {u["task_id"]: u for u in result["units"]}
    assert roles(units["t1"]) == {"Điều 11": "target", "Điều 16": "candidate"}
    assert roles(units["t2"]) == {"Điều 16": "target"}


def test_comparison_expands_cohorts_without_losing_task_local_target(parents):
    first = task("t1", "So sánh Điều 11 Quy chế đào tạo K50 và K51 về điểm trung bình?")
    first["cohorts"] = ["K50", "K51"]
    second = task("t2", "So sánh Điều 16 Quy chế đào tạo K50 và K51 về nghỉ học?")
    second["cohorts"] = ["K50", "K51"]
    citations = [source(parents, article, task_id, cohort)
                 for cohort in ["K50", "K51"] for article, task_id in [(11, "t1"), (16, "t1"), (16, "t2")]]
    result = packet([first, second], citations)
    assert len(result["units"]) == 4
    for unit in result["units"]:
        expected = {"Điều 11": "target", "Điều 16": "candidate"} if unit["task_id"] == "t1" else {"Điều 16": "target"}
        assert roles(unit) == expected
        assert all(s["source_cohort"] == unit["cohort"] for s in unit["primary_evidence"])


@pytest.mark.parametrize("named_article", [11, 16])
def test_single_logical_task_can_fall_back_to_original_explicit_article(parents, named_article):
    first = task("t1", "Quy định này của K51 nói gì?")
    result = packet([first], [source(parents, 11, "t1"), source(parents, 16, "t1")],
                    query=f"Điều {named_article} Quy chế đào tạo K51 nói gì?")
    expected = {"Điều 11": "candidate", "Điều 16": "candidate"}
    expected[f"Điều {named_article}"] = "target"
    assert roles(result["units"][0]) == expected


def test_single_logical_multicohort_task_can_use_global_fallback(parents):
    first = task("t1", "So sánh quy định đó giữa K50 và K51?")
    first["cohorts"] = ["K50", "K51"]
    citations = [source(parents, article, "t1", cohort) for cohort in ["K50", "K51"] for article in [11, 16]]
    result = packet([first], citations, query="So sánh Điều 11 Quy chế đào tạo K50 và K51?")
    assert len(result["units"]) == 2
    assert all(roles(u) == {"Điều 11": "target", "Điều 16": "candidate"} for u in result["units"])


def test_unplanned_retrieval_preserves_explicit_target_fallback(parents):
    result = build_authorized_evidence_packet(query="Điều 11 Quy chế đào tạo K51 nói gì?", retrieval_result={
        "effective_query": "Quy định này nói gì?", "citations": [source(parents, 11, "unused"), source(parents, 16, "unused")],
    }, selected_citations=None, fallback_cohort="K51", max_context_chars=160000)
    assert result["units"][0]["task_id"] == "_unplanned"
    assert roles(result["units"][0]) == {"Điều 11": "target", "Điều 16": "candidate"}


def test_local_named_article_is_not_overridden_by_single_query_fallback(parents):
    result = packet([task("t1", "Điều 11 Quy chế đào tạo K51 nói gì?")],
                    [source(parents, 11, "t1"), source(parents, 16, "t1")],
                    query="Điều 16 Quy chế đào tạo K51 nói gì?")
    assert roles(result["units"][0]) == {"Điều 11": "target", "Điều 16": "candidate"}


def test_multiple_articles_in_one_task_do_not_make_one_retrieved_article_the_unique_target(parents):
    result = packet([task("t1", "Điều 11 và Điều 16 Quy chế đào tạo K51 nói gì?")], [source(parents, 11, "t1")])
    assert roles(result["units"][0]) == {"Điều 11": "candidate"}


def test_same_article_number_in_distinct_documents_stays_ambiguous(parents):
    first = source(parents, 11, "t1")
    other = {**first, "source_parent_id": "other-document-article-11", "chunk_id": "other-document-article-11",
             "document_identity": "Một quy định khác", "content": "Điều 11 của văn bản khác."}
    result = packet([task("t1", "Điều 11 quy định gì trong K51?")], [first, other])
    assert all(s["role"] == "candidate" for s in result["units"][0]["primary_evidence"])


def test_missing_canonical_identity_does_not_prove_two_sources_are_one_document():
    from src.generation.prompt_builder import _assign_evidence_roles

    sources = [{"article_label": "Điều 11", "content": "First source"},
               {"article_label": "Điều 11", "content": "Second source"}]
    result = _assign_evidence_roles(sources, unit_question="Điều 11 nói gì?", original_query="Điều 11 nói gì?")
    assert all(s["role"] == "candidate" for s in result)


def test_single_missing_identity_stays_candidate_in_helper_and_packet():
    from src.generation.prompt_builder import _assign_evidence_roles

    citation = {"article_label": "Điều 11", "content": "Nguồn chưa có identity", "cohort": "K51",
                "supports_task_ids": ["t1"]}
    direct = _assign_evidence_roles([citation], unit_question="Điều 11 nói gì?", original_query="Điều 11 nói gì?")
    assert direct[0]["role"] == "candidate"
    result = packet([task("t1", "Điều 11 nói gì trong K51?")], [citation])
    source_item = result["units"][0]["primary_evidence"][0]
    assert source_item["source_id"] == "source-1"  # Display fallback remains available.
    assert source_item["role"] == "candidate" and source_item["content"] == citation["content"]
    assert "_has_source_identity" not in source_item


def test_blank_identity_cannot_promote_the_only_article():
    citation = {"source_parent_id": "  ", "article_label": "Điều 11", "content": "Nguồn chưa có identity",
                "cohort": "K51", "supports_task_ids": ["t1"]}
    result = packet([task("t1", "Điều 11 nói gì trong K51?")], [citation])
    assert result["units"][0]["primary_evidence"][0]["role"] == "candidate"


def test_same_source_id_from_different_applicable_editions_remains_ambiguous(parents):
    first = source(parents, 11, "t1")
    inherited = {**first, "cohort": "K50", "source_cohort": "K50", "applicable_cohorts": ["K51"],
                 "applicability_validated": True, "content": "Điều 11 được in trong một khóa khác."}
    result = packet([task("t1", "Điều 11 quy định gì trong K51?")], [first, inherited])
    assert len(result["units"][0]["primary_evidence"]) == 2
    assert all(s["role"] == "candidate" for s in result["units"][0]["primary_evidence"])


def test_missing_requested_article_does_not_promote_a_different_article(parents):
    result = packet([task("t1", "Điều 11 Quy chế đào tạo K51 nói gì?")], [source(parents, 16, "t1")],
                    query="Điều 11 và Điều 16 Quy chế đào tạo K51 nói gì?")
    assert roles(result["units"][0]) == {"Điều 16": "candidate"}


def test_clarification_sibling_cannot_supply_anonymous_tasks_target(parents):
    tasks = [task("t1", "K51 điểm trung bình được tính thế nào?"), task("t2", "Điều 16 của văn bản nào?", mode="clarify")]
    result = packet(tasks, [source(parents, 11, "t1"), source(parents, 16, "t1")])
    assert roles(result["units"][0]) == {"Điều 11": "candidate", "Điều 16": "candidate"}


def test_one_fused_parent_can_be_target_for_one_task_and_candidate_for_another(parents):
    tasks = [task("t1", "Điều 11 Quy chế đào tạo K51 nói gì?"), task("t2", "K51 cách tính điểm trung bình?")]
    merged = PlanExecutor._merge_task_citations([source(parents, 11, "t1"), source(parents, 11, "t2")])
    assert len(merged) == 1
    result = packet(tasks, merged)
    assert roles(result["units"][0]) == {"Điều 11": "target"}
    assert roles(result["units"][1]) == {"Điều 11": "candidate"}
    assert result["units"][0]["primary_evidence"][0]["source_ref"] == result["units"][1]["primary_evidence"][0]["source_ref"]


def test_two_representations_of_one_canonical_article_are_not_two_documents(parents):
    first = source(parents, 11, "t1")
    variant = {**first, "content": "Một biểu diễn khác của cùng nguồn Điều 11."}
    result = packet([task("t1", "Điều 11 Quy chế đào tạo K51 nói gì?")], [first, variant])
    assert len(result["units"][0]["primary_evidence"]) == 2
    assert all(s["role"] == "target" for s in result["units"][0]["primary_evidence"])


def test_budget_protects_each_tasks_own_target_not_a_siblings_article(parents):
    tasks = [task("t1", "Điều 11 Quy chế đào tạo K51 nói gì?"), task("t2", "Điều 16 Quy chế đào tạo K51 nói gì?")]
    first = {**source(parents, 11, "t1"), "content": "Căn cứ Điều 11. " * 300 + "TARGET_11_TAIL"}
    distraction = {**source(parents, 16, "t1"), "content": "Nguồn chỉ liên quan một phần. " * 2000}
    second = {**source(parents, 16, "t2"), "content": "Căn cứ Điều 16. " * 300 + "TARGET_16_TAIL"}
    result = packet(tasks, [first, distraction, second], budget=14000)
    units = {u["task_id"]: u for u in result["units"]}
    assert "TARGET_11_TAIL" in units["t1"]["primary_evidence"][0]["content"]
    assert "TARGET_16_TAIL" in units["t2"]["primary_evidence"][0]["content"]
    assert sum(len(s["content"]) for u in result["units"] for s in u["primary_evidence"]) <= 14000 * 3 // 4


@pytest.mark.parametrize("streaming", [False, True])
def test_real_normalizer_executor_and_composer_keep_local_targets(parents, monkeypatch, streaming):
    raw_tasks = [task("t1", "Điều 11 Quy chế đào tạo K51 tính điểm trung bình thế nào?"),
                 task("t2", "Điều 16 Quy chế đào tạo K51 quy định nghỉ học thế nào?")]
    query = " và ".join(t["question"] for t in raw_tasks)
    plan, errors = normalize_query_plan({"context_mode": "standalone", "out_of_domain": False, "tasks": raw_tasks},
                                      query=query, selected_cohort="K51")
    assert not errors

    def retrieval(**kwargs):
        articles = [11, 16] if "Điều 11" in kwargs["query"] else [16]
        citations = [source(parents, article, "unused") for article in articles]
        items = [{**parents[c["source_parent_id"]], "chunk_id": c["source_parent_id"]} for c in citations]
        return {"retrieved_items": items, "citations": citations}

    monkeypatch.setattr("src.generation.plan_executor.run_hybrid_retrieval_pipeline", retrieval)
    executor = PlanExecutor(router=SimpleNamespace(plan=lambda *a, **kw: plan),
        slang_normalizer=SimpleNamespace(normalize_for_retrieval=lambda q: q),
        catalogs=StructuredCatalogs([], [], [], [], [], []), parent_sources_by_id=parents,
        top_k=5, public_source_limit=10, graph=SimpleNamespace(expand_context=lambda *a, **kw: []))
    result = executor.run(query=query, cohort="K51", chat_history=[])
    prompts = []

    class Composer:
        def generate(self, prompt):
            prompts.append(prompt)
            return {"ok": True, "text": "Trả lời từ hai nguồn riêng.", "model_used": "fake", "usage": {}}

        def generate_stream(self, prompt):
            prompts.append(prompt)
            yield "Trả lời từ hai nguồn riêng."
            return {"model_used": "fake", "usage": {}}

    pipeline = AnswerPipeline(llm_client=Composer())
    pipeline._run_retrieval = lambda *a, **kw: result
    output = list(pipeline.answer_stream(query, cohort="K51"))[-1] if streaming else pipeline.answer(query, cohort="K51")
    assert output["status"] == "answered" and len(prompts) == 1
    actual, _ = json.JSONDecoder().raw_decode(prompts[0].split("\nAUTHORIZED_EVIDENCE_BY_UNIT\n", 1)[1])
    units = {u["task_id"]: u for u in actual["units"]}
    assert roles(units["t1"]) == {"Điều 11": "target", "Điều 16": "candidate"}
    assert roles(units["t2"]) == {"Điều 16": "target"}


def test_role_change_does_not_modify_composer_instructions(parents):
    query = "Điều 11 Quy chế đào tạo K51 nói gì?"
    _, context = build_answer_prompt_bundle(query, {"citations": [source(parents, 11, "t1")]}, cohort="K51")
    result = json.loads(context)
    assert result["answer_prompt_version"] == "student-handbook-answer-v3.35-student-scope"


def test_real_structured_and_rag_same_parent_keep_role_fact_lock_and_source_context(parents, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    tables = json.loads((root / "data/processed/tables/structured_tables_registry.json").read_text(encoding="utf-8"))
    first = {**task("t1", "K51 học phần còn lại được 6,1/10 đổi thành điểm chữ gì?", mode="structured"),
             "intent": "direct_value", "lookup_type": "scoring",
             "slots": {"operation": "grade_10_to_letter", "score_or_grade": "6.1/10", "course_scope": "remaining"},
             "slot_spans": {"score_or_grade": "6,1/10", "course_scope": "học phần còn lại"}}
    second = task("t2", "Điều 10 Quy chế đào tạo K51 quy định điểm học lại thế nào?")
    query = first["question"] + " và " + second["question"]
    plan, errors = normalize_query_plan({"context_mode": "standalone", "out_of_domain": False, "tasks": [first, second]},
                                      query=query, selected_cohort="K51")
    assert not errors
    citation = source(parents, 10, "unused")
    item = {**parents[citation["source_parent_id"]], "chunk_id": citation["source_parent_id"]}
    monkeypatch.setattr("src.generation.plan_executor.run_hybrid_retrieval_pipeline",
                        lambda **kw: {"retrieved_items": [item], "citations": [citation]})
    executor = PlanExecutor(router=SimpleNamespace(plan=lambda *a, **kw: plan),
        slang_normalizer=SimpleNamespace(normalize_for_retrieval=lambda q: q),
        catalogs=StructuredCatalogs([], [], [], [], tables, []), parent_sources_by_id=parents,
        top_k=5, public_source_limit=10, graph=SimpleNamespace(expand_context=lambda *a, **kw: []))
    result = executor.run(query=query, cohort="K51", chat_history=[])
    _, context = build_answer_prompt_bundle(query, result, result["evidence_citations"], cohort="K51")
    units = {u["task_id"]: u for u in json.loads(context)["units"]}
    structured = units["t1"]["primary_evidence"][0]
    regulation = units["t2"]["primary_evidence"][0]
    assert structured["source_id"] == regulation["source_id"]
    assert structured["role"] == "candidate" and regulation["role"] == "target"
    assert structured["resolved_result"]["input_value"] == 6.1 and structured["source_context"]
    assert "resolved_result" not in regulation
    assert regulation["content"] == citation["content"]
