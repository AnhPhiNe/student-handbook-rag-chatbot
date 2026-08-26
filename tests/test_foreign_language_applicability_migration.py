from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.migrate_foreign_language_applicability import (
    RETIRE_METADATA,
    apply_migration,
    build_local_manifest,
    inventory_cloud,
    load_backup,
    rollback_from_backup,
    validate_inventory,
    verify_applied,
    write_backup,
)
from scripts.push_to_qdrant import string_to_uuid


SOURCE_ID = "K50_QuyDinhChuanDauRaNgoaiNgu_KhongCoChuong_Dieu1"
CLONE_ID = "K51_QuyDinhChuanDauRaNgoaiNgu_KhongCoChuong_Dieu1"
CHILD_ID = f"{SOURCE_ID}_child_0"


def _source_document() -> dict:
    return {
        "_id": SOURCE_ID,
        "content": "Điều 1. Phạm vi áp dụng",
        "document_id": "so_tay_sinh_vien_khoa_50",
        "metadata": {
            "cohort": "K50",
            "document_id": "so_tay_sinh_vien_khoa_50",
            "document_title": (
                "Quy định tổ chức dạy học và công nhận đạt chuẩn đầu ra "
                "ngoại ngữ cho sinh viên tốt nghiệp các ngành đào tạo trình "
                "độ đại học của Trường Đại học Sư phạm Thành phố Hồ Chí Minh"
            ),
            "source_file": "QuyDinhChuanDauRaNgoaiNgu.pdf",
            "doc_type": "QuyDinhChuanDauRaNgoaiNgu",
        },
    }


def _clone_document() -> dict:
    return {
        "_id": CLONE_ID,
        "content": "Điều 1. Phạm vi áp dụng",
        "metadata": {
            "cohort": "K51",
            "source_cohort": "K50",
            "derived_from_cohort": "K50",
            "derivation_method": "foreign_language_policy_from_k50",
            "source_file": "QuyDinhChuanDauRaNgoaiNgu.pdf",
            "doc_type": "QuyDinhChuanDauRaNgoaiNgu",
        },
    }


def _child() -> dict:
    return {
        "_id": CHILD_ID,
        "metadata": {"parent_section_id": SOURCE_ID},
    }


def _point(point_id: str, chunk_id: str, parent_id: str) -> dict:
    return {
        "id": point_id,
        "payload": {"chunk_id": chunk_id, "parent_section_id": parent_id},
    }


class FakeMongoCollection:
    name = "parents"

    def __init__(self, documents: list[dict]) -> None:
        self.documents = {item["_id"]: deepcopy(item) for item in documents}
        self.update_filters: list[dict] = []

    def find(self, query: dict) -> list[dict]:
        ids = query["_id"]["$in"]
        return [deepcopy(self.documents[item_id]) for item_id in ids if item_id in self.documents]

    def update_many(self, query: dict, update: dict) -> None:
        self.update_filters.append(deepcopy(query))
        for item_id in query["_id"]["$in"]:
            document = self.documents[item_id]
            for dotted_key, value in update["$set"].items():
                target = document
                parts = dotted_key.split(".")
                for part in parts[:-1]:
                    target = target.setdefault(part, {})
                target[parts[-1]] = deepcopy(value)

    def replace_one(self, query: dict, document: dict, *, upsert: bool) -> None:
        assert upsert is False
        self.documents[query["_id"]] = deepcopy(document)


class FakeQdrant:
    def __init__(self, points: list[dict]) -> None:
        self.points = {item["id"]: deepcopy(item["payload"]) for item in points}
        self.writes: list[tuple[str, tuple[str, ...]]] = []

    def scroll(self, **kwargs):
        parents = set(kwargs["scroll_filter"].must[0].match.any)
        matches = [
            SimpleNamespace(id=point_id, payload=deepcopy(payload))
            for point_id, payload in self.points.items()
            if payload.get("parent_section_id") in parents
        ]
        return matches, None

    def set_payload(self, *, payload: dict, points: list[str], **kwargs) -> None:
        self.writes.append(("set", tuple(points)))
        for point_id in points:
            self.points[point_id].update(deepcopy(payload))

    def overwrite_payload(self, *, payload: dict, points: list[str], **kwargs) -> None:
        self.writes.append(("overwrite", tuple(points)))
        for point_id in points:
            self.points[point_id] = deepcopy(payload)


def _manifest():
    return build_local_manifest([_source_document()], [_child()])


def _cloud(*, include_clone: bool = True):
    documents = [_source_document()]
    points = [_point(string_to_uuid(CHILD_ID), CHILD_ID, SOURCE_ID)]
    if include_clone:
        documents.append(_clone_document())
        points.append(_point("clone-point", "clone-child", CLONE_ID))
    return FakeMongoCollection(documents), FakeQdrant(points)


