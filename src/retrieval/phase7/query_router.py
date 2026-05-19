import re
from typing import Any


def normalize_query(query: str) -> str:
    query = query.strip().lower()
    query = query.replace("–", "-")
    query = re.sub(r"\s+", " ", query)
    return query


def contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def route_query(query: str) -> dict[str, Any]:
    q = normalize_query(query)

    has_form_signal = contains_any(q, [
        "mẫu đơn",
        "đơn xin",
        "biểu mẫu",
        "phiếu",
        "form",
        "mẫu",
        "điền mẫu",
        "giấy",
        "giấy xác nhận",
        "xác nhận sinh viên",
        "đơn học lại",
        "theo dõi tiến độ",
        "trợ cấp",
        "trợ cấp xã hội",
        "miễn giảm",
        "miễn, giảm",
        "miễn giảm học phí",
        "hỗ trợ chi phí",
        "hỗ trợ chi phí học tập",
        "đơn gì",
        "cần đơn",
        "cần đơn gì",
        "làm đơn",
        "làm đơn gì",
        "dùng đơn",
        "dùng đơn gì",
    ])

    has_reg_signal = contains_any(q, [
        "điều kiện",
        "quy định",
        "thủ tục",
        "khi nào",
        "cần đáp ứng",
        "tiêu chí",
        "xét theo",
        "được phép",
    ])

    has_contact_question = contains_any(q, [
        "email",
        "số điện thoại",
        "điện thoại",
        "website",
        "địa chỉ",
        "văn phòng",
        "tầng",
        "liên hệ",
        "phòng nào",
        "đơn vị nào",
        "ở đâu",
    ])

    has_ktx_signal = contains_any(q, [
        "ký túc xá",
        "kí túc xá",
        "ktx",
        "nội trú",
        "vào ở",
    ])

    has_faculty_signal = contains_any(q, [
        "khoa",
        "ngành",
        "tổ trực thuộc",
        "chuyên ngành",
    ])

    has_explicit_office_entity = contains_any(q, [
        "phòng",
        "ban",
        "trung tâm",
        "thư viện",
    ])

    # 1. Calculation query
    has_calc = contains_any(q, ["tính", "tính giúp", "bao nhiêu nếu"])
    has_gpa = contains_any(q, ["gpa", "điểm trung bình", "tbc"])
    has_scholarship_score = "điểm học bổng" in q and contains_any(q, ["tính", "bao nhiêu", "nếu"])

    if has_calc and (has_gpa or has_scholarship_score):
        return {
            "intent": "calculation_query",
            "strategy": "calculator_tool",
            "target_chunk_types": [],
        }

    # 2. KTX/procedure phải bắt trước office.
    # Không xem "ký túc xá" là office entity vì đa số câu KTX hỏi quy trình/tiêu chí/mẫu đơn.
    if has_ktx_signal:
        if has_form_signal or contains_any(q, ["đơn", "mẫu", "giấy"]):
            return {
                "intent": "mixed_query",
                "strategy": "semantic_multi_filter",
                "target_chunk_types": ["form", "procedure"],
            }

        if contains_any(q, ["quy trình", "tiêu chí", "ưu tiên", "điều kiện", "thủ tục", "xét", "hội đồng"]):
            return {
                "intent": "procedure_query",
                "strategy": "semantic_filtered_rerank",
                "target_chunk_types": ["procedure"],
            }

        return {
            "intent": "procedure_query",
            "strategy": "semantic_filtered_rerank",
            "target_chunk_types": ["procedure"],
        }

    # 3. Mixed query: hỏi nhiều nhu cầu cùng lúc
    has_office_signal = has_contact_question or has_explicit_office_entity

    if has_form_signal and (has_reg_signal or has_office_signal):
        target_types = ["form"]

        if has_reg_signal:
            target_types.append("regulation")

        if has_office_signal:
            target_types.append("office_directory")

        return {
            "intent": "mixed_query",
            "strategy": "semantic_multi_filter",
            "target_chunk_types": list(dict.fromkeys(target_types)),
            "trigger": ["đơn gì", "cần đơn gì", "làm đơn gì", "dùng đơn gì"],
            "expansion": ["mẫu đơn", "biểu mẫu", "đơn xin"]
            
        }

    # 4. Form query
    if has_form_signal:
        return {
            "intent": "form_query",
            "strategy": "semantic_filtered_rerank",
            "target_chunk_types": ["form"],
        }

    # 5. Nếu query gốc nói rõ Khoa/Ngành thì ưu tiên faculty,
    # trừ khi query cũng nói rõ "phòng".
    # Ví dụ: "Khoa Tiếng Anh ở đâu?" -> faculty
    # Nhưng: "Website phòng CNTT là gì?" -> office
    if has_faculty_signal and not has_explicit_office_entity:
        return {
            "intent": "faculty_query",
            "strategy": "semantic_filtered_rerank",
            "target_chunk_types": ["faculty_program_directory"],
        }

    # 6. Office/contact query
    # Ví dụ: "Website Phòng Công nghệ Thông tin là gì?"
    # Không đưa "ký túc xá" vào office entity ở đây.
    if has_explicit_office_entity or (
        has_contact_question and not has_faculty_signal
    ):
        return {
            "intent": "office_query",
            "strategy": "semantic_filtered_rerank",
            "target_chunk_types": ["office_directory"],
        }

    # 7. Faculty query còn lại
    if has_faculty_signal:
        return {
            "intent": "faculty_query",
            "strategy": "semantic_filtered_rerank",
            "target_chunk_types": ["faculty_program_directory"],
        }

    # 8. Các câu điểm qua môn/rớt môn là quy chế, không phải lookup bảng xếp loại
    if contains_any(q, ["qua môn", "đạt học phần", "rớt môn", "trượt môn", "học lại"]):
        return {
            "intent": "regulation_query",
            "strategy": "semantic_filtered",
            "target_chunk_types": ["regulation"],
        }

    # 9. Score lookup chỉ dành cho bảng/range rõ
    if contains_any(q, [
        "quy đổi",
        "xếp loại",
        "loại gì",
        "loại học lực",
        "học lực",
        "thang điểm 4",
        "thang 4",
        "rèn luyện",
        "điểm chữ",
    ]):
        return {
            "intent": "score_lookup_query",
            "strategy": "structured_lookup",
            "target_chunk_types": [],
        }

    # 10. Default: regulation
    return {
        "intent": "regulation_query",
        "strategy": "semantic_filtered",
        "target_chunk_types": ["regulation"],
    }