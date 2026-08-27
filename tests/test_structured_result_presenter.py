import json
from pathlib import Path

from src.api.routes.chat import _to_chat_response
from src.generation.answer_pipeline import AnswerPipeline
from src.generation.structured_result_presenter import (
    build_structured_results,
    public_regulation_citations,
)
from src.retrieval.core.citation_builder import build_citation_from_lookup
from src.retrieval.core.foreign_language_lookup import foreign_language_lookup
from src.retrieval.core.office_lookup import office_lookup
from src.retrieval.core.program_lookup import program_lookup
from src.retrieval.core.scholarship_lookup import scholarship_classification_lookup
from src.retrieval.core.structured_lookup import structured_lookup
from src.retrieval.core.study_duration_lookup import study_duration_lookup


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_json(relative_path: str):
    return json.loads((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))


def test_builds_display_table_without_internal_source_fields() -> None:
    result = build_structured_results(
        {
            "lookup_type": "scholarship_classification",
            "table_name": "Xếp loại học bổng",
            "source_label": "Bảng học bổng trong Sổ tay",
            "cohort": "K51",
            "source_pages": [42],
            "items": [
                {
                    "scholarship_level": "Khá",
                    "academic_classification": "Xuất sắc",
                    "value": "1.2 lần mức học phí",
                    "source_pages": [42],
                    "raw_text": "internal",
                }
            ],
        }
    )

    assert len(result) == 1
    assert result[0]["cohort"] == "K51"
    assert result[0]["columns"] == [
        "scholarship_level",
        "academic_classification",
        "value",
    ]
    assert "source_pages" not in result[0]["rows"][0]
    assert "raw_text" not in result[0]["rows"][0]
    assert result[0]["provenance"]["source_pages"] == [42]
    assert result[0]["presentation_type"] == "table"


def test_office_directory_uses_contact_card_and_hides_internal_fields() -> None:
    result = build_structured_results(
        {
            "lookup_type": "office_directory",
            "lookup_scope": "office",
            "table_name": "Danh sách phòng ban liên hệ",
            "cohort": "K51",
            "items": [
                {
                    "unit_name": "Phòng Đào tạo",
                    "aliases": ["PĐT"],
                    "office": "Nhà A, phòng 101",
                    "phones": ["(028) 1234 5678"],
                    "emails": ["pdt@hcmue.edu.vn"],
                    "websites": ["pdt.hcmue.edu.vn"],
                    "responsibilities": ["Một mô tả nhiệm vụ rất dài"],
                    "summary": "Thông tin nội bộ không dành cho contact card",
                    "cohort": "K51",
                    "source_pages": [10],
                }
            ],
        }
    )

    assert result[0]["presentation_type"] == "contact_card"
    assert result[0]["columns"] == [
        "unit_name",
        "address",
        "phone",
        "email",
        "website",
    ]
    assert result[0]["rows"] == [
        {
            "unit_name": "Phòng Đào tạo",
            "address": "Nhà A, phòng 101",
            "phone": "(028) 1234 5678",
            "email": "pdt@hcmue.edu.vn",
            "website": "pdt.hcmue.edu.vn",
        }
    ]
    assert not {
        "aliases",
        "cohort",
        "summary",
        "responsibilities",
    }.intersection(result[0]["rows"][0])


def test_presentation_type_is_data_driven_by_lookup_scope(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.generation.structured_result_presenter.load_lookup_registry",
        lambda: {
            "tools": {
                "demo_directory": {"presentation_type": "contact_card"},
            }
        },
    )
    result = build_structured_results(
        {
            "lookup_type": "custom_directory",
            "lookup_scope": "demo_directory",
            "items": [{"unit_name": "Đơn vị thử nghiệm", "phone": "123"}],
        }
    )

    assert result[0]["presentation_type"] == "contact_card"
    assert result[0]["rows"] == [
        {"unit_name": "Đơn vị thử nghiệm", "phone": "123"}
    ]


