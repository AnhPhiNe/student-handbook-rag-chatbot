"""Scripted plans through real offline execution; no live model/retriever."""

import copy
import json
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.common.score import grounded_score
from src.generation.plan_executor import PlanExecutor, StructuredCatalogs
from src.generation.prompt_builder import build_authorized_evidence_packet
from src.retrieval.core.query_plan import normalize_query_plan
from src.retrieval.core.slang_normalizer import SlangNormalizer


SCALE_CONTRACT_CASES = Path(__file__).resolve().parent / "fixtures/scale_contract_cases"


@lru_cache(maxsize=1)
def _catalogs():
    base = Path(__file__).resolve().parents[1] / "data/processed"

    def read(path):
        return json.loads((base / path).read_text(encoding="utf-8"))

    return StructuredCatalogs(
        formula_rules=[],
        office_directory=read("directories/student_office_profiles.json"),
        student_service_directory=read("directories/student_service_directory.json"),
        student_faculty_profiles=read("directories/student_faculty_profiles.json"),
        structured_tables_registry=read("tables/structured_tables_registry.json"),
        program_directory=read("directories/program_directory.json"),
    )


def _task(question, lookup, slots, spans, cohorts=("K50",)):
    return {"question": question, "mode": "structured", "intent": "direct_value",
            "lookup_type": lookup, "slots": slots, "slot_spans": spans,
            "cohorts": list(cohorts), "clarification_question": None}


def _score_task(question, value, span, *, scope="graded", scope_span="Môn tính GPA",
                operation="pass_threshold", cohorts=("K50",)):
    return _task(question, "scoring", {"operation": operation,
                 "score_or_grade": value, "course_scope": scope},
                 {"score_or_grade": span, "course_scope": scope_span}, cohorts)


def _run(query, tasks, *, catalogs=None, cohort="K50", grounding_context="",
         context_mode="standalone"):
    plan, errors = normalize_query_plan(
        {"schema_version": "v1", "context_mode": context_mode,
         "normalized_query": query, "standalone_query": query if context_mode == "follow_up" else None,
         "referenced_turns": [0] if context_mode == "follow_up" else [],
         "out_of_domain": False, "tasks": copy.deepcopy(tasks)},
        query=query, selected_cohort=cohort, grounding_context=grounding_context,
    )
    assert errors == []
    executor = PlanExecutor(
        router=SimpleNamespace(plan=lambda *_args, **_kwargs: copy.deepcopy(plan)),
        slang_normalizer=SlangNormalizer(), catalogs=catalogs or _catalogs(),
        parent_sources_by_id={}, top_k=5, public_source_limit=10, directory_selector=None,
        graph=SimpleNamespace(expand_context=lambda *_args, **_kwargs: []),
    )
    result = executor.run(query=query, cohort=cohort, chat_history=None)
    packet = build_authorized_evidence_packet(
        query=query, retrieval_result=result, selected_citations=result["citations"],
        fallback_cohort=cohort, max_context_chars=50000,
    )
    return result, packet


@pytest.mark.parametrize("value,span,literal,locked", [
    (3.6, "3,6/4", "3,6/4", False),
    ([3.6], ["3,6/4"], "3,6/4", False),
    (3.6, "3,6", "3,6/4", False),
    ("3,6/10", "3,6/4", "3,6/4", False),
    (4, "4", "3,6/4", False),  # Denominator is not an operand.
    (3.5, "3,6/10", "3,6/10", False),
    (3.6, "3,6/10", "3,6/10", True),
    ("3,60/10", "3,6/10", "3,6/10", True),
    (3.6, "3,6", "3,6", True),
    ("3.60", "3,60", "3,60", True),
])
def test_score_scale_normalizer_to_resolver_and_composer(value, span, literal, locked):
    query = f"Môn tính GPA em được {literal} thì có qua không?"
    task = _score_task(query, value, span)
    original = copy.deepcopy(task)
    result, packet = _run(query, [task])
    assert task == original
    evidence = result["structured_result"]
    assert bool(evidence.get("resolved_result")) is locked
    assert result["task_results"][0]["resolution_by_cohort"]["K50"] == (
        "resolved" if locked else "evidence_only")
    assert result["citations"]  # Invalid operands do not erase source evidence.
    primary = [item for unit in packet["units"] for item in unit["primary_evidence"]]
    assert bool(any(item.get("resolved_result") for item in primary)) is locked


