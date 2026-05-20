import re
import unicodedata
from typing import Any

from .routing_rules import load_query_routing_rules


ASCII_AMBIGUOUS_KEYWORDS = {"ban", "tầng"}


def normalize_query(query: str) -> str:
    query = query.strip().lower()
    query = query.replace("–", "-")
    query = re.sub(r"\s+", " ", query)
    return query


def strip_accents(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def contains_any(text: str, keywords: list[str]) -> bool:
    ascii_text = strip_accents(text)
    return any(
        _contains_phrase(text, keyword)
        or (
            keyword not in ASCII_AMBIGUOUS_KEYWORDS
            and _contains_phrase(ascii_text, strip_accents(keyword))
        )
        for keyword in keywords
    )


def _contains_phrase(text: str, phrase: str) -> bool:
    phrase = phrase.strip()
    if not phrase:
        return False

    starts_word = phrase[0].isalnum() or phrase[0] == "_"
    ends_word = phrase[-1].isalnum() or phrase[-1] == "_"
    prefix = r"(?<!\w)" if starts_word else ""
    suffix = r"(?!\w)" if ends_word else ""
    return re.search(prefix + re.escape(phrase) + suffix, text) is not None


def route_query(query: str) -> dict[str, Any]:
    q = normalize_query(query)
    rules = load_query_routing_rules()

    has_form_signal = contains_any(q, rules["form_signal"])
    has_reg_signal = contains_any(q, rules["regulation_signal"])
    has_contact_question = contains_any(q, rules["contact_question"])
    has_contact_question = has_contact_question or contains_any(
        q,
        ["hỏi ai", "hỏi ở đâu", "tìm ai", "gặp ai", "liên hệ ai"],
    )
    has_ktx_signal = contains_any(q, rules["ktx_signal"])
    has_faculty_signal = contains_any(q, rules["faculty_signal"])
    has_explicit_office_entity = contains_any(q, rules["explicit_office_entity"])

    # 1. Calculation query
    has_calc = contains_any(q, rules["calculation_signal"])
    has_gpa = contains_any(q, rules["gpa_signal"])
    has_scholarship_score = contains_any(q, rules["scholarship_score_signal"]) and contains_any(
        q,
        rules["calculation_signal"],
    )

    if has_calc and (has_gpa or has_scholarship_score):
        return {
            "intent": "calculation_query",
            "strategy": "calculator_tool",
            "target_chunk_types": [],
        }

    # 2. KTX/procedure phải bắt trước office.
    # Không xem "ký túc xá" là office entity vì đa số câu KTX hỏi quy trình/tiêu chí/mẫu đơn.
    if has_ktx_signal:
        if has_form_signal or contains_any(q, rules["ktx_form_signal"]):
            return {
                "intent": "mixed_query",
                "strategy": "semantic_multi_filter",
                "target_chunk_types": ["form", "procedure"],
            }

        if contains_any(q, rules["ktx_procedure_signal"]):
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
    if contains_any(q, rules["pass_fail_regulation_signal"]):
        return {
            "intent": "regulation_query",
            "strategy": "semantic_filtered",
            "target_chunk_types": ["regulation"],
        }

    # 9. Score lookup chỉ dành cho bảng/range rõ
    ascii_q = strip_accents(q)
    asks_failed_grade_policy = bool(re.search(r"\bdiem\s+f\b", ascii_q, flags=re.IGNORECASE)) and contains_any(
        q,
        ["bị", "thì sao", "xử lý", "rớt", "trượt"],
    )
    if asks_failed_grade_policy:
        return {
            "intent": "regulation_query",
            "strategy": "semantic_filtered",
            "target_chunk_types": ["regulation"],
        }

    asks_letter_grade = bool(re.search(r"\bdiem\s+[abcdf]\+?\b", ascii_q, flags=re.IGNORECASE))
    asks_gpa_classification = has_gpa and contains_any(
        q,
        ["loại", "xếp", "xuất sắc", "giỏi", "khá", "trung bình", "yếu"],
    )

    if contains_any(q, rules["score_lookup_signal"]) or asks_letter_grade or asks_gpa_classification:
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