def test_presenter_prefers_full_display_rows_over_matched_result() -> None:
    lookup = {
        "lookup_type": "conduct_classification",
        "table_name": "Bảng phân loại kết quả rèn luyện",
        "cohort": "K51",
        "result": {"label": "Tốt", "range": "Từ 80 đến dưới 90"},
        "display_rows": [
            {"label": "Xuất sắc", "range": "Từ 90 đến 100"},
            {"label": "Tốt", "range": "Từ 80 đến dưới 90"},
            {"label": "Khá", "range": "Từ 65 đến dưới 80"},
        ],
    }

    projection = build_structured_results(lookup)

    assert lookup["result"] == {
        "label": "Tốt",
        "range": "Từ 80 đến dưới 90",
    }
    assert projection[0]["rows"] == lookup["display_rows"]


def test_real_conduct_lookup_keeps_match_and_displays_complete_table() -> None:
    scoring_tables = _load_json("data/processed/tables/scoring_tables.json")

    lookup = structured_lookup(
        "85 điểm rèn luyện được xếp loại gì?",
        scoring_tables,
        "K51",
    )

    assert lookup is not None
    assert lookup["result"]["label"] == "Tốt"
    expected_rows = next(
        table["rows"]
        for table in scoring_tables
        if table.get("cohort") == "K51"
        and table.get("table_id") == "conduct_classification"
    )
    projection = build_structured_results(lookup)
    assert projection[0]["rows"] == expected_rows


def test_flattens_multi_cohort_nested_tables() -> None:
    result = build_structured_results(
        {
            "lookup_type": "multi_cohort_structured",
            "sub_lookups": [
                {
                    "lookup_type": "study_duration",
                    "cohort": "K50",
                    "table_name": "Thời gian học tập",
                    "items": [
                        {
                            "training_mode": "chinh_quy",
                            "rows": [{"program_type": "Đại học", "max_years": 8}],
                        }
                    ],
                },
                {
                    "lookup_type": "study_duration",
                    "cohort": "K51",
                    "table_name": "Thời gian học tập",
                    "items": [
                        {
                            "training_mode": "chinh_quy",
                            "rows": [{"program_type": "Đại học", "max_years": 8}],
                        }
                    ],
                },
            ],
        }
    )

    assert [item["cohort"] for item in result] == ["K50", "K51"]
    assert result[0]["rows"] == [
        {"training_mode": "chinh_quy", "program_type": "Đại học", "max_years": 8}
    ]


def test_manual_program_faculty_mapping_has_field_level_provenance() -> None:
    result = build_structured_results(
        {
            "lookup_type": "program_directory",
            "table_name": "Danh sách ngành đào tạo",
            "cohort": "K51",
            "result": [
                {
                    "program_name": "Công nghệ Thông tin",
                    "faculty_name": "Khoa Công nghệ Thông tin",
                    "faculty_name_source": "manual_program_faculty_rule",
                    "quality_status": "approved",
                    "source_pages": [178, 179],
                }
            ],
        }
    )

    faculty_provenance = result[0]["field_provenance"]["faculty_name"]
    assert faculty_provenance["source_type"] == "curated_registry"
    assert faculty_provenance["registry"] == "configs/program_overrides.yaml"
    assert "faculty_name_source" not in result[0]["rows"][0]


def test_program_lookup_preserves_mapping_provenance_for_the_presenter() -> None:
    lookup = program_lookup(
        "Công nghệ Thông tin thuộc khoa nào?",
        [
            {
                "program_name": "Công nghệ Thông tin",
                "faculty_name": "Khoa Công nghệ Thông tin",
                "faculty_name_source": "manual_program_faculty_rule",
                "quality_status": "approved",
                "cohort": "K51",
                "document_id": "so_tay_sinh_vien_khoa_51",
                "source_pages": [178, 179],
            }
        ],
        cohort="K51",
        routing={
            "content_type": "program_directory",
            "action": "resolve_faculty",
            "scope": "school",
        },
    )

    assert lookup is not None
    assert lookup["result"][0]["faculty_name_source"] == "manual_program_faculty_rule"
    projection = build_structured_results(lookup)
    assert projection[0]["field_provenance"]["faculty_name"]["source_type"] == "curated_registry"


def test_structured_lookup_citation_is_separated_from_regulation_citation() -> None:
    structured = build_citation_from_lookup(
        {
            "lookup_type": "conduct_classification",
            "result": {"label": "Tốt", "range": "80-89"},
            "source_label": "Bảng điểm rèn luyện",
        }
    )[0]
    regulation = {"chunk_id": "K51_Dieu_4", "chunk_type": "article"}

    assert structured["evidence_kind"] == "structured_result"
    assert public_regulation_citations([structured, regulation]) == [regulation]


