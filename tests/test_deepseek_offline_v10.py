"""Offline contracts for the V10 transition; no model or network calls."""

import json
import time
from functools import lru_cache
from pathlib import Path

import pytest

from src.common.score import parse_score, scores_equal
from src.evaluation.deterministic import _evaluate_outcome_case, evaluate_deterministic
from src.generation.plan_executor import PlanExecutor
from src.generation.prompt_builder import build_authorized_evidence_packet
from src.retrieval.core.catalog_relationship import (
    _declared_alias_span, _keys, identity, resolve_relationship,
)
from src.retrieval.core.citation_builder import build_citation_from_lookup
from src.retrieval.core.office_lookup import directory_result
from src.retrieval.core.structured_dispatcher import resolve_structured_task
from src.retrieval.core.query_plan import normalize_query_plan


ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def catalogs():
    base = ROOT / "data/processed"
    return {
        "tables": json.loads((base / "tables/structured_tables_registry.json").read_text(encoding="utf-8")),
        "office": json.loads((base / "directories/student_office_profiles.json").read_text(encoding="utf-8")),
        "student_service": json.loads((base / "directories/student_service_directory.json").read_text(encoding="utf-8")),
        "faculty": json.loads((base / "directories/student_faculty_profiles.json").read_text(encoding="utf-8")),
        "program": json.loads((base / "directories/program_directory.json").read_text(encoding="utf-8")),
    }


def resolve(task, cohort):
    data = catalogs()
    return resolve_structured_task(
        task, query=task["question"], cohort=cohort,
        formula_rules=[], office_directory=data["office"],
        student_service_directory=data["student_service"],
        student_faculty_profiles=data["faculty"],
        structured_tables_registry=data["tables"],
        program_directory=data["program"], directory_selector=None,
    )


def test_score_parser_preserves_scale_and_decimal_equivalence():
    assert str(parse_score("3,6/10").value) == "3.6"
    assert str(parse_score("3,6/10").scale) == "10"
    assert scores_equal("3,6/10", "3.60", expected_scale=10)
    assert scores_equal("3.6", "3,60", expected_scale=10)
    assert not scores_equal("3,6/4", "3,6", expected_scale=10)


def test_graded_k51_keeps_two_exclusive_tables_unlocked():
    task = {"lookup_type": "scoring", "question": "Môn tính GPA được 3,6/10 có qua không?",
            "intent": "direct_value", "slots": {"operation": "pass_threshold",
            "score_or_grade": "3,6/10", "course_scope": "graded"},
            "slot_spans": {"score_or_grade": "3,6/10"}, "cohorts": ["K51"]}
    resolution = resolve(task, "K51")
    assert resolution.resolution_status == "evidence_only"
    assert "resolved_result" not in resolution.result
    tables = resolution.result["result"]["tables"]
    assert {table["table_subtype"] for table in tables} == {"grade_scale"}
    assert len(tables) == 2
    assert all(table.get("resolved_rows") for table in tables)


def test_graded_is_accepted_by_planner_contract():
    query = "Môn tính GPA em được 3,6/10 thì có qua không?"
    task = {"question": query, "mode": "structured", "intent": "direct_value",
            "lookup_type": "scoring", "slots": {"operation": "pass_threshold",
            "score_or_grade": "3,6/10", "course_scope": "graded"},
            "slot_spans": {"score_or_grade": "3,6/10",
                           "course_scope": "Môn tính GPA"}, "cohorts": ["K48-K49"]}
    plan, errors = normalize_query_plan(
        {"context_mode": "standalone", "tasks": [task]},
        query=query, selected_cohort="K48-K49")
    assert errors == []
    assert plan["tasks"][0]["slots"]["course_scope"] == "graded"


