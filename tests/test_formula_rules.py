from __future__ import annotations

import json
from pathlib import Path

from src.extraction.formula_rules import extract_formula_rules
from src.retrieval.core.formula_lookup import formula_lookup
from src.retrieval.core.structured_dispatcher import resolve_structured_decision


def _section(
    *,
    section_id: str,
    article: str,
    title: str,
    content: str,
    page_start: int,
    page_end: int,
) -> dict:
    return {
        "section_id": section_id,
        "article": article,
        "title": title,
        "content": content,
        "page_start": page_start,
        "page_end": page_end,
    }


def test_scholarship_formula_is_extracted_from_content_not_article_number() -> None:
    procedure_only = _section(
        section_id="K51_QuyCheCongTacSinhVien_Chuong5_Dieu28",
        article="Điều 28.",
        title="Trình tự và thủ tục xét cấp học bổng",
        content="Điều 28. Học bổng được phân bổ theo thứ tự điểm học bổng giảm dần.",
        page_start=72,
        page_end=73,
    )
    formula_source = _section(
        section_id="K51_QuyCheCongTacSinhVien_Chuong5_Dieu27",
        article="Điều 27.",
        title="Tiêu chuẩn, mức, quỹ học bổng khuyến khích học tập",
        content=(
            "Điểm học bổng = (Điểm học tập x 80 + "
            "Điểm rèn luyện / 25 x 20) / 100."
        ),
        page_start=70,
        page_end=72,
    )

    rules = extract_formula_rules([procedure_only, formula_source])

    assert len(rules) == 1
    assert rules[0]["source_article"] == "Điều 27."
    assert rules[0]["source_parent_id"] == formula_source["section_id"]
    assert rules[0]["source_pages"] == [70, 71, 72]


def test_combined_formula_request_returns_every_named_formula() -> None:
    rules = json.loads(
        Path("data/processed/tables/formula_rules.json").read_text(encoding="utf-8")
    )

    result = formula_lookup(
        "K48-K49: cac cong thuc GPA va diem hoc bong duoc trinh bay the nao?",
        rules,
        cohort="K48-K49",
    )

    assert result is not None
    assert result["lookup_type"] == "multi_formula"
    assert {item["rule_id"] for item in result["sub_lookups"]} == {
        "gpa_weighted_average",
        "scholarship_score",
    }


def test_single_formula_request_is_not_expanded_by_incidental_scholarship_phrase() -> None:
    rules = json.loads(
        Path("data/processed/tables/formula_rules.json").read_text(encoding="utf-8")
    )

    result = formula_lookup(
        "Công thức GPA dùng để xét học bổng là gì?",
        rules,
        cohort="K48-K49",
    )

    assert result is not None
    assert result["lookup_type"] == "formula"
    assert result["rule_id"] == "gpa_weighted_average"


def test_formula_sources_bind_to_each_formula_parent() -> None:
    rules = json.loads(
        Path("data/processed/tables/formula_rules.json").read_text(encoding="utf-8")
    )
    registry = json.loads(
        Path("data/processed/tables/structured_tables_registry.json").read_text(
            encoding="utf-8"
        )
    )

    resolution = resolve_structured_decision(
        {"lookup_type": "formula", "intent": "direct_value", "slots": {}},
        query="K48-K49: cac cong thuc GPA va diem hoc bong duoc trinh bay the nao?",
        cohort="K48-K49",
        scoring_tables=[],
        formula_rules=rules,
        office_directory=[],
        student_service_directory=[],
        student_faculty_profiles=[],
        foreign_language_tables=[],
        structured_tables_registry=registry,
        program_directory=[],
        probe_other_domains=False,
    )

    assert resolution is not None
    parents = {
        item["rule_id"]: item["source_parent_id"]
        for item in resolution.result["sub_lookups"]
    }
    assert parents == {
        "gpa_weighted_average": "K48-K49_K48_49_QuyCheDaoTao_Chuong3_Dieu11",
        "scholarship_score": "K48-K49_K48_49_QuyCheCongTacSinhVien_Chuong5_Dieu28",
    }


def test_generated_scholarship_formula_provenance_matches_each_cohort() -> None:
    rules = json.loads(
        Path("data/processed/tables/formula_rules.json").read_text(encoding="utf-8")
    )
    scholarship_by_cohort = {
        rule["cohort"]: rule
        for rule in rules
        if rule.get("rule_id") == "scholarship_score"
    }

    assert {
        cohort: (rule["source_article"], rule["source_parent_id"])
        for cohort, rule in scholarship_by_cohort.items()
    } == {
        "K48-K49": (
            "Điều 28.",
            "K48-K49_K48_49_QuyCheCongTacSinhVien_Chuong5_Dieu28",
        ),
        "K50": (
            "Điều 27.",
            "K50_QuyCheCongTacSinhVien_Chuong5_Dieu27",
        ),
        "K51": (
            "Điều 27.",
            "K51_QuyCheCongTacSinhVien_Chuong5_Dieu27",
        ),
    }
