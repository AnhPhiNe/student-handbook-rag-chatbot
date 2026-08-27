import os
from typing import Any


def build_scoring_tables(cohort: str | None = None) -> list[dict[str, Any]]:
    cohort = (cohort or os.environ.get("COHORT", "")).upper()
    grade_tables = (
        _new_cohort_grade_10_tables(cohort)
        if cohort in {"K51", "K50-K51"}
        else [_legacy_grade_10_table()]
    )
    return grade_tables + _shared_scoring_tables(cohort)


def _legacy_grade_10_table() -> dict[str, Any]:
    return {
        "table_id": "grade_10_to_letter",
        "lookup_group": "grade_10_to_letter",
        "table_name": "Quy đổi thang điểm 10 sang điểm chữ",
        "source_pages": [20],
        "review_status": "needs_human_verified",
        "applicability": "Áp dụng chung theo bảng quy đổi điểm học phần",
        "pass_threshold": "Từ 4.0 trở lên",
        "rows": [
            {"status": "Đạt", "score_10_range": "8.5-10", "letter_grade": "A"},
            {"status": "Đạt", "score_10_range": "7.8-8.4", "letter_grade": "B+"},
            {"status": "Đạt", "score_10_range": "7.0-7.7", "letter_grade": "B"},
            {"status": "Đạt", "score_10_range": "6.3-6.9", "letter_grade": "C+"},
            {"status": "Đạt", "score_10_range": "5.5-6.2", "letter_grade": "C"},
            {"status": "Đạt", "score_10_range": "4.8-5.4", "letter_grade": "D+"},
            {"status": "Đạt", "score_10_range": "4.0-4.7", "letter_grade": "D"},
            {"status": "Không đạt", "score_10_range": "3.0-3.9", "letter_grade": "F+"},
            {"status": "Không đạt", "score_10_range": "0.0-2.9", "letter_grade": "F"},
        ],
    }


def _new_cohort_grade_10_tables(cohort: str) -> list[dict[str, Any]]:
    cohort_label = "K51" if cohort == "K50-K51" else cohort
    base = {
        "lookup_group": "grade_10_to_letter",
        "source_pages": [20],
        "review_status": "needs_human_verified",
        "note": (
            "Quy định sửa đổi áp dụng từ khóa tuyển sinh năm 2025 trở về sau; "
            "cần xác định loại học phần trước khi kết luận điểm qua môn."
        ),
    }

    return [
        {
            **base,
            "table_id": "grade_10_to_letter_foundation",
            "table_name": f"{cohort_label}: quy đổi điểm cho học phần giáo dục đại cương/học phần chung",
            "applicability": "Học phần giáo dục đại cương hoặc học phần chung thuộc nhóm học phần nền tảng",
            "pass_threshold": "Từ 4.0 trở lên",
            "rows": _grade_rows_with_d_as_pass(),
        },
        {
            **base,
            "table_id": "grade_10_to_letter_remaining",
            "table_name": f"{cohort_label}: quy đổi điểm cho các học phần còn lại",
            "applicability": "Các học phần còn lại",
            "pass_threshold": "Từ 5.5 trở lên",
            "rows": _grade_rows_with_d_as_fail(),
        },
        {
            **base,
            "table_id": "grade_10_to_letter_pass_fail_ungraded",
            "table_name": f"{cohort_label}: học phần đạt/không đạt không phân mức",
            "applicability": "Học phần chỉ yêu cầu đạt, không tính vào điểm trung bình học tập",
            "pass_threshold": "Từ 5.0 trở lên",
            "rows": [
                {"status": "Đạt", "score_10_range": "5.0-10", "letter_grade": "P"},
                {"status": "Không đạt", "score_10_range": "0.0-dưới 5.0", "letter_grade": "F"},
            ],
        },
    ]


def _grade_rows_with_d_as_pass() -> list[dict[str, str]]:
    return [
        {"status": "Đạt", "score_10_range": "8.5-10", "letter_grade": "A"},
        {"status": "Đạt", "score_10_range": "7.8-8.4", "letter_grade": "B+"},
        {"status": "Đạt", "score_10_range": "7.0-7.7", "letter_grade": "B"},
        {"status": "Đạt", "score_10_range": "6.3-6.9", "letter_grade": "C+"},
        {"status": "Đạt", "score_10_range": "5.5-6.2", "letter_grade": "C"},
        {"status": "Đạt", "score_10_range": "4.8-5.4", "letter_grade": "D+"},
        {"status": "Đạt", "score_10_range": "4.0-4.7", "letter_grade": "D"},
        {"status": "Không đạt", "score_10_range": "3.0-3.9", "letter_grade": "F+"},
        {"status": "Không đạt", "score_10_range": "0.0-2.9", "letter_grade": "F"},
    ]


