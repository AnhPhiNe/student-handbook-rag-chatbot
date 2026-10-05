"""Candidate-only table search through the existing hybrid/parent-child seam."""
import copy
import hashlib
import json
from types import SimpleNamespace

import pytest

from scripts.build_table_search_candidate import ROOT, build_candidate, assert_separate_output
from src.generation.prompt_builder import build_answer_prompt_bundle
from src.generation.structured_result_presenter import public_regulation_citations
from src.retrieval.core.citation_builder import build_citations_from_vector_results
from src.retrieval.core.hybrid_pipeline import ChildParentHybridRetriever, reciprocal_rank_fusion
from src.retrieval.core.table_search import build_table_descriptions, load_table_search, raw_table_for_handle, table_key, table_digest


def sources():
    tables = json.loads((ROOT / "data/processed/tables/structured_tables_registry.json").read_text(encoding="utf-8"))
    parents = json.loads((ROOT / "data/processed/chunks/all_docstore_items.json").read_text(encoding="utf-8"))
    return tables, parents


def test_all_reviewed_tables_have_stable_unique_handles_and_unchanged_sources():
    tables, parents = sources()
    before = copy.deepcopy((tables, parents))
    handles = build_table_descriptions(tables, parents)
    assert len(handles) == 35
    assert len({h["_id"] for h in handles}) == 35
    assert len({table_key(t) for t in tables}) == 35
    assert len({t["table_id"] for t in tables}) == 27
    assert build_table_descriptions(list(reversed(tables)), parents) == handles
    assert (tables, parents) == before
    assert all("275" not in h["content"] for h in handles)


def test_build_candidate_keeps_baseline_and_separate_namespace(tmp_path):
    before = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in
              ["data/processed/chunks/child_parent_chunks.json", "configs/retrieval.yaml",
               "data/processed/metadata/build_manifest.json"]}
    report = build_candidate(ROOT, tmp_path)
    assert report["artifacts"]["child_chunks"]["count"] == 2678  # 2646 clause chunks + 32 in-scope table handles
    assert report["model_calls"] == 0 and not report["embedding_created"]
    assert report["storage_targets"]["qdrant_collection"] != "student_handbook_semantic_v35"
    assert report["storage_targets"]["mongo_parent_collection"] != "parent_docs_v35"
    assert {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in before} == before
    with pytest.raises(ValueError):
        build_candidate(ROOT, ROOT / "data/processed")


def test_candidate_loader_pins_registry_and_refuses_baseline(tmp_path):
    registry = ROOT / "data/processed/tables/structured_tables_registry.json"
    config = {"registry_path": str(registry), "registry_sha256": hashlib.sha256(registry.read_bytes()).hexdigest(),
              "collection_name": "candidate", "baseline_collection": "baseline"}
    assert len(load_table_search(config, "candidate")) == 35
    assert load_table_search({}, "baseline") == {}
    with pytest.raises(ValueError):
        load_table_search(config, "baseline")
    with pytest.raises(ValueError):
        load_table_search({**config, "registry_sha256": "stale"}, "candidate")


@pytest.mark.parametrize("field,value", [("cohort", "K51"), ("parent_section_id", "wrong"),
                                        ("table_sha256", "stale"), ("document_id", "wrong")])
def test_tampered_handle_cannot_materialize_raw_table(field, value):
    tables, parents = sources()
    handles = build_table_descriptions(tables, parents)
    h = next(h for h in handles if 'foreign_language' in h["metadata"]["table_search_key"])
    h["metadata"][field] = value
    assert raw_table_for_handle(h, {table_key(t): t for t in tables}) is None


@pytest.mark.parametrize("table_type", ["foreign_language", "conduct", "scoring", "scholarship", "study_duration"])
def test_summary_rrf_parent_hydration_sends_raw_table_not_description(table_type):
    tables, parents = sources()
    handles = build_table_descriptions(tables, parents)
    table = next(t for t in tables if t["table_type"] == table_type)
    h = next(h for h in handles if h["metadata"]["table_search_key"] == table_key(table))
    by_parent = {p["_id"]: p for p in parents}
    retriever = ChildParentHybridRetriever.__new__(ChildParentHybridRetriever)
    retriever.table_search_tables = {table_key(t): t for t in tables}
    retriever.collection_name = "candidate"
    retriever._get_parent = by_parent.get
    scored = reciprocal_rank_fusion([(1.0, h)], [(1.0, h)])
    result = retriever._group_parent_results(query="fixture", scored_chunks=scored, top_k_final=5)
    assert len(result) == 1
    assert result[0]["document"] == by_parent[h["metadata"]["parent_section_id"]]["content"]
    raw = json.loads(result[0]["metadata"]["raw_table_context"])["tables"][0]
    assert raw["rows"] == table["rows"]
    assert h["content"] not in result[0]["content"]
    citations = [{**c, "supports_task_ids": ["t1"]} for c in build_citations_from_vector_results(result)]
    _, context = build_answer_prompt_bundle("fixture", {"query_plan": {"tasks": [
        {"id": "t1", "question": "fixture", "mode": "rag", "cohorts": [table["cohort"]]}]},
        "task_results": [{"task_id": "t1", "coverage": "covered"}]}, citations, 160000, table["cohort"])
    source = json.loads(context)["units"][0]["primary_evidence"][0]
    assert json.loads(source["content"])["tables"][0]["rows"] == table["rows"]
    assert "resolved_result" not in source
    assert "raw_table_context" not in public_regulation_citations(citations)[0]
    assert '"tables":' not in public_regulation_citations(citations)[0]["relevant_excerpt"]


