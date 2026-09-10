"""Contract tests for planner-owned structured resolver inputs."""

from __future__ import annotations

from copy import deepcopy

from src.retrieval.core.foreign_language_lookup import foreign_language_lookup
from src.retrieval.core.formula_lookup import formula_lookup
from src.retrieval.core.office_lookup import office_lookup
from src.retrieval.core.program_lookup import program_lookup
from src.retrieval.core.scholarship_lookup import scholarship_table_lookup
from src.retrieval.core.study_duration_lookup import study_duration_lookup
from src.retrieval.core.structured_dispatcher import (
    StructuredResolution,
    resolve_structured_decision,
)
from src.retrieval.core.structured_lookup import structured_lookup_from_slots


def _foreign_tables() -> list[dict]:
    return [
        {
            "table_id": "K51_foreign_language",
            "cohort": "K51",
            "source_cohort": "K51",
            "rows": [
                {
                    "language": "Tiếng Anh",
                    "certificate": "IELTS",
                    "equivalent_level_4": "5.5 - 6.5",
                },
                {
                    "language": "Tiếng Anh",
                    "certificate": "TOEFL iBT",
                    "equivalent_level_4": "46 - 93",
                },
            ],
        }
    ]


def _duration_tables() -> list[dict]:
    row = {
        "Chương trình đào tạo": "Đào tạo đại học cấp bằng thứ nhất",
        "Thời gian học tập tối đa": "06 năm học",
    }
    return [
        {
            "table_id": "K51_study_duration_chinh_quy",
            "table_type": "study_duration",
            "cohort": "K51",
            "rows": [row],
        },
        {
            "table_id": "K51_study_duration_vua_lam_vua_hoc",
            "table_type": "study_duration",
            "cohort": "K51",
            "rows": [row | {"Thời gian học tập tối đa": "7,5 năm học"}],
        },
    ]


def _scholarship_tables() -> list[dict]:
    return [
        {
            "table_id": "scholarship_classification",
            "cohort": "K51",
            "rows": [
                {"label": "Khá", "scholarship_score_range": "7 - dưới 8"},
                {"label": "Giỏi", "scholarship_score_range": "8 - dưới 9"},
            ],
        }
    ]


def _formula_rules() -> list[dict]:
    return [
        {
            "rule_id": "gpa_weighted_average",
            "calculation_type": "gpa_weighted_average",
            "rule_name": "GPA có trọng số",
            "formula_text": "sum(score * credits) / sum(credits)",
        },
        {
            "rule_id": "scholarship_score",
            "calculation_type": "scholarship_score",
            "rule_name": "Điểm học bổng",
            "formula_text": "academic + conduct",
        },
    ]


def _without_input_value(result: dict) -> dict:
    """Compare resolver output while ignoring display-only query metadata."""

    copied = deepcopy(result)
    copied.pop("input_value", None)
    return copied


def _resolve_student_service(
    query: str,
    cohort: str,
    directory: list[dict],
) -> StructuredResolution | None:
    return resolve_structured_decision(
        {
            "lookup_type": "student_service",
            "intent": "contact",
            "slots": {"requested_field": "unit"},
            "slot_spans": {"requested_field": "đơn vị"},
        },
        query=query,
        cohort=cohort,
        scoring_tables=[],
        formula_rules=[],
        office_directory=[],
        student_service_directory=directory,
        student_faculty_profiles=[],
        foreign_language_tables=[],
        structured_tables_registry=[],
        program_directory=[],
    )


