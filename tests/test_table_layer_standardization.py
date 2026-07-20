from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_table_quality import classify_item
from scripts.build_structured_table_layer import (
    build_registry,
    build_structured_table_layer,
    repair_boundary_leaks,
)
from src.extraction.directory_parser import extract_office_directory
from src.retrieval.core.office_lookup import office_lookup
from src.retrieval.core.query_router import route_query
from src.retrieval.core.structured_context import build_structured_context


def test_table_audit_does_not_flag_plain_bang_diem_text() -> None:
    item = {
        "_id": "K50_plain_article",
        "cohort": "K50",
        "document_id": "doc",
        "metadata": {"article": "Điều 1.", "title": "Text"},
        "content": "Sinh viên xem bảng điểm và kết quả học tập trên hệ thống.",
    }

    assert classify_item(item) is None


def test_table_audit_detects_foreign_language_flattened_table() -> None:
    item = {
        "_id": "K50_foreign_flattened",
        "cohort": "K50",
        "document_id": "doc",
        "metadata": {"article": "Điều 8.", "title": "Tổ chức thực hiện"},
        "content": (
            "TT Ngôn ngữ Chứng chỉ/Văn bằng Trình độ/Thang điểm "
            "Tương đương bậc 3 Tương đương bậc 4 TOEFL IELTS TOEIC"
        ),
    }

    result = classify_item(item)

    assert result is not None
    assert result["category"] == "regulation_table"
    assert result["extraction_status"] == "flattened"


def test_office_parser_keeps_health_station_separate_from_library() -> None:
    records = extract_office_directory(
        [
            {
                "page_number": 10,
                "content_type": "office_directory",
                "text": (
                    "1. Thư viện\nEmail: thuvien@hcmue.edu.vn\n"
                    "2. Trạm Y tế\nEmail: tramyte@hcmue.edu.vn\n"
                    "Văn phòng làm việc: Nhà A, P.006"
                ),
            }
        ]
    )

    assert [record["unit_name"] for record in records] == [
        "1. Thư viện",
        "2. Trạm Y tế",
    ]
    assert "tramyte@hcmue.edu.vn" not in records[0]["raw_text"]
    assert "tramyte@hcmue.edu.vn" in records[1]["raw_text"]


def test_structured_table_registry_ignores_synthetic_retrieval_copies() -> None:
    table = {
        "table_id": "K50_study_duration",
        "table_type": "study_duration",
        "rows": [{"program": "first_degree", "maximum": "8 years"}],
    }
    items = [
        {
            "_id": "K50_Dieu3",
            "cohort": "K50",
            "document_id": "handbook_k50",
            "metadata": {},
            "tables": [table],
        },
        {
            "_id": "SYN_K50_study_duration",
            "cohort": "K50",
            "document_id": "handbook_k50",
            "metadata": {"synthetic_source": True},
            "tables": [table],
        },
    ]

    assert len(build_registry(items)) == 1


def test_boundary_repair_detaches_appended_notice_from_article() -> None:
    article = (
        "Tài liệu: Quy định\nNội dung:\nĐiều 15. Hiệu lực.\n"
        + "Quy định có hiệu lực kể từ ngày ký./.\n"
        + "Nội dung điều khoản " * 30
        + "Nơi nhận:\nHIỆU TRƯỞNG\n(đã ký)\n"
        + "x" * 5000
        + "\nTHÔNG BÁO\nVề việc hỗ trợ học phí\n"
        + "Nội dung chính sách " * 40
    )
    items, report = repair_boundary_leaks(
        [
            {
                "_id": "K50_Dieu15",
                "content": article,
                "normalized_content": article,
                "cohort": "K50",
                "document_id": "handbook_k50",
                "tables": [],
                "metadata": {
                    "article": "Điều 15.",
                    "cohort": "K50",
                    "document_id": "handbook_k50",
                    "content_type": "regulation_text",
                },
            }
        ]
    )

    assert report["repaired_parent_count"] == 1
    assert report["supplement_parent_count"] == 1
    assert len(items) == 2
    assert "THÔNG BÁO" not in items[0]["content"]
    assert items[1]["metadata"]["source_type"] == "supplemental_regulation"