def test_disabled_feature_and_wrong_parent_do_not_pass_summary_as_evidence():
    tables, parents = sources()
    h = build_table_descriptions(tables, parents)[0]
    r = ChildParentHybridRetriever.__new__(ChildParentHybridRetriever)
    r.table_search_tables = {}
    r.collection_name = "candidate"
    r._get_parent = lambda parent_id: pytest.fail("disabled handle must be ignored")
    assert r._group_parent_results(query="q", scored_chunks=[(1.0, h)], top_k_final=5) == []
    r.table_search_tables = {table_key(t): t for t in tables}
    r._get_parent = lambda parent_id: {"_id": parent_id, "cohort": "WRONG", "document_id": "wrong", "content": "wrong"}
    assert r._group_parent_results(query="q", scored_chunks=[(1.0, h)], top_k_final=5) == []


def test_new_reviewed_table_uses_same_generator_without_query_rules():
    tables, parents = sources()
    new = copy.deepcopy(tables[0])
    new["table_id"] = "new_reference_table"
    assert len(build_table_descriptions([*tables, new], parents)) == 36
    with pytest.raises(ValueError):
        build_table_descriptions([*tables, copy.deepcopy(tables[0])], parents)


def test_existing_dense_rrf_rerank_path_uses_fake_embedder_and_store():
    tables, parents = sources()
    handles = build_table_descriptions(tables, parents)
    h = next(h for h in handles if 'foreign_language' in h["metadata"]["table_search_key"])
    calls = []
    r = ChildParentHybridRetriever.__new__(ChildParentHybridRetriever)
    r.collection_name = "candidate"
    r.candidate_children = 24
    r.table_search_tables = {table_key(t): t for t in tables}
    r._get_parent = {p["_id"]: p for p in parents}.get
    r.embedder = SimpleNamespace(embed_query=lambda query: [0.5, 0.5])
    def query_points(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(points=[SimpleNamespace(id=h["_id"], score=0.9,
            payload={**h["metadata"], "content": h["content"]})])
    r.qdrant_client = SimpleNamespace(query_points=query_points)
    r.bm25 = SimpleNamespace(sparse_search=lambda *a, **kw: [])
    r.reranker = SimpleNamespace(rerank=lambda query, ranked: (ranked, {"reranker_applied": True}))
    result = r.retrieve("TOEIC cần bao nhiêu điểm?", graph_depth=0, cohort="K48-K49")
    assert len(calls) == 1 and calls[0]["collection_name"] == "candidate"
    assert "275" in result[0]["metadata"]["raw_table_context"]
    assert result[0]["metadata"]["retrieval_telemetry"]["reranker_applied"]


def test_context_budget_does_not_pass_a_cut_json_table_as_complete_evidence():
    citation = {"chunk_id": "p", "cohort": "K51", "content": "Điều kiện áp dụng.",
                "raw_table_context": json.dumps({"rows": [{"value": "x" * 2000}]}),
                "supports_task_ids": ["t1"]}
    _, context = build_answer_prompt_bundle("fixture", {"query_plan": {"tasks": [
        {"id": "t1", "question": "fixture", "mode": "rag", "cohorts": ["K51"]}]}}, [citation], 1000, "K51")
    source = json.loads(context)["units"][0]["primary_evidence"][0]
    assert source["table_context_unavailable"] == "context_budget"
    assert "x" * 20 not in source["content"]


def test_shared_parent_cannot_broaden_table_applicability_even_with_tampered_handle():
    tables, parents = sources()
    restricted = copy.deepcopy(next(t for t in tables if t["table_type"] == "foreign_language"))
    for field in ("applicable_cohorts", "applicability_validated", "applicability_basis_parent_id", "applicability"):
        restricted.pop(field, None)
    h = build_table_descriptions([restricted], parents)[0]
    assert not h["metadata"]["applicability_validated"]
    h["metadata"].update(applicable_cohorts=["K50", "K51"], applicability_validated=True)
    assert raw_table_for_handle(h, {table_key(restricted): restricted}, "K51") is None
    assert raw_table_for_handle(h, {table_key(restricted): restricted}, "K50") == restricted


def test_unsupported_cohort_rejected_by_generator_and_hydration():
    tables, parents = sources()
    table = copy.deepcopy(tables[0])
    table["cohort"] = table["source_cohort"] = "K99"
    with pytest.raises(ValueError):
        build_table_descriptions([table], parents)
    h = {"metadata": {"table_search_key": "unknown", "table_sha256": table_digest(table)}}
    assert raw_table_for_handle(h, {"unknown": table}) is None


def test_zero_source_budget_retains_table_omission_diagnostic():
    citations = [{"chunk_id": "p1", "cohort": "K51", "article_label": "Điều 10",
                  "content": "Nguồn chính " * 1000, "supports_task_ids": ["t1"]},
                 {"chunk_id": "p2", "cohort": "K51", "content": "Bảng",
                  "raw_table_context": '{"rows":[{"x":1}]}', "supports_task_ids": ["t1"]}]
    _, context = build_answer_prompt_bundle("Điều 10 và bảng", {"query_plan": {"tasks": [
        {"id": "t1", "question": "Điều 10 và bảng", "mode": "rag", "cohorts": ["K51"]}]}},
        citations, 1000, "K51")
    sources = json.loads(context)["units"][0]["primary_evidence"]
    omitted = next(s for s in sources if s["source_id"] == "p2")
    assert omitted["table_context_unavailable"] == "context_budget"
    assert omitted["content"] == ""


@pytest.mark.parametrize("relative", ["data/eval/gold.json", "DATA/eval/gold.json", "configs/retrieval.yaml", "README.md",
                                      "tests/fixtures/cases.json", "docs/historical.md"])
def test_reports_cannot_overwrite_protected_files(relative):
    with pytest.raises(ValueError):
        assert_separate_output(ROOT, ROOT / relative)
