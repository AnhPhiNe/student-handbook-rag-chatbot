from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.common.cohort import cohort_admission_years, valid_cohorts


DEFAULT_DOCSTORE_PATH = Path("data/processed/chunks/all_docstore_items.json")
DEFAULT_REPORT_PATH = Path("data/processed/metadata/derived_foreign_language_policy_report.json")

SOURCE_COHORT = "K50"
SOURCE_DOCUMENT_ID = "so_tay_sinh_vien_khoa_50"
APPLICABILITY_MIN_ADMISSION_YEAR = 2022
POLICY_ID_MARKER = "QuyDinhChuanDauRaNgoaiNgu"
POLICY_TITLE = (
    "Quy định tổ chức dạy học và công nhận đạt chuẩn đầu ra ngoại ngữ "
    "cho sinh viên tốt nghiệp các ngành đào tạo trình độ đại học của "
    "Trường Đại học Sư phạm Thành phố Hồ Chí Minh"
)

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


def _is_derived_from_source(item: dict[str, Any]) -> bool:
    metadata = _metadata(item)
    return (
        metadata.get("derived_from_cohort") == SOURCE_COHORT
        and metadata.get("derivation_method") == "foreign_language_policy_from_k50"
    )
def derive_foreign_language_policy(
    docstore_path: Path = DEFAULT_DOCSTORE_PATH,
    report_path: Path | None = DEFAULT_REPORT_PATH,
) -> dict[str, Any]:
    items = json.loads(docstore_path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise ValueError(f"Expected JSON array in {docstore_path}")

    source_items = [item for item in items if isinstance(item, dict) and _is_source_policy_item(item)]
    if not source_items:
        raise RuntimeError("No K50 foreign-language policy sections found to annotate.")

    source_items.sort(key=lambda item: str(item.get("_id") or ""))
    years_by_cohort = cohort_admission_years()
    applicable_cohorts = [
        cohort
        for cohort in valid_cohorts()
        if any(
            year >= APPLICABILITY_MIN_ADMISSION_YEAR
            for year in years_by_cohort.get(cohort, ())
        )
    ]

    # Older builds cloned the same policy into target handbooks.  Remove only
    # those generated copies and retain any real source section untouched.
    removed_derived_ids = [
        str(item.get("_id") or "")
        for item in items
        if isinstance(item, dict) and _is_derived_from_source(item)
    ]
    output_items = [
        item
        for item in items
        if not (isinstance(item, dict) and _is_derived_from_source(item))
    ]
    for source_item in source_items:
        metadata = dict(source_item.get("metadata") or {})
        metadata.update(
            {
                "source_cohort": SOURCE_COHORT,
                "applicable_cohorts": applicable_cohorts,
                "applicability": (
                    "Điều 1 quy định áp dụng cho sinh viên đại học thuộc phạm vi "
                    f"quy định từ khóa tuyển sinh năm {APPLICABILITY_MIN_ADMISSION_YEAR} "
                    "trở về sau."
                ),
                "applicability_basis_parent_id": (
                    "K50_QuyDinhChuanDauRaNgoaiNgu_KhongCoChuong_Dieu1"
                ),
                "applicability_validated": True,
            }
        )
        source_item["metadata"] = metadata

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
        "applicability_min_admission_year": APPLICABILITY_MIN_ADMISSION_YEAR,
        "applicable_cohorts": applicable_cohorts,
        "annotated_section_count": len(source_items),
        "derived_section_count": 0,
        "removed_existing_derived_ids": sorted(removed_derived_ids),
        "total_docstore_items": len(output_items),
    }
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Annotate the source foreign-language policy with cohort applicability."
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
