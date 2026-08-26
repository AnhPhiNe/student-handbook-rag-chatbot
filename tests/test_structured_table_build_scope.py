from scripts.build_structured_table_layer import build_registry


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