@pytest.mark.parametrize("span", ["3,6/4", "3,6"])
def test_wrong_scale_does_not_emit_k51_candidate_arithmetic(span):
    query = "Môn tính GPA được 3,6/4 có qua không?"
    result, packet = _run(query, [_score_task(query, 3.6, span, cohorts=("K51",))], cohort="K51")
    evidence = result["structured_result"]
    assert len(evidence["sub_lookups"]) == 2
    assert not evidence.get("resolved_result")
    assert all(not leaf.get("resolved_rows") and not leaf["result"].get("resolved_rows")
               for leaf in evidence["sub_lookups"])
    assert packet["units"][0]["resolution_status"] == "evidence_only"


@pytest.mark.parametrize("cohort", ["K48-K49", "K50", "K51"])
def test_reference_level_with_partial_scores_reaches_executor_and_composer(cohort):
    query = "TOEIC 4 kỹ năng: Nói 130, Viết 130; Nghe và Đọc cần khoảng nào cho bậc 3?"
    task = _task(query, "foreign_language", {
        "certificate_or_language": "TOEIC", "score_or_level": "bậc 3",
        "speaking_score": 130, "writing_score": 130,
    }, {"certificate_or_language": "TOEIC 4 kỹ năng", "score_or_level": "bậc 3",
        "speaking_score": "130", "writing_score": "130"}, cohorts=(cohort,))
    result, packet = _run(query, [task], cohort=cohort)
    assert result["coverage_by_task"]["t1"] == "covered"
    assert result["task_results"][0]["resolution_by_cohort"][cohort] == "evidence_only"
    assert not result["structured_result"].get("resolved_result")
    assert result["citations"]
    unit = packet["units"][0]
    assert unit["cohort"] == cohort and unit["coverage"] == "covered"
    assert unit["primary_evidence"] and unit["allowed_source_refs"]
    assert all(not evidence.get("resolved_result") for evidence in unit["primary_evidence"])
    text = json.dumps(unit, ensure_ascii=False)
    assert "TOEIC" in text and "275" in text and "399" in text


def test_personal_component_scores_without_level_still_require_missing_inputs():
    query = "TOEIC Nói 130, Viết 130 thì tương đương bậc mấy?"
    task = _task(query, "foreign_language", {
        "certificate_or_language": "TOEIC", "speaking_score": 130, "writing_score": 130,
    }, {"certificate_or_language": "TOEIC", "speaking_score": "130", "writing_score": "130"})
    result, packet = _run(query, [task])
    assert packet["units"][0]["coverage"] == "needs_clarification"
    assert not (result["structured_result"] or {}).get("resolved_result")


@pytest.mark.parametrize("literal,expected", [("3,6/4", True), ("3,6/10", False)])
def test_academic_table_checks_input_scale_not_just_value(literal, expected):
    query = f"Xếp loại học lực với GPA {literal}?"
    task = _task(query, "scoring", {"operation": "academic_classification", "score_or_grade": 3.6},
                 {"score_or_grade": literal})
    result, _ = _run(query, [task])
    assert bool(result["structured_result"].get("resolved_result")) is expected


def test_unparsed_score_phrase_is_not_resolved_by_taking_its_first_number():
    query = "Xếp loại học lực với GPA 3,6 hệ 10?"
    task = _task(query, "scoring", {"operation": "academic_classification", "score_or_grade": "3,6 hệ 10"},
                 {"score_or_grade": "3,6 hệ 10"})
    result, _ = _run(query, [task])
    assert not result["structured_result"].get("resolved_result")


def test_grounding_rejects_conflicting_short_span_and_cohort_digits():
    assert grounded_score(3.6, "3,6", "A: 3,6/4; B: 3,6/10") is None
    assert grounded_score(4, "4", "Điểm 3,6/4") is None
    assert grounded_score(50, "50", "Khóa K50") is None


def test_multi_task_paraphrase_cannot_hide_scale_in_original_query():
    full = "Môn tính GPA được 3,6/4 có qua không?"
    shortened = "Môn tính GPA được 3,6 có qua không?"
    other = "Môn tính GPA được 7,6/10 có qua không?"
    result, _ = _run(full + " " + other, [
        _score_task(shortened, 3.6, "3,6"), _score_task(other, "7,6/10", "7,6/10"),
    ])
    assert len(result["query_plan"]["tasks"]) == 2
    assert "score_or_grade" not in result["query_plan"]["tasks"][0]["slots"]
    assert not result["task_results"][0]["evidence"][0].get("resolved_result")
    assert result["task_results"][1]["evidence"][0]["resolved_result"]


