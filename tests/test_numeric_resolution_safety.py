"""Typed score inputs and completed equivalencies, using real source tables."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.common.score import parse_score
from src.generation.answer_pipeline import AnswerPipeline
from src.generation.plan_executor import PlanExecutor, StructuredCatalogs
from src.generation.prompt_builder import build_authorized_evidence_packet
from src.retrieval.core.query_plan import normalize_query_plan
from src.retrieval.core.foreign_language_lookup import foreign_language_lookup
from src.retrieval.core.scholarship_lookup import scholarship_table_lookup
from src.retrieval.core.structured_dispatcher import resolve_structured_task
from src.retrieval.core.structured_lookup import in_range, structured_lookup_from_slots


@pytest.fixture(scope="module")
def tables():
    root = Path(__file__).resolve().parents[1]
    return json.loads((root / "data/processed/tables/structured_tables_registry.json").read_text(encoding="utf-8"))


def normalized_task(tool, slots, cohort="K51", task_id="t1"):
    question = f"{cohort}: " + "; ".join(str(v) for v in slots.values()) + " tương ứng kết quả nào?"
    spans = {k: str(v) for k, v in slots.items()}
    task = {"id": task_id, "question": question, "mode": "structured", "intent": "direct_value",
            "lookup_type": tool, "cohorts": [cohort], "slots": slots, "slot_spans": spans}
    plan, errors = normalize_query_plan({"context_mode": "standalone", "out_of_domain": False, "tasks": [task]},
                                       query=question, selected_cohort=cohort)
    assert not errors and plan["tasks"][0]["mode"] == "structured"
    return question, plan["tasks"][0]


def resolve(tables, tool, slots, cohort="K51"):
    question, task = normalized_task(tool, slots, cohort)
    resolution = resolve_structured_task(task, query=question, cohort=cohort, formula_rules=[],
        office_directory=[], student_service_directory=[], student_faculty_profiles=[],
        structured_tables_registry=tables, program_directory=[])
    assert resolution is not None
    return resolution


@pytest.mark.parametrize("cohort", ["K48-K49", "K50", "K51"])
@pytest.mark.parametrize("operation,value", [
    ("academic_classification", "-3.6/4"), ("academic_classification", "4.1/4"),
    ("conduct_classification", "-80/100"), ("conduct_classification", "101/100"),
    ("grade_10_to_letter", "-5.2/10"), ("grade_10_to_letter", "10.1/10"),
])
def test_invalid_scoring_input_never_locks_a_valid_result(tables, cohort, operation, value):
    resolution = resolve(tables, "scoring", {"operation": operation, "score_or_grade": value}, cohort)
    assert resolution.resolution_status == "evidence_only"
    assert not resolution.result.get("resolved_result")
    assert "resolved_rows" not in json.dumps(resolution.result)


@pytest.mark.parametrize("operation,value,label", [
    ("academic_classification", "+3,6/4", "Xuất sắc"),
    ("academic_classification", "0/4", "Kém"),
    ("conduct_classification", "+80/100", "Tốt"),
    ("conduct_classification", "0/100", "Kém"),
])
def test_valid_boundaries_and_positive_sign_keep_classification(tables, operation, value, label):
    resolution = resolve(tables, "scoring", {"operation": operation, "score_or_grade": value})
    locked = resolution.result["resolved_result"]
    assert locked["input_value"] == float(parse_score(value).value)
    assert locked["result"]["label"] == label


@pytest.mark.parametrize("cohort", ["K48-K49", "K50"])
@pytest.mark.parametrize("value", ["-3.0", "-3,6", "-0.1", "9.0"])
def test_scholarship_invalid_score_does_not_become_a_positive_lock(tables, cohort, value):
    resolution = resolve(tables, "scholarship_classification",
                         {"aspect": "classification", "score_or_label": value}, cohort)
    assert resolution.resolution_status == "evidence_only"
    assert not resolution.result.get("resolved_result")


@pytest.mark.parametrize("value,expected", [("+3.0", "Khá"), ("Giỏi", "Giỏi")])
def test_scholarship_valid_scores_and_labels_stay_supported(tables, value, expected):
    resolution = resolve(tables, "scholarship_classification",
                         {"aspect": "classification", "score_or_label": value}, "K50")
    assert resolution.result["resolved_result"]["result"]["label"] == expected


@pytest.mark.parametrize("certificate,value", [
    ("IELTS", "-5.5"), ("IELTS", "7.0"), ("IELTS", "5.5/10"),
    ("TOPIK II", "-150"), ("JLPT", "N30"), ("Cambridge", "B10"),
])
def test_one_certificate_row_is_not_a_completed_equivalency(tables, certificate, value):
    resolution = resolve(tables, "foreign_language", {"certificate_or_language": certificate, "score_or_level": value})
    assert resolution.resolution_status == "evidence_only"
    assert not resolution.result.get("resolved_result")
    assert resolution.result["display_rows"]  # Reference evidence/UI is still available.


@pytest.mark.parametrize("certificate,value,expected", [
    ("IELTS", "+5,5", "bac_4"), ("IELTS", "4,5", "bac_3"),
    ("TOPIK II", "150", "bac_4"), ("JLPT", "N3", "bac_4"),
    ("TOEIC", "bậc 4", "bac_4"),
])
def test_completed_equivalencies_and_requested_reference_columns_keep_lock(tables, certificate, value, expected):
    resolution = resolve(tables, "foreign_language", {"certificate_or_language": certificate, "score_or_level": value})
    assert resolution.result["resolved_result"]["result"]["matched_level"] == expected


def test_complete_components_do_not_claim_a_level_not_computed_by_resolver(tables):
    slots = {"certificate_or_language": "TOEIC", "listening_score": 410, "reading_score": 400,
             "speaking_score": 170, "writing_score": 160}
    resolution = resolve(tables, "foreign_language", slots)
    assert resolution.resolution_status == "evidence_only"
    assert resolution.result["display_rows"]
    assert not resolution.result.get("resolved_result")


def test_two_reference_columns_keep_verified_row_without_claiming_a_personal_level(tables):
    question = "K51 TOEFL iBT bậc 3 và bậc 4 yêu cầu bao nhiêu điểm?"
    task = {"lookup_type": "foreign_language", "intent": "direct_value",
            "slots": {"certificate_or_language": "TOEFL iBT", "score_or_level": ["bậc 3", "bậc 4"]},
            "slot_spans": {"certificate_or_language": "TOEFL iBT", "score_or_level": ["bậc 3", "bậc 4"]}}
    resolution = resolve_structured_task(task, query=question, cohort="K51", formula_rules=[],
        office_directory=[], student_service_directory=[], student_faculty_profiles=[],
        structured_tables_registry=tables, program_directory=[])
    row = resolution.result["resolved_result"]["result"]
    assert row["matched_level"] is None
    assert row["equivalent_level_3"] == "30 - 45" and row["equivalent_level_4"] == "46 - 93"


@pytest.mark.parametrize("value", ["-3.0", "-3.6", "3.0/4", "2.56-3.35"])
def test_scholarship_leaf_does_not_extract_positive_operands_from_invalid_inputs(tables, value):
    assert scholarship_table_lookup("query", tables, "K50", slots={"score_or_label": value}) is None


@pytest.mark.parametrize("value", ["-5.5", "5.5/10", "4.0-5.0"])
def test_foreign_leaf_does_not_extract_personal_score_from_sign_fraction_or_range(tables, value):
    result = foreign_language_lookup("query", tables, "K51",
                                    slots={"certificate_or_language": "IELTS", "score_or_level": value})
    assert result["result"]["matched_level"] is None
    assert "matched_value" not in result["result"]


@pytest.mark.parametrize("values", [[5.5, -5.5], [-5.5, 5.5], [5.5, "N30"], [5.5, "5.5/10"], [5.5, 6.0]])
def test_foreign_mixed_list_never_collapses_to_one_valid_scalar(tables, values):
    result = foreign_language_lookup("query", tables, "K51",
                                    slots={"certificate_or_language": "IELTS", "score_or_level": values})
    assert result["result"]["matched_level"] is None
    assert "matched_value" not in result["result"]


@pytest.mark.parametrize("text,value", [("4.0-5.0", 4.5), ("4,0 - 5,0", 4.5), ("3.2 - dưới 3.6", 3.5)])
def test_source_range_hyphens_are_not_numeric_input_signs(text, value):
    assert in_range(value, text)
    assert not in_range(-value, text)


@pytest.mark.parametrize("operation,value", [("academic_classification", "-3.6/4"),
                                           ("conduct_classification", "-80/100")])
def test_legacy_slot_interface_also_rejects_negative_input(operation, value):
    table = {"table_id": operation, "rows": [{"range": "0 - 100", "label": "Not a valid negative result"}]}
    assert structured_lookup_from_slots({"operation": operation, "score_or_grade": value}, [table]) is None


@pytest.mark.parametrize("values", [[5.2, -5.2], [-5.2, 5.2]])
def test_opposite_signed_list_inputs_cannot_collapse_into_conditional_rows(tables, values):
    question = "K51 5.2 và -5.2 đổi sang điểm chữ?"
    task = {"lookup_type": "scoring", "intent": "direct_value",
            "slots": {"operation": "grade_10_to_letter", "score_or_grade": values},
            "slot_spans": {"score_or_grade": ["5.2", "-5.2"]}}
    resolution = resolve_structured_task(task, query=question, cohort="K51", formula_rules=[],
        office_directory=[], student_service_directory=[], student_faculty_profiles=[],
        structured_tables_registry=tables, program_directory=[])
    assert not resolution.result.get("resolved_result")
    assert "resolved_rows" not in json.dumps(resolution.result)


@pytest.mark.parametrize("streaming", [False, True])
def test_invalid_numeric_task_cannot_lock_while_valid_sibling_still_reaches_composer(tables, streaming):
    tasks = [normalized_task("scoring", {"operation": "academic_classification", "score_or_grade": value})[1]
             for value in ("-3.6/4", "+3.6/4")]
    for i, task in enumerate(tasks, 1):
        task["id"] = f"t{i}"
    query = " và ".join(t["question"] for t in tasks)
    executor = PlanExecutor(router=SimpleNamespace(plan=lambda *a, **kw: {"tasks": tasks, "context_mode": "standalone"}),
        slang_normalizer=SimpleNamespace(normalize_for_retrieval=lambda q: q),
        catalogs=StructuredCatalogs([], [], [], [], tables, []), parent_sources_by_id={},
        top_k=5, public_source_limit=10, graph=SimpleNamespace(expand_context=lambda *a, **kw: []))
    result = executor.run(query=query, cohort="K51", chat_history=[])
    packet = build_authorized_evidence_packet(query=query, retrieval_result=result,
        selected_citations=result["evidence_citations"], fallback_cohort="K51", max_context_chars=160000)
    invalid, valid = packet["units"]
    assert all("resolved_result" not in s for s in invalid["primary_evidence"])
    assert valid["primary_evidence"][0]["resolved_result"]["input_value"] == 3.6
    prompts = []

    class Composer:
        def generate(self, prompt):
            prompts.append(prompt)
            return {"ok": True, "text": "Kết quả từ evidence.", "model_used": "fake", "usage": {}}

        def generate_stream(self, prompt):
            prompts.append(prompt)
            yield "Kết quả từ evidence."
            return {"model_used": "fake", "usage": {}}

    pipeline = AnswerPipeline(llm_client=Composer())
    pipeline._run_retrieval = lambda *a, **kw: result
    output = list(pipeline.answer_stream(query, cohort="K51"))[-1] if streaming else pipeline.answer(query, cohort="K51")
    assert output["status"] == "answered" and len(prompts) == 1
    actual_packet, _ = json.JSONDecoder().raw_decode(prompts[0].split("\nAUTHORIZED_EVIDENCE_BY_UNIT\n", 1)[1])
    assert all("resolved_result" not in s for s in actual_packet["units"][0]["primary_evidence"])
