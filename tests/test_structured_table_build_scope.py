import json

from scripts.build_structured_table_layer import (
    attach_scholarship_tables,
    build_student_office_profiles,
    build_student_service_directory,
    build_registry,
    extract_websites,
)
from src.extraction.scoring_tables import build_scoring_tables


def test_registry_inherits_validated_scope_from_source_parent() -> None:
    parent = {
        "_id": "K50_example_parent",
        "cohort": "K50",
        "document_id": "example_handbook",
        "metadata": {
            "title": "Example",
            "cohort": "K50",
            "document_id": "example_handbook",
            "source_cohort": "K50",
            "applicable_cohorts": ["K48-K49", "K50", "K51"],
            "applicability": "Applies from the configured admission year.",
            "applicability_basis_parent_id": "K50_example_scope",
            "applicability_validated": True,
        },
        "tables": [
            {
                "table_id": "example_table",
                "table_type": "foreign_language",
                "table_subtype": "foreign_language_equivalency",
                "columns": ["value"],
                "rows": [{"value": "example"}],
            }
        ],
    }

    records = build_registry([parent])

    assert len(records) == 1
    assert records[0]["source_cohort"] == "K50"
    assert records[0]["applicable_cohorts"] == ["K48-K49", "K50", "K51"]
    assert records[0]["applicability_validated"] is True
    assert parent["tables"][0]["applicability_basis_parent_id"] == "K50_example_scope"


def test_table_scope_is_not_overwritten_by_parent_scope() -> None:
    parent = {
        "_id": "K50_example_parent",
        "cohort": "K50",
        "document_id": "example_handbook",
        "metadata": {
            "cohort": "K50",
            "document_id": "example_handbook",
            "applicable_cohorts": ["K48-K49", "K50", "K51"],
        },
        "tables": [
            {
                "table_id": "example_table",
                "table_type": "foreign_language",
                "table_subtype": "foreign_language_equivalency",
                "applicable_cohorts": ["K50"],
                "columns": ["value"],
                "rows": [{"value": "example"}],
            }
        ],
    }

    records = build_registry([parent])

    assert records[0]["applicable_cohorts"] == ["K50"]


def test_scholarship_policy_tables_coexist_on_same_parent(tmp_path) -> None:
    parent_id = "K51_QuyCheCongTacSinhVien_Chuong5_Dieu27"
    parent = {
        "_id": parent_id,
        "cohort": "K51",
        "document_id": "so_tay_sinh_vien_khoa_51",
        "metadata": {
            "title": "Tiêu chuẩn, mức, quỹ học bổng khuyến khích học tập",
            "cohort": "K51",
            "document_id": "so_tay_sinh_vien_khoa_51",
            "source_pages": [70, 71, 72],
        },
        "tables": [],
    }
    scoring_path = tmp_path / "scoring_tables.json"
    scoring_tables = [
        {**table, "cohort": "K51"}
        for table in build_scoring_tables("K51")
    ]
    scoring_path.write_text(
        json.dumps(scoring_tables, ensure_ascii=False),
        encoding="utf-8",
    )

    attach_scholarship_tables([parent], scoring_path)

    assert {
        table["table_subtype"] for table in parent["tables"]
    } == {
        "scholarship_classification",
        "scholarship_amount",
        "scholarship_score_formula",
        "scholarship_eligibility",
    }
    records = build_registry([parent], scoring_path)
    assert len(records) == 4
    assert {record["source_parent_id"] for record in records} == {parent_id}


def test_directory_build_preserves_official_website_outside_hcmue_domain() -> None:
    raw_text = (
        "Viện Nghiên cứu Giáo dục\n"
        "Email: vienncgd@hcmue.edu.vn\n"
        "Website: www.ier.edu.vn\n"
        "Những công việc của đơn vị liên quan đến sinh viên:\n"
        "- Hỗ trợ nghiên cứu khoa học."
    )
    records = [
        {
            "record_id": "office_1",
            "cohort": "K50",
            "unit_name": "Viện Nghiên cứu Giáo dục",
            "raw_text": raw_text,
            "source_pages": [1],
            "document_id": "handbook_k50",
        }
    ]

    assert extract_websites(raw_text) == ["www.ier.edu.vn"]
    services = build_student_service_directory(source_records=records)
    profiles = build_student_office_profiles(services)

    assert profiles[0]["websites"] == ["www.ier.edu.vn"]
    assert profiles[0]["website"] == "www.ier.edu.vn"