def test_chat_response_exposes_structured_results_but_not_structured_citation() -> None:
    table = {
        "id": "conduct:K51:0",
        "lookup_type": "conduct_classification",
        "title": "Điểm rèn luyện",
        "columns": ["label"],
        "rows": [{"label": "Tốt"}],
        "provenance": {"source_type": "structured_dataset"},
    }
    response = _to_chat_response(
        {
            "answer": "Xếp loại Tốt.",
            "status": "answered",
            "structured_results": [table],
            "citations_used": [
                {"chunk_id": "structured:x", "evidence_kind": "structured_result"},
                {"chunk_id": "K51_Dieu_4", "chunk_type": "article"},
            ],
        },
        include_debug=False,
    )

    assert response.structured_results == [table]
    assert response.citations_used == [
        {"chunk_id": "K51_Dieu_4", "chunk_type": "article"}
    ]


def test_stream_metadata_uses_the_same_structured_result_projection() -> None:
    pipeline = AnswerPipeline.__new__(AnswerPipeline)
    pipeline.llm_config = {"model_name": "mock-model"}
    lookup = {
        "lookup_type": "conduct_classification",
        "table_name": "Điểm rèn luyện",
        "result": {"label": "Tốt", "range": "80-89"},
    }

    metadata = pipeline._build_stream_metadata(
        {"structured_result": lookup},
        status="answered",
        effective_query="80 điểm rèn luyện xếp loại gì?",
    )

    assert metadata["structured_results"] == build_structured_results(lookup)


def test_current_structured_assets_project_across_supported_domains() -> None:
    scoring_tables = _load_json("data/processed/tables/scoring_tables.json")
    structured_tables = _load_json(
        "data/processed/tables/structured_tables_registry.json"
    )
    language_tables = _load_json(
        "data/processed/tables/foreign_language_equivalency_table.json"
    )
    programs = _load_json("data/processed/directories/program_directory.json")
    offices = _load_json("data/processed/directories/student_office_profiles.json")

    lookups = [
        structured_lookup("85 điểm rèn luyện xếp loại gì?", scoring_tables, "K51"),
        structured_lookup("GPA 3.4 xếp loại học lực gì?", scoring_tables, "K51"),
        structured_lookup("8.0 quy đổi sang điểm chữ nào?", scoring_tables, "K51"),
        foreign_language_lookup(
            "IELTS 6.0 tương đương bậc mấy?",
            language_tables,
            "K51",
            slots={"certificate_or_language": "IELTS", "score_or_level": "6.0"},
        ),
        scholarship_classification_lookup(
            "Học bổng loại Giỏi",
            structured_tables,
            "K51",
            slots={"score_or_label": "Giỏi"},
        ),
        study_duration_lookup(
            "Thời gian đào tạo đại học chính quy",
            structured_tables,
            "K51",
            slots={"training_mode": "chính quy", "program_type": "đại học"},
        ),
        program_lookup(
            "Công nghệ Thông tin thuộc khoa nào?",
            programs,
            cohort="K51",
            routing={
                "content_type": "program_directory",
                "action": "resolve_faculty",
                "scope": "school",
            },
        ),
        office_lookup(
            "Phòng Đào tạo",
            offices,
            cohort="K51",
            routing={"intent": "office_query", "content_type": "office_directory"},
            candidate_text="Phòng Đào tạo",
            require_confident_match=True,
        ),
    ]

    assert all(lookup is not None for lookup in lookups)
    projections = [build_structured_results(lookup) for lookup in lookups]
    assert all(projection for projection in projections)
    assert all(table["rows"] and table["columns"] for projection in projections for table in projection)
    # Bounded policy tables expose their complete applicable table, while
    # large program/office directories remain scoped to the matched record.
    assert len(projections[0][0]["rows"]) == 6
    assert len(projections[3][0]["rows"]) == 10
    assert len(projections[-2][0]["rows"]) == 1
    assert len(projections[-1][0]["rows"]) == 1
    assert all(
        "raw_text" not in row and "source_pages" not in row
        for projection in projections
        for table in projection
        for row in table["rows"]
    )
