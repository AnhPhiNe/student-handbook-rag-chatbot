from __future__ import annotations

import json
from pathlib import Path

from src.extraction.program_parser import extract_program_directory


def _page(page_number: int, text: str, *, detection_source: str = "config_only") -> dict:
    return {
        "page_number": page_number,
        "content_type": "faculty_program_directory",
        "detection_source": detection_source,
        "text": text,
    }


def test_program_parser_keeps_long_and_wrapped_layout_headings(monkeypatch) -> None:
    monkeypatch.setenv("COHORT", "K51")
    records = extract_program_directory(
        [
            _page(
                10,
                "\n".join(
                    [
                        "1. Ngành Tiếng Việt và văn hoá Việt Nam (dành cho sinh viên nước ngoài)",
                        "Cơ hội nghề nghiệp sau khi tốt nghiệp:",
                        "Làm việc trong lĩnh vực phù hợp.",
                    ]
                ),
            ),
            _page(
                11,
                "\n".join(
                    [
                        "TIẾNG VIỆT VÀ VĂN HÓA VIỆT NAM (DÀNH CHO SINH",
                        "VIÊN NƯỚC NGOÀI)",
                        "Cơ hội nghề nghiệp sau khi tốt nghiệp:",
                        "Làm việc trong lĩnh vực phù hợp.",
                    ]
                ),
            ),
        ]
    )

    assert [record["program_name"] for record in records] == [
        "Tiếng Việt và văn hoá Việt Nam (dành cho sinh viên nước ngoài)",
        "TIẾNG VIỆT VÀ VĂN HÓA VIỆT NAM (DÀNH CHO SINH VIÊN NƯỚC NGOÀI)",
    ]


def test_program_parser_ignores_pattern_only_false_positive(monkeypatch) -> None:
    monkeypatch.setenv("COHORT", "K51")
    records = extract_program_directory(
        [
            _page(
                99,
                "NGÀNH HỌC: ................................ của Trường",
                detection_source="pattern_only",
            )
        ]
    )
    assert records == []


def test_processed_program_catalog_has_source_audited_cohort_differences() -> None:
    records = json.loads(
        Path("data/processed/directories/program_directory.json").read_text(
            encoding="utf-8"
        )
    )
    by_cohort = {
        cohort: {
            record["program_name"]: record
            for record in records
            if record["cohort"] == cohort
        }
        for cohort in ("K48-K49", "K50", "K51")
    }

    assert {cohort: len(items) for cohort, items in by_cohort.items()} == {
        "K48-K49": 41,
        "K50": 43,
        "K51": 45,
    }
    assert set(by_cohort["K50"]) - set(by_cohort["K48-K49"]) == {
        "Du lịch",
        "Sinh học ứng dụng",
    }
    assert set(by_cohort["K51"]) - set(by_cohort["K50"]) == {
        "Công nghệ Giáo dục",
        "Toán ứng dụng",
    }
    special_program = (
        "Tiếng Việt và văn hoá Việt Nam (dành cho sinh viên nước ngoài)"
    )
    assert all(special_program in programs for programs in by_cohort.values())
    assert all(
        record.get("faculty_name")
        for programs in by_cohort.values()
        for record in programs.values()
    )
