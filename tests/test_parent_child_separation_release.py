import copy
import json
from pathlib import Path

import pytest

from scripts import build_child_parent_index, push_to_mongo, push_to_qdrant
from scripts.build_artifact_manifest import build_artifact_manifest
from scripts.build_parent_child_artifacts import (
    POLICY,
    artifact_digest,
    separate_tables,
    text_hash,
    validate_publish_separation,
    validate_separation_contract,
)
from tests.test_build_artifact_manifest import _inputs, _write_json
from tests.test_table_separation_candidate import fixture
from src.common.io import sha256_file


def test_reviewed_page_correction_preserves_content_and_updates_children():
    parents, tables, review, _ = fixture()
    parents[0]["metadata"]["source_pages"] = [3, 4, 5]
    review["source_page_corrections"] = [
        {
            "parent_id": "p1",
            "content_sha256": text_hash(parents[0]["content"]),
            "cohort": "K51",
            "document_id": "handbook",
            "original_source_pages": [3, 4, 5],
            "source_pages": [3],
            "review_status": "source_checked",
        }
    ]
    full, narrative, children, audit = separate_tables(parents, tables, review)
    assert parents[0]["metadata"]["source_pages"] == [3, 4, 5]
    assert (
        full[0]["metadata"]["source_pages"]
        == narrative[0]["metadata"]["source_pages"]
        == [3]
    )
    assert all(c["metadata"]["source_pages"] == [3] for c in children)
    assert full[0]["normalized_content"] == full[0]["content"]
    validate_separation_contract(full, children, audit)
    wrong_table_page = copy.deepcopy(review)
    wrong_table_page["source_page_corrections"][0]["source_pages"] = [4]
    with pytest.raises(ValueError, match="excludes a reviewed table"):
        separate_tables(parents, tables, wrong_table_page)
    for key, value in [
        ("content_sha256", "stale"),
        ("source_pages", [7]),
        ("cohort", "K50"),
    ]:
        broken = copy.deepcopy(review)
        broken["source_page_corrections"][0][key] = value
        with pytest.raises(ValueError, match="source-page correction"):
            separate_tables(parents, tables, broken)


def test_legacy_child_command_refuses_display_and_narrative_separated_views(
    tmp_path, monkeypatch
):
    parents, tables, review, _ = fixture()
    full, narrative, _, _ = separate_tables(parents, tables, review)
    for records in [full, narrative]:
        path = tmp_path / "parents.json"
        _write_json(path, records)
        monkeypatch.setattr(
            "sys.argv", ["build_child_parent_index", "--docstore", str(path)]
        )
        with pytest.raises(RuntimeError, match="legacy child CLI"):
            build_child_parent_index.main()
    with pytest.raises(ValueError, match="already separated"):
        separate_tables(full, tables, review)


def separated_inputs(tmp_path):
    inputs = _inputs(tmp_path)
    parents = json.loads(inputs["parent_path"].read_text())
    children = json.loads(inputs["child_path"].read_text())
    for records, role in [(parents, "full_parent"), (children, "narrative_child")]:
        for i, record in enumerate(records):
            record["metadata"].update(
                corpus_role=role,
                table_separation_policy=POLICY,
                cohort=("K48-K49", "K50", "K51")[i],
                document_id=f"handbook-{i}",
                source_pages=[i + 1],
            )
    _write_json(inputs["parent_path"], parents)
    _write_json(inputs["child_path"], children)
    separation = {
        "policy": POLICY,
        "review_sha256": "review-test",
        "artifact_content_sha256": {
            "parent_docstore": artifact_digest(parents),
            "child_chunks": artifact_digest(children),
        },
    }
    audit = {
        "structured_registry_sha256": sha256_file(inputs["table_path"]),
        "child_count": 3,
        "total_table_like_rows": 0,
        "excluded_as_structured": 0,
        "retained_unmatched": 0,
        "ignored_non_content": 0,
        "separation": separation,
    }
    audit_path = tmp_path / "audit.json"
    _write_json(audit_path, audit)
    inputs["table_embedding_audit_path"] = audit_path
    return inputs


