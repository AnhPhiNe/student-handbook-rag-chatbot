from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_artifact_manifest import build_artifact_manifest


COHORTS = ("K48-K49", "K50", "K51")


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _inputs(tmp_path: Path) -> dict[str, object]:
    pdf_paths = []
    for index, cohort in enumerate(COHORTS, start=1):
        path = tmp_path / f"handbook-{index}.pdf"
        path.write_bytes(f"pdf-{cohort}".encode())
        pdf_paths.append(path)

    parent_path = tmp_path / "parents.json"
    child_path = tmp_path / "children.json"
    table_path = tmp_path / "tables.json"
    graph_path = tmp_path / "graph.json"
    output_path = tmp_path / "build_manifest.json"
    parents = [
        {"_id": f"parent-{index}", "cohort": cohort, "metadata": {}}
        for index, cohort in enumerate(COHORTS, start=1)
    ]
    children = [
        {
            "_id": f"child-{index}",
            "content": f"content-{index}",
            "metadata": {
                "cohort": cohort,
                "parent_section_id": f"parent-{index}",
            },
        }
        for index, cohort in enumerate(COHORTS, start=1)
    ]
    _write_json(parent_path, parents)
    _write_json(child_path, children)
    _write_json(table_path, [{"table_id": "table-1", "cohort": "K51"}])
    _write_json(graph_path, [{"source": "parent-1", "target": "parent-2"}])
    return {
        "pdf_paths": pdf_paths,
        "parent_path": parent_path,
        "child_path": child_path,
        "table_path": table_path,
        "graph_path": graph_path,
        "output_path": output_path,
        "qdrant_collection": "student_handbook_semantic_v30",
        "mongo_collection": "parent_docs_v30",
    }


def test_manifest_is_deterministic_and_tags_parent_child_artifacts(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    first = build_artifact_manifest(**inputs)
    second = build_artifact_manifest(**inputs)

    assert first["build_id"] == second["build_id"]
    assert first["storage_targets"] == {
        "qdrant_collection": "student_handbook_semantic_v30",
        "mongo_parent_collection": "parent_docs_v30",
    }
    assert first["artifacts"]["parent_docstore"]["count"] == 3
    assert first["artifacts"]["child_chunks"]["count"] == 3

    parents = json.loads(Path(inputs["parent_path"]).read_text(encoding="utf-8"))
    children = json.loads(Path(inputs["child_path"]).read_text(encoding="utf-8"))
    assert {item["build_id"] for item in parents} == {first["build_id"]}
    assert {item["metadata"]["build_id"] for item in parents} == {
        first["build_id"]
    }
    assert {item["metadata"]["build_id"] for item in children} == {
        first["build_id"]
    }


def test_manifest_identity_changes_when_source_artifact_changes(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    first = build_artifact_manifest(**inputs)
    parents_path = Path(inputs["parent_path"])
    parents = json.loads(parents_path.read_text(encoding="utf-8"))
    parents[0]["content"] = "changed"
    _write_json(parents_path, parents)

    second = build_artifact_manifest(**inputs)
    assert second["build_id"] != first["build_id"]


def test_manifest_rejects_orphan_child(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    child_path = Path(inputs["child_path"])
    children = json.loads(child_path.read_text(encoding="utf-8"))
    children[0]["metadata"]["parent_section_id"] = "missing-parent"
    _write_json(child_path, children)

    with pytest.raises(RuntimeError, match="orphan parent ids"):
        build_artifact_manifest(**inputs)


def test_manifest_requires_all_three_cohorts(tmp_path: Path) -> None:
    inputs = _inputs(tmp_path)
    child_path = Path(inputs["child_path"])
    children = json.loads(child_path.read_text(encoding="utf-8"))
    children[0]["metadata"]["cohort"] = "K51"
    _write_json(child_path, children)

    with pytest.raises(RuntimeError, match="must both contain exactly"):
        build_artifact_manifest(**inputs)


def test_manifest_binds_table_embedding_audit_to_registry_and_build(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    table_path = Path(inputs["table_path"])
    child_path = Path(inputs["child_path"])
    audit_path = tmp_path / "table_embedding_audit.json"
    from scripts.build_artifact_manifest import sha256_file

    _write_json(
        audit_path,
        {
            "schema_version": "structured-table-embedding-audit-v1",
            "structured_registry_sha256": sha256_file(table_path),
            "child_count": len(json.loads(child_path.read_text(encoding="utf-8"))),
            "total_table_like_rows": 3,
            "excluded_as_structured": 2,
            "retained_unmatched": 1,
            "ignored_non_content": 0,
            "rows": [],
        },
    )
    inputs["table_embedding_audit_path"] = audit_path

    manifest = build_artifact_manifest(**inputs)
    persisted_audit = json.loads(audit_path.read_text(encoding="utf-8"))

    assert persisted_audit["build_id"] == manifest["build_id"]
    assert manifest["index_contract"]["covered_table_rows_indexed_in_qdrant"] is False
    assert manifest["artifacts"]["table_embedding_audit"][
        "retained_unmatched"
    ] == 1


def test_manifest_rejects_table_embedding_audit_for_other_registry(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    audit_path = tmp_path / "table_embedding_audit.json"
    _write_json(
        audit_path,
        {
            "structured_registry_sha256": "wrong",
            "child_count": 3,
            "total_table_like_rows": 0,
            "excluded_as_structured": 0,
            "retained_unmatched": 0,
            "ignored_non_content": 0,
        },
    )
    inputs["table_embedding_audit_path"] = audit_path

    with pytest.raises(RuntimeError, match="structured registry hash"):
        build_artifact_manifest(**inputs)
