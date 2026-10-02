"""Live probe scorer tested without network/model calls."""
import copy
import json
import os
import sys
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from scripts.build_table_search_candidate import ROOT
from scripts.evaluate_table_search_live import check_results, main
from src.retrieval.core.retrieval_mode import DEFAULT_RETRIEVAL_MODE


@pytest.mark.parametrize("mutation", [None, "rows", "cohort", "document", "collection", "provenance", "added_sharing"])
def test_live_probe_checks_original_table_parent_and_candidate_store(mutation):
    source = json.loads((ROOT / "data/processed/metadata/build_manifest.json").read_text(encoding="utf-8"))
    parents = json.loads((ROOT / source["artifacts"]["parent_docstore"]["path"]).read_text(encoding="utf-8"))
    tables = json.loads((ROOT / source["artifacts"]["structured_tables"]["path"]).read_text(encoding="utf-8"))
    table = next(t for t in tables if t["cohort"] == "K51" and t["table_type"] == "conduct")
    parent = next(p for p in parents if p["_id"] == table["source_parent_id"])
    raw = {field: copy.deepcopy(table.get(field)) for field in
           ("table_id", "table_name", "cohort", "applicability", "columns", "rows")}
    result = {**parent, "chunk_id": parent["_id"], "document": parent["content"],
              "metadata": {**parent["metadata"], "collection": "candidate", "parent_source": "mongodb"}}
    if mutation == "rows":
        raw["rows"] = [{"invented": True}]
    elif mutation == "cohort":
        raw["cohort"] = "K50"
    elif mutation == "document":
        result["document"] = "wrong"
    elif mutation == "collection":
        result["metadata"]["collection"] = "baseline"
    elif mutation == "provenance":
        result["metadata"].update(cohort="K50", source_cohort="K50", document_id="wrong", applicable_cohorts=["K50"])
    elif mutation == "added_sharing":
        result["metadata"].update(source_cohort="K50", applicable_cohorts=["K48-K49", "K50", "K51"], applicability_validated=True)
    result["metadata"]["raw_table_context"] = json.dumps({"tables": [raw]}, ensure_ascii=False)
    row = check_results([result], {"source_cohort": "K51", "cohort": "K51", "table_subtype": "conduct_classification"},
                        {"source": source, "parents": parents, "manifest": {"storage_targets": {"qdrant_collection": "candidate"}}})
    assert row["parent_hit_at_5"]
    if mutation in {"rows", "cohort"}:
        assert row["incorrect_raw_tables"] == 1 and not row["expected_table_family_hydrated"]
    elif mutation in {"document", "collection", "provenance", "added_sharing"}:
        assert row["incorrect_parent_sources"] == 1
    else:
        assert row["expected_table_family_hydrated"] and row["cross_cohort_leaks"] == 0
        assert row["incorrect_raw_tables"] == row["incorrect_parent_sources"] == 0


@pytest.mark.parametrize("failure", ["setup", "probes"])
def test_runner_reports_operational_failures_without_success_exit(tmp_path, monkeypatch, failure):
    for name in ("MONGODB_PARENT_COLLECTION", "MONGODB_PARENT_LOOKUP_ENABLED", "QDRANT_COLLECTION_NAME",
                 "STUDENT_RAG_HYBRID_COLLECTION", "STUDENT_RAG_RETRIEVAL_CONFIG"):
        monkeypatch.setenv(name, os.environ.get(name, ""))
    monkeypatch.setattr("scripts.evaluate_table_search_live.logging.disable", lambda *_: None)
    source = json.loads((ROOT / "data/processed/metadata/build_manifest.json").read_text(encoding="utf-8"))
    targets = {"qdrant_collection": "candidate", "mongo_parent_collection": "candidate_mongo"}
    prepared = {"directory": tmp_path, "manifest": {"storage_targets": targets}, "source": source, "config": {}}
    monkeypatch.setattr("scripts.evaluate_table_search_live.prepare_candidate", lambda *args: prepared)
    (tmp_path / "publication_report.json").write_text(json.dumps({"completed": True, "storage_targets": targets}), encoding="utf-8")
    monkeypatch.setenv("QDRANT_URL", "https://unused.example")
    monkeypatch.setenv("QDRANT_API_KEY", "test")
    monkeypatch.setenv("STUDENT_RAG_RETRIEVAL_MODE", "vector_only")
    monkeypatch.setattr(sys, "argv", ["live", "--candidate", str(tmp_path), "--env-file", str(tmp_path / "missing.env")])
    def construct(*args):
        assert os.environ["STUDENT_RAG_RETRIEVAL_MODE"] == DEFAULT_RETRIEVAL_MODE
        if failure == "setup":
            raise ValueError("fake setup failure")
        return NS(mongo_store=NS(collection=NS(name="candidate_mongo")), qdrant_client=Mock(),
                  bm25=NS(bm25_index=object()), retrieve=Mock(side_effect=ValueError("fake probe failure")))
    monkeypatch.setattr("scripts.evaluate_table_search_live.ChildParentHybridRetriever", construct)
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    report = json.loads((tmp_path / "live_retrieval_report.json").read_text(encoding="utf-8"))
    assert not report["completed"]
    assert report["execution_error_n"] == (15 if failure == "probes" else 0)
    assert report["not_run_n"] == (0 if failure == "probes" else 15)
    assert report["all_cases_attempted"] == (failure == "probes")