def test_manifest_and_both_publishers_validate_pair_without_network(
    tmp_path, monkeypatch
):
    inputs = separated_inputs(tmp_path)
    manifest = build_artifact_manifest(**inputs)
    assert build_artifact_manifest(**inputs)["build_id"] == manifest["build_id"]
    validate_publish_separation(manifest)
    parents = json.loads(inputs["parent_path"].read_text())
    children = json.loads(inputs["child_path"].read_text())
    monkeypatch.setattr(push_to_mongo, "BUILD_MANIFEST_PATH", inputs["output_path"])
    monkeypatch.setattr(push_to_qdrant, "BUILD_MANIFEST_PATH", inputs["output_path"])
    monkeypatch.setattr(push_to_qdrant, "DATA_PATH", inputs["child_path"])
    assert (
        push_to_mongo.validate_build_contract(
            parents,
            docstore_path=inputs["parent_path"],
            collection_name=inputs["mongo_collection"],
        )
        == manifest["build_id"]
    )
    assert (
        push_to_qdrant.validate_build_contract(
            children, collection_name=inputs["qdrant_collection"]
        )
        == manifest["build_id"]
    )
    # Even a Qdrant-only upload must reject a stale Mongo input, and vice versa.
    for path, records, call in [
        (
            inputs["parent_path"],
            parents,
            lambda: push_to_qdrant.validate_build_contract(
                children, collection_name=inputs["qdrant_collection"]
            ),
        ),
        (
            inputs["child_path"],
            children,
            lambda: push_to_mongo.validate_build_contract(
                parents,
                docstore_path=inputs["parent_path"],
                collection_name=inputs["mongo_collection"],
            ),
        ),
    ]:
        old_bytes = path.read_bytes()
        altered = copy.deepcopy(records)
        altered[0]["content"] = "unreviewed replacement"
        _write_json(path, altered)
        with pytest.raises(RuntimeError, match="missing or stale"):
            call()
        path.write_bytes(old_bytes)


def test_manifest_rejects_missing_audit_or_changed_pair(tmp_path):
    inputs = separated_inputs(tmp_path)
    no_audit = dict(inputs, table_embedding_audit_path=None)
    with pytest.raises(RuntimeError, match="require their separation audit"):
        build_artifact_manifest(**no_audit)
    parents = json.loads(inputs["parent_path"].read_text())
    parents[0]["content"] = "changed without rebuilding audit"
    _write_json(inputs["parent_path"], parents)
    with pytest.raises(RuntimeError, match="does not match parent_docstore"):
        build_artifact_manifest(**inputs)


def test_pair_validator_checks_source_identity_even_with_current_hashes(tmp_path):
    inputs = separated_inputs(tmp_path)
    parents = json.loads(inputs["parent_path"].read_text())
    children = json.loads(inputs["child_path"].read_text())
    audit = json.loads(inputs["table_embedding_audit_path"].read_text())["separation"]
    children[0]["metadata"]["source_pages"] = [999]
    audit["artifact_content_sha256"]["child_chunks"] = artifact_digest(children)
    with pytest.raises(RuntimeError, match="source identity"):
        validate_separation_contract(parents, children, audit)


def test_corpus_page_corrections_are_limited_to_two_reviewed_parents():
    def read(path):
        return json.loads(Path(path).read_text(encoding="utf-8"))

    parents = read("tests/fixtures/reviewed_parent_source_snapshot.json")
    tables = read("data/processed/tables/structured_tables_registry.json")
    review = read("data/curated/regulation_table_regions.json")
    full, _, children, audit = separate_tables(parents, tables, review)
    changes = [
        (a["_id"], b["metadata"]["source_pages"])
        for a, b in zip(parents, full)
        if a["metadata"]["source_pages"] != b["metadata"]["source_pages"]
    ]
    assert sorted(pages for _, pages in changes) == [[152], [155]]
    assert len(full) == len(parents) == 18
    assert children
    validate_separation_contract(full, children, audit)
