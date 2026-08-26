from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bson import json_util
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.derive_foreign_language_policy import (
    SOURCE_COHORT,
    _is_derived_from_source,
    _is_source_policy_item,
    foreign_language_applicability_metadata,
)
from scripts.push_to_qdrant import string_to_uuid
from src.common.env_loader import load_project_env
from src.retrieval.vectorstore.mongo_store import get_mongo_store


DEFAULT_DOCSTORE = Path("data/processed/chunks/all_docstore_items.json")
DEFAULT_CHILDREN = Path("data/processed/chunks/child_parent_chunks.json")
DEFAULT_BACKUP_ROOT = Path("tmp/migrations/foreign_language_applicability")
RETIRE_METADATA = {
    "content_type": "retired_regulation_text",
    "migration_status": "retired",
    "retired_reason": "replaced_by_source_applicability_metadata",
}
CLONE_COHORTS = ("K48-K49", "K51")


@dataclass(frozen=True)
class LocalManifest:
    source_parent_ids: tuple[str, ...]
    source_child_ids: tuple[str, ...]
    source_point_ids: tuple[str, ...]
    clone_parent_ids: tuple[str, ...]
    applicability: dict[str, Any]


@dataclass
class CloudInventory:
    source_documents: list[dict[str, Any]]
    clone_documents: list[dict[str, Any]]
    source_points: list[dict[str, Any]]
    clone_points: list[dict[str, Any]]


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise RuntimeError(f"Expected a list of objects in {path}")
    return payload


def build_local_manifest(
    docstore_items: list[dict[str, Any]],
    child_items: list[dict[str, Any]],
) -> LocalManifest:
    source_parent_ids = sorted(
        str(item.get("_id") or "")
        for item in docstore_items
        if _is_source_policy_item(item)
    )
    if not source_parent_ids or any(not item_id for item_id in source_parent_ids):
        raise RuntimeError("No valid source foreign-language policy parents found.")
    if any(not item_id.startswith(f"{SOURCE_COHORT}_") for item_id in source_parent_ids):
        raise RuntimeError("Source policy parent IDs do not use the expected K50 prefix.")

    parent_set = set(source_parent_ids)
    source_child_ids = sorted(
        str(item.get("_id") or item.get("chunk_id") or "")
        for item in child_items
        if str((item.get("metadata") or {}).get("parent_section_id") or "")
        in parent_set
    )
    if not source_child_ids or any(not item_id for item_id in source_child_ids):
        raise RuntimeError("No valid child chunks found for the source policy parents.")

    clone_parent_ids = sorted(
        source_id.replace(f"{SOURCE_COHORT}_", f"{cohort}_", 1)
        for source_id in source_parent_ids
        for cohort in CLONE_COHORTS
    )
    return LocalManifest(
        source_parent_ids=tuple(source_parent_ids),
        source_child_ids=tuple(source_child_ids),
        source_point_ids=tuple(string_to_uuid(item_id) for item_id in source_child_ids),
        clone_parent_ids=tuple(clone_parent_ids),
        applicability=foreign_language_applicability_metadata(),
    )


def _scroll_by_parent_ids(
    client: Any,
    collection_name: str,
    parent_ids: tuple[str, ...],
) -> list[dict[str, Any]]:
    if not parent_ids:
        return []
    points: list[dict[str, Any]] = []
    offset: Any = None
    while True:
        batch, offset = client.scroll(
            collection_name=collection_name,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="parent_section_id",
                        match=MatchAny(any=list(parent_ids)),
                    )
                ]
            ),
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        points.extend(
            {"id": str(point.id), "payload": dict(point.payload or {})}
            for point in batch
        )
        if offset is None:
            return points


def inventory_cloud(
    mongo_collection: Any,
    qdrant_client: Any,
    collection_name: str,
    manifest: LocalManifest,
) -> CloudInventory:
    source_documents = list(
        mongo_collection.find({"_id": {"$in": list(manifest.source_parent_ids)}})
    )
    clone_documents = list(
        mongo_collection.find({"_id": {"$in": list(manifest.clone_parent_ids)}})
    )
    source_points = _scroll_by_parent_ids(
        qdrant_client, collection_name, manifest.source_parent_ids
    )
    clone_points = _scroll_by_parent_ids(
        qdrant_client, collection_name, manifest.clone_parent_ids
    )
    return CloudInventory(
        source_documents=source_documents,
        clone_documents=clone_documents,
        source_points=source_points,
        clone_points=clone_points,
    )