def test_manifest_uses_exact_parent_child_and_point_allow_lists() -> None:
    manifest = build_local_manifest(
        [_source_document(), {"_id": "K50_unrelated", "metadata": {}}],
        [_child(), {"_id": "other", "metadata": {"parent_section_id": "K50_unrelated"}}],
    )

    assert manifest.source_parent_ids == (SOURCE_ID,)
    assert manifest.source_child_ids == (CHILD_ID,)
    assert manifest.source_point_ids == (string_to_uuid(CHILD_ID),)
    assert CLONE_ID in manifest.clone_parent_ids
    assert manifest.applicability["applicable_cohorts"] == ["K48-K49", "K50", "K51"]


def test_inventory_is_read_only_and_scoped_to_manifest() -> None:
    mongo, qdrant = _cloud()
    inventory = inventory_cloud(mongo, qdrant, "children", _manifest())

    assert [item["_id"] for item in inventory.source_documents] == [SOURCE_ID]
    assert [item["_id"] for item in inventory.clone_documents] == [CLONE_ID]
    assert mongo.update_filters == []
    assert qdrant.writes == []


def test_validation_rejects_unverified_clone() -> None:
    mongo, qdrant = _cloud()
    mongo.documents[CLONE_ID]["metadata"].pop("derived_from_cohort")
    inventory = inventory_cloud(mongo, qdrant, "children", _manifest())

    with pytest.raises(RuntimeError, match="unverified clone"):
        validate_inventory(_manifest(), inventory)


def test_validation_rejects_missing_source_child() -> None:
    mongo, qdrant = _cloud(include_clone=False)
    qdrant.points.clear()
    inventory = inventory_cloud(mongo, qdrant, "children", _manifest())

    with pytest.raises(RuntimeError, match="Qdrant source child IDs differ"):
        validate_inventory(_manifest(), inventory)


def test_apply_is_scoped_and_retires_verified_clones() -> None:
    unrelated = {"_id": "unrelated", "content": "keep", "metadata": {"cohort": "K50"}}
    mongo, qdrant = _cloud()
    mongo.documents["unrelated"] = deepcopy(unrelated)
    manifest = _manifest()
    before = inventory_cloud(mongo, qdrant, "children", manifest)

    validate_inventory(manifest, before)
    apply_migration(mongo, qdrant, "children", manifest, before)
    after = inventory_cloud(mongo, qdrant, "children", manifest)
    verify_applied(manifest, after)

    assert mongo.documents["unrelated"] == unrelated
    assert mongo.documents[SOURCE_ID]["content"] == _source_document()["content"]
    assert mongo.documents[CLONE_ID]["metadata"]["migration_status"] == "retired"
    assert qdrant.points["clone-point"]["content_type"] == RETIRE_METADATA["content_type"]


def test_apply_is_state_idempotent() -> None:
    mongo, qdrant = _cloud()
    manifest = _manifest()
    before = inventory_cloud(mongo, qdrant, "children", manifest)
    apply_migration(mongo, qdrant, "children", manifest, before)
    state_once = (deepcopy(mongo.documents), deepcopy(qdrant.points))
    current = inventory_cloud(mongo, qdrant, "children", manifest)
    apply_migration(mongo, qdrant, "children", manifest, current)

    assert (mongo.documents, qdrant.points) == state_once


def test_backup_hash_and_rollback_restore_exact_state(tmp_path: Path, monkeypatch) -> None:
    mongo, qdrant = _cloud()
    manifest = _manifest()
    before = inventory_cloud(mongo, qdrant, "children", manifest)
    original = (deepcopy(mongo.documents), deepcopy(qdrant.points))
    monkeypatch.setattr(
        "scripts.migrate_foreign_language_applicability._git_commit", lambda: "abc123"
    )
    backup_path = tmp_path / "backup.json"

    write_backup(
        backup_path,
        mongo_collection_name=mongo.name,
        qdrant_collection_name="children",
        manifest=manifest,
        inventory=before,
    )
    apply_migration(mongo, qdrant, "children", manifest, before)
    rollback_from_backup(mongo, qdrant, "children", load_backup(backup_path))

    assert (mongo.documents, qdrant.points) == original


def test_tampered_backup_is_rejected(tmp_path: Path, monkeypatch) -> None:
    mongo, qdrant = _cloud(include_clone=False)
    manifest = _manifest()
    monkeypatch.setattr(
        "scripts.migrate_foreign_language_applicability._git_commit", lambda: "abc123"
    )
    backup_path = tmp_path / "backup.json"
    write_backup(
        backup_path,
        mongo_collection_name=mongo.name,
        qdrant_collection_name="children",
        manifest=manifest,
        inventory=inventory_cloud(mongo, qdrant, "children", manifest),
    )
    backup_path.write_text(backup_path.read_text(encoding="utf-8") + " ", encoding="utf-8")

    # Whitespace does not affect the canonical payload, so alter an actual value.
    text = backup_path.read_text(encoding="utf-8").replace("abc123", "def456")
    backup_path.write_text(text, encoding="utf-8")
    with pytest.raises(RuntimeError, match="hash validation failed"):
        load_backup(backup_path)
