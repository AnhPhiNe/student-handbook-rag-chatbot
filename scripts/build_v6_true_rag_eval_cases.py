from __future__ import annotations

import json
from pathlib import Path
from typing import Any


OUTPUT_PATHS = [
    Path("data/eval/true_rag_eval_cases_v6.json"),
    Path("data/eval/true_rag_eval_cases.json"),
]


COHORTS = ("K48-K49", "K50", "K51", "general")


COHORT_REGULATION_QUERIES = [
    ("Điều kiện xét học bổng khuyến khích học tập là gì?", ["citation_required"]),
    ("Sinh viên cần bao nhiêu tín chỉ trong học kỳ để được xét học bổng?", ["table_heavy", "citation_required"]),
    ("Khi nào sinh viên bị cảnh báo học tập?", ["cohort_sensitive", "citation_required"]),
    ("Sinh viên bị buộc thôi học trong những trường hợp nào?", ["cohort_sensitive", "citation_required"]),
    ("Điều kiện công nhận tốt nghiệp gồm những gì?", ["citation_required"]),
    ("Trường có mấy đợt xét tốt nghiệp chính thức trong năm?", ["table_heavy", "graph_expected", "citation_required"]),
    ("Thời gian học tập tối đa của chương trình đại học là bao nhiêu năm?", ["table_heavy", "graph_expected", "citation_required"]),
    ("Sinh viên có được học lại học phần đã đạt để cải thiện điểm không?", ["citation_required"]),
    ("Điểm đánh giá học phần gồm những thành phần nào?", ["citation_required"]),
    ("Điểm thi kết thúc học phần có được phúc khảo không?", ["citation_required"]),
    ("Điều kiện để được học cùng lúc hai chương trình là gì?", ["citation_required"]),
    ("Sinh viên được tạm nghỉ học trong những trường hợp nào?", ["citation_required"]),
    ("Bảo lưu kết quả học tập có tính vào thời gian học tối đa không?", ["citation_required"]),
    ("Sinh viên vi phạm kỷ luật thì ảnh hưởng thế nào đến xét tốt nghiệp?", ["citation_required"]),
    ("Hạng tốt nghiệp bị giảm trong những trường hợp nào?", ["table_heavy", "citation_required"]),
    ("Sinh viên có quyền khiếu nại quyết định kỷ luật không?", ["citation_required"]),
]


COHORT_PROCEDURE_QUERIES = [
    ("Quy trình xét tốt nghiệp được thực hiện như thế nào?", ["procedure", "citation_required"]),
    ("Sinh viên cần làm gì khi kết quả xét tốt nghiệp dự kiến bị sai?", ["procedure", "citation_required"]),
    ("Quy trình xin tạm nghỉ học gồm những bước nào?", ["procedure", "citation_required"]),
    ("Quy trình phúc khảo điểm thi kết thúc học phần như thế nào?", ["procedure", "citation_required"]),
]


COHORT_PROGRAM_QUERIES = [
    ("Ngành Công nghệ thông tin học về những nội dung gì?", ["program_detail", "citation_required"]),
    ("Ngành Sư phạm Tin học có cơ hội nghề nghiệp nào sau tốt nghiệp?", ["program_detail", "citation_required"]),
    ("Ngành Sư phạm Toán học phù hợp với định hướng nghề nghiệp nào?", ["program_detail", "citation_required"]),
]


COHORT_FACULTY_QUERIES = [
    ("Khoa Công nghệ Thông tin có thông tin liên hệ nào?", ["faculty_detail", "citation_required"]),
    ("Khoa Toán - Tin học phụ trách những thông tin gì trong sổ tay?", ["faculty_detail", "citation_required"]),
]