def validate_inventory(manifest: LocalManifest, inventory: CloudInventory) -> None:
    mongo_source_ids = {str(item.get("_id") or "") for item in inventory.source_documents}
    if mongo_source_ids != set(manifest.source_parent_ids):
        raise RuntimeError(
            "Mongo source parent IDs differ from the local allow-list: "
            f"expected={len(manifest.source_parent_ids)} actual={len(mongo_source_ids)}"
        )

    qdrant_child_ids = {
        str((point.get("payload") or {}).get("chunk_id") or "")
        for point in inventory.source_points
    }
    if qdrant_child_ids != set(manifest.source_child_ids):
        raise RuntimeError(
            "Qdrant source child IDs differ from the local allow-list: "
            f"expected={len(manifest.source_child_ids)} actual={len(qdrant_child_ids)}"
        )

    confirmed_clone_ids: set[str] = set()
    for item in inventory.clone_documents:
        item_id = str(item.get("_id") or "")
        if item_id not in manifest.clone_parent_ids or not _is_derived_from_source(item):
            raise RuntimeError(f"Refusing to retire an unverified clone candidate: {item_id}")
        confirmed_clone_ids.add(item_id)

    qdrant_clone_parent_ids = {
        str((point.get("payload") or {}).get("parent_section_id") or "")
        for point in inventory.clone_points
    }
    if not qdrant_clone_parent_ids.issubset(confirmed_clone_ids):
        unexpected = sorted(qdrant_clone_parent_ids - confirmed_clone_ids)
        raise RuntimeError(
            "Qdrant clone points have no verified derived Mongo parent: "
            + ", ".join(unexpected[:10])
        )


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def write_backup(
    path: Path,
    *,
    mongo_collection_name: str,
    qdrant_collection_name: str,
    manifest: LocalManifest,
    inventory: CloudInventory,
) -> str:
    payload = {
        "schema_version": "foreign-language-applicability-backup-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evaluated_commit": _git_commit(),
        "mongo_collection": mongo_collection_name,
        "qdrant_collection": qdrant_collection_name,
        "manifest": asdict(manifest),
        "mongo_documents": inventory.source_documents + inventory.clone_documents,
        "qdrant_points": inventory.source_points + inventory.clone_points,
    }
    canonical = json_util.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    digest = hashlib.sha256(canonical).hexdigest()
    output = {**payload, "payload_sha256": digest}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_util.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    return digest


