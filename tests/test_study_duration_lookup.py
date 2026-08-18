from src.retrieval.core.study_duration_lookup import study_duration_lookup


def test_source_records_only_include_tables_that_contributed_rows() -> None:
    tables = [
        {
            "table_type": "study_duration",
            "table_id": "K51_study_duration_chinh_quy_used",
            "table_name": "Thoi gian hoc chinh quy",
            "cohort": "K51",
            "document_id": "handbook-k51-used",
            "source_section_id": "K51_Dieu_Used",
            "source_pages": [10],
            "rows": [
                {
                    "Chuong trinh dao tao": "Dao tao dai hoc cap bang thu nhat",
                    "Thoi gian chuan": "4 nam",
                    "Thoi gian toi da": "8 nam",
                }
            ],
        },
        {
            "table_type": "study_duration",
            "table_id": "K51_study_duration_chinh_quy_unused",
            "table_name": "Bang cung loai khong co ket qua",
            "cohort": "K51",
            "document_id": "handbook-k51-unused",
            "source_section_id": "K51_Dieu_Unused",
            "source_pages": [99],
            "rows": [],
        },
    ]

    result = study_duration_lookup(
        "K51 thoi gian hoc toi da he chinh quy la bao lau?",
        tables,
        cohort="K51",
        slots={"training_mode": "chinh_quy"},
    )

    assert result is not None
    assert result["result"]["table_count"] == 1
    assert result["source_pages"] == [10]
    assert [record["table_id"] for record in result["source_records"]] == [
        "K51_study_duration_chinh_quy_used"
    ]
    assert [record["document_id"] for record in result["source_records"]] == [
        "handbook-k51-used"
    ]
    assert [record["parent_section_id"] for record in result["source_records"]] == [
        "K51_Dieu_Used"
    ]