def test_graded_k50_unique_row_locks_but_wrong_scale_does_not():
    task = {"lookup_type": "scoring", "question": "Môn tính GPA được 3,6/10 có qua không?",
            "intent": "direct_value", "slots": {"operation": "pass_threshold",
            "score_or_grade": "3,6/10", "course_scope": "graded"},
            "slot_spans": {"score_or_grade": "3,6/10", "course_scope": "Môn tính GPA"},
            "cohorts": ["K50"]}
    good = resolve(task, "K50")
    assert good.resolution_status == "resolved"
    assert good.result["resolved_result"]["table_id"] == good.result["table_id"]
    bad = resolve({**task, "slots": {**task["slots"], "score_or_grade": "3,6/4"},
                   "slot_spans": {"score_or_grade": "3,6/4", "course_scope": "Môn tính GPA"}}, "K50")
    assert bad.resolution_status == "evidence_only"
    assert "resolved_result" not in bad.result


def test_historical_pending_018_now_resolves_one_row():
    # V9 case 018 had a unique pass/fail table and row but no fact lock.
    # Previously pending: preserve the exact scope/operand spans while fixing
    # single-row result packaging. The desired assertion now passes.
    question = "Môn không tính GPA, chỉ xét đạt hay trượt, 4,9 có qua không?"
    task = {"lookup_type": "scoring", "question": question,
            "intent": "direct_value", "slots": {"operation": "pass_threshold",
            "score_or_grade": 4.9, "course_scope": "pass_fail_ungraded"},
            "slot_spans": {"score_or_grade": "4,9", "course_scope": "Môn không tính GPA, chỉ xét đạt hay trượt"},
            "cohorts": ["K51"]}
    resolution = resolve(task, "K51")
    assert resolution.resolution_status == "resolved"
    assert resolution.result.get("resolved_result")
    assert build_citation_from_lookup(resolution.result)


def test_historical_033_resolves_single_combined_catalog_row():
    # V9 case 033 had no fact lock. TCF and DELF are two names in one reviewed
    # row, so one result is valid after checking the actual catalog cardinality.
    question = "TCF hay DELF cần mức nào để tương đương bậc 3?"
    task = {"lookup_type": "foreign_language", "question": question,
            "intent": "direct_value", "slots": {"certificate_or_language": ["TCF", "DELF"],
            "score_or_level": "bậc 3"},
            "slot_spans": {"certificate_or_language": ["TCF", "DELF"],
                           "score_or_level": "bậc 3"}, "cohorts": ["K51"]}
    resolution = resolve(task, "K51")
    assert resolution.resolution_status == "resolved"
    assert resolution.result["resolved_result"]["result"]["certificate"] == "TCF / DELF"
    assert build_citation_from_lookup(resolution.result)


@pytest.mark.parametrize("case_id,program,cohort", [
    ("114", "Công tác xã hội", "K51"),
    ("119", "Ngôn ngữ Pháp", "K50"),
])
def test_program_faculty_one_task_requires_two_sources(case_id, program, cohort):
    cases = json.loads((ROOT / "data/eval/official_v1/deterministic_tool_cases_v10.json").read_text(encoding="utf-8"))
    case = next(case for case in cases if case["id"].endswith(case_id))
    task = {"id": "t1", "lookup_type": "program", "mode": "structured",
            "question": case["query"], "intent": "direct_value",
            "slots": {"requested_field": "email"},
            "slot_spans": {"program_or_faculty": program}, "cohorts": [cohort]}
    resolution = resolve(task, cohort)
    assert resolution.result["relationship_status"] == "resolved"
    assert [part["content_type"] for part in resolution.result["sub_lookups"]] == [
        "program_directory", "student_faculty_profile"]
    citations = build_citation_from_lookup(resolution.result)
    assert len({(item["document_id"], item["source_section"]) for item in citations}) == 2
    result = {"query_plan": {"tasks": [task], "out_of_domain": False},
              "task_results": [{"task_id": "t1", "mode": "structured", "lookup_type": "program",
                                "cohorts": [cohort], "coverage": "covered",
                                "evidence": [resolution.result]}],
              "structured_result": resolution.result, "citations": citations}
    scored = _evaluate_outcome_case(case, result, started=time.perf_counter())
    assert scored["passed"] is True
    assert scored["matched_outcome"] == "one-hop-program-faculty-contact"
    assert scored["relationship_correct"] is True
    # Same facts without target provenance must fail the V10 one-task outcome.
    missing_target = dict(resolution.result)
    missing_target["sub_lookups"] = [resolution.result["sub_lookups"][0]]
    result["task_results"][0]["evidence"] = [missing_target]
    result["structured_result"] = missing_target
    assert not _evaluate_outcome_case(case, result, started=time.perf_counter())["passed"]