def test_supplied_slots_make_each_leaf_invariant_to_irrelevant_query() -> None:
    foreign_slots = {
        "certificate_or_language": "IELTS",
        "score_or_level": "6.0",
    }
    first = foreign_language_lookup(
        "IELTS 6.0 tương đương bậc mấy?",
        _foreign_tables(),
        "K51",
        slots=foreign_slots,
    )
    second = foreign_language_lookup(
        "TOEFL 46 tương đương bậc mấy?",
        _foreign_tables(),
        "K51",
        slots=foreign_slots,
    )
    assert first and second
    assert _without_input_value(first) == _without_input_value(second)

    duration_slots = {"training_mode": "chinh_quy", "program_type": "first_degree"}
    first = study_duration_lookup(
        "chính quy bằng thứ nhất",
        _duration_tables(),
        "K51",
        slots=duration_slots,
    )
    second = study_duration_lookup(
        "VLVH liên thông",
        _duration_tables(),
        "K51",
        slots=duration_slots,
    )
    assert first and second
    assert _without_input_value(first) == _without_input_value(second)

    scholarship_slots = {"score_or_label": "Giỏi"}
    first = scholarship_table_lookup(
        "Học bổng loại Giỏi",
        _scholarship_tables(),
        "K51",
        slots=scholarship_slots,
    )
    second = scholarship_table_lookup(
        "Học bổng loại Khá",
        _scholarship_tables(),
        "K51",
        slots=scholarship_slots,
    )
    assert first and second
    assert _without_input_value(first) == _without_input_value(second)

    formula_slots = {"formula_type": "gpa_weighted_average"}
    first = formula_lookup("công thức GPA", _formula_rules(), slots=formula_slots)
    second = formula_lookup("công thức học bổng", _formula_rules(), slots=formula_slots)
    assert first and second
    assert _without_input_value(first) == _without_input_value(second)


def test_empty_slots_do_not_infer_leaf_selectors_from_query() -> None:
    foreign = foreign_language_lookup(
        "IELTS 6.0 tương đương bậc mấy?",
        _foreign_tables(),
        "K51",
        slots={},
    )
    assert foreign and len(foreign["items"]) == 2

    duration = study_duration_lookup(
        "chính quy bằng thứ nhất", _duration_tables(), "K51", slots={}
    )
    assert duration and len(duration["display_rows"]) == 2

    scholarship = scholarship_table_lookup(
        "Học bổng loại Giỏi", _scholarship_tables(), "K51", slots={}
    )
    assert scholarship and len(scholarship["display_rows"]) == 2

    formulas = formula_lookup("công thức GPA", _formula_rules(), slots={})
    assert formulas and formulas["formula_count"] == 2

    assert (
        structured_lookup_from_slots(
            {"score_or_grade": "C"},
            [
                {
                    "table_id": "letter_to_grade_4",
                    "rows": [{"letter_grade": "C", "score_4": 2.0}],
                }
            ],
        )
        is None
    )

    assert (
        program_lookup(
            [{"program_name": "Sư phạm Toán", "cohort": "K51"}],
            candidate_text="Trường có những ngành nào?",
            cohort="K51",
            action="",
            scope="",
        )
        is None
    )


def test_directory_selection_uses_only_validated_candidate_text() -> None:
    result = office_lookup(
        "Phòng Đào tạo và Phòng Công tác sinh viên",
        [
            {
                "record_id": "training-office",
                "unit_name": "Phòng Đào tạo",
                "aliases": ["phòng đào tạo"],
                "cohort": "shared",
            },
            {
                "record_id": "student-affairs-office",
                "unit_name": "Phòng Công tác sinh viên",
                "aliases": ["phòng công tác sinh viên"],
                "cohort": "shared",
            },
        ],
        candidate_text="Phòng Đào tạo",
        cohort="K51",
        require_confident_match=True,
    )

    assert result is not None
    assert [item["unit_name"] for item in result["items"]] == ["Phòng Đào tạo"]


def test_multiple_explicit_entities_preserve_union_rows() -> None:
    result = foreign_language_lookup(
        "irrelevant",
        _foreign_tables(),
        "K51",
        slots={"certificate_or_language": ["IELTS", "TOEFL iBT"]},
    )
    assert result and {row["certificate"] for row in result["items"]} == {
        "IELTS",
        "TOEFL iBT",
    }

    duration = study_duration_lookup(
        "irrelevant",
        _duration_tables(),
        "K51",
        slots={
            "training_mode": ["chinh_quy", "vua_lam_vua_hoc"],
            "program_type": "first_degree",
        },
    )
    assert duration and len(duration["items"]) == 2

    scholarship = scholarship_table_lookup(
        "irrelevant",
        _scholarship_tables(),
        "K51",
        slots={"score_or_label": ["Khá", "Giỏi"]},
    )
    assert scholarship and {row["label"] for row in scholarship["items"]} == {
        "Khá",
        "Giỏi",
    }


