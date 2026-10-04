"""Real catalog identity survives lookup, fusion, composition and presentation."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.generation.answer_pipeline import AnswerPipeline
from src.generation.citation_formatter import deduplicate_citations
from src.generation.plan_executor import PlanExecutor, StructuredCatalogs
from src.generation.prompt_builder import build_authorized_evidence_packet
from src.generation.structured_result_presenter import build_structured_results
from src.retrieval.core.office_lookup import directory_result
from src.retrieval.core.program_lookup import _program_summary
from src.retrieval.core.query_plan import QUERY_PLAN_SCHEMA_VERSION, normalize_query_plan


ROOT = Path(__file__).resolve().parents[1]
FAMILIES = {
    "office": ("office_directory", "unit_name", "office", "office_profile_id"),
    "faculty": ("student_faculty_profiles", "unit_name", "faculty", "faculty_profile_id"),
    "student_service": ("student_service_directory", "service", "service", "service_id"),
    "program": ("program_directory", "program_name", "program_or_faculty", "record_id"),
}


@pytest.fixture(scope="module")
def catalogs():
    def read(name):
        return json.loads((ROOT / f"data/processed/directories/{name}.json").read_text(encoding="utf-8"))

    return StructuredCatalogs([], read("student_office_profiles"), read("student_service_directory"),
                              read("student_faculty_profiles"), [], read("program_directory"))


def execute_pair(catalogs, family, cohort="K50", reverse=False, same_record=False):
    catalog_name, entity_field, slot, id_field = FAMILIES[family]
    candidates = [r for r in getattr(catalogs, catalog_name) if r["cohort"] == cohort]
    first = candidates[0]
    second = first if same_record else next(
        r for r in candidates if r[entity_field] != first[entity_field]
        and (family != "student_service" or r["unit_name"] != first["unit_name"])
    )
    records = [first, second]
    fields, phrases = (["faculty", "career"], ["khoa phụ trách", "cơ hội nghề nghiệp"]) if family == "program" else (
        ["email", "phone"], ["email", "số điện thoại"]
    )
    tasks = [
        {"id": f"t{i}", "question": f"{phrase} của {record[entity_field]} {cohort} là gì?",
         "mode": "structured", "intent": "direct_value" if family == "program" else "contact",
         "lookup_type": family, "cohorts": [cohort],
         "slots": {slot: record[entity_field], "requested_field": field},
         "slot_spans": {slot: record[entity_field], "requested_field": phrase}}
        for i, (record, field, phrase) in enumerate(zip(records, fields, phrases), 1)
    ]
    if reverse:
        tasks.reverse()
    query = " và ".join(t["question"] for t in tasks)
    plan, errors = normalize_query_plan({
        "schema_version": QUERY_PLAN_SCHEMA_VERSION, "context_mode": "standalone",
        "out_of_domain": False, "tasks": tasks,
    }, query=query, selected_cohort=cohort)
    assert not errors and len(plan["tasks"]) == 2
    executor = PlanExecutor(
        router=SimpleNamespace(plan=lambda *a, **kw: plan),
        slang_normalizer=SimpleNamespace(normalize_for_retrieval=lambda text: text),
        catalogs=catalogs, parent_sources_by_id={}, top_k=5, public_source_limit=10,
        graph=SimpleNamespace(expand_context=lambda *a, **kw: []), directory_selector=None,
    )
    result = executor.run(query=query, cohort=cohort, chat_history=[])
    expected = {t["id"]: next(r for r in records if r[entity_field] == t["slots"][slot])
                for t in plan["tasks"]}
    return query, result, expected, id_field


def assert_packet_records(packet, expected, id_field):
    for unit in packet["units"]:
        sources = unit["primary_evidence"]
        assert len(sources) == 1
        records = json.loads(sources[0]["content"])
        assert isinstance(records, list)
        assert [r["record_id"] for r in records] == [expected[unit["task_id"]][id_field]]


@pytest.mark.parametrize("family", FAMILIES)
def test_every_catalog_record_keeps_its_existing_identity(catalogs, family):
    catalog_name, _, _, id_field = FAMILIES[family]
    records = getattr(catalogs, catalog_name)
    assert records and all(r.get(id_field) for r in records)
    assert len({(r["cohort"], r[id_field]) for r in records}) == len(records)
    for record in records:
        summary = _program_summary(record) if family == "program" else directory_result(
            "Contact", [record], cohort=record["cohort"]
        )["result"][0]
        assert summary["record_id"] == record[id_field]
        assert summary["source_pages"] == record["source_pages"]
        assert summary["cohort"] == record["cohort"]


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("cohort", ["K48-K49", "K50", "K51"])
@pytest.mark.parametrize("reverse", [False, True])
def test_real_two_record_tasks_keep_separate_evidence_and_provenance(catalogs, family, cohort, reverse):
    query, result, expected, id_field = execute_pair(catalogs, family, cohort, reverse)
    assert result["coverage_by_task"] == {"t1": "covered", "t2": "covered"}
    citations = result["evidence_citations"]
    assert len(citations) == 2
    for citation in citations:
        assert len(citation["supports_task_ids"]) == 1
        record = expected[citation["supports_task_ids"][0]]
        assert citation["source_pages"] == record["source_pages"]
        assert citation["cohort"] == record["cohort"]
    packet = build_authorized_evidence_packet(
        query=query, retrieval_result=result, selected_citations=citations,
        fallback_cohort=cohort, max_context_chars=160000,
    )
    assert_packet_records(packet, expected, id_field)
    assert len(deduplicate_citations(citations)) == 2


@pytest.mark.parametrize("family", FAMILIES)
def test_same_real_record_can_still_support_two_tasks(catalogs, family):
    query, result, expected, id_field = execute_pair(catalogs, family, same_record=True)
    citations = result["evidence_citations"]
    assert len(citations) == 1
    assert citations[0]["supports_task_ids"] == ["t1", "t2"]
    packet = build_authorized_evidence_packet(
        query=query, retrieval_result=result, selected_citations=citations,
        fallback_cohort="K50", max_context_chars=160000,
    )
    assert_packet_records(packet, expected, id_field)
    assert len(deduplicate_citations(citations)) == 1


def entry(records, task_id, cohort="K50", page=1):
    return {"chunk_id": "catalog", "source_parent_id": "catalog", "cohort": cohort,
            "metadata": {"cohort": cohort}, "chunk_type": "office_directory",
            "evidence_kind": "structured_result", "supports_task_ids": [task_id],
            "source_pages": [page], "content": json.dumps(records, ensure_ascii=False)}


@pytest.mark.parametrize("kind", ["missing", "empty", "whitespace", "partial"])
def test_missing_or_partial_identity_cannot_merge_different_records(kind):
    records = [{"unit_name": "First"}]
    if kind in {"empty", "whitespace"}:
        records[0]["record_id"] = "" if kind == "empty" else "  "
    if kind == "partial":
        records.insert(0, {"record_id": "shared", "unit_name": "Shared"})
    other = copy.deepcopy(records)
    other[-1]["unit_name"] = "Second"
    entries = [entry(records, "t1", page=1), entry(other, "t2", page=2)]
    before = copy.deepcopy(entries)
    for merge in (PlanExecutor._merge_task_items, PlanExecutor._merge_task_citations, deduplicate_citations):
        merged = merge(entries)
        assert len(merged) == 2
        assert [e["supports_task_ids"] for e in merged] == [["t1"], ["t2"]]
        assert [e["source_pages"] for e in merged] == [[1], [2]]
    assert entries == before


def test_unidentified_identical_payload_is_still_task_local():
    entries = [entry([{"unit_name": "Same"}], task_id) for task_id in ("t1", "t2")]
    for merge in (PlanExecutor._merge_task_items, PlanExecutor._merge_task_citations, deduplicate_citations):
        assert len(merge(entries)) == 2


@pytest.mark.parametrize("identified", [False, True])
def test_identical_directory_duplicate_within_one_task_still_deduplicates(identified):
    record = {"unit_name": "Same"}
    if identified:
        record["record_id"] = "existing-id"
    original = entry([record], "t1")
    for merge in (PlanExecutor._merge_task_items, PlanExecutor._merge_task_citations, deduplicate_citations):
        merged = merge([original, copy.deepcopy(original)])
        assert len(merged) == 1 and merged[0]["supports_task_ids"] == ["t1"]


def test_directory_identity_does_not_cross_cohort():
    entries = [entry([{"record_id": "shared-id", "unit_name": "Same"}], "t1", cohort)
               for cohort in ("K50", "K51")]
    for merge in (PlanExecutor._merge_task_items, PlanExecutor._merge_task_citations, deduplicate_citations):
        assert len(merge(entries)) == 2


def test_plain_rag_json_list_keeps_existing_parent_fusion():
    entries = [entry([{"record_id": "not-a-directory", "value": "Shared text"}], task_id)
               for task_id in ("t1", "t2")]
    for item in entries:
        item.pop("evidence_kind")
        item["chunk_type"] = "regulation"
    for merge in (PlanExecutor._merge_task_items, PlanExecutor._merge_task_citations, deduplicate_citations):
        assert len(merge(entries)) == 1


@pytest.mark.parametrize("family", ["office", "program"])
@pytest.mark.parametrize("streaming", [False, True])
def test_sync_and_stream_composers_receive_both_real_records(catalogs, family, streaming):
    query, result, expected, id_field = execute_pair(catalogs, family)
    prompts = []

    class Composer:
        def generate(self, prompt):
            prompts.append(prompt)
            return {"ok": True, "text": "Hai kết quả độc lập.", "model_used": "fake", "usage": {}}

        def generate_stream(self, prompt):
            prompts.append(prompt)
            yield "Hai kết quả độc lập."
            return {"model_used": "fake", "usage": {}}

    pipeline = AnswerPipeline(llm_client=Composer())
    pipeline._run_retrieval = lambda *a, **kw: result
    output = list(pipeline.answer_stream(query, cohort="K50"))[-1] if streaming else pipeline.answer(query, cohort="K50")
    assert output["status"] == "answered" and len(output["citations_used"]) == 2
    assert len(prompts) == 1
    packet, _ = json.JSONDecoder().raw_decode(prompts[0].split("\nAUTHORIZED_EVIDENCE_BY_UNIT\n", 1)[1])
    assert_packet_records(packet, expected, id_field)


def test_program_record_id_is_internal_not_a_display_column(catalogs):
    record = _program_summary(catalogs.program_directory[0])
    projected = build_structured_results({"lookup_type": "program_directory", "lookup_scope": "program",
                                         "cohort": record["cohort"], "result": [record]})
    assert len(projected) == 1 and projected[0]["rows"][0]["program_name"] == record["program_name"]
    assert "record_id" not in projected[0]["columns"]
    assert "record_id" not in projected[0]["rows"][0]