def test_follow_up_history_does_not_allow_abbreviated_scale():
    query = "Môn tính GPA được 3,6 có qua không?"
    result, _ = _run(query, [_score_task(query, 3.6, "3,6")],
                     context_mode="follow_up", grounding_context="Điểm của em là 3,6/4.")
    assert "score_or_grade" not in result["query_plan"]["tasks"][0]["slots"]
    assert not result["structured_result"].get("resolved_result")


def test_same_table_different_operands_remain_paired_through_packet():
    questions = [f"Môn tính GPA môn {name} được {score}/10 ra điểm chữ gì?"
                 for name, score in [("Alpha", "3,6"), ("Beta", "7,6")]]
    tasks = [_score_task(q, value, span, operation="grade_10_to_letter")
             for q, value, span in zip(questions, [3.6, 7.6], ["3,6/10", "7,6/10"], strict=True)]
    result, packet = _run(" ".join(questions), tasks)
    assert len(result["query_plan"]["tasks"]) == 2
    for execution, expected in zip(result["task_results"], ["F+", "B"], strict=True):
        lock = execution["evidence"][0]["resolved_result"]
        assert lock["items"][0]["row"]["letter_grade"] == expected
    for unit, expected in zip(packet["units"], [3.6, 7.6], strict=True):
        locks = [item["resolved_result"] for item in unit["primary_evidence"] if item.get("resolved_result")]
        assert locks and all(lock["input_value"] == expected for lock in locks)


def test_different_tables_keep_their_own_entity_score_pair():
    questions = ["Môn nền tảng Alpha được 5,2/10 ra điểm chữ gì?",
                 "Môn còn lại Beta được 7,6/10 ra điểm chữ gì?"]
    tasks = [_score_task(q, value, span, scope=scope, scope_span=scope_span,
                         operation="grade_10_to_letter", cohorts=("K51",))
             for q, value, span, scope, scope_span in zip(questions, [5.2, 7.6],
                 ["5,2/10", "7,6/10"], ["foundation", "remaining"],
                 ["Môn nền tảng", "Môn còn lại"], strict=True)]
    result, packet = _run(" ".join(questions), tasks, cohort="K51")
    assert len(packet["units"]) == 2
    locks = [execution["evidence"][0]["resolved_result"] for execution in result["task_results"]]
    assert locks[0]["table_id"] != locks[1]["table_id"]
    assert [lock["input_value"] for lock in locks] == [5.2, 7.6]
    for unit, lock in zip(packet["units"], locks, strict=True):
        assert all(item.get("resolved_result", {}).get("table_id") == lock["table_id"]
                   for item in unit["primary_evidence"] if item.get("resolved_result"))


def test_direct_directory_list_keeps_all_entities_without_relationship_join():
    names = ["Khoa Tiếng Anh", "Khoa Tiếng Pháp"]
    query = "Email " + " và ".join(names) + "?"
    task = _task(query, "faculty", {"faculty": names, "requested_field": "email"},
                 {"faculty": names})
    task["intent"] = "contact"
    result, packet = _run(query, [task])
    assert len(result["query_plan"]["tasks"]) == 1
    records = result["structured_result"]["result"]
    assert {record["unit_name"] for record in records} == set(names)
    assert packet["units"][0]["primary_evidence"]


def test_multi_cohort_is_one_task_and_packet_locks_do_not_mix():
    query = "So sánh K50 và K51: môn nền tảng 7,6/10 ra điểm chữ gì?"
    task = _score_task(query, 7.6, "7,6/10", scope="foundation", scope_span="môn nền tảng",
                       operation="grade_10_to_letter", cohorts=("K50", "K51"))
    result, packet = _run(query, [task], cohort="K51")
    assert len(result["query_plan"]["tasks"]) == 1
    assert {unit["cohort"] for unit in packet["units"]} == {"K50", "K51"}
    for unit in packet["units"]:
        locks = [item["resolved_result"] for item in unit["primary_evidence"] if item.get("resolved_result")]
        assert locks and all(lock["cohort"] == unit["cohort"] for lock in locks)
    assert {citation["cohort"] for citation in result["citations"]} == {"K50", "K51"}


