from __future__ import annotations

from src.extraction.formula_rules import extract_formula_rules
from src.retrieval.core.formula_lookup import formula_lookup


def _section(content: str, section_id: str) -> dict[str, object]:
    return {
        "article": "Điều 28.",
        "title": "Trình tự và thủ tục xét cấp học bổng",
        "content": content,
        "section_id": section_id,
        "page_start": 72,
        "page_end": 73,
    }


def test_scholarship_formula_requires_exact_source_expression() -> None:
    without_formula = _section(
        "Học bổng được phân bổ theo thứ tự điểm học bổng giảm dần.",
        "K51_Dieu28",
    )
    with_formula = _section(
        "Điểm học tập x 80 + Điểm rèn luyện /25 x 20, tất cả chia 100.",
        "K48_Dieu28",
    )

    rules = extract_formula_rules([without_formula, with_formula])

    assert [rule["source_parent_id"] for rule in rules] == ["K48_Dieu28"]
    assert rules[0]["rule_id"] == "scholarship_score"


def test_formula_lookup_ignores_rejected_disabled_records() -> None:
    disabled = {
        "rule_id": "scholarship_score",
        "rule_name": "Công thức tính điểm học bổng",
        "cohort": "K51",
        "disabled": True,
    }

    assert (
        formula_lookup(
            "công thức điểm học bổng",
            [disabled],
            cohort="K51",
            slots={"formula_type": "scholarship_score"},
        )
        is None
    )