def test_declared_alias_joins_tam_ly_without_accent_folding():
    assert identity(" Tâm  lý ") != identity("Tâm lí")
    task = {"lookup_type": "program", "question": "Công tác xã hội email khoa?",
            "intent": "direct_value", "slots": {"requested_field": "email"},
            "slot_spans": {"program_or_faculty": "Công tác xã hội"},
            "cohorts": ["K48-K49"]}
    resolution = resolve(task, "K48-K49")
    assert resolution.result["relationship_status"] == "resolved"
    assert resolution.result["result"]["targets"][0]["unit_name"] == "Khoa Tâm lí học"


@pytest.mark.parametrize("program", ["Ngôn ngữ Trung Quốc", "Sư phạm tiếng Trung Quốc"])
def test_k51_chinese_program_faculty_email_has_two_provenances(program):
    task = {"lookup_type": "program", "question": f"Email khoa của ngành {program}?",
            "intent": "direct_value", "slots": {"requested_field": "email"},
            "slot_spans": {"program_or_faculty": program},
            "cohorts": ["K51"]}
    resolution = resolve(task, "K51")
    assert resolution.result["relationship_status"] == "resolved"
    source, target = resolution.result["sub_lookups"]
    assert source["result"][0]["program_name"] == program
    assert source["result"][0]["faculty_name"] == "Khoa Tiếng Trung Quốc"
    assert target["result"][0]["unit_name"] == "Khoa Tiếng Trung"
    assert target["result"][0]["emails"] == ["khoatiengtrung@hcmue.edu.vn"]
    assert source["cohort"] == target["cohort"] == "K51"
    assert source["document_id"] == target["document_id"] == "so_tay_sinh_vien_khoa_51"
    citations = build_citation_from_lookup(resolution.result)
    assert {item["source_section"] for item in citations} == {
        "program_directory", "student_faculty_profiles"}
    assert all(item["cohort"] == "K51" for item in citations)


def test_chinese_faculty_alias_does_not_enable_generic_prefix_matching():
    assert not _declared_alias_span({"khoa tiếng trung quốc"},
                                    {"aliases": ["Khoa Tiếng Trung"]})


def test_faculty_profiles_reproduce_curated_alias_from_pipeline():
    from scripts.build_structured_table_layer import (
        build_student_faculty_profiles, normalize_directory_catalog,
    )

    generated = normalize_directory_catalog(
        build_student_faculty_profiles(), "student_faculty_profiles")
    assert generated == catalogs()["faculty"]
    target = next(profile for profile in generated
                  if profile["cohort"] == "K51"
                  and profile["unit_name"] == "Khoa Tiếng Trung")
    assert "Khoa Tiếng Trung Quốc" in target["aliases"]


def test_office_to_services_returns_multiple_targets_not_clarification():
    data = catalogs()
    office = next(item for item in data["office"] if len(item.get("service_ids") or []) > 1)
    cohort = office["cohort"]
    source = directory_result(office["unit_name"], [office], cohort=cohort)
    from src.retrieval.core.structured_dispatcher import _RELATIONSHIPS
    result = resolve_relationship(source, source_lookup="office", requested_field="services",
                                  cohort=cohort, relationships=_RELATIONSHIPS,
                                  catalogs={"office": data["office"],
                                            "student_service": data["student_service"]})
    assert result["relationship_status"] == "resolved"
    assert len(result["result"]["targets"]) > 1
    assert len(result["sub_lookups"]) == len(result["result"]["targets"]) + 1
    broken = [dict(item) for item in data["student_service"]
              if item["service_id"] != office["service_ids"][0]]
    unavailable = resolve_relationship(source, source_lookup="office",
                                       requested_field="services", cohort=cohort,
                                       relationships=_RELATIONSHIPS,
                                       catalogs={"office": data["office"],
                                                 "student_service": broken})
    assert unavailable["relationship_status"] == "target_unavailable"
    assert identity(office["service_ids"][0]) in unavailable["missing_target_keys"]


