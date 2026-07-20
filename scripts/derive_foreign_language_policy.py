from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from typing import Any


DEFAULT_DOCSTORE_PATH = Path("data/processed/chunks/all_docstore_items.json")
DEFAULT_REPORT_PATH = Path("data/processed/metadata/derived_foreign_language_policy_report.json")

SOURCE_COHORT = "K50"
SOURCE_DOCUMENT_ID = "so_tay_sinh_vien_khoa_50"
POLICY_ID_MARKER = "QuyDinhChuanDauRaNgoaiNgu"
POLICY_TITLE = (
    "Quy định tổ chức dạy học và công nhận đạt chuẩn đầu ra ngoại ngữ "
    "cho sinh viên tốt nghiệp các ngành đào tạo trình độ đại học của "
    "Trường Đại học Sư phạm Thành phố Hồ Chí Minh"
)

TARGET_COHORTS = {
    "K48-K49": {
        "document_id": "so_tay_sinh_vien_khoa_48_49",
        "handbook_label": "SỔ TAY SINH VIÊN KHÓA 48-49",
    },
    "K51": {
        "document_id": "so_tay_sinh_vien_khoa_51",
        "handbook_label": "SỔ TAY SINH VIÊN KHÓA 51",
    },
}

SOURCE_FOOTER_RE = re.compile(r"(\b\d+\s+)?SỔ TAY SINH VIÊN KHÓA 50\b")


def _metadata(item: dict[str, Any]) -> dict[str, Any]:
    metadata = item.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _cohort(item: dict[str, Any]) -> str:
    metadata = _metadata(item)
    return str(item.get("cohort") or metadata.get("cohort") or "")


def _document_id(item: dict[str, Any]) -> str:
    metadata = _metadata(item)
    return str(item.get("document_id") or metadata.get("document_id") or "")


def _is_source_policy_item(item: dict[str, Any]) -> bool:
    metadata = _metadata(item)
    item_id = str(item.get("_id") or "")
    document_title = str(metadata.get("document_title") or "")
    return (
        _cohort(item) == SOURCE_COHORT
        and _document_id(item) == SOURCE_DOCUMENT_ID
        and (
            POLICY_ID_MARKER in item_id
            or document_title == POLICY_TITLE
        )
    )


def _is_target_policy_item(item: dict[str, Any], cohort: str) -> bool:
    metadata = _metadata(item)
    return (
        _cohort(item) == cohort
        and (
            POLICY_ID_MARKER in str(item.get("_id") or "")
            or str(metadata.get("document_title") or "") == POLICY_TITLE
        )
    )


def _is_derived_from_source(item: dict[str, Any]) -> bool:
    metadata = _metadata(item)
    return (
        metadata.get("derived_from_cohort") == SOURCE_COHORT
        and metadata.get("derivation_method") == "foreign_language_policy_from_k50"
    )


def _rewrite_source_string(value: str, *, target_cohort: str, target_document_id: str, handbook_label: str) -> str:
    value = value.replace(f"{SOURCE_COHORT}_", f"{target_cohort}_")
    value = value.replace(SOURCE_DOCUMENT_ID, target_document_id)
    value = SOURCE_FOOTER_RE.sub(lambda match: f"{match.group(1) or ''}{handbook_label}", value)
    return value


def _rewrite_strings(value: Any, *, target_cohort: str, target_document_id: str, handbook_label: str) -> Any:
    if isinstance(value, str):
        return _rewrite_source_string(
            value,
            target_cohort=target_cohort,
            target_document_id=target_document_id,
            handbook_label=handbook_label,
        )
    if isinstance(value, list):
        return [
            _rewrite_strings(
                item,
                target_cohort=target_cohort,
                target_document_id=target_document_id,
                handbook_label=handbook_label,
            )
            for item in value
        ]
    if isinstance(value, dict):
        return {
            key: _rewrite_strings(
                item,
                target_cohort=target_cohort,
                target_document_id=target_document_id,
                handbook_label=handbook_label,
            )
            for key, item in value.items()
        }
    return value