def test_boundary_repair_excludes_existing_ktx_procedure() -> None:
    parent = {
        "_id": "K50_Dieu15",
        "content": "Điều 15. Hiệu lực.",
        "normalized_content": "Điều 15. Hiệu lực.",
        "cohort": "K50",
        "document_id": "handbook_k50",
        "tables": [],
        "metadata": {
            "article": "Điều 15.",
            "cohort": "K50",
            "document_id": "handbook_k50",
            "content_type": "regulation_text",
            "boundary_repaired": True,
            "detached_supplement_count": 1,
        },
    }
    ktx_supplement = {
        "_id": "K50_Dieu15_Supplement_01",
        "content": "QUY TRÌNH XÉT SINH VIÊN VÀO Ở KÝ TÚC XÁ\nNội dung quy trình.",
        "normalized_content": "QUY TRÌNH XÉT SINH VIÊN VÀO Ở KÝ TÚC XÁ",
        "cohort": "K50",
        "document_id": "handbook_k50",
        "tables": [],
        "metadata": {
            "source_type": "supplemental_regulation",
            "content_type": "regulation_text",
            "boundary_repair_generated": True,
            "boundary_source_parent_id": "K50_Dieu15",
        },
    }

    items, report = repair_boundary_leaks([parent, ktx_supplement])

    assert [item["_id"] for item in items] == ["K50_Dieu15"]
    assert items[0]["metadata"]["detached_supplement_count"] == 0
    assert report["supplement_parent_count"] == 0


def test_structured_context_keeps_full_selected_tables() -> None:
    small = {
        "table_id": "K50_small",
        "data_category": "regulation_table",
        "table_type": "scoring",
        "table_subtype": "academic_classification",
        "cohort": "K50",
        "document_id": "handbook_k50",
        "source_parent_id": "K50_Dieu11",
        "rows": [{"label": "Giỏi", "range": "3.2-3.59"}],
    }
    large = {
        **small,
        "table_id": "K50_large",
        "source_parent_id": "K50_Dieu12",
        "rows": [{"label": f"Mức {index}", "range": str(index)} for index in range(40)],
    }
    decision = {
        "lookup_type": "scoring",
        "execution_mode": "structured",
        "slots": {"operation": "academic_classification"},
        "cohort": "K50",
    }

    result = build_structured_context(
        decision,
        [small, large],
        query="So sánh các mức học lực K50",
        cohort="K50",
    )

    assert result is not None
    assert all(item["selection_method"] == "full_table" for item in result["items"])
    assert sorted(len(item["rows"]) for item in result["items"]) == [1, 40]


def test_structured_context_selects_k51_pass_fail_table_by_applicability() -> None:
    tables = [
        {
            "table_id": "K51_Dieu10_grade_scale_foundation",
            "table_type": "scoring",
            "table_subtype": "grade_scale",
            "cohort": "K51",
            "source_parent_id": "K51_Dieu10",
            "rows": [{"Kết quả": "Đạt", "Thang điểm 10": "4,0 - 4,7"}],
        },
        {
            "table_id": "K51_Dieu10_pass_fail_ungraded",
            "table_type": "scoring",
            "table_subtype": "pass_fail_ungraded",
            "cohort": "K51",
            "source_parent_id": "K51_Dieu10",
            "applicability": "Học phần chỉ yêu cầu đạt, không tính GPA.",
            "rows": [{"Kết quả": "Đạt", "Thang điểm 10": "Từ 5,0 trở lên"}],
        },
    ]
    decision = {
        "lookup_type": "scoring",
        "execution_mode": "structured",
        "cohort": "K51",
        "slots": {"operation": "pass_fail_ungraded"},
    }

    result = build_structured_context(
        decision,
        tables,
        query="Học phần chỉ đánh giá đạt chưa đạt của K51 cần mấy điểm?",
        cohort="K51",
    )

    assert result is not None
    assert [item["table_subtype"] for item in result["items"]] == [
        "pass_fail_ungraded"
    ]
    assert result["items"][0]["rows"][0]["Thang điểm 10"] == "Từ 5,0 trở lên"


