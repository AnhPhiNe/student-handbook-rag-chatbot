"""Closed-catalog search outcomes survive lookup, evidence fusion and UI."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.generation.answer_pipeline import AnswerPipeline
from src.generation.plan_executor import PlanExecutor, StructuredCatalogs
from src.generation.prompt_builder import build_authorized_evidence_packet
from src.generation.structured_result_presenter import build_structured_results
from src.retrieval.core.citation_builder import build_citation_from_lookup
from src.retrieval.core.program_lookup import program_lookup
from src.retrieval.core.query_plan import normalize_query_plan
from tests.scripted_selector import scripted_selector


@pytest.fixture(scope="module")
def programs():
    root = Path(__file__).resolve().parents[1]
    return json.loads((root / "data/processed/directories/program_directory.json").read_text(encoding="utf-8"))


def known(programs, cohort):
    return next(p for p in programs if p["cohort"] == cohort)


def lookup(programs, names, cohort="K51", selector=None):
    return program_lookup(programs, candidate_text=names, cohort=cohort, action="exists",
                          scope="school", selector=selector if selector is not None else scripted_selector({}))


def run(programs, names, cohorts=("K51",), selector=None, separate=False):
    values = names if isinstance(names, list) else [names]
    grouped = [[name] for name in values] if separate else [values]
    questions = [f"So sánh {', '.join(cohorts)}: có các ngành {' và '.join(group)} không?" for group in grouped]
    tasks = [{"id": f"t{i}", "question": q, "mode": "structured", "intent": "exists", "lookup_type": "program",
              "cohorts": list(cohorts), "slots": {"program_or_faculty": group if len(group) > 1 else group[0]},
              "slot_spans": {"program_or_faculty": group if len(group) > 1 else group[0]}}
             for i, (q, group) in enumerate(zip(questions, grouped), 1)]
    query = " và ".join(questions)
    plan, errors = normalize_query_plan({"context_mode": "standalone", "out_of_domain": False, "tasks": tasks},
                                      query=query, selected_cohort=cohorts[0])
    assert not errors and all(t["mode"] == "structured" for t in plan["tasks"])
    executor = PlanExecutor(router=SimpleNamespace(plan=lambda *a, **kw: plan),
        slang_normalizer=SimpleNamespace(normalize_for_retrieval=lambda q: q),
        catalogs=StructuredCatalogs([], [], [], [], [], programs), parent_sources_by_id={},
        top_k=5, public_source_limit=10, graph=SimpleNamespace(expand_context=lambda *a, **kw: []),
        directory_selector=selector if selector is not None else scripted_selector({}))
    result = executor.run(query=query, cohort=cohorts[0], chat_history=[])
    packet = build_authorized_evidence_packet(query=query, retrieval_result=result,
        selected_citations=result["evidence_citations"], fallback_cohort=cohorts[0], max_context_chars=160000)
    return query, result, packet


@pytest.mark.parametrize("cohort", ["K48-K49", "K50", "K51"])
def test_scalar_none_keeps_scoped_negative_evidence_and_catalog_provenance(programs, cohort):
    result = lookup(programs, "Ngành chưa có trong danh mục", cohort)
    assert result["exists"] is False and result["program_count"] == 0
    outcomes = result["existence_results"]
    assert len(outcomes) == 1 and outcomes[0]["queried_program"] == "Ngành chưa có trong danh mục"
    assert outcomes[0]["exists"] is False and outcomes[0]["status"] == "not_found"
    assert outcomes[0]["matched_programs"] == [] and outcomes[0]["cohort"] == cohort
    assert "sổ tay" in outcomes[0]["scope_note"].lower()
    assert result["document_id"] == known(programs, cohort)["document_id"]
    assert result["source_pages"] == sorted({page for p in programs if p["cohort"] == cohort for page in p["source_pages"]})
    citation = build_citation_from_lookup(result)[0]
    assert json.loads(citation["content"]) == outcomes
    assert citation["document_id"] == result["document_id"] and citation["cohort"] == cohort


def test_all_real_program_records_keep_positive_search_outcomes(programs):
    assert len(programs) == 129
    for record in programs:
        result = lookup(programs, record["program_name"], record["cohort"])
        assert result["exists"] is True
        outcome = result["existence_results"][0]
        assert outcome["queried_program"] == record["program_name"]
        assert outcome["exists"] is True and outcome["status"] == "match"
        assert record["record_id"] in [r["record_id"] for r in outcome["matched_programs"]]
        assert result["result"][0]["record_id"] == outcome["matched_programs"][0]["record_id"]


@pytest.mark.parametrize("cohort", ["K48-K49", "K50", "K51"])
@pytest.mark.parametrize("reverse", [False, True])
def test_mixed_list_never_uses_any_match_as_whole_request_exists(programs, cohort, reverse):
    present = known(programs, cohort)["program_name"]
    names = [present, "Ngành chưa có trong danh mục"]
    if reverse:
        names.reverse()
    result = lookup(programs, names, cohort)
    assert result["exists"] is False  # Summary means all requested names matched.
    assert len(result["result"]) == result["program_count"] == 1
    assert [o["queried_program"] for o in result["existence_results"]] == names
    by_name = {o["queried_program"]: o for o in result["existence_results"]}
    assert by_name[present]["exists"] is True
    assert by_name["Ngành chưa có trong danh mục"]["exists"] is False
    evidence = json.loads(build_citation_from_lookup(result)[0]["content"])
    assert [o["queried_program"] for o in evidence] == names
    assert [o["exists"] for o in evidence] == [o["exists"] for o in result["existence_results"]]
    assert [r["record_id"] for o in evidence for r in o["matched_programs"]] == [
        r["record_id"] for o in result["existence_results"] for r in o["matched_programs"]]
    assert all("raw_text" not in r and "summary" not in r for o in evidence for r in o["matched_programs"])


@pytest.mark.parametrize("kind", ["malformed", "unknown_id", "timeout", "ambiguous"])
def test_selector_failure_and_ambiguity_do_not_become_negative_results(programs, kind):
    choices = [p["program_name"] for p in programs if p["cohort"] == "K51"][:2]
    selector = {
        "malformed": scripted_selector(raw="not JSON"),
        "unknown_id": scripted_selector(raw='{"decision":"match","ids":["S9999"]}'),
        "timeout": scripted_selector(fail=True),
        "ambiguous": scripted_selector({"Tên ngành mơ hồ": tuple(choices)}),
    }[kind]
    result = lookup(programs, "Tên ngành mơ hồ", selector=selector)
    assert result["needs_clarification"]
    assert "exists" not in result and "existence_results" not in result
    _, execution, packet = run(programs, "Tên ngành mơ hồ", selector=selector)
    assert execution["needs_clarification"] and not execution["evidence_citations"]
    assert not packet["units"][0]["primary_evidence"]


def test_absent_or_empty_catalog_cannot_prove_absence(programs):
    assert lookup([], "Missing") is None
    assert lookup(programs, "Missing", cohort="UNSUPPORTED") is None
    assert program_lookup(programs, candidate_text="Missing", cohort=None, action="exists", scope="school") is None
    assert lookup(programs, "  ") is None


@pytest.mark.parametrize("separate", [False, True])
def test_multi_entity_negative_proof_reaches_own_composer_units(programs, separate):
    present = known(programs, "K51")["program_name"]
    names = [present, "Ngành chưa có trong danh mục"]
    _, result, packet = run(programs, names, separate=separate)
    expected_groups = [[name] for name in names] if separate else [names]
    assert len(packet["units"]) == len(expected_groups)
    for unit, expected in zip(packet["units"], expected_groups):
        assert unit["coverage"] == "covered" and len(unit["primary_evidence"]) == 1
        outcomes = json.loads(unit["primary_evidence"][0]["content"])
        assert [o["queried_program"] for o in outcomes] == expected
        assert all(o["cohort"] == unit["cohort"] for o in outcomes)
        assert "resolved_result" not in unit["primary_evidence"][0]
    assert build_structured_results(result["structured_result"], result["evidence_citations"])


def test_two_missing_names_do_not_collapse_when_sources_are_fused(programs):
    _, result, packet = run(programs, ["Missing Alpha", "Missing Beta"], separate=True)
    assert len(result["evidence_citations"]) == 2
    for unit, name in zip(packet["units"], ["Missing Alpha", "Missing Beta"]):
        assert json.loads(unit["primary_evidence"][0]["content"])[0]["queried_program"] == name


def test_cross_cohort_exists_outcomes_and_provenance_do_not_mix(programs):
    name = "Công nghệ Giáo dục"
    selector = scripted_selector({})
    _, result, packet = run(programs, name, cohorts=("K50", "K51"), selector=selector)
    assert len(packet["units"]) == len(result["evidence_citations"]) == 2
    by_cohort = {u["cohort"]: u for u in packet["units"]}
    for cohort, expected in [("K50", False), ("K51", True)]:
        source_item = by_cohort[cohort]["primary_evidence"][0]
        outcome = json.loads(source_item["content"])[0]
        assert outcome["cohort"] == source_item["source_cohort"] == cohort
        assert outcome["exists"] is expected


def test_display_rows_include_negative_result_without_inventing_catalog_record(programs):
    before = copy.deepcopy(programs)
    result = lookup(programs, "Ngành chưa có trong danh mục")
    displayed = build_structured_results(result, build_citation_from_lookup(result))
    assert len(displayed) == 1 and displayed[0]["rows"]
    text = json.dumps(displayed[0]["rows"], ensure_ascii=False)
    assert "Ngành chưa có trong danh mục" in text and "Không tìm thấy" in text
    assert displayed[0]["provenance"]["document_id"] == result["document_id"]
    assert result["result"] == [] and programs == before


@pytest.mark.parametrize("streaming", [False, True])
def test_sync_and_stream_composers_receive_same_positive_and_negative_outcomes(programs, streaming):
    name = known(programs, "K51")["program_name"]
    query, result, _ = run(programs, [name, "Ngành chưa có trong danh mục"])
    prompts = []

    class Composer:
        def generate(self, prompt):
            prompts.append(prompt)
            return {"ok": True, "text": "Kết quả chỉ theo danh mục sổ tay.", "model_used": "fake", "usage": {}}

        def generate_stream(self, prompt):
            prompts.append(prompt)
            yield "Kết quả chỉ theo danh mục sổ tay."
            return {"model_used": "fake", "usage": {}}

    pipeline = AnswerPipeline(llm_client=Composer())
    pipeline._run_retrieval = lambda *a, **kw: result
    output = list(pipeline.answer_stream(query, cohort="K51"))[-1] if streaming else pipeline.answer(query, cohort="K51")
    assert output["status"] == "answered" and len(prompts) == 1
    context, _ = json.JSONDecoder().raw_decode(prompts[0].split("\nAUTHORIZED_EVIDENCE_BY_UNIT\n", 1)[1])
    outcomes = json.loads(context["units"][0]["primary_evidence"][0]["content"])
    assert [o["exists"] for o in outcomes] == [True, False]
    assert "selection" not in outcomes[1] and "reply" not in json.dumps(outcomes)


@pytest.mark.parametrize("action,scope", [("resolve_faculty", "school"), ("list", "school")])
def test_non_existence_actions_keep_catalog_records_and_original_citation_shape(programs, action, scope):
    record = known(programs, "K51")
    result = program_lookup(programs, candidate_text=record["program_name"], cohort="K51", action=action, scope=scope)
    assert result["result"] and "existence_results" not in result
    assert json.loads(build_citation_from_lookup(result)[0]["content"]) == result["result"]


def test_alias_result_retains_query_name_and_canonical_record_identity(programs):
    record = known(programs, "K51")
    selector = scripted_selector({"Tên gọi tắt của ngành": record["program_name"]})
    result = lookup(programs, "Tên gọi tắt của ngành", selector=selector)
    outcome = result["existence_results"][0]
    assert outcome["queried_program"] == "Tên gọi tắt của ngành" and outcome["exists"] is True
    assert outcome["matched_programs"][0]["record_id"] == record["record_id"]
    assert outcome["matched_programs"][0]["program_name"] == record["program_name"]
    assert "reply" not in json.dumps(json.loads(build_citation_from_lookup(result)[0]["content"]))


def test_two_positive_entities_do_not_merge_even_when_their_catalog_source_is_shared(programs):
    names = [p["program_name"] for p in programs if p["cohort"] == "K51"][:2]
    _, result, packet = run(programs, names, separate=True)
    assert len(result["evidence_citations"]) == len(packet["units"]) == 2
    for unit, name in zip(packet["units"], names):
        outcomes = json.loads(unit["primary_evidence"][0]["content"])
        assert len(outcomes) == 1 and outcomes[0]["queried_program"] == name
        assert outcomes[0]["exists"] is True


def test_repeated_aliases_keep_independent_results_without_fake_record_ids(programs):
    record = known(programs, "K51")
    alias = "Tên gọi tắt của ngành"
    result = lookup(programs, [record["program_name"], alias], selector=scripted_selector({alias: record["program_name"]}))
    outcomes = result["existence_results"]
    assert len(result["result"]) == result["program_count"] == 1
    assert len(outcomes) == 2 and all(o["exists"] for o in outcomes)
    assert all("record_id" not in outcome for outcome in outcomes)
    assert [o["matched_programs"][0]["record_id"] for o in outcomes] == [record["record_id"], record["record_id"]]


def test_error_after_an_exact_match_does_not_deny_the_other_program(programs):
    name = known(programs, "K51")["program_name"]
    result = lookup(programs, [name, "Unknown query"], selector=scripted_selector(fail=True))
    assert result["needs_clarification"] and "exists" not in result and "existence_results" not in result
    assert [entry["status"] for entry in result["selection"]] == ["match", "unavailable"]


def test_catalog_and_lookup_are_not_mutated_by_citation_or_ui_projection(programs):
    catalog_before = copy.deepcopy(programs)
    result = lookup(programs, [known(programs, "K51")["program_name"], "Missing query"])
    before = copy.deepcopy(result)
    citations = build_citation_from_lookup(result)
    build_structured_results(result, citations)
    assert result == before and programs == catalog_before


def test_supported_large_batch_keeps_all_outcomes_under_default_context_budget(programs):
    names = [p["program_name"] for p in programs if p["cohort"] == "K51"]
    query, result, packet = run(programs, names, cohorts=("K48-K49", "K50", "K51"))
    assert len(query) <= 2000  # This is a request the current HTTP limit supports.
    assert len(packet["units"]) == 3 and len(result["evidence_citations"]) == 3
    for unit in packet["units"]:
        outcomes = json.loads(unit["primary_evidence"][0]["content"])
        assert len(outcomes) == len(names) == 45
        assert [o["queried_program"] for o in outcomes] == names
        assert all(o["cohort"] == unit["cohort"] for o in outcomes)
        assert unit["coverage"] == "covered"
    displayed = build_structured_results(result["structured_result"], result["evidence_citations"])
    assert len(displayed) == 3 and all(len(table["rows"]) == 45 for table in displayed)


def test_mixed_exists_and_career_keeps_positive_detail_and_negative_outcome(programs):
    from src.retrieval.core.structured_dispatcher import resolve_structured_task

    record = known(programs, "K51")
    names = [record["program_name"], "Missing query"]
    query = f"K51 có ngành {' và '.join(names)} không và cơ hội nghề nghiệp thế nào?"
    task = {"lookup_type": "program", "intent": "exists",
            "slots": {"program_or_faculty": names, "requested_field": ["exists", "career"]},
            "slot_spans": {"program_or_faculty": names}}
    resolution = resolve_structured_task(task, query=query, cohort="K51", formula_rules=[], office_directory=[],
        student_service_directory=[], student_faculty_profiles=[], structured_tables_registry=[],
        program_directory=programs, directory_selector=scripted_selector({}))
    result = resolution.result
    evidence = json.loads(build_citation_from_lookup(result)[0]["content"])
    assert [o["exists"] for o in evidence] == [True, False]
    assert evidence[0]["matched_programs"][0]["raw_text"] == record["raw_text"]
    assert result["result"][0]["raw_text"] == record["raw_text"]
