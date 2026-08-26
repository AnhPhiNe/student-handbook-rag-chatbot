from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import fitz

from src.preprocessing.structure_parser import reassociate_trailing_amendment_footnotes


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "data/processed/amendments/amendments.json"
SECTIONS_PATH = ROOT / "data/processed/metadata/structured_sections.json"
LEGAL_AMENDMENT_RE = re.compile(
    r"(?:^|\n)\s*\d+\s+(?:Điểm|Khoản|Điều|Nội dung)\s+này\b"
    r".{0,3000}?(?:sửa\s+đổi|bổ\s+sung).{0,3000}?Cụ thể\s+như\s+sau\s*:",
    flags=re.IGNORECASE | re.DOTALL,
)


def _fold_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def test_registry_is_complete_unique_and_grounded_in_k51_sections() -> None:
    records = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    sections = json.loads(SECTIONS_PATH.read_text(encoding="utf-8"))
    sections = reassociate_trailing_amendment_footnotes(copy.deepcopy(sections))
    content_by_id = {
        section["section_id"]: _fold_space(str(section.get("content") or ""))
        for section in sections
    }

    assert len(records) == 7
    assert {record["footnote_marker"] for record in records} == set(range(1, 8))
    assert len({record["amendment_id"] for record in records}) == len(records)
    assert len(
        {
            (
                record["cohort"],
                record["target_parent_id"],
                record["target_kind"],
                record["target_anchor"],
            )
            for record in records
        }
    ) == len(records)

    expected_pages = {1: [10], 2: [17], 3: [17], 4: [18], 5: [19], 6: [21], 7: [26]}
    for record in records:
        assert record["cohort"] == "K51"
        assert record["importance"] == "substantive"
        assert record["source_document_id"] == "4743/QĐ-ĐHSP"
        assert record["source_handbook_id"] == "so_tay_sinh_vien_khoa_51"
        assert record["source_handbook_title"] == "Sổ tay sinh viên khóa 51"
        assert record["source_pages"] == expected_pages[record["footnote_marker"]]
        assert record["target_parent_id"] in content_by_id
        assert _fold_space(record["replacement_text"]) in content_by_id[
            record["target_parent_id"]
        ]


def test_all_three_handbooks_have_exactly_the_curated_legal_amendments() -> None:
    counts: dict[str, int] = {}
    for path in sorted((ROOT / "data/raw").glob("so-tay-sinh-vien-khoa-*.pdf")):
        count = 0
        with fitz.open(path) as document:
            for page in document:
                count += len(LEGAL_AMENDMENT_RE.findall(page.get_text()))
        counts[path.name] = count

    assert counts == {
        "so-tay-sinh-vien-khoa-48-49.pdf": 0,
        "so-tay-sinh-vien-khoa-50.pdf": 0,
        "so-tay-sinh-vien-khoa-51.pdf": 7,
    }
