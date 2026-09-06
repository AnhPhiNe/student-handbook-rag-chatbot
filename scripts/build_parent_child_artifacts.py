"""Build narrative-only children and readable full parents from reviewed regions.

Review metadata is source data, not a query-routing rule. Exact source hashes and
non-overlapping ranges must validate before any source text can be replaced.
No live store writes and no table-derived embedding chunks.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.build_child_parent_index import (  # noqa: E402
    build_child_parent_chunks,
    build_table_embedding_audit_report,
    validate_child_parent_chunks,
)

POLICY = "reviewed-table-separation-v1"
REGIONS = ROOT / "data/curated/regulation_table_regions.json"


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def text_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def artifact_digest(value):
    """Bind complete artifacts independently of the subsequently attached build ID."""
    return digest(_without_stamp(value))


def _without_stamp(value):
    if isinstance(value, dict):
        return {k: _without_stamp(v) for k, v in value.items() if k != "build_id"}
    if isinstance(value, list):
        return [_without_stamp(v) for v in value]
    return value


def validate_separation_contract(parents, children, separation):
    """Reject mixing narrative/display views or artifacts from different builds."""
    marked = any(
        (r.get("metadata") or {}).get("table_separation_policy")
        for r in parents + children
    )
    if not separation:
        if marked:
            raise RuntimeError("Separated artifacts require their separation audit")
        return  # Historical unseparated manifests remain verifiable.
    if separation.get("policy") != POLICY or not separation.get("review_sha256"):
        raise RuntimeError("Unknown or incomplete table separation policy")
    for name, records, role in [
        ("parent_docstore", parents, "full_parent"),
        ("child_chunks", children, "narrative_child"),
    ]:
        if artifact_digest(records) != separation.get(
            "artifact_content_sha256", {}
        ).get(name):
            raise RuntimeError(f"Separation audit does not match {name}")
        if any(
            (r.get("metadata") or {}).get("corpus_role") != role
            or r["metadata"].get("table_separation_policy") != POLICY
            for r in records
        ):
            raise RuntimeError(f"Invalid corpus role for {name}")
    by_id = {p["_id"]: p for p in parents}
    if len(by_id) != len(parents):
        raise RuntimeError("Duplicate separated parent IDs")
    for child in children:
        meta = child["metadata"]
        parent = by_id.get(meta.get("parent_section_id"))
        if parent is None:
            raise RuntimeError("Separated child has no parent")
        pm = parent["metadata"]
        if (
            any(meta.get(k) != pm.get(k) for k in ("cohort", "document_id"))
            or not meta.get("source_pages")
            or not set(meta["source_pages"]).issubset(pm["source_pages"])
        ):
            raise RuntimeError("Separated child source identity differs from parent")


def validate_publish_separation(manifest):
    """For new separated builds, verify the complete pair before either upload."""
    policy = manifest.get("index_contract", {}).get("table_separation_policy")
    if not policy:
        return
    if policy != POLICY:
        raise RuntimeError("Unknown published table separation policy")
    artifacts = manifest.get("artifacts", {})
    loaded = {}
    for key in (
        "parent_docstore",
        "child_chunks",
        "structured_tables",
        "table_embedding_audit",
    ):
        item = artifacts.get(key, {})
        path = Path(item.get("path") or "")
        if not path.is_file() or hashlib.sha256(
            path.read_bytes()
        ).hexdigest() != item.get("sha256"):
            raise RuntimeError(f"Separation publish artifact missing or stale: {key}")
        loaded[key] = json.loads(path.read_text(encoding="utf-8"))
    audit = loaded["table_embedding_audit"]
    if (
        audit.get("build_id") != manifest.get("build_id")
        or audit.get("structured_registry_sha256")
        != artifacts["structured_tables"]["sha256"]
    ):
        raise RuntimeError("Separation audit build/registry identity mismatch")
    separation = audit.get("separation")
    if not separation or separation.get("review_sha256") != manifest[
        "index_contract"
    ].get("source_review_sha256"):
        raise RuntimeError("Separation review identity mismatch")
    validate_separation_contract(
        loaded["parent_docstore"], loaded["child_chunks"], separation
    )


def apply_page_corrections(parents, corrections):
    """Apply only reviewed, hash-bound source-page corrections; never infer pages."""
    by_id = {p["_id"]: p for p in parents}
    seen = set()
    for entry in corrections:
        pid = entry["parent_id"]
        if pid in seen or pid not in by_id:
            raise ValueError(f"Duplicate or unknown page correction: {pid}")
        seen.add(pid)
        parent = by_id[pid]
        meta = parent["metadata"]
        pages = entry["source_pages"]
        if (
            entry.get("review_status") != "source_checked"
            or text_hash(parent["content"]) != entry["content_sha256"]
            or any(meta.get(k) != entry[k] for k in ("cohort", "document_id"))
            or meta.get("source_pages") != entry["original_source_pages"]
            or not pages
            or pages != sorted(set(pages))
            or not set(pages).issubset(entry["original_source_pages"])
        ):
            raise ValueError(f"Stale or invalid source-page correction: {pid}")
        meta["source_pages"] = list(pages)


def render_table(spec, registry):
    columns = spec["columns"]
    if spec.get("source_only"):
        rows = spec["rows"]
    else:
        rows = []
        for table_id in spec["registry_ids"]:
            table = registry[table_id]
            rows.extend([[row[key] for key in spec["keys"]] for row in table["rows"]])
    if not columns or not rows or any(len(row) != len(columns) for row in rows):
        raise ValueError("Invalid source table shape")

    def cell(value):
        if isinstance(value, (dict, list)):
            raise ValueError("Runtime metadata cannot be rendered as a source cell")
        return (
            str(value if value is not None else "")
            .replace("|", "&#124;")
            .replace("\n", "<br>")
        )

    lines = [columns, ["---"] * len(columns), *rows]
    return "\n".join(
        "| " + " | ".join(cell(c) for c in row) + " |" for row in lines
    ), len(rows)


def separate_tables(
    parents, registry, review, *, max_child_chars=1600, audit_rows=None
):
    if review.get("policy") != POLICY or review.get("registry_sha256") != digest(
        registry
    ):
        raise ValueError(
            "Registry or review policy changed; review source regions again"
        )
    full, narrative = copy.deepcopy(parents), copy.deepcopy(parents)
    if any((p.get("metadata") or {}).get("table_separation_policy") for p in parents):
        raise ValueError(
            "Input is already separated; rebuild from the original source snapshot"
        )
    full_map = {p["_id"]: p for p in full}
    narrative_map = {p["_id"]: p for p in narrative}
    if len(full_map) != len(parents):
        raise ValueError("Duplicate input parent IDs")
    audit = []
    seen = set()
    for entry in review["parents"]:
        pid = entry["parent_id"]
        if pid in seen or pid not in full_map:
            raise ValueError(f"Duplicate or unknown reviewed parent: {pid}")
        seen.add(pid)
        parent = full_map[pid]
        original = parent["content"]
        meta = parent["metadata"]
        if (
            entry.get("review_status") != "source_checked"
            or text_hash(original) != entry["content_sha256"]
        ):
            raise ValueError(f"Stale or unreviewed parent: {pid}")
        if any(meta.get(key) != entry[key] for key in ("cohort", "document_id")):
            raise ValueError(f"Wrong source identity: {pid}")
        bound = {t["table_id"]: t for t in registry if t["source_parent_id"] == pid}
        if any(
            t["cohort"] != entry["cohort"]
            or t["document_id"] != entry["document_id"]
            or t.get("quality_status") != "approved"
            or t.get("used_by_runtime") is False
            for t in bound.values()
        ):
            raise ValueError(f"Invalid registry source binding: {pid}")
        if set(bound) != set(entry["registry_dispositions"]):
            raise ValueError(f"Incomplete registry review: {pid}")
        allowed_dispositions = {
            "prose_derived_keep_original_policy",
            "physical_source_table",
            "physical_amendment_table_with_prose_exception",
        }
        if not set(entry["registry_dispositions"].values()).issubset(
            allowed_dispositions
        ):
            raise ValueError(f"Unknown registry disposition: {pid}")
        regions = sorted(entry["regions"], key=lambda r: r["start"])
        end = 0
        rows_preserved = 0
        represented_ids = set()
        rendered = []
        for region in regions:
            a, b = region["start"], region["end"]
            if (
                not (end <= a < b <= len(original))
                or original[a:b] != region["source_text"]
            ):
                raise ValueError(f"Overlapping or mismatched region: {pid}")
            if not set(region["source_pages"]).issubset(meta["source_pages"]):
                raise ValueError(f"Wrong page binding: {pid}")
            end = b
            if region["kind"] == "physical_table":
                represented_ids.update(region["table"].get("registry_ids", []))
                replacement, count = render_table(region["table"], bound)
                rows_preserved += count
            elif region["kind"] == "generated_table_appendix":
                if not region["source_text"].startswith(
                    "BẢNG/DANH SÁCH CHUẨN HÓA TỪ NGUỒN:"
                ):
                    raise ValueError("Unexpected generated appendix marker")
                replacement = ""
            else:
                raise ValueError("Unknown reviewed region kind")
            rendered.append((a, b, replacement))
        required_ids = {
            k
            for k, v in entry["registry_dispositions"].items()
            if v.startswith("physical_")
        }
        if represented_ids != required_ids:
            raise ValueError(f"Physical table lacks a reviewed representation: {pid}")
        parent_text = child_text = original
        for a, b, replacement in reversed(rendered):
            parent_text = parent_text[:a] + "\n" + replacement + "\n" + parent_text[b:]
            child_text = child_text[:a] + "\n" + child_text[b:]
        parent["content"] = parent_text
        narrative_map[pid]["content"] = child_text
        audit.append(
            {
                "parent_id": pid,
                "physical_tables": sum(r["kind"] == "physical_table" for r in regions),
                "generated_appendices_removed": sum(
                    r["kind"] == "generated_table_appendix" for r in regions
                ),
                "parent_table_rows": rows_preserved,
                "original_sha256": text_hash(original),
                "parent_sha256": text_hash(parent_text),
                "narrative_sha256": text_hash(child_text),
            }
        )
    registry_parents = {t["source_parent_id"] for t in registry}
    if seen != registry_parents:
        raise ValueError("Every registry parent must have a source review disposition")
    corrected = copy.deepcopy(parents)
    corrections = review.get("source_page_corrections", [])
    apply_page_corrections(corrected, corrections)
    corrected_map = {p["_id"]: p for p in corrected}
    for entry in review["parents"]:
        pages = corrected_map[entry["parent_id"]]["metadata"]["source_pages"]
        if any(
            not set(region["source_pages"]).issubset(pages)
            for region in entry["regions"]
        ):
            raise ValueError(
                f"Source-page correction excludes a reviewed table: {entry['parent_id']}"
            )
    for records, role in ((full, "full_parent"), (narrative, "narrative_only")):
        for record in records:
            meta = record["metadata"]
            meta["source_pages"] = corrected_map[record["_id"]]["metadata"][
                "source_pages"
            ]
            meta["table_separation_policy"] = POLICY
            meta["corpus_role"] = role
            record["normalized_content"] = record["content"]
    # Existing child builder sees only the narrative view. Full parents never enter embeddings.
    children = build_child_parent_chunks(
        narrative,
        structured_tables=registry,
        max_child_chars=max_child_chars,
        table_embedding_audit=audit_rows,
    )
    for child in children:
        child["metadata"].update(
            table_separation_policy=POLICY, corpus_role="narrative_child"
        )
    validate_child_parent_chunks(children, full)
    # An old build stamp cannot identify newly generated candidate data.
    for record in full + narrative + children:
        record.pop("build_id", None)
        record.get("metadata", {}).pop("build_id", None)
    return (
        full,
        narrative,
        children,
        {
            "policy": POLICY,
            "parents": audit,
            "review_sha256": digest(review),
            "source_page_corrections": corrections,
            "artifact_content_sha256": {
                "parent_docstore": artifact_digest(full),
                "child_chunks": artifact_digest(children),
            },
            "physical_tables": sum(a["physical_tables"] for a in audit),
            "parent_table_rows": sum(a["parent_table_rows"] for a in audit),
            "generated_appendices_removed": sum(
                a["generated_appendices_removed"] for a in audit
            ),
            "parent_count": len(full),
            "child_count": len(children),
            "table_embedding_chunks_added": 0,
        },
    )


def verify_mongo_parents(parents, review):
    """Read only the in-scope live parents and compare to the build input snapshot."""
    from src.retrieval.vectorstore.mongo_store import get_mongo_store

    store = get_mongo_store()
    if not hasattr(store, "collection"):
        raise ValueError("MongoDB is disabled; live source verification cannot run")
    expected = {p["_id"]: p for p in parents}
    comparisons = []
    try:
        for entry in review["parents"]:
            pid = entry["parent_id"]
            live = store.get_document_by_id(pid)
            local = expected[pid]
            same = (
                bool(live)
                and live.get("content") == local["content"]
                and all(
                    (live.get("metadata") or {}).get(k) == local["metadata"].get(k)
                    for k in ("cohort", "document_id", "source_pages")
                )
            )
            comparisons.append(
                {
                    "parent_id": pid,
                    "matches_snapshot": same,
                    "live_content_sha256": text_hash(live.get("content", ""))
                    if live
                    else None,
                }
            )
        return {
            "collection": store.collection.name,
            "read_only": True,
            "parents": comparisons,
            "matched": sum(c["matches_snapshot"] for c in comparisons),
            "checked": len(comparisons),
        }
    finally:
        if hasattr(store, "client"):
            store.client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--output-dir", type=Path, help="New isolated directory under work/"
    )
    mode.add_argument(
        "--publish-artifacts",
        action="store_true",
        help="Finalize local data/processed outputs after source build; no remote writes",
    )
    parser.add_argument(
        "--docstore",
        type=Path,
        default=ROOT / "data/processed/chunks/all_docstore_items.json",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=ROOT / "data/processed/tables/structured_tables_registry.json",
    )
    parser.add_argument("--review", type=Path, default=REGIONS)
    parser.add_argument(
        "--verify-mongo",
        action="store_true",
        help="Read-only comparison of reviewed live parents with local inputs",
    )
    args = parser.parse_args()
    directory = (
        ROOT / "data/processed/chunks"
        if args.publish_artifacts
        else args.output_dir.resolve()
    )
    if not args.publish_artifacts and (
        not directory.is_relative_to((ROOT / "work").resolve())
        or directory == (ROOT / "work").resolve()
        or directory.exists()
    ):
        parser.error("Use a new candidate directory under work/")
    inputs = {
        "parents": args.docstore,
        "registry": args.registry,
        "review": args.review,
    }
    data = {k: json.loads(p.read_text(encoding="utf-8")) for k, p in inputs.items()}
    audit_rows = []
    full, narrative, children, audit = separate_tables(**data, audit_rows=audit_rows)
    if args.verify_mongo:
        audit["live_parent_verification"] = verify_mongo_parents(
            data["parents"], data["review"]
        )
    audit["input_sha256"] = {
        k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in inputs.items()
    }
    directory.mkdir(parents=True, exist_ok=args.publish_artifacts)
    for name, value in [
        ("all_docstore_items.json", full),
        ("narrative_docstore_items.json", narrative),
        ("child_parent_chunks.json", children),
        ("audit.json", audit),
    ]:
        (directory / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    embedding_audit = build_table_embedding_audit_report(
        audit_rows,
        docstore_path=directory / "all_docstore_items.json",
        registry_path=args.registry,
        child_output_path=directory / "child_parent_chunks.json",
        child_count=len(children),
    )
    embedding_audit["separation"] = audit
    audit_path = (
        ROOT / "data/processed/metadata" if args.publish_artifacts else directory
    ) / "structured_table_embedding_audit.json"
    audit_path.write_text(
        json.dumps(embedding_audit, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {k: v for k, v in audit.items() if k != "parents"}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