def test_source_ambiguity_and_missing_target_are_safe():
    from src.retrieval.core.structured_dispatcher import _RELATIONSHIPS
    data = catalogs()
    first = next(item for item in data["program"] if item["cohort"] == "K51")
    source = {"result": [first, dict(first)], "cohort": "K51", "content_type": "program_directory"}
    ambiguous = resolve_relationship(source, source_lookup="program", requested_field="email",
                                     cohort="K51", relationships=_RELATIONSHIPS,
                                     catalogs={"program": data["program"], "faculty": data["faculty"]})
    assert ambiguous["needs_clarification"] is True
    missing = {"result": [{**first, "faculty_name": "Không có trong catalog"}],
               "cohort": "K51", "content_type": "program_directory"}
    unavailable = resolve_relationship(missing, source_lookup="program", requested_field="email",
                                       cohort="K51", relationships=_RELATIONSHIPS,
                                       catalogs={"program": data["program"], "faculty": data["faculty"]})
    assert unavailable["relationship_status"] == "target_unavailable"
    assert unavailable["sub_lookups"] == [missing]

    # A target in a different cohort is not evidence for this source.
    other_cohort = [{"unit_name": "Không có trong catalog", "cohort": "K50"}]
    cross = resolve_relationship(missing, source_lookup="program", requested_field="email",
                                 cohort="K51", relationships=_RELATIONSHIPS,
                                 catalogs={"program": data["program"], "faculty": other_cohort})
    assert cross["relationship_status"] == "target_unavailable"

    # Multiple same-cohort targets with the same declared key require review;
    # their contact fields must not be picked by order.
    duplicate = [{"unit_name": "Không có trong catalog", "cohort": "K51",
                  "emails": ["one@example.test"]},
                 {"unit_name": "Không có trong catalog", "cohort": "K51",
                  "emails": ["two@example.test"]}]
    ambiguous_target = resolve_relationship(
        missing, source_lookup="program", requested_field="email",
        cohort="K51", relationships=_RELATIONSHIPS,
        catalogs={"program": data["program"], "faculty": duplicate})
    assert ambiguous_target["needs_clarification"] is True


def test_catalog_relationship_integrity_all_records():
    data = catalogs()
    assert len(data["program"]) == 129
    # 2026-09-28: services the handbook does not list (wifi) and a duplicate
    # of a listed one (student loans) were removed from the catalog build.
    # The K50 branch campus unit (Phân hiệu Long An) followed when the
    # chatbot's scope was set to the main campus.
    assert len(data["student_service"]) == 232
    for source_kind, target_kind, source_key, target_keys in (
        ("program", "faculty", "faculty_name", ["unit_name", "faculty_name", "aliases"]),
        ("student_service", "office", "unit_name", ["unit_name", "aliases"]),
    ):
        missing = []
        for source in data[source_kind]:
            keys = _keys(source, [source_key])
            scoped = [target for target in data[target_kind]
                      if target["cohort"] == source["cohort"]]
            matches = [target for target in scoped if _keys(target, target_keys) & keys]
            if not matches:
                matches = [target for target in scoped if _declared_alias_span(keys, target)]
            assert len(matches) <= 1, (source_kind, source.get("record_id"), matches)
            if not matches:
                missing.append((source["cohort"], source.get("record_id"), source.get(source_key)))
        assert not missing, missing
    service_keys = {(item["cohort"], identity(item["service_id"]))
                    for item in data["student_service"]}
    assert all((office["cohort"], identity(service_id)) in service_keys
               for office in data["office"]
               for service_id in office.get("service_ids") or [])