def test_distinct_score_list_keeps_evidence_without_false_fact_lock() -> None:
    table = {
        "table_id": "K51_grade_scale_general",
        "table_type": "scoring",
        "table_subtype": "grade_scale",
        "data_category": "regulation_table",
        "cohort": "K51",
        "source_cohort": "K51",
        "applicable_cohorts": ["K51"],
        "applicability_validated": True,
        "source_parent_id": "K51_Dieu10",
        "rows": [
            {"Thang điểm 10": "6,0 - 6,9", "Thang điểm chữ": "C"},
            {"Thang điểm 10": "7,0 - 7,9", "Thang điểm chữ": "B"},
        ],
    }
    resolution = resolve_structured_decision(
        {
            "lookup_type": "scoring",
            "intent": "direct_value",
            "slots": {"operation": "grade_10_to_letter", "score_or_grade": [6.1, 7.1]},
            "slot_spans": {
                "score_or_grade": ["6,1", "7,1"],
                "operation": "đổi sang điểm chữ",
            },
        },
        query="6,1 và 7,1 đổi sang điểm chữ",
        cohort="K51",
        scoring_tables=[],
        formula_rules=[],
        office_directory=[],
        student_service_directory=[],
        student_faculty_profiles=[],
        foreign_language_tables=[],
        structured_tables_registry=[table],
        program_directory=[],
    )
    assert resolution is not None
    assert resolution.resolution_status == "evidence_only"
    assert "resolved_result" not in resolution.result


def test_student_service_query_fallback_is_task_local_and_cohort_scoped() -> None:
    directory = [
        {
            "service_id": "print-k50",
            "service": "In giáo trình",
            "aliases": ["in giáo trình"],
            "unit": "Nhà xuất bản K50",
            "cohort": "K50",
            "content_type": "student_service_directory",
        },
        {
            "service_id": "print-k51",
            "service": "In giáo trình",
            "aliases": ["in giáo trình"],
            "unit": "Nhà xuất bản K51",
            "cohort": "K51",
            "content_type": "student_service_directory",
        },
        {
            "service_id": "certificate-k50",
            "service": "Cấp giấy chứng nhận điểm",
            "aliases": ["giấy chứng nhận điểm"],
            "unit": "Phòng Khảo thí K50",
            "cohort": "K50",
            "content_type": "student_service_directory",
        },
    ]

    resolution = _resolve_student_service(
        "Muốn in giáo trình thì liên hệ đơn vị nào?",
        "K50",
        directory,
    )

    assert resolution is not None
    assert resolution.result["cohort"] == "K50"
    assert resolution.result["result"][0]["unit_name"] == "Nhà xuất bản K50"
    assert all(
        item["cohort"] == "K50" for item in resolution.result["result"]
    )


def test_student_service_query_fallback_preserves_ambiguity_clarification() -> None:
    directory = [
        {
            "service_id": "score-certificate",
            "service": "Cấp giấy chứng nhận điểm",
            "aliases": ["giấy chứng nhận điểm"],
            "unit": "Phòng Khảo thí",
            "cohort": "K51",
            "content_type": "student_service_directory",
        },
        {
            "service_id": "student-certificate",
            "service": "Cấp giấy chứng nhận sinh viên",
            "aliases": ["giấy chứng nhận sinh viên"],
            "unit": "Phòng Công tác sinh viên",
            "cohort": "K51",
            "content_type": "student_service_directory",
        },
    ]

    resolution = _resolve_student_service(
        "Xin giấy chứng nhận thì liên hệ đơn vị nào?",
        "K51",
        directory,
    )

    assert resolution is not None
    assert resolution.resolution_status == "needs_clarification"
    assert resolution.result["resolution_status"] == "ambiguous"
    assert len(resolution.result["clarification_options"]) == 2