def test_structured_context_filters_study_duration_by_training_mode() -> None:
    tables = [
        {
            "table_id": "K48_study_duration_chinh_quy",
            "table_type": "study_duration",
            "cohort": "K48-K49",
            "source_parent_id": "K48_Dieu3",
            "applicability": "Ap dung cho hinh thuc dao tao chinh quy.",
            "rows": [{"program": "first_degree", "max": "8 nam"}],
        },
        {
            "table_id": "K48_study_duration_vua_lam_vua_hoc",
            "table_type": "study_duration",
            "cohort": "K48-K49",
            "source_parent_id": "K48_Dieu3",
            "applicability": "Ap dung cho hinh thuc dao tao vua lam vua hoc.",
            "rows": [{"program": "first_degree", "max": "9 nam"}],
        },
    ]
    decision = {
        "lookup_type": "study_duration",
        "execution_mode": "structured",
        "cohort": "K48-K49",
        "slots": {"training_mode": "chinh_quy", "program_type": None},
    }

    result = build_structured_context(
        decision,
        tables,
        query="K48-K49 he chinh quy hoc toi da may nam?",
        cohort="K48-K49",
    )

    assert result is not None
    assert [item["table_id"] for item in result["items"]] == [
        "K48_study_duration_chinh_quy"
    ]


