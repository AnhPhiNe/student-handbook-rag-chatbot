from typing import Any


def build_scoring_tables() -> list[dict[str, Any]]:
    return [
        {
            "table_id": "grade_10_to_letter",
            "table_name": "Quy đổi thang điểm 10 sang điểm chữ",
            "source_pages": [20],
            "review_status": "needs_human_verified",
            "rows": [
                {"status": "Đạt", "score_10_range": "8.5-10", "letter_grade": "A"},
                {"status": "Đạt", "score_10_range": "7.8-8.4", "letter_grade": "B+"},
                {"status": "Đạt", "score_10_range": "7.0-7.7", "letter_grade": "B"},
                {"status": "Đạt", "score_10_range": "6.3-6.9", "letter_grade": "C+"},
                {"status": "Đạt", "score_10_range": "5.5-6.2", "letter_grade": "C"},
                {"status": "Đạt", "score_10_range": "4.8-5.4", "letter_grade": "D+"},
                {"status": "Đạt", "score_10_range": "4.0-4.7", "letter_grade": "D"},
                {
                    "status": "Không đạt",
                    "score_10_range": "3.0-3.9",
                    "letter_grade": "F+",
                },
                {
                    "status": "Không đạt",
                    "score_10_range": "0.0-2.9",
                    "letter_grade": "F",
                },
            ],
        },
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
        {
            "table_id": "scholarship_classification",
            "table_name": "Xếp loại học bổng khuyến khích học tập",
            "source_pages": [53],
            "review_status": "needs_human_verified",
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
        },
    ]