def test_v10_only_adds_two_architectural_outcomes_and_keeps_gold_facts():
    from scripts.build_official_deterministic import CONTRACT_V10, build

    bundle = ROOT / "data/eval/official_v1"
    old = json.loads((bundle / "deterministic_tool_cases.json").read_text(encoding="utf-8"))
    new = json.loads((bundle / "deterministic_tool_cases_v10.json").read_text(encoding="utf-8"))
    assert build(bundle, contract=CONTRACT_V10) == new
    assert [item["id"] for item in old] == [item["id"] for item in new]
    assert all(left["gold_evidence"] == right["gold_evidence"]
               for left, right in zip(old, new, strict=True))
    changed_outcomes = [right["id"] for left, right in zip(old, new, strict=True)
                        if left["accepted_outcomes"] != right["accepted_outcomes"]]
    assert changed_outcomes == ["official_det_114", "official_det_119"]


@pytest.mark.parametrize("case_id", ["093", "096"])
def test_v10_keeps_wrong_office_tool_semantically_wrong(case_id):
    cases = json.loads((ROOT / "data/eval/official_v1/deterministic_tool_cases_v10.json").read_text(encoding="utf-8"))
    case = next(item for item in cases if item["id"].endswith(case_id))
    wrong_task = {"id": "t1", "mode": "structured", "lookup_type": "office",
                  "cohorts": [case["cohort"]], "slots": {"requested_field": "unit"}}
    scored = _evaluate_outcome_case(case, {"query_plan": {"tasks": [wrong_task]},
                                           "task_results": [], "structured_result": {}},
                                    started=time.perf_counter())
    assert scored["task_semantics_correct"] is False
    assert scored["passed"] is False


def test_planner_diagnostics_survive_downstream_execution_exception():
    from types import SimpleNamespace

    from src.generation.plan_executor import PlanExecutor

    class Router:
        def plan(self, *_args, **_kwargs):
            return {"context_mode": "standalone", "out_of_domain": False,
                    "tasks": [{"id": "t1", "mode": "rag", "question": "test",
                               "cohorts": ["K51"]}],
                    "planner_diagnostics": {"schema_version": "synthetic"}}

    normalizer = SimpleNamespace(normalize_for_retrieval=lambda value: value)
    executor = PlanExecutor(router=Router(), slang_normalizer=normalizer,
                            catalogs={}, parent_sources_by_id={}, top_k=5,
                            public_source_limit=5)

    def fail(**_kwargs):
        raise RuntimeError("downstream retrieval failed")

    executor.execute_task = fail
    with pytest.raises(RuntimeError) as captured:
        executor.run(query="test", cohort="K51", chat_history=None)
    assert captured.value.planner_diagnostics == {"schema_version": "synthetic"}
    assert captured.value.planner_latency_ms >= 0


def test_operational_failures_stay_in_request_denominator():
    cases = [{"id": f"offline_{index}", "query": f"q{index}", "cohort": "K51",
              "contract_version": "query-plan-grounded-outcome-v10",
              "accepted_outcomes": [{"name": "rag", "state": "answer",
                                     "allowed_modes": ["rag"],
                                     "task_count": {"min": 1, "max": 1},
                                     "required_tasks": [{"mode": "rag", "cohorts": ["K51"]}]}]}
             for index in range(3)]

    class Pipeline:
        def __init__(self):
            self.position = 0

        def _run_retrieval(self, _query, **_kwargs):
            self.position += 1
            if self.position == 3:
                error = RuntimeError("synthetic downstream failure")
                error.planner_latency_ms = 30.0
                raise error
            return {"query_plan": {"tasks": [{"id": "t1", "mode": "rag",
                                              "cohorts": ["K51"]}]},
                    "task_results": [], "planner_latency_ms": self.position * 10.0,
                    **({"planner_error_type": "timeout"} if self.position == 2 else
                       {"needs_clarification": True})}

    report = evaluate_deterministic(cases, pipeline_factory=Pipeline,
                                    evaluation_contract="query-plan-grounded-outcome-v10")
    summary = report["summary"]
    assert summary["n"] == summary["requested_n"] == 3
    assert summary["not_run_n"] == 0
    assert summary["runtime_error_n"] == 1
    assert summary["execution_error_n"] == 1
    assert summary["planner_request_failure_n"] == 1
    assert summary["evaluation_failure_n"] == 1
    assert summary["request_success_after_retry"] == pytest.approx(1 / 3)
    assert summary["passed"] == 0
    assert summary["accuracy"] == 0.0
    assert summary["planner_latency_p95_ms"] == 30.0
    assert summary["planner_latency_support_n"] == 3


