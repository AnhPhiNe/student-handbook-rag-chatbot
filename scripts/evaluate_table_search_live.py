"""Fifteen live retrieval probes on the published candidate, not answer quality."""
import argparse
import hashlib
import json
import logging
import os
import time
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

from scripts.build_table_search_candidate import ROOT
from scripts.publish_table_search_candidate import prepare_candidate
from src.common.cohort import is_validated_source_applicable
from src.retrieval.core.hybrid_pipeline import ChildParentHybridRetriever
from src.retrieval.core.retrieval_mode import DEFAULT_RETRIEVAL_MODE
from src.retrieval.core.table_search import table_key


def check_results(results: list[dict], case: dict, prepared: dict) -> dict:
    """Check exact source/table hydration and authorization, not answer semantics."""
    source_path = ROOT / prepared["source"]["artifacts"]["structured_tables"]["path"]
    tables = json.loads(source_path.read_text(encoding="utf-8"))
    expected = {t["source_parent_id"] for t in tables if t["cohort"] == case["source_cohort"]
                and t["table_subtype"] == case["table_subtype"]}
    expected_keys = {table_key(t) for t in tables if t["cohort"] == case["source_cohort"]
                     and t["table_subtype"] == case["table_subtype"]}
    parents = {p["_id"]: p for p in prepared["parents"]}
    seen, hydrated = [], []
    leaks, incorrect_parents, incorrect_tables = 0, 0, 0
    for result in results:
        parent_id = result["chunk_id"]
        seen.append(parent_id)
        parent = parents.get(parent_id)
        if parent is None or result["document"] != parent["content"]:
            incorrect_parents += 1
            continue
        if not is_validated_source_applicable(result, case["cohort"]):
            leaks += 1
        metadata = result["metadata"]
        parent_metadata = parent.get("metadata") or {}
        runtime_fields = {"chunk_id", "chunk_type", "content_type", "chunk_granularity", "retrieval_role"}
        scope_fields = {"cohort", "source_cohort", "document_id", "applicable_cohorts",
                        "applicability_validated", "applicability_basis_parent_id", "applicability"}
        if (metadata.get("collection") != prepared["manifest"]["storage_targets"]["qdrant_collection"]
                or metadata.get("parent_source") != "mongodb"
                or any(metadata.get(field) != parent_metadata.get(field) for field in
                       (set(parent_metadata) | scope_fields) - runtime_fields)
                or any(result.get(field) != parent.get(field) for field in scope_fields)):
            incorrect_parents += 1
        context = metadata.get("raw_table_context")
        if not context:
            continue
        for raw in json.loads(context)["tables"]:
            table = next((t for t in tables if t["source_parent_id"] == parent_id and t["table_id"] == raw["table_id"]), None)
            if (table is None or raw != {field: table.get(field) for field in
                                        ("table_id", "table_name", "cohort", "applicability", "columns", "rows")}
                    or not is_validated_source_applicable(table, case["cohort"])):
                incorrect_tables += 1
            else:
                hydrated.append(table_key(table))
    telemetry = results[0]["metadata"].get("retrieval_telemetry", {}) if results else {}
    return {"parent_hit_at_5": bool(expected.intersection(seen[:5])), "parent_ids": seen,
            "expected_table_family_hydrated": bool(expected_keys.intersection(hydrated)),
            "hydrated_table_keys": hydrated, "cross_cohort_leaks": leaks,
            "incorrect_parent_sources": incorrect_parents, "incorrect_raw_tables": incorrect_tables,
            "dense_failed": telemetry.get("dense_failed"), "dense_candidate_n": telemetry.get("qdrant_seed_chunks", 0),
            "reranker_applied": telemetry.get("reranker_applied", False),
            "reranker_fallback_reason": telemetry.get("reranker_fallback_reason"),
            "foreign_language_policy_parent_present": any("QuyDinhChuanDauRaNgoaiNgu" in p and p.endswith("_Dieu4") for p in seen)
                if case["table_subtype"] == "foreign_language_equivalency" else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args()
    prepared = prepare_candidate(ROOT, args.candidate)
    directory = prepared["directory"]
    published = json.loads((directory / "publication_report.json").read_text(encoding="utf-8"))
    if not published.get("completed") or published["storage_targets"] != prepared["manifest"]["storage_targets"]:
        raise ValueError("Only the exactly verified candidate may be tested")
    path = directory / "live_retrieval_report.json"
    if path.exists():
        raise FileExistsError("Preserve existing live report")
    fixture = ROOT / "tests/fixtures/table_search_development.json"
    cases = json.loads(fixture.read_text(encoding="utf-8"))
    if cases["source_build_id"] != prepared["source"]["build_id"] or len(cases["cases"]) != 15:
        raise ValueError("Live probes require the frozen 15-case development suite")
    load_dotenv(args.env_file, override=False)
    targets = prepared["manifest"]["storage_targets"]
    os.environ.update(MONGODB_PARENT_COLLECTION=targets["mongo_parent_collection"],
                      MONGODB_PARENT_LOOKUP_ENABLED="true", QDRANT_COLLECTION_NAME=targets["qdrant_collection"],
                      STUDENT_RAG_HYBRID_COLLECTION=targets["qdrant_collection"],
                      STUDENT_RAG_RETRIEVAL_CONFIG=str(directory / "retrieval.yaml"),
                      STUDENT_RAG_RETRIEVAL_MODE=DEFAULT_RETRIEVAL_MODE)
    logging.disable(logging.CRITICAL)
    report = {"suite": "table-search-live-development-retrieval", "answer_quality_measured": False,
              "planner_composer_calls": 0, "storage_targets": targets, "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
              "requested_n": 15, "cases": [], "retrieval_mode": DEFAULT_RETRIEVAL_MODE}
    retriever = None
    try:
        retriever = ChildParentHybridRetriever(os.environ["QDRANT_URL"], os.environ["QDRANT_API_KEY"],
                                               targets["qdrant_collection"], prepared["config"])
        if retriever.mongo_store.collection.name != targets["mongo_parent_collection"]:
            raise ValueError("Live test must read the candidate MongoDB collection")
        deadline = time.monotonic() + 180
        while retriever.bm25.bm25_index is None:
            if time.monotonic() >= deadline:
                raise TimeoutError("Candidate BM25 did not become ready")
            time.sleep(0.5)
        for index, case in enumerate(cases["cases"], 1):
            started = time.perf_counter()
            try:
                results = retriever.retrieve(case["query"], top_k_final=5, graph_depth=0, cohort=case["cohort"])
                row = {**case, **check_results(results, case, prepared)}
            except Exception as exc:
                row = {**case, "error_type": type(exc).__name__, "parent_hit_at_5": False}
            row["latency_ms"] = (time.perf_counter() - started) * 1000
            report["cases"].append(row)
            print(f"Retrieval {index}/15 {case['id']}: parent_hit={row['parent_hit_at_5']}", flush=True)
    except Exception as exc:
        report["setup_error_type"] = type(exc).__name__
    finally:
        if retriever is not None:
            retriever.qdrant_client.close()
            if hasattr(retriever.mongo_store, "client"):
                retriever.mongo_store.client.close()
        rows = report["cases"]
        execution_errors = sum("error_type" in r for r in rows)
        report.update(completed=len(rows) == 15 and execution_errors == 0 and "setup_error_type" not in report,
                      all_cases_attempted=len(rows) == 15, n=len(rows), not_run_n=15 - len(rows),
                      parent_hits_at_5=sum(r["parent_hit_at_5"] for r in rows),
                      expected_table_family_hydrated_n=sum(r.get("expected_table_family_hydrated", False) for r in rows),
                      cross_cohort_leaks=sum(r.get("cross_cohort_leaks", 0) for r in rows),
                      incorrect_parent_sources=sum(r.get("incorrect_parent_sources", 0) for r in rows),
                      incorrect_raw_tables=sum(r.get("incorrect_raw_tables", 0) for r in rows),
                      dense_success_n=sum(r.get("dense_candidate_n", 0) > 0 and not r.get("dense_failed") for r in rows),
                      reranker_applied_n=sum(r.get("reranker_applied", False) for r in rows),
                      execution_error_n=execution_errors,
                      retrieval_p95_ms=float(np.percentile([r["latency_ms"] for r in rows], 95)) if rows else None)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "cases"}, ensure_ascii=False, indent=2))
    if (not report["completed"] or report["cross_cohort_leaks"] or report["incorrect_parent_sources"]
            or report["incorrect_raw_tables"]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