GENERAL_CASES = [
    ("Liên hệ Phòng Đào tạo bằng email nào?", "office_directory", ["office_detail", "citation_required"]),
    ("Phòng Công tác chính trị và Học sinh, sinh viên hỗ trợ những việc gì?", "office_directory", ["office_detail", "citation_required"]),
    ("Sinh viên liên hệ phòng nào về học phí và tài chính?", "office_directory", ["office_detail", "citation_required"]),
    ("Tôi cần giấy xác nhận sinh viên thì liên hệ ở đâu?", "office_directory", ["office_detail", "citation_required"]),
    ("Liên hệ phòng nào khi có vấn đề về tài khoản sinh viên?", "office_directory", ["office_detail", "ambiguous", "citation_required"]),
    ("Phòng Khảo thí và Đảm bảo chất lượng phụ trách nội dung gì?", "office_directory", ["office_detail", "citation_required"]),
    ("Ký túc xá có thông tin liên hệ hoặc đơn vị phụ trách nào?", "office_directory", ["office_detail", "citation_required"]),
    ("Nếu cần hỏi về biểu mẫu hành chính thì liên hệ bộ phận nào?", "office_directory", ["office_detail", "ambiguous", "citation_required"]),
    ("Khoa Ngữ văn có thông tin liên hệ gì?", "faculty_directory", ["faculty_detail", "citation_required"]),
    ("Khoa Địa lý có những thông tin liên hệ nào?", "faculty_directory", ["faculty_detail", "citation_required"]),
    ("Khoa Giáo dục Chính trị phụ trách những ngành hoặc thông tin nào?", "faculty_directory", ["faculty_detail", "citation_required"]),
    ("Khoa Tâm lý học có email hoặc website không?", "faculty_directory", ["faculty_detail", "citation_required"]),
    ("Khoa Sinh học có thông tin liên hệ nào?", "faculty_directory", ["faculty_detail", "citation_required"]),
    ("Khoa Vật lý có thông tin liên hệ nào?", "faculty_directory", ["faculty_detail", "citation_required"]),
    ("Khoa Tiếng Anh có thông tin liên hệ nào?", "faculty_directory", ["faculty_detail", "citation_required"]),
    ("Quy trình đăng ký ở ký túc xá như thế nào?", "procedures", ["procedure", "citation_required"]),
    ("Đối tượng nào được ưu tiên xét vào ký túc xá?", "procedures", ["procedure", "citation_required"]),
    ("Sinh viên muốn xin miễn giảm học phí thì quy trình ra sao?", "procedures", ["procedure", "citation_required"]),
    ("Thủ tục xin giấy xác nhận sinh viên thực hiện như thế nào?", "procedures", ["procedure", "citation_required"]),
    ("Quy trình hỗ trợ chi phí học tập gồm những bước nào?", "procedures", ["procedure", "citation_required"]),
    ("Sinh viên có những nhiệm vụ gì theo sổ tay?", "regulation_sections", ["citation_required"]),
    ("Sinh viên có những quyền gì theo sổ tay?", "regulation_sections", ["citation_required"]),
    ("Nhà trường quy định thế nào về đánh giá kết quả rèn luyện?", "regulation_sections", ["table_heavy", "citation_required"]),
    ("Ngành Việt Nam học học gì và có cơ hội nghề nghiệp nào?", "program_directory", ["program_detail", "citation_required"]),
    ("Ngành Tâm lý học có định hướng nghề nghiệp nào?", "program_directory", ["program_detail", "citation_required"]),
]


def make_case(
    index: int,
    query: str,
    cohort: str,
    content_type: str,
    tags: list[str],
) -> dict[str, Any]:
    expected_content_type = {
        "regulation_sections": "regulation",
        "procedures": "procedure",
    }.get(content_type, content_type)
    prefixed_query = query if cohort == "general" else f"{cohort}: {query}"
    return {
        "id": f"v6_true_rag_{index:03d}",
        "query": prefixed_query,
        "cohort": cohort,
        "expected_cohort": cohort,
        "eval_type": "true_rag",
        "content_type": content_type,
        "expected_content_types": [expected_content_type],
        "expected_intent": "regulation_query",
        "expected_strategy": "semantic_filtered",
        "tags": sorted(set(tags + ["true_rag"])),
    }


def build_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []

    for cohort in COHORTS:
        if cohort == "general":
            for query, content_type, tags in GENERAL_CASES:
                cases.append(make_case(len(cases) + 1, query, cohort, content_type, tags))
            continue

        for query, tags in COHORT_REGULATION_QUERIES:
            cases.append(
                make_case(len(cases) + 1, query, cohort, "regulation_sections", tags)
            )
        for query, tags in COHORT_PROCEDURE_QUERIES:
            cases.append(make_case(len(cases) + 1, query, cohort, "procedures", tags))
        for query, tags in COHORT_PROGRAM_QUERIES:
            cases.append(
                make_case(len(cases) + 1, query, cohort, "program_directory", tags)
            )
        for query, tags in COHORT_FACULTY_QUERIES:
            cases.append(
                make_case(len(cases) + 1, query, cohort, "faculty_directory", tags)
            )

    if len(cases) != 100:
        raise RuntimeError(f"Expected 100 cases, got {len(cases)}")
    return cases


def main() -> None:
    cases = build_cases()
    for path in OUTPUT_PATHS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(cases, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {len(cases)} cases to {path}")


if __name__ == "__main__":
    main()