def load_backup(path: Path) -> dict[str, Any]:
    backup = json_util.loads(path.read_text(encoding="utf-8"))
    expected_digest = str(backup.pop("payload_sha256", ""))
    canonical = json_util.dumps(
        backup, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    actual_digest = hashlib.sha256(canonical).hexdigest()
    if not expected_digest or actual_digest != expected_digest:
        raise RuntimeError("Migration backup hash validation failed.")
    backup["payload_sha256"] = expected_digest
    return backup


def _source_mongo_set(applicability: dict[str, Any]) -> dict[str, Any]:
    return {f"metadata.{key}": value for key, value in applicability.items()}


def _clone_mongo_set() -> dict[str, Any]:
    return {
        "content_type": RETIRE_METADATA["content_type"],
        **{f"metadata.{key}": value for key, value in RETIRE_METADATA.items()},
    }


def apply_migration(
    mongo_collection: Any,
    qdrant_client: Any,
    collection_name: str,
    manifest: LocalManifest,
    inventory: CloudInventory,
) -> None:
    source_ids = [str(item["_id"]) for item in inventory.source_documents]
    clone_ids = [str(item["_id"]) for item in inventory.clone_documents]
    source_point_ids = [point["id"] for point in inventory.source_points]
    clone_point_ids = [point["id"] for point in inventory.clone_points]

    mongo_collection.update_many(
        {"_id": {"$in": source_ids}}, {"$set": _source_mongo_set(manifest.applicability)}
    )
    if clone_ids:
        mongo_collection.update_many(
            {"_id": {"$in": clone_ids}}, {"$set": _clone_mongo_set()}
        )
    if source_point_ids:
        qdrant_client.set_payload(
            collection_name=collection_name,
            payload=manifest.applicability,
            points=source_point_ids,
            wait=True,
        )
    if clone_point_ids:
        qdrant_client.set_payload(
            collection_name=collection_name,
            payload=RETIRE_METADATA,
            points=clone_point_ids,
            wait=True,
        )


def rollback_from_backup(
    mongo_collection: Any,
    qdrant_client: Any,
    collection_name: str,
    backup: dict[str, Any],
) -> None:
    for document in backup.get("mongo_documents") or []:
        mongo_collection.replace_one({"_id": document["_id"]}, document, upsert=False)
    for point in backup.get("qdrant_points") or []:
        qdrant_client.overwrite_payload(
            collection_name=collection_name,
            payload=point.get("payload") or {},
            points=[point["id"]],
            wait=True,
        )


def verify_applied(manifest: LocalManifest, inventory: CloudInventory) -> None:
    for document in inventory.source_documents:
        metadata = document.get("metadata") or {}
        if any(metadata.get(key) != value for key, value in manifest.applicability.items()):
            raise RuntimeError(f"Mongo applicability verification failed: {document.get('_id')}")
    for point in inventory.source_points:
        payload = point.get("payload") or {}
        if any(payload.get(key) != value for key, value in manifest.applicability.items()):
            raise RuntimeError(f"Qdrant applicability verification failed: {point.get('id')}")
    for document in inventory.clone_documents:
        metadata = document.get("metadata") or {}
        if metadata.get("migration_status") != "retired":
            raise RuntimeError(f"Mongo clone retirement verification failed: {document.get('_id')}")
    for point in inventory.clone_points:
        payload = point.get("payload") or {}
        if payload.get("migration_status") != "retired":
            raise RuntimeError(f"Qdrant clone retirement verification failed: {point.get('id')}")


def _summary(manifest: LocalManifest, inventory: CloudInventory) -> dict[str, Any]:
    return {
        "source_parent_count": len(inventory.source_documents),
        "source_child_count": len(inventory.source_points),
        "clone_parent_count": len(inventory.clone_documents),
        "clone_child_count": len(inventory.clone_points),
        "expected_source_parent_count": len(manifest.source_parent_ids),
        "expected_source_child_count": len(manifest.source_child_ids),
        "applicable_cohorts": manifest.applicability["applicable_cohorts"],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Patch foreign-language applicability metadata without rebuilding vectors."
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--apply", action="store_true")
    action.add_argument("--rollback", type=Path)
    parser.add_argument("--docstore", type=Path, default=DEFAULT_DOCSTORE)
    parser.add_argument("--children", type=Path, default=DEFAULT_CHILDREN)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    load_project_env(override=False)
    qdrant_url = os.environ.get("QDRANT_URL")
    qdrant_key = os.environ.get("QDRANT_API_KEY")
    collection_name = os.environ.get("QDRANT_COLLECTION_NAME")
    if not qdrant_url or not qdrant_key or not collection_name:
        raise RuntimeError("QDRANT_URL, QDRANT_API_KEY and QDRANT_COLLECTION_NAME are required.")

    mongo_store = get_mongo_store()
    if not hasattr(mongo_store, "collection"):
        raise RuntimeError("Mongo parent lookup must be enabled for this migration.")
    qdrant_client = QdrantClient(url=qdrant_url, api_key=qdrant_key, timeout=90.0)
    mongo_collection = mongo_store.collection

    if args.rollback:
        backup = load_backup(args.rollback)
        if backup.get("mongo_collection") != mongo_collection.name:
            raise RuntimeError("Backup Mongo collection does not match runtime configuration.")
        if backup.get("qdrant_collection") != collection_name:
            raise RuntimeError("Backup Qdrant collection does not match runtime configuration.")
        rollback_from_backup(mongo_collection, qdrant_client, collection_name, backup)
        print(json.dumps({"status": "rolled_back", "backup": str(args.rollback)}))
        return 0

    manifest = build_local_manifest(
        _load_json_list(args.docstore), _load_json_list(args.children)
    )
    inventory = inventory_cloud(
        mongo_collection, qdrant_client, collection_name, manifest
    )
    validate_inventory(manifest, inventory)
    summary = _summary(manifest, inventory)
    if not args.apply:
        print(json.dumps({"status": "dry_run", **summary}, ensure_ascii=False, indent=2))
        return 0

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = args.backup_root / timestamp / "backup.json"
    digest = write_backup(
        backup_path,
        mongo_collection_name=mongo_collection.name,
        qdrant_collection_name=collection_name,
        manifest=manifest,
        inventory=inventory,
    )
    try:
        apply_migration(
            mongo_collection, qdrant_client, collection_name, manifest, inventory
        )
        updated = inventory_cloud(
            mongo_collection, qdrant_client, collection_name, manifest
        )
        validate_inventory(manifest, updated)
        verify_applied(manifest, updated)
    except Exception:
        backup = load_backup(backup_path)
        rollback_from_backup(mongo_collection, qdrant_client, collection_name, backup)
        raise

    print(
        json.dumps(
            {
                "status": "applied",
                **summary,
                "backup": str(backup_path),
                "backup_sha256": digest,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