def _derive_item(source_item: dict[str, Any], *, target_cohort: str, target_document_id: str, handbook_label: str) -> dict[str, Any]:
    original_id = str(source_item.get("_id") or "")
    if not original_id.startswith(f"{SOURCE_COHORT}_"):
        raise ValueError(f"Unexpected source policy id: {original_id}")

    derived = copy.deepcopy(source_item)
    derived = _rewrite_strings(
        derived,
        target_cohort=target_cohort,
        target_document_id=target_document_id,
        handbook_label=handbook_label,
    )

    metadata = dict(derived.get("metadata") or {})
    source_metadata = _metadata(source_item)
    derived["_id"] = original_id.replace(f"{SOURCE_COHORT}_", f"{target_cohort}_", 1)
    derived["cohort"] = target_cohort
    derived["document_id"] = target_document_id
    if "chunk_id" in derived and derived["chunk_id"]:
        derived["chunk_id"] = str(derived["chunk_id"]).replace(f"{SOURCE_COHORT}_", f"{target_cohort}_", 1)

    metadata.update(
        {
            "cohort": target_cohort,
            "document_id": target_document_id,
            "derived_from_cohort": SOURCE_COHORT,
            "derived_from_document_id": SOURCE_DOCUMENT_ID,
            "derived_from_parent_section_id": original_id,
            "derived_from_source_pages": source_metadata.get("source_pages") or [],
            "derivation_method": "foreign_language_policy_from_k50",
            "applicability": (
                "Derived from the K50 foreign-language regulation because Article 1 "
                "states that the regulation applies to undergraduate students from "
                "the 2022 admission cohort onward."
            ),
            "source_pages": [],
        }
    )
    derived["metadata"] = metadata
    return derived


def derive_foreign_language_policy(
    docstore_path: Path = DEFAULT_DOCSTORE_PATH,
    report_path: Path | None = DEFAULT_REPORT_PATH,
) -> dict[str, Any]:
    items = json.loads(docstore_path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError(f"Expected JSON array in {docstore_path}")

    source_items = [item for item in items if isinstance(item, dict) and _is_source_policy_item(item)]
    if not source_items:
        raise RuntimeError("No K50 foreign-language policy sections found to derive from.")

    source_items.sort(key=lambda item: str(item.get("_id") or ""))
    ids = {str(item.get("_id") or "") for item in items if isinstance(item, dict)}
    derived_items: list[dict[str, Any]] = []
    removed_existing: dict[str, int] = {}
    non_derived_conflicts: list[str] = []

    retained_items = list(items)
    for target_cohort, target in TARGET_COHORTS.items():
        existing = [
            item
            for item in retained_items
            if isinstance(item, dict) and _is_target_policy_item(item, target_cohort)
        ]
        conflicts = [
            str(item.get("_id") or "")
            for item in existing
            if not _is_derived_from_source(item)
        ]
        if conflicts:
            non_derived_conflicts.extend(conflicts)
            continue

        if existing:
            retained_items = [
                item
                for item in retained_items
                if not (
                    isinstance(item, dict)
                    and _is_target_policy_item(item, target_cohort)
                    and _is_derived_from_source(item)
                )
            ]
            removed_existing[target_cohort] = len(existing)

        for source_item in source_items:
            derived = _derive_item(
                source_item,
                target_cohort=target_cohort,
                target_document_id=str(target["document_id"]),
                handbook_label=str(target["handbook_label"]),
            )
            derived_id = str(derived.get("_id") or "")
            if derived_id in ids and not any(str(item.get("_id") or "") == derived_id for item in existing):
                non_derived_conflicts.append(derived_id)
                continue
            derived_items.append(derived)

    if non_derived_conflicts:
        preview = ", ".join(non_derived_conflicts[:10])
        raise RuntimeError(
            "Refusing to overwrite existing non-derived foreign-language policy sections: "
            f"{preview}"
        )

    output_items = retained_items + derived_items
    output_ids = [str(item.get("_id") or "") for item in output_items if isinstance(item, dict)]
    duplicate_ids = sorted({item_id for item_id in output_ids if output_ids.count(item_id) > 1})
    if duplicate_ids:
        raise RuntimeError(f"Duplicate docstore ids after derivation: {duplicate_ids[:10]}")

    docstore_path.write_text(json.dumps(output_items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = {
        "status": "ok",
        "docstore_path": str(docstore_path),
        "source_cohort": SOURCE_COHORT,
        "source_document_id": SOURCE_DOCUMENT_ID,
        "source_section_count": len(source_items),
        "target_cohorts": sorted(TARGET_COHORTS),
        "derived_section_count": len(derived_items),
        "removed_existing_derived": removed_existing,
        "total_docstore_items": len(output_items),
        "derived_ids_by_cohort": {
            cohort: [
                str(item.get("_id"))
                for item in derived_items
                if _cohort(item) == cohort
            ]
            for cohort in TARGET_COHORTS
        },
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Derive K48-K49/K51 foreign-language policy parent sections from K50."
    )
    parser.add_argument("--docstore", type=Path, default=DEFAULT_DOCSTORE_PATH)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = parse_args(argv)
    report = derive_foreign_language_policy(args.docstore, args.report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
