"""Conditional score rows through real offline execution and composition."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.generation.answer_pipeline import AnswerPipeline
from src.generation.plan_executor import PlanExecutor, StructuredCatalogs
from src.generation.prompt_builder import build_authorized_evidence_packet
from src.generation.structured_result_presenter import build_structured_results
from src.retrieval.core.citation_builder import scoped_resolved_rows
from src.retrieval.core.query_plan import normalize_query_plan
from src.retrieval.core.slang_normalizer import SlangNormalizer


@pytest.fixture(scope="module")
def source_data():
    base = Path(__file__).resolve().parents[1] / "data/processed"
    tables = json.loads((base / "tables/structured_tables_registry.json").read_text(encoding="utf-8"))
    parents = {p["_id"]: p for p in json.loads((base / "chunks/all_docstore_items.json").read_text(encoding="utf-8"))}
    return tables, parents


def score_task(score="5,2/10", scope="graded", cohort="K51"):
    phrase = {"graded": "Môn tính GPA", "foundation": "Môn nền tảng", "remaining": "Học phần còn lại"}[scope]
    question = f"{cohort} {phrase} được {score} thì điểm chữ là gì?"
    return {"question": question, "mode": "structured", "intent": "direct_value", "lookup_type": "scoring",
            "cohorts": [cohort], "slots": {"operation": "grade_10_to_letter", "course_scope": scope, "score_or_grade": score},
            "slot_spans": {"course_scope": phrase, "score_or_grade": score}}


def execute(source_data, tasks):
    tables, parents = source_data
    question = " ".join(t["question"] for t in tasks)
    cohort = tasks[0]["cohorts"][0]
    plan, errors = normalize_query_plan({"schema_version": "v1", "context_mode": "standalone",
        "normalized_query": question, "tasks": copy.deepcopy(tasks), "out_of_domain": False},
        query=question, selected_cohort=cohort)
    assert errors == []
    executor = PlanExecutor(router=SimpleNamespace(plan=lambda *a, **kw: plan),
        slang_normalizer=SlangNormalizer(), catalogs=StructuredCatalogs([], [], [], [], tables, []),
        parent_sources_by_id=parents, top_k=5, public_source_limit=10,
        graph=SimpleNamespace(expand_context=lambda *a, **kw: []))
    return question, executor.run(query=question, cohort=cohort, chat_history=[])


def packet(question, result, budget=160000):
    return build_authorized_evidence_packet(query=question, retrieval_result=result,
        selected_citations=result["evidence_citations"], fallback_cohort="K51", max_context_chars=budget)


@pytest.mark.parametrize("score,letter", [
    ("3,6/10", "F+"), ("4,5/10", "D"), ("5,2/10", "D+"), ("5,20/10", "D+"),
    ("5,4/10", "D+"), ("5,5/10", "C"), ("6,2/10", "C"), ("6,3/10", "C+"),
    ("7,6/10", "B"), ("8,0/10", "B+"), ("9,0/10", "A"),
])
def test_unresolved_scope_exposes_only_the_computed_rows_and_keeps_full_ui_tables(source_data, score, letter):
    question, result = execute(source_data, [score_task(score)])
    original = copy.deepcopy(result)
    composed = packet(question, result)
    unit = composed["units"][0]
    source = unit["primary_evidence"][0]
    assert unit["resolution_status"] == "evidence_only"
    assert "resolved_result" not in source
    assert len(source["resolved_rows"]) == 2
    assert {r["row"]["letter_grade"] for r in source["resolved_rows"]} == {letter}
    assert {r["table_id"] for r in source["resolved_rows"]} == {
        "K51_QuyCheDaoTao_Chuong3_Dieu10_grade_scale_foundation",
        "K51_QuyCheDaoTao_Chuong3_Dieu10_grade_scale_remaining"}
    assert all(r["applicability"] for r in source["resolved_rows"])
    assert json.loads(source["content"]) == {"resolved_rows": source["resolved_rows"]}
    # The amended parent remains available for policy conditions and source display.
    assert source["source_context"] and source["source_id"] in source_data[1]
    assert [len(table["rows"]) for table in build_structured_results(result["structured_result"])] == [9, 9]
    assert result == original
    if letter == "D+":
        assert [r["row"]["status"] for r in source["resolved_rows"]] == ["Đạt", "Không đạt"]


@pytest.mark.parametrize("scope", ["foundation", "remaining"])
def test_known_scope_retains_its_original_fact_lock(source_data, scope):
    question, result = execute(source_data, [score_task(scope=scope)])
    source = packet(question, result)["units"][0]["primary_evidence"][0]
    assert "resolved_rows" not in source
    assert source["resolved_result"]["result"][0]["row"]["letter_grade"] == "D+"
    assert source["resolved_result"]["result"][0]["row"]["status"] == ("Đạt" if scope == "foundation" else "Không đạt")


@pytest.mark.parametrize("scores", [("5,2/10", "6,2/10"), ("6,2/10", "5,2/10")])
def test_two_ambiguous_scores_in_same_parent_do_not_share_computed_rows(source_data, scores):
    question, result = execute(source_data, [score_task(s) for s in scores])
    units = packet(question, result)["units"]
    assert len(units) == 2
    for unit, value in zip(units, scores):
        assert len(unit["primary_evidence"]) == 1
        source = unit["primary_evidence"][0]
        assert source["supports_task_ids"] == [unit["task_id"]]
        assert {r["row"]["letter_grade"] for r in source["resolved_rows"]} == ({"D+"} if value.startswith("5") else {"C"})


def test_wrong_scale_keeps_reference_evidence_without_computed_rows(source_data):
    question, result = execute(source_data, [score_task("3,6/4")])
    source = packet(question, result)["units"][0]["primary_evidence"][0]
    assert "resolved_rows" not in source and "resolved_result" not in source
    assert "tables" in json.loads(source["content"])


def test_small_budget_does_not_bypass_cap_with_explicit_conditional_rows(source_data):
    question, result = execute(source_data, [score_task()])
    source = packet(question, result, budget=80)["units"][0]["primary_evidence"][0]
    assert "resolved_rows" not in source
    assert len(source["content"]) + len(source.get("source_context", "")) <= 60


def test_scoped_rows_do_not_leak_to_rag_or_other_execution_cohort(source_data):
    question, result = execute(source_data, [score_task()])
    citation = copy.deepcopy(result["evidence_citations"][0])
    citation.update(applicable_cohorts=["K51", "K50"], applicability_validated=True,
                    supports_task_ids=["t1", "t2", "t3"])
    result["query_plan"]["tasks"] += [
        {"id": "t2", "question": "Quy định học lại", "mode": "rag", "cohorts": ["K51"]},
        {"id": "t3", "question": "Điểm K50", "mode": "structured", "cohorts": ["K50"]}]
    result["evidence_citations"] = [citation]
    units = packet(question, result)["units"]
    assert units[0]["primary_evidence"][0]["resolved_rows"]
    assert "resolved_rows" not in units[1]["primary_evidence"][0]
    assert units[1]["primary_evidence"][0]["content"] == citation["parent_content"].strip()
    assert units[2]["primary_evidence"] == []


@pytest.mark.parametrize("fault", ["rag", "partial", "wrong_id", "empty", "non_object"])
def test_incomplete_or_untrusted_groups_do_not_become_explicit_resolutions(fault):
    payload = {"tables": [{"table_id": "scope", "resolved_rows": [{"table_id": "scope", "row": {"result": "R"}}]}]}
    citation = {"evidence_kind": "structured_result"}
    if fault == "rag":
        citation["evidence_kind"] = "regulation"
    elif fault == "partial":
        payload["tables"].append({"table_id": "unresolved", "rows": [{"result": "S"}]})
    elif fault == "wrong_id":
        payload["tables"][0]["resolved_rows"][0]["table_id"] = "different"
    elif fault == "empty":
        payload["tables"][0]["resolved_rows"][0]["row"] = {}
    else:
        payload = [payload]
    citation["content"] = json.dumps(payload)
    assert scoped_resolved_rows(citation) == []


def compose(question, result, streaming, inspect_packet):
    prompts = []
    def answer_from_prompt(prompt):
        prompts.append(prompt)
        context, _ = json.JSONDecoder().raw_decode(prompt.split("\nAUTHORIZED_EVIDENCE_BY_UNIT\n", 1)[1])
        return inspect_packet(context)
    class Composer:
        def generate(self, prompt):
            return {"ok": True, "text": answer_from_prompt(prompt), "model_used": "fake", "usage": {}}
        def generate_stream(self, prompt):
            yield answer_from_prompt(prompt)
            return {"model_used": "fake", "usage": {}}
    pipeline = AnswerPipeline(llm_client=Composer())
    pipeline._run_retrieval = lambda *a, **kw: result
    if streaming:
        events = list(pipeline.answer_stream(question, cohort="K51"))
        assert events[-1]["status"] == "answered"
        answer = "".join(e.get("text", "") for e in events if e["type"] == "token")
        metadata = [e for e in events if e["type"] == "metadata"][-1]
        assert metadata["llm_called"] is True and metadata["structured_results"]
    else:
        response = pipeline.answer(question, cohort="K51")
        answer = response["answer"]
        assert response["llm_called"] is True and response["status"] == "answered"
        assert response["structured_results"]
    assert len(prompts) == 1
    return answer


@pytest.mark.parametrize("streaming", [False, True])
def test_conditional_grade_rows_reach_composer_sync_and_sse(source_data, streaming):
    question, result = execute(source_data, [score_task()])
    def inspect(context):
        unit = context["units"][0]
        source = unit["primary_evidence"][0]
        assert unit["resolution_status"] == "evidence_only"
        assert "resolved_result" not in source
        assert [item["row"]["letter_grade"] for item in source["resolved_rows"]] == ["D+", "D+"]
        assert source["source_context"]
        return "D+: nền tảng Đạt, học phần còn lại Không đạt."
    assert compose(question, result, streaming, inspect) == "D+: nền tảng Đạt, học phần còn lại Không đạt."


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("intent", ["direct_value", "open_question"])
@pytest.mark.parametrize("operation", ["grade_10_to_letter", "pass_threshold"])
def test_graduation_condition_survives_normalization_and_reaches_composer(source_data, streaming, intent, operation):
    question = "K51 Môn tính GPA được 5,2/10; nếu là học phần tốt nghiệp thì có cần làm lại không?"
    planned = score_task()
    planned.update(question=question, intent=intent)
    planned["slots"]["operation"] = operation
    question, result = execute(source_data, [planned])
    # Scoring normalizes unsupported intents to direct_value: that label alone
    # never proves that the student asked only for a numeric/table value.
    assert result["query_plan"]["tasks"][0]["intent"] == "direct_value"
    def inspect(context):
        unit = context["units"][0]
        assert "học phần tốt nghiệp" in unit["question"]
        source = unit["primary_evidence"][0]
        assert {item["row"]["letter_grade"] for item in source["resolved_rows"]} == {"D+"}
        assert "dưới C" in source["source_context"] and "phải thực hiện lại" in source["source_context"]
        return "Học phần tốt nghiệp dưới C phải thực hiện lại; giá trị tra bảng là D+."
    answer = compose(question, result, streaming, inspect)
    assert "phải thực hiện lại" in answer


@pytest.mark.parametrize("score,letter", [("4,5/10", "D"), ("5,5/10", "C"), ("6,3/10", "C+"), ("8,0/10", "B+")])
def test_composer_receives_catalog_results_for_other_values(source_data, score, letter):
    question, result = execute(source_data, [score_task(score)])
    def inspect(context):
        rows = context["units"][0]["primary_evidence"][0]["resolved_rows"]
        assert {item["row"]["letter_grade"] for item in rows} == {letter}
        return f"Điểm chữ {letter}."
    assert compose(question, result, False, inspect) == f"Điểm chữ {letter}."


def test_composer_receives_two_scores_in_separate_units(source_data):
    question, result = execute(source_data, [score_task("5,2/10"), score_task("6,2/10")])
    def inspect(context):
        units = context["units"]
        assert len(units) == 2
        for unit, letter in zip(units, ("D+", "C")):
            assert len(unit["primary_evidence"]) == 1
            assert {item["row"]["letter_grade"] for item in unit["primary_evidence"][0]["resolved_rows"]} == {letter}
        return "Môn 5,2/10 là D+; môn 6,2/10 là C."
    assert compose(question, result, False, inspect) == "Môn 5,2/10 là D+; môn 6,2/10 là C."
