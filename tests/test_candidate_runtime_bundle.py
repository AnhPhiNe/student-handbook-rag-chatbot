"""Portable candidate deployment without changing source data or calling services."""
import copy
import json
from pathlib import Path

import pytest
import yaml

from scripts.build_candidate_runtime_bundle import build_runtime_bundle, DESCRIPTIONS_PATH
from scripts.build_table_search_candidate import ROOT, build_candidate
from scripts.build_parent_child_artifacts import validate_publish_separation
from scripts.check_deploy_artifacts import validate_build_manifest
from scripts.verify_remote_build import indexed_record_count
from src.retrieval.core.table_search import load_table_search
from src.retrieval.runtime_config import load_retrieval_build_contract
from src.api.routes.health import _build_manifest_matches_environment


def candidate(tmp_path):
    directory = tmp_path / "frozen"
    record = build_candidate(ROOT, directory, ROOT / "configs/table_search_descriptions.yaml")
    production = {"student_handbook_table_search_f3c77e0908bc": 3835, "parent_docs_table_search_f3c77e0908bc": 541}
    publication = {"completed": True, "stage": "complete", "storage_targets": record["storage_targets"],
                   "model": record["embedding"]["model"], "baseline_before": production,
                   "baseline_after": production,
                   "verification": {"verified_vectors": 2843, "verified_parents": 541, "dimension": 1024,
                                    "distance": "Cosine", "payload_mismatches": 0, "vector_mismatches": 0,
                                    "parent_mismatches": 0}}
    (directory / "publication_report.json").write_text(json.dumps(publication), encoding="utf-8")
    return directory, record


def test_portable_overlay_keeps_sources_and_runtime_manifest_consistent(tmp_path, monkeypatch):
    directory, frozen = candidate(tmp_path)
    before = {p: p.read_bytes() for p in (ROOT / "data/processed/metadata/build_manifest.json",
                                        ROOT / "configs/retrieval.yaml", ROOT / ".env.example")}
    output = tmp_path / "runtime"
    report = build_runtime_bundle(ROOT, directory, output)
    assert report["indexed_record_count"] == 2843 and report["narrative_child_count"] == 2811
    assert report["description_count"] == 32 and report["parent_count"] == 541
    assert report["model_calls"] == report["remote_writes"] == 0 and not report["remote_reverified"]
    manifest = json.loads((output / "data/processed/metadata/build_manifest.json").read_text(encoding="utf-8"))
    config = yaml.safe_load((output / "configs/retrieval.yaml").read_text(encoding="utf-8"))
    registry = config["retrieval"]["table_search"]["registry_path"]
    assert registry == "data/processed/tables/structured_tables_registry.json"
    assert manifest["build_id"] == frozen["source_build_id"]
    assert manifest["storage_targets"] == frozen["storage_targets"]
    assert indexed_record_count(manifest) == 2843
    assert (output / DESCRIPTIONS_PATH).read_bytes() == Path(frozen["artifacts"]["table_descriptions"]["path"]).read_bytes()
    for name, artifact in manifest["artifacts"].items():
        if name != "table_search_descriptions":
            assert (output / artifact["path"]).read_bytes() == (ROOT / artifact["path"]).read_bytes()
    for name, value in report["release_env"].items():
        monkeypatch.setenv(name, value)
    monkeypatch.chdir(output)
    assert validate_build_manifest() == []
    validate_publish_separation(manifest)  # Narrative audit still means narrative, not summaries.
    contract = load_retrieval_build_contract()
    assert contract["qdrant_collection"] == frozen["storage_targets"]["qdrant_collection"]
    assert contract["mongo_parent_collection"] == frozen["storage_targets"]["mongo_parent_collection"]
    assert _build_manifest_matches_environment()
    assert len(load_table_search(config["retrieval"]["table_search"], contract["qdrant_collection"])) == 35  # registry keeps all tables
    assert {p: p.read_bytes() for p in before} == before