def test_resolution_evidence_citation_and_composer_snapshot():
    """Small behavior snapshot across fact lock, evidence-only and join."""

    specs = [
        ("unique", "K51", {"lookup_type": "scoring", "question": "Môn không tính GPA 4,9 có qua?",
         "intent": "direct_value", "slots": {"operation": "pass_threshold", "score_or_grade": 4.9,
         "course_scope": "pass_fail_ungraded"},
         "slot_spans": {"score_or_grade": "4,9", "course_scope": "Môn không tính GPA"},
         "cohorts": ["K51"]}),
        ("multi_scope", "K51", {"lookup_type": "scoring", "question": "Môn tính GPA 3,6/10 có qua?",
         "intent": "direct_value", "slots": {"operation": "pass_threshold", "score_or_grade": "3,6/10",
         "course_scope": "graded"}, "slot_spans": {"score_or_grade": "3,6/10",
         "course_scope": "Môn tính GPA"}, "cohorts": ["K51"]}),
        ("one_hop", "K51", {"lookup_type": "program", "question": "Email khoa Công tác xã hội?",
         "intent": "direct_value", "slots": {"requested_field": "email"},
         "slot_spans": {"program_or_faculty": "Công tác xã hội"}, "cohorts": ["K51"]}),
    ]
    observed = {}
    for name, cohort, task in specs:
        resolution = resolve(task, cohort)
        citations = [{**citation, "supports_task_ids": ["t1"]}
                     for citation in build_citation_from_lookup(resolution.result)]
        packet = build_authorized_evidence_packet(
            query=task["question"],
            retrieval_result={"query_plan": {"tasks": [{**task, "id": "t1"}]},
                              "coverage_by_task": {"t1": "covered"}},
            selected_citations=PlanExecutor._merge_task_citations(citations),
            fallback_cohort=cohort, max_context_chars=30000,
        )
        primary = [evidence for unit in packet["units"]
                   for evidence in unit["primary_evidence"]]
        observed[name] = {
            "resolution": resolution.resolution_status,
            "locked": bool(resolution.result.get("resolved_result")),
            "per_table_rows": sum(bool(item.get("resolved_rows"))
                                  for item in resolution.result.get("sub_lookups") or []),
            "citation_sections": sorted({item.get("source_section") for item in citations}),
            "composer_units": len(packet["units"]),
            "composer_has_lock": any(bool(item.get("resolved_result")) for item in primary),
            "composer_has_evidence": bool(primary),
        }
    assert observed == {
        "unique": {"resolution": "resolved", "locked": True, "per_table_rows": 0,
                   "citation_sections": ["K51_QuyCheDaoTao_Chuong3_Dieu10"],
                   "composer_units": 1, "composer_has_lock": True, "composer_has_evidence": True},
        "multi_scope": {"resolution": "evidence_only", "locked": False, "per_table_rows": 2,
                        "citation_sections": ["K51_QuyCheDaoTao_Chuong3_Dieu10"],
                        "composer_units": 1, "composer_has_lock": False, "composer_has_evidence": True},
        "one_hop": {"resolution": "evidence_only", "locked": False, "per_table_rows": 0,
                    "citation_sections": ["program_directory", "student_faculty_profiles"],
                    "composer_units": 1, "composer_has_lock": False, "composer_has_evidence": True},
    }
