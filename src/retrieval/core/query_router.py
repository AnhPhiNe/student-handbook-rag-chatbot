import re
import unicodedata
from typing import Any

from .routing_rules import load_query_routing_rules


ASCII_AMBIGUOUS_KEYWORDS = {"ban", "khoa", "tầng"}


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
    # Match ca ban co dau va khong dau, nhung bo qua keyword de gay nham nhu "ban".
    return any(
        _contains_phrase(text, keyword)
        or (
            keyword not in ASCII_AMBIGUOUS_KEYWORDS
            and _contains_phrase(ascii_text, strip_accents(keyword))
        )
        for keyword in keywords
    )


def infer_program_lookup_metadata(query: str) -> dict[str, str] | None:
    """Nhan dien thao tac tra cuu nganh dao tao o tang router."""
    ascii_query = strip_accents(query)
    if not contains_any(query, ["ngành", "nganh", "chuyên ngành", "chuyen nganh"]):
        return None

    asks_list = contains_any(
        query,
        [
            "có những",
            "co nhung",
            "có các",
            "co cac",
            "những ngành",
            "nhung nganh",
            "các ngành",
            "cac nganh",
            "ngành nào",
            "nganh nao",
            "ngành gì",
            "nganh gi",
            "danh sách",
            "danh sach",
            "liệt kê",
            "liet ke",
            "bao nhiêu ngành",
            "bao nhieu nganh",
            "đào tạo ngành",
            "dao tao nganh",
        ],
    )
    asks_program_faculty = contains_any(
        query,
        [
            "thuộc khoa",
            "thuoc khoa",
            "khoa nào",
            "khoa nao",
            "khoa phụ trách",
            "khoa phu trach",
            "phụ trách",
            "phu trach",
        ],
    )
    faculty_scope = contains_any(query, ["khoa", "faculty"])

    if asks_program_faculty and not (asks_list and faculty_scope):
        return {
            "content_type": "program_directory",
            "action": "resolve_faculty",
            "scope": "program",
        }

    if not asks_list:
        return None

    school_scope = contains_any(
        query,
        [
            "trường",
            "truong",
            "hcmue",
            "đại học sư phạm",
            "dai hoc su pham",
        ],
    )
    scope = "school"
    if faculty_scope and not school_scope:
        scope = "faculty"
    elif school_scope:
        scope = "school"
    elif re.search(r"\b(cntt|toan|van|anh|phap|nga|trung|han|nhat)\b", ascii_query):
        scope = "faculty"

    return {
        "content_type": "program_directory",
        "action": "list",
        "scope": scope,
    }


def infer_score_lookup_metadata(query: str) -> bool:
    """Nhan dien nhom cau hoi diem/bang quy doi nen tra cuu bang du lieu bang."""
    ascii_query = strip_accents(query)
    score_cues = [
        "diem",
        "d+",
        "d",
        "c+",
        "c",
        "b+",
        "b",
        "a",
        "f+",
        "f",
        "he 4",
        "thang 4",
        "thang diem",
        "quy doi",
        "ren luyen",
        "hoc luc",
        "gpa",
        "trung binh",
    ]
    action_cues = [
        "qua mon",
        "rot mon",
        "dat",
        "khong dat",
        "bao nhieu",
        "may diem",
        "xep loai",
        "loai gi",
        "quy doi",
        "sang he 4",
        "thang 4",
    ]
    has_letter_grade = re.search(r"(?<!\w)(a|b\+?|c\+?|d\+?|f\+?)(?!\w)", ascii_query)
    if "gpa" in ascii_query and "hoc luc" in ascii_query:
        return True

    return (contains_any(ascii_query, score_cues) or bool(has_letter_grade)) and contains_any(
        ascii_query,
        action_cues,
    )