@pytest.mark.parametrize("index", range(6))
def test_scale_contracts_pass_with_their_source_backed_plan(index):
    from scripts.build_official_deterministic import CONTRACT_V10, build
    from src.evaluation.deterministic import _evaluate_outcome_case
    import time

    case = build(SCALE_CONTRACT_CASES, contract=CONTRACT_V10)[index]
    query = case["query"]
    if index in {0, 1}:
        literal = "3,60/10" if index == 0 else "3,6/4"
        tasks = [_score_task(query, literal, literal,
                            operation="grade_10_to_letter" if index == 0 else "pass_threshold")]
    elif index == 2:
        tasks = [_score_task(question, literal, literal, operation="grade_10_to_letter")
                 for question, literal in [("Môn tính GPA Alpha được 3,6/10 ra điểm chữ gì?", "3,6/10"),
                                           ("Môn tính GPA Beta được 7,6/10 ra điểm chữ gì?", "7,6/10")]]
    elif index == 3:
        tasks = [_score_task(question, literal, literal, scope=scope, scope_span=span,
                             operation="grade_10_to_letter", cohorts=("K51",))
                 for question, literal, scope, span in [
                     ("Môn nền tảng Alpha được 5,2/10 ra điểm chữ gì?", "5,2/10", "foundation", "Môn nền tảng"),
                     ("Môn còn lại Beta được 7,6/10 ra điểm chữ gì?", "7,6/10", "remaining", "Môn còn lại")]]
    elif index == 4:
        names = ["Khoa Tiếng Anh", "Khoa Tiếng Pháp"]
        task = _task(query, "faculty", {"faculty": names, "requested_field": "email"}, {"faculty": names})
        task["intent"] = "contact"
        tasks = [task]
    else:
        tasks = [_score_task(query, "7,6/10", "7,6/10", scope="foundation", scope_span="môn nền tảng",
                             operation="grade_10_to_letter", cohorts=("K50", "K51"))]
    result, _ = _run(query, tasks, cohort=case["cohort"])
    row = _evaluate_outcome_case(case, result, started=time.perf_counter())
    assert row["passed"], row
    if index == 1:
        assert not result["structured_result"].get("resolved_result")


@pytest.mark.parametrize("modes", [("structured", "structured"), ("rag", "rag"), ("structured", "rag")])
def test_execution_mode_pairs_reach_separate_composer_units(monkeypatch, modes):
    calls = []

    def retrieve(query, **kwargs):
        calls.append(query)
        cohort = kwargs["cohort"]
        parent = f"{cohort}_offline_source_{len(calls)}"
        metadata = {"cohort": cohort, "source_cohort": cohort, "source_parent_id": parent,
                    "document_id": f"handbook_{cohort}", "content_type": "article"}
        return {"retrieved_items": [{"chunk_id": parent, "content": query, "metadata": metadata}],
                "citations": [{**metadata, "chunk_id": parent, "content": query, "title": parent}]}

    monkeypatch.setattr("src.generation.plan_executor.run_hybrid_retrieval_pipeline", retrieve)
    tasks = []
    for index, mode in enumerate(modes):
        question = f"Môn tính GPA được {3 + index},6/10 ra điểm chữ gì?" if mode == "structured" else f"Quy định về chủ đề {index}?"
        task = _score_task(question, 3.6 + index, f"{3 + index},6/10", operation="grade_10_to_letter")
        if mode == "rag":
            task.update(mode="rag", intent="open_question", lookup_type=None, slots={}, slot_spans={})
        tasks.append(task)
    result, packet = _run(" ".join(task["question"] for task in tasks), tasks)
    assert len(result["task_results"]) == len(packet["units"]) == 2
    assert len(calls) == modes.count("rag")
    for unit, mode in zip(packet["units"], modes, strict=True):
        assert unit["mode"] == mode and unit["primary_evidence"]
        assert all(unit["task_id"] in item["supports_task_ids"] for item in unit["primary_evidence"])
        assert any(item.get("resolved_result") for item in unit["primary_evidence"]) is (mode == "structured")