def test_overlay_can_replace_only_the_deploy_scripts_identical_baseline_copy(tmp_path):
    directory, _ = candidate(tmp_path)
    output = tmp_path / "runtime"
    for relative in ("data/processed/metadata/build_manifest.json", "configs/retrieval.yaml"):
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    build_runtime_bundle(ROOT, directory, output)
    preserved = (output / "data/processed/metadata/build_manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        build_runtime_bundle(ROOT, directory, output)
    assert (output / "data/processed/metadata/build_manifest.json").read_bytes() == preserved


@pytest.mark.parametrize("mutation", ["incomplete", "targets", "vector_mismatch", "count", "dimension", "baseline"])
def test_invalid_publication_does_not_write_bundle(tmp_path, mutation):
    directory, _ = candidate(tmp_path)
    path = directory / "publication_report.json"
    published = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "incomplete":
        published["completed"] = False
    elif mutation == "targets":
        published["storage_targets"]["qdrant_collection"] = "student_handbook_semantic_v35"
    elif mutation == "vector_mismatch":
        published["verification"]["vector_mismatches"] = 1
    elif mutation == "count":
        published["verification"]["verified_vectors"] = 3800
    elif mutation == "dimension":
        published["verification"]["dimension"] = 768
    else:
        published.pop("baseline_before")
        published.pop("baseline_after")
    path.write_text(json.dumps(published), encoding="utf-8")
    output = tmp_path / "runtime"
    with pytest.raises(ValueError):
        build_runtime_bundle(ROOT, directory, output)
    assert not output.exists()


@pytest.mark.parametrize("where", ["source", "candidate"])
def test_bundle_refuses_protected_and_frozen_destinations(tmp_path, where):
    directory, _ = candidate(tmp_path)
    output = ROOT / "data/processed" if where == "source" else directory
    with pytest.raises(ValueError):
        build_runtime_bundle(ROOT, directory, output)


def test_manifest_count_retains_v35_and_rejects_malformed_extensions():
    manifest = {"artifacts": {"child_chunks": {"count": 3800}, "table_search_descriptions": {"count": 35}}}
    assert indexed_record_count(manifest) == 3800
    manifest["index_contract"] = {"indexed_artifacts": ["child_chunks", "table_search_descriptions"]}
    assert indexed_record_count(manifest) == 3835
    for names in ([], ["child_chunks", "child_chunks"], ["child_chunks", "unknown"], [True], [["nested"]]):
        malformed = copy.deepcopy(manifest)
        malformed["index_contract"]["indexed_artifacts"] = names
        with pytest.raises(RuntimeError):
            indexed_record_count(malformed)
    for count in (0, -1, True, "35"):
        malformed = copy.deepcopy(manifest)
        malformed["artifacts"]["table_search_descriptions"]["count"] = count
        with pytest.raises(RuntimeError):
            indexed_record_count(malformed)


def test_portable_package_readiness_accepts_the_new_identity_without_services(tmp_path, monkeypatch):
    from src.api.routes import health
    from src.common.runtime_artifacts import RUNTIME_FILES
    directory, _ = candidate(tmp_path)
    output = tmp_path / "runtime"
    report = build_runtime_bundle(ROOT, directory, output)
    for relative in RUNTIME_FILES:
        path = output / relative
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((ROOT / relative).read_bytes())
    for name in health.REQUIRED_ENV_VARS:
        monkeypatch.setenv(name, "not-a-real-credential")
    for name, value in report["release_env"].items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("STUDENT_RAG_RETRIEVAL_MODE", "vector_primary_graph_supplement")
    monkeypatch.chdir(output)
    monkeypatch.setattr(health, "get_dependency_runtime_statuses", lambda: {
        "qdrant": {"status": "ready"}, "mongodb": {"status": "ready"}})
    monkeypatch.setattr(health, "get_bm25_runtime_status", lambda: {"status": "ready", "attempts": 1})
    response = health.readiness()
    assert response.ready and response.missing_count == 0


def test_deploy_option_is_explicit_and_hashed_description_bytes_are_preserved():
    script = (ROOT / "scripts/deploy_hf_backend.ps1").read_text(encoding="utf-8")
    assert "$CandidateArtifacts" in script and "scripts.build_candidate_runtime_bundle" in script
    assert 'ContainsKey("QdrantCollection")' in script and 'ContainsKey("MongoCollection")' in script
    assert "Real deployment requires a clean source worktree" in script
    assert "!" + DESCRIPTIONS_PATH in (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert DESCRIPTIONS_PATH + " -text" in (ROOT / ".gitattributes").read_text(encoding="utf-8")