def _contains_phrase(text: str, phrase: str) -> bool:
    phrase = phrase.strip()
    if not phrase:
        return False

    # Dung boundary tuy theo dau/cuoi phrase de "hoc vu" khong match vao "hoc vuot".
    starts_word = phrase[0].isalnum() or phrase[0] == "_"
    ends_word = phrase[-1].isalnum() or phrase[-1] == "_"
    prefix = r"(?<!\w)" if starts_word else ""
    suffix = r"(?!\w)" if ends_word else ""
    return re.search(prefix + re.escape(phrase) + suffix, text) is not None


def _is_obvious_out_of_domain(query: str) -> bool:
    ascii_query = strip_accents(query)
    food_or_cooking = [
        "nau pho",
        "an gi",
        "banh trang",
        "ban do an",
        "quan an",
    ]
    weather = ["thoi tiet", "hom nay mua", "troi mua", "nhiet do"]
    return contains_any(ascii_query, food_or_cooking + weather)


def _has_regulation_priority_signal(query: str) -> bool:
    """Nhận diện câu hỏi quy định nên ưu tiên RAG trước tín hiệu khoa/ngành."""
    ascii_query = strip_accents(query)
    return bool(re.search(r"\b(dieu|article)\s*\d+\b", ascii_query)) or contains_any(
        query,
        [
            "quy chế",
            "quy định",
            "điều kiện",
            "chuyển ngành",
            "chuyển nơi học",
            "chuyển trường",
            "học vượt",
            "học lại",
            "miễn giảm học phí",
            "nghiên cứu khoa học",
            "thông tin khoa học",
            "khoa học và công nghệ",
            "kế hoạch giảng dạy",
            "kế hoạch học tập",
            "học kỳ",
            "thời khóa biểu",
            "có được giảm học phí",
            "có được miễn giảm",
            "có được hỗ trợ chi phí",
        ],
    )


def _has_office_support_signal(query: str) -> bool:
    """Nhận diện câu hỏi về nguồn lực/phòng ban hỗ trợ sinh viên."""
    return contains_any(
        query,
        [
            "nguồn lực hỗ trợ",
            "hỗ trợ sinh viên",
            "dịch vụ hỗ trợ",
            "đơn vị hỗ trợ",
            "phòng ban hỗ trợ",
            "liên hệ ở đâu",
            "liên hệ phòng nào",
        ],
    )


def _clarification_question(query: str) -> str | None:
    ascii_query = strip_accents(query)
    contact_cues = ["hoi ai", "lien he ai", "gap ai", "o dau", "lam o dau"]
    if "cntt" in ascii_query and contains_any(ascii_query, ["o dau"]):
        return (
            "Bạn muốn liên hệ về Khoa Công nghệ Thông tin, Phòng Công nghệ Thông tin, "
            "hay ngành Công nghệ Thông tin?"
        )
    if "hoc bong" in ascii_query and contains_any(ascii_query, contact_cues):
        return (
            "Bạn muốn liên hệ về điều kiện học bổng, kết quả xét học bổng, "
            "hay phòng ban phụ trách học bổng?"
        )
    if "hoc vu" in ascii_query and contains_any(ascii_query, contact_cues):
        return (
            "Bạn muốn liên hệ về chương trình đào tạo, điểm số, học lại, "
            "hay một thủ tục học vụ cụ thể?"
        )
    if any(term in ascii_query for term in ["giay to", "giay xac nhan"]) and contains_any(
        ascii_query, contact_cues
    ):
        return (
            "Bạn muốn liên hệ về giấy xác nhận sinh viên, biểu mẫu cần nộp, "
            "hay phòng ban tiếp nhận hồ sơ?"
        )
    return None