@pytest.mark.parametrize("target_state", ["present", "missing", "wrong_cohort"])
def test_program_contact_join_through_executor_keeps_provenance(target_state):
    data = copy.deepcopy(_catalogs())
    program = next(item for item in data.program_directory if item["cohort"] == "K51")
    name = program["program_name"]
    if target_state != "present":
        target = next(item for item in data.student_faculty_profiles
                      if item["cohort"] == "K51" and item["unit_name"] == program["faculty_name"])
        data.student_faculty_profiles.remove(target)
        if target_state == "wrong_cohort":
            data.student_faculty_profiles.append({**target, "cohort": "K50"})
    query = f"Ngành {name} thuộc khoa nào và email khoa?"
    task = _task(query, "program", {"program_or_faculty": name, "requested_field": ["faculty", "email"]},
                 {"program_or_faculty": name}, ("K51",))
    result, packet = _run(query, [task], catalogs=data, cohort="K51")
    evidence = result["structured_result"]
    assert evidence["relationship_status"] == ("resolved" if target_state == "present" else "target_unavailable")
    assert len(evidence["sub_lookups"]) == (2 if target_state == "present" else 1)
    assert all(part["cohort"] == "K51" for part in evidence["sub_lookups"])
    assert len({citation["source_section"] for citation in result["citations"]}) == (
        2 if target_state == "present" else 1)
    assert packet["units"][0]["primary_evidence"]


def test_multiple_relationship_sources_clarify_instead_of_reverse_guessing():
    names = ["Công tác xã hội", "Ngôn ngữ Pháp"]
    query = "Email khoa của ngành " + " và ".join(names) + "?"
    task = _task(query, "program", {"program_or_faculty": names, "requested_field": "email"},
                 {"program_or_faculty": names}, ("K51",))
    result, packet = _run(query, [task], cohort="K51")
    assert result["needs_clarification"]
    assert not result["citations"]
    assert packet["units"][0]["coverage"] == "needs_clarification"


def test_relationship_sources_split_into_independent_tasks():
    names = ["Công tác xã hội", "Ngôn ngữ Pháp"]
    tasks = [_task(f"Email khoa của ngành {name}?", "program",
                   {"program_or_faculty": name, "requested_field": "email"},
                   {"program_or_faculty": name}, ("K51",)) for name in names]
    result, packet = _run(" ".join(task["question"] for task in tasks), tasks, cohort="K51")
    assert len(result["query_plan"]["tasks"]) == len(packet["units"]) == 2
    for execution, name, unit in zip(result["task_results"], names, packet["units"], strict=True):
        evidence = execution["evidence"][0]
        assert evidence["relationship_status"] == "resolved"
        assert evidence["result"]["source"]["program_name"] == name
        assert len(evidence["sub_lookups"]) == 2
        assert unit["primary_evidence"]


def test_office_services_one_to_many_is_a_list_not_ambiguity():
    office = next(item for item in _catalogs().office_directory
                  if item["cohort"] == "K50" and len(item.get("service_ids") or []) > 1)
    name = office["unit_name"]
    query = f"{name} hỗ trợ những dịch vụ nào?"
    task = _task(query, "office", {"office": name, "requested_field": "services"}, {"office": name})
    task["intent"] = "contact"
    result, packet = _run(query, [task])
    evidence = result["structured_result"]
    assert not result["needs_clarification"]
    assert evidence["relationship_status"] == "resolved"
    assert len(evidence["result"]["targets"]) == len(office["service_ids"]) > 1
    assert len(evidence["sub_lookups"]) == len(office["service_ids"]) + 1
    assert packet["units"][0]["primary_evidence"]


def test_more_than_three_relationship_sources_clarify_without_partial_execution():
    names = ["Công tác xã hội", "Ngôn ngữ Pháp", "Ngôn ngữ Anh", "Công nghệ thông tin"]
    tasks = [_task(f"Email khoa của ngành {name}?", "program",
                   {"program_or_faculty": name, "requested_field": "email"},
                   {"program_or_faculty": name}, ("K51",)) for name in names]
    result, packet = _run(" ".join(task["question"] for task in tasks), tasks, cohort="K51")
    assert len(result["query_plan"]["tasks"]) == 1
    assert result["execution_mode"] == "clarify"
    assert result["needs_clarification"] and not result["citations"]
    assert not packet["units"][0]["primary_evidence"]