def test_builder_attaches_pass_fail_table_to_authoritative_parent(tmp_path: Path) -> None:
    docstore_path = tmp_path / "all_docstore_items.json"
    table_dir = tmp_path / "tables"
    directory_dir = tmp_path / "directories"
    directory_dir.mkdir()
    content = (
        "Điều 10. Đánh giá và tính điểm học phần. Thang điểm 10 Thang điểm chữ. "
        "Các học phần thuộc loại đạt không phân mức (chỉ yêu cầu đạt, không tính "
        "vào điểm trung bình học tập) yêu cầu đạt 5,0 trở lên theo thang điểm 10, "
        "và được quy đổi ra điểm chữ là P."
    )
    docstore_path.write_text(
        json.dumps(
            [
                {
                    "_id": "K51_QuyCheDaoTao_Chuong3_Dieu10",
                    "cohort": "K51",
                    "document_id": "so_tay_sinh_vien_khoa_51",
                    "content": content,
                    "metadata": {
                        "cohort": "K51",
                        "document_id": "so_tay_sinh_vien_khoa_51",
                        "article": "Điều 10.",
                        "title": "Đánh giá và tính điểm học phần",
                        "source_pages": [19],
                    },
                    "tables": [],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = build_structured_table_layer(docstore_path, table_dir, directory_dir)

    assert report["pass_fail_ungraded_table_count"] == 1
    assert report["pass_fail_ungraded_attached_count"] == 1
    parent = json.loads(docstore_path.read_text(encoding="utf-8"))[0]
    assert parent["tables"][0]["table_kind"] == "pass_fail_ungraded"
    registry = json.loads(
        (table_dir / "structured_tables_registry.json").read_text(encoding="utf-8")
    )
    assert registry[0]["table_subtype"] == "pass_fail_ungraded"
    assert registry[0]["source_parent_id"] == parent["_id"]

    second_report = build_structured_table_layer(docstore_path, table_dir, directory_dir)
    assert second_report["pass_fail_ungraded_table_count"] == 1
    assert second_report["pass_fail_ungraded_attached_count"] == 0
    second_registry = json.loads(
        (table_dir / "structured_tables_registry.json").read_text(encoding="utf-8")
    )
    assert len(second_registry) == 1


def test_build_structured_table_layer_outputs_foreign_table_and_services(tmp_path: Path) -> None:
    docstore_path = tmp_path / "all_docstore_items.json"
    table_dir = tmp_path / "tables"
    directory_dir = tmp_path / "directories"
    directory_dir.mkdir()

    docstore_path.write_text(
        json.dumps(
            [
                {
                    "_id": "K50_QuyDinhChuanDauRaNgoaiNgu_KhongCoChuong_Dieu8",
                    "cohort": "K50",
                    "document_id": "so_tay_sinh_vien_khoa_50",
                    "content": "Điều 8. Tổ chức thực hiện\nIELTS 4.0 - 5.0",
                    "metadata": {
                        "cohort": "K50",
                        "document_id": "so_tay_sinh_vien_khoa_50",
                        "article": "Điều 8.",
                        "title": "Tổ chức thực hiện",
                        "source_pages": [114, 115],
                    },
                    "tables": [],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (directory_dir / "K50_office_directory.json").write_text(
        json.dumps(
            [
                {
                    "record_id": "office_1",
                    "cohort": "K50",
                    "document_id": "so_tay_sinh_vien_khoa_50",
                    "unit_name": "1. Phòng Công tác chính trị và Học sinh, sinh viên",
                    "source_pages": [173],
                    "raw_text": (
                        "1. Phòng Công tác chính trị và Học sinh, sinh viên\n"
                        "Điện thoại liên lạc: (028) 38352020\n"
                        "Email: hopthusinhvien@hcmue.edu.vn\n"
                        "Văn phòng làm việc: Nhà A, tầng 1, P.108\n"
                        "Những công việc của đơn vị liên quan đến sinh viên:\n"
                        "- xác nhận và chứng thực các giấy tờ liên quan đến sinh viên;\n"
                    ),
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = build_structured_table_layer(docstore_path, table_dir, directory_dir)

    assert report["foreign_language_table_count"] == 1
    assert report["student_service_count"] == 2
    docstore = json.loads(docstore_path.read_text(encoding="utf-8"))
    assert docstore[0]["tables"][0]["table_type"] == "foreign_language"
    assert docstore[0]["tables"][0]["data_category"] == "regulation_table"
    services = json.loads(
        (directory_dir / "student_service_directory.json").read_text(encoding="utf-8")
    )
    assert services[0]["content_type"] == "student_service_directory"
    assert services[0]["data_category"] == "directory_table"
    assert "giấy xác nhận đang học" in services[0]["aliases"]
    assert any("hồ sơ vay vốn" in service["aliases"] for service in services)


def test_office_lookup_matches_student_service_alias() -> None:
    result = office_lookup(
        "xin giấy đang học liên hệ ai",
        [
            {
                "service_id": "K50_office_2_service_1",
                "cohort": "K50",
                "service": "xác nhận và chứng thực các giấy tờ liên quan đến sinh viên",
                "aliases": ["giấy xác nhận đang học", "giấy đang học"],
                "unit": "Phòng Công tác chính trị và Học sinh, sinh viên",
                "emails": ["hopthusinhvien@hcmue.edu.vn"],
                "phones": ["(028) 38352020"],
                "source_pages": [173],
                "content_type": "student_service_directory",
            }
        ],
        cohort="K50",
        routing={"intent": "office_query", "target_chunk_types": ["office_directory"]},
    )

    assert result is not None
    assert result["lookup_scope"] == "student_service"
    assert result["result"][0]["service_id"] == "K50_office_2_service_1"


def test_service_contact_query_routes_to_service_lookup_before_form_lookup() -> None:
    route = route_query("xin giấy đang học liên hệ ai")

    assert route["intent"] == "office_query"
    assert route["strategy"] == "student_service_lookup"
    assert route["lookup_scope"] == "student_service"