def _grade_rows_with_d_as_fail() -> list[dict[str, str]]:
    return [
        {"status": "Đạt", "score_10_range": "8.5-10", "letter_grade": "A"},
        {"status": "Đạt", "score_10_range": "7.8-8.4", "letter_grade": "B+"},
        {"status": "Đạt", "score_10_range": "7.0-7.7", "letter_grade": "B"},
        {"status": "Đạt", "score_10_range": "6.3-6.9", "letter_grade": "C+"},
        {"status": "Đạt", "score_10_range": "5.5-6.2", "letter_grade": "C"},
        {"status": "Không đạt", "score_10_range": "4.8-5.4", "letter_grade": "D+"},
        {"status": "Không đạt", "score_10_range": "4.0-4.7", "letter_grade": "D"},
        {"status": "Không đạt", "score_10_range": "3.0-3.9", "letter_grade": "F+"},
        {"status": "Không đạt", "score_10_range": "0.0-2.9", "letter_grade": "F"},
    ]


def _scholarship_classification_table(cohort: str) -> dict[str, Any]:
    if cohort in {"K51", "K50-K51"}:
        return {
            "table_id": "scholarship_classification",
            "table_name": "Xếp loại học bổng khuyến khích học tập",
            "source_pages": [70, 71, 72],
            "review_status": "source_verified",
            "schema_variant": "classification_matrix",
            "rows": [
                {
                    "scholarship_level": "Xuất sắc",
                    "academic_classification": "Xuất sắc",
                    "conduct_classification_condition": "Xuất sắc",
                },
                {
                    "scholarship_level": "Giỏi",
                    "academic_classification": "Xuất sắc",
                    "conduct_classification_condition": "Tốt",
                },
                {
                    "scholarship_level": "Giỏi",
                    "academic_classification": "Giỏi",
                    "conduct_classification_condition": "Tốt trở lên",
                },
                {
                    "scholarship_level": "Khá",
                    "academic_classification": "Xuất sắc",
                    "conduct_classification_condition": "Khá",
                },
                {
                    "scholarship_level": "Khá",
                    "academic_classification": "Giỏi",
                    "conduct_classification_condition": "Khá",
                },
                {
                    "scholarship_level": "Khá",
                    "academic_classification": "Khá",
                    "conduct_classification_condition": "Khá trở lên",
                },
            ],
        }

    return {
        "table_id": "scholarship_classification",
        "table_name": "Xếp loại học bổng khuyến khích học tập",
        "source_pages": [53],
        "review_status": "needs_human_verified",
        "schema_variant": "score_ranges",
        "rows": [
            {
                "label": "Khá",
                "scholarship_score_range": "2.56-3.352",
                "academic_score_range": "2.50-3.19",
                "conduct_score_condition": ">=70",
            },
            {
                "label": "Giỏi",
                "scholarship_score_range": "3.20-3.672",
                "academic_score_range": "3.20-3.59",
                "conduct_score_condition": ">=80",
            },
            {
                "label": "Xuất sắc",
                "scholarship_score_range": "3.60-4.0",
                "academic_score_range": "3.60-4.0",
                "conduct_score_condition": ">=90",
            },
        ],
    }


def _scholarship_amount_table(cohort: str) -> dict[str, Any] | None:
    """Return the source-verified HBKKHT amount formula table for a cohort."""

    if cohort not in {"K48-K49", "K50", "K51", "K50-K51"}:
        return None

    tuition_basis = (
        "định mức học phí 01 tín chỉ, phụ thuộc vào ngành học và mức thu "
        "học phí của năm học"
        if cohort in {"K50", "K51", "K50-K51"}
        else "định mức học phí 01 tín chỉ tự nhiên hoặc xã hội, tùy ngành học"
    )
    return {
        "table_id": "scholarship_amount",
        "table_name": "Mức học bổng khuyến khích học tập",
        "review_status": "source_verified",
        "schema_variant": "amount_formula_by_level",
        "rows": [
            {
                "scholarship_level": "Khá",
                "formula": "Số tín chỉ x định mức học phí 01 tín chỉ x 1,0",
                "multiplier": 1.0,
                "tuition_basis": tuition_basis,
            },
            {
                "scholarship_level": "Giỏi",
                "formula": "Số tín chỉ x định mức học phí 01 tín chỉ x 1,25",
                "multiplier": 1.25,
                "tuition_basis": tuition_basis,
            },
            {
                "scholarship_level": "Xuất sắc",
                "formula": "Số tín chỉ x định mức học phí 01 tín chỉ x 1,5",
                "multiplier": 1.5,
                "tuition_basis": tuition_basis,
            },
        ],
    }