def route_query(query: str) -> dict[str, Any]:
    q = normalize_query(query)
    rules = load_query_routing_rules()
    clarification = _clarification_question(q)
    if clarification:
        return {
            "intent": "needs_clarification",
            "strategy": "none",
            "target_chunk_types": [],
            "needs_clarification": True,
            "clarification_question": clarification,
        }

    if _is_obvious_out_of_domain(q):
        return {
            "intent": "out_of_domain",
            "strategy": "none",
            "target_chunk_types": [],
        }

    program_metadata = infer_program_lookup_metadata(q)

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
    has_reg_priority_signal = _has_regulation_priority_signal(q)
    has_office_support_signal = _has_office_support_signal(q)

    if has_reg_priority_signal:
        program_metadata = None
        has_faculty_signal = False
        has_reg_signal = True

    # 1. Calculation query
    # Calculator chi kich hoat khi co tin hieu tinh toan va du so dau vao.
    has_calc = contains_any(q, rules["calculation_signal"])
    has_gpa = contains_any(q, rules["gpa_signal"])
    has_formula = contains_any(q, rules["formula_signal"])
    has_raw_scholarship_score = contains_any(q, rules["scholarship_score_signal"])
    numbers = re.findall(r"\d+(?:[,.]\d+)?", q)
    has_scholarship_score = has_raw_scholarship_score and contains_any(
        q,
        rules["calculation_signal"],
    )

    if has_formula and (has_gpa or has_raw_scholarship_score):
        return {
            "intent": "formula_query",
            "strategy": "formula_lookup",
            "target_chunk_types": [],
        }

    if has_calc and has_scholarship_score and len(numbers) >= 2:
        return {
            "intent": "calculation_query",
            "strategy": "calculator_tool",
            "target_chunk_types": [],
        }

    # 2. KTX/procedure phải bắt trước office.
    # Không xem "ký túc xá" là office entity vì đa số câu KTX hỏi quy trình/tiêu chí/mẫu đơn.
    if program_metadata and program_metadata.get("action") == "resolve_faculty":
        return {
            "intent": "faculty_query",
            "strategy": "program_lookup",
            "target_chunk_types": ["program_directory"],
            **program_metadata,
        }

    if infer_score_lookup_metadata(q):
        return {
            "intent": "score_lookup_query",
            "strategy": "structured_lookup",
            "target_chunk_types": [],
        }

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

    if contains_any(q, ["quy trình", "trình tự", "các bước"]) and contains_any(
        q,
        ["sinh viên", "khoa", "phòng", "đơn vị", "công việc"],
    ):
        return {
            "intent": "procedure_query",
            "strategy": "semantic_filtered_rerank",
            "target_chunk_types": ["procedure"],
        }

    if has_office_support_signal and not has_reg_priority_signal:
        return {
            "intent": "office_query",
            "strategy": "semantic_filtered_rerank",
            "target_chunk_types": ["office_directory"],
        }

    if program_metadata:
        return {
            "intent": "faculty_query",
            "strategy": "program_lookup",
            "target_chunk_types": ["program_directory"],
            **program_metadata,
        }

    has_office_signal = has_contact_question or has_explicit_office_entity
    has_pass_score_signal = contains_any(
        q,
        ["may diem", "máº¥y Ä‘iá»ƒm", "bao nhieu diem", "bao nhiÃªu Ä‘iá»ƒm", "d+", "diem d", "Ä‘iá»ƒm d"],
    ) and contains_any(q, ["qua mon", "qua mÃ´n", "dat", "Ä‘áº¡t"])
    has_pass_score_signal = has_pass_score_signal or bool(
        re.search(
            r"\b(khoa\s*)?(48|49|50|51)\b.*\b(may|bao).*\bdiem\b.*\b(dat|qua)\b",
            strip_accents(q),
        )
    )

    # Faculty duoc uu tien neu user noi ro "khoa/nganh".
    # Vi du "Khoa CNTT o dau?" khong nen bi route thanh office chi vi co "o dau".
    if has_faculty_signal and not has_explicit_office_entity and not has_pass_score_signal:
        route = {
            "intent": "faculty_query",
            "strategy": "semantic_filtered_rerank",
            "target_chunk_types": ["faculty_directory", "program_directory"],
        }
        if program_metadata:
            route.update(program_metadata)
            route["strategy"] = "program_lookup"
            route["target_chunk_types"] = ["program_directory"]
        return route

    if has_form_signal and not has_reg_signal and not has_ktx_signal and not has_faculty_signal:
        return {
            "intent": "form_query",
            "strategy": "form_lookup",
            "target_chunk_types": ["form"],
        }

    if contains_any(q, ["phuc khao", "phÃºc kháº£o"]) and contains_any(
        q, ["quy trinh", "quy trÃ¬nh", "thu tuc", "thá»§ tá»¥c"]
    ):
        return {
            "intent": "procedure_query",
            "strategy": "semantic_filtered_rerank",
            "target_chunk_types": ["procedure"],
        }

    # --- 1. CONFLICT DETECTION LOGIC ---
    # Nếu câu hỏi chứa từ 2 loại tín hiệu trở lên, Rule-based Router sẽ "giơ cờ trắng"
    # và nhường quyền phân tích cho AI Router để xử lý ngữ nghĩa phức tạp (Mixed Query).
    active_signals = []
    if has_form_signal:
        active_signals.append("form")
    if has_reg_signal:
        active_signals.append("regulation")
    if has_office_signal:
        active_signals.append("office")
    if has_ktx_signal:
        active_signals.append("ktx")
    if has_faculty_signal:
        active_signals.append("faculty")

    if len(active_signals) >= 2:
        target_chunk_types = []
        if has_form_signal:
            target_chunk_types.append("form")
        if has_reg_signal:
            target_chunk_types.append("regulation")
        if has_office_signal:
            target_chunk_types.append("office_directory")
        if has_ktx_signal:
            target_chunk_types.append("procedure")
        if has_faculty_signal:
            target_chunk_types.extend(["faculty_directory", "program_directory"])

        # Conflict phổ biến là câu hỏi nhiều ý; xử lý bằng multi-filter trước.
        # Multi-filter giu lai nhieu loai chunk de reranker tu chon nguon tot nhat.
        return {
            "intent": "mixed_query",
            "strategy": "semantic_multi_filter",
            "target_chunk_types": list(dict.fromkeys(target_chunk_types)),
        }
    # -----------------------------------

    # 4. Form query
    if has_form_signal:
        return {
            "intent": "form_query",
            "strategy": "form_lookup",
            "target_chunk_types": ["form"],
        }

    # 5. Nếu query gốc nói rõ Khoa/Ngành thì ưu tiên faculty,
    # trừ khi query cũng nói rõ "phòng".
    # Ví dụ: "Khoa Tiếng Anh ở đâu?" -> faculty
    # Nhưng: "Website phòng CNTT là gì?" -> office
    if has_faculty_signal and not has_explicit_office_entity and not has_pass_score_signal:
        route = {
            "intent": "faculty_query",
            "strategy": "semantic_filtered_rerank",
            "target_chunk_types": ["faculty_directory", "program_directory"],
        }
        if program_metadata:
            route.update(program_metadata)
            route["strategy"] = "program_lookup"
            route["target_chunk_types"] = ["program_directory"]
        return route

    # 6. Office/contact query
    # Ví dụ: "Website Phòng Công nghệ Thông tin là gì?"
    # Không đưa "ký túc xá" vào office entity ở đây.
    if has_explicit_office_entity or (has_contact_question and not has_faculty_signal):
        return {
            "intent": "office_query",
            "strategy": "semantic_filtered_rerank",
            "target_chunk_types": ["office_directory"],
        }

    if has_form_signal and not has_reg_signal and not has_ktx_signal and not has_faculty_signal:
        return {
            "intent": "form_query",
            "strategy": "form_lookup",
            "target_chunk_types": ["form"],
        }

    if contains_any(q, ["phuc khao", "phÃºc kháº£o"]) and contains_any(
        q, ["quy trinh", "quy trÃ¬nh", "thu tuc", "thá»§ tá»¥c"]
    ):
        return {
            "intent": "procedure_query",
            "strategy": "semantic_filtered_rerank",
            "target_chunk_types": ["procedure"],
        }

    # 7. Faculty query còn lại
    if has_faculty_signal:
        route = {
            "intent": "faculty_query",
            "strategy": "semantic_filtered_rerank",
            "target_chunk_types": ["faculty_directory", "program_directory"],
        }
        if program_metadata:
            route.update(program_metadata)
            route["strategy"] = "program_lookup"
            route["target_chunk_types"] = ["program_directory"]
        return route

    # 8. Các câu điểm qua môn/rớt môn
    # Nếu hỏi TỪ KHÓA ĐIỂM + RỚT/QUA MÔN -> Tra cứu JSON
    # Nếu hỏi RỚT MÔN chung chung (học lại, xử lý, etc) -> Regulation
    asks_passing_score = contains_any(
        q, rules["pass_fail_regulation_signal"]
    ) and contains_any(q, ["mấy điểm", "bao nhiêu điểm", "thang điểm", "quy đổi"])
    asks_passing_score = asks_passing_score or (
        contains_any(q, ["diem", "d+", "d", "Ä‘iá»ƒm"])
        and contains_any(q, ["qua mon", "qua mÃ´n", "dat", "Ä‘áº¡t", "khong dat", "khÃ´ng Ä‘áº¡t"])
    )
    if asks_passing_score:
        return {
            "intent": "score_lookup_query",
            "strategy": "structured_lookup",
            "target_chunk_types": [],
        }

    # Nếu chỉ hỏi về quy chế rớt/qua mà không hỏi điểm cụ thể
    if contains_any(q, rules["pass_fail_regulation_signal"]):
        return {
            "intent": "regulation_query",
            "strategy": "semantic_filtered",
            "target_chunk_types": ["regulation"],
        }

    # 9. Score lookup chỉ dành cho bảng/range rõ
    ascii_q = strip_accents(q)
    asks_failed_grade_policy = bool(
        re.search(r"\bdiem\s+f\b", ascii_q, flags=re.IGNORECASE)
    ) and contains_any(
        q,
        ["bị", "thì sao", "xử lý", "rớt", "trượt"],
    )
    if asks_failed_grade_policy:
        return {
            "intent": "regulation_query",
            "strategy": "semantic_filtered",
            "target_chunk_types": ["regulation"],
        }

    asks_letter_grade = bool(
        re.search(r"\bdiem\s+[abcdf]\+?\b", ascii_q, flags=re.IGNORECASE)
    )
    asks_gpa_classification = has_gpa and contains_any(
        q,
        ["loại", "xếp", "xuất sắc", "giỏi", "khá", "trung bình", "yếu"],
    )

    # Score lookup chi danh cho cau hoi tra bang diem/range.
    if (
        contains_any(q, rules["score_lookup_signal"])
        or asks_letter_grade
        or asks_gpa_classification
    ):
        return {
            "intent": "score_lookup_query",
            "strategy": "structured_lookup",
            "target_chunk_types": [],
        }

    # 10. Fallback cho quy chế nếu có từ khóa
    if has_reg_signal:
        return {
            "intent": "regulation_query",
            "strategy": "semantic_filtered",
            "target_chunk_types": ["regulation"],
        }

    if contains_any(
        q,
        [
            "tín chỉ",
            "tin chi",
            "chậm tiến độ",
            "cham tien do",
            "học vượt",
            "hoc vuot",
            "ra trường sớm",
            "ra truong som",
        ],
    ):
        return {
            "intent": "regulation_query",
            "strategy": "semantic_filtered",
            "target_chunk_types": ["regulation"],
        }

    # 11. Default: unknown (sẽ được xử lý bởi AIRouter)
    return {
        "intent": "unknown",
        "strategy": "semantic_filtered",
        "target_chunk_types": [],
    }