def _scholarship_eligibility_table(cohort: str) -> dict[str, Any] | None:
    """Return cohort-specific HBKKHT eligibility facts from the same policy article."""

    common_rows = [
        {
            "criterion": "Đối tượng",
            "requirement": (
                "Sinh viên hệ chính quy đang học theo kế hoạch đào tạo của khóa; "
                "không quá thời gian học tập chuẩn"
            ),
        },
        {
            "criterion": "Học tập, rèn luyện và kỷ luật",
            "requirement": (
                "Kết quả học tập và rèn luyện từ loại Khá trở lên; không bị kỷ luật "
                "từ mức khiển trách trở lên"
            ),
        },
        {
            "criterion": "Khối lượng học tập thông thường",
            "requirement": (
                "Tích lũy ít nhất 15 tín chỉ theo kế hoạch; các tín chỉ dùng để xét "
                "phải đạt và không tính tín chỉ trả nợ, cải thiện hoặc tương đương"
            ),
        },
    ]
    if cohort == "K51":
        rows = [
            *common_rows,
            {
                "criterion": "Học kỳ cuối theo chương trình chuẩn",
                "requirement": (
                    "Khóa tuyển sinh từ năm 2022 trở về sau tích lũy ít nhất 11 tín chỉ; "
                    "khóa từ năm 2021 trở về trước ít nhất 06 tín chỉ"
                ),
            },
            {
                "criterion": "Tốt nghiệp sớm",
                "requirement": (
                    "Học kỳ cuối được phép có tổng số tín chỉ tích lũy nhỏ hơn 15"
                ),
            },
            {
                "criterion": "Học cùng lúc hai chương trình",
                "requirement": (
                    "Chỉ xét học bổng cho chương trình thứ nhất; các tín chỉ đã đăng ký "
                    "ở chương trình thứ hai trong học kỳ xét học bổng vẫn phải đạt"
                ),
            },
        ]
    elif cohort in {"K48-K49", "K50", "K50-K51"}:
        rows = [
            *common_rows,
            {
                "criterion": "Học kỳ II năm cuối",
                "requirement": "Đăng ký từ 06 tín chỉ trở lên",
            },
        ]
    else:
        return None

    return {
        "table_id": "scholarship_eligibility",
        "table_name": "Điều kiện xét học bổng khuyến khích học tập",
        "review_status": "source_verified",
        "schema_variant": "eligibility_criteria",
        "rows": rows,
    }


def _shared_scoring_tables(cohort: str) -> list[dict[str, Any]]:
    tables = [
        {
            "table_id": "letter_to_grade_4",
            "table_name": "Quy đổi điểm chữ sang thang điểm 4",
            "source_pages": [22],
            "review_status": "needs_human_verified",
            "rows": [
                {"letter_grade": "A", "score_4": 4.0},
                {"letter_grade": "B+", "score_4": 3.5},
                {"letter_grade": "B", "score_4": 3.0},
                {"letter_grade": "C+", "score_4": 2.5},
                {"letter_grade": "C", "score_4": 2.0},
                {"letter_grade": "D+", "score_4": 1.5},
                {"letter_grade": "D", "score_4": 1.0},
                {"letter_grade": "F+", "score_4": 0.5},
                {"letter_grade": "F", "score_4": 0.0},
            ],
        },
        {
            "table_id": "academic_classification",
            "table_name": "Xếp loại học lực theo thang điểm 4",
            "source_pages": [23],
            "review_status": "needs_human_verified",
            "rows": [
                {"range": "3.6-4.0", "label": "Xuất sắc"},
                {"range": "3.2-dưới 3.6", "label": "Giỏi"},
                {"range": "2.5-dưới 3.2", "label": "Khá"},
                {"range": "2.0-dưới 2.5", "label": "Trung bình"},
                {"range": "1.0-dưới 2.0", "label": "Yếu"},
                {"range": "dưới 1.0", "label": "Kém"},
            ],
        },
        {
            "table_id": "conduct_classification",
            "table_name": "Phân loại kết quả rèn luyện",
            "source_pages": [74],
            "review_status": "needs_human_verified",
            "rows": [
                {"range": "90-100", "label": "Xuất sắc"},
                {"range": "80-dưới 90", "label": "Tốt"},
                {"range": "65-dưới 80", "label": "Khá"},
                {"range": "50-dưới 65", "label": "Trung bình"},
                {"range": "35-dưới 50", "label": "Yếu"},
                {"range": "dưới 35", "label": "Kém"},
            ],
        },
        _scholarship_classification_table(cohort),
    ]
    scholarship_amount = _scholarship_amount_table(cohort)
    scholarship_eligibility = _scholarship_eligibility_table(cohort)
    return tables + [
        table
        for table in (scholarship_amount, scholarship_eligibility)
        if table is not None
    ]
