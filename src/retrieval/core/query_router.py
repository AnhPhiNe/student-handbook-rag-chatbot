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
    has_program_term = contains_any(
        query,
        [
            "ngành",
            "nganh",
            "chuyên ngành",
            "chuyen nganh",
            "danh mục ngành",
            "danh muc nganh",
        ],
    )
    asks_program_faculty_without_program_word = contains_any(
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
    ) and not contains_any(query, ["phòng", "phong", "trung tâm", "trung tam"])
    if not has_program_term and not asks_program_faculty_without_program_word:
        return None

    asks_list = contains_any(
        query,
        [
            "tổng cộng",
            "tong cong",
            "tất cả",
            "tat ca",
            "mấy ngành",
            "may nganh",
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
        "qua hoc phan",
        "rot mon",
        "dat",
        "dat hoc phan",
        "khong dat",
        "bao nhieu",
        "may diem",
        "xep loai",
        "loai gi",
        "quy doi",
        "sang he 4",
        "thang 4",
        "tinh nhu the nao",
        "tinh the nao",
        "he thong tinh",
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
    out_of_domain_topics = {
        "weather": ["thoi tiet", "mua lon", "co mua", "mua khong", "nhiet do"],
        "market": ["bitcoin", "tien ao", "gia vang", "chung khoan"],
        "creative": ["bai tho", "tho tinh", "viet truyen", "sang tac"],
        "sports": ["doi tuyen", "bong da", "lich thi dau", "da luc may gio"],
        "device_repair": ["xanh man hinh", "sua may tinh", "loi laptop"],
        "food": ["quan an", "mon an", "nau pho", "an gi", "banh trang"],
        "translation": ["dich cau", "dich sang tieng", "phien dich"],
        "shopping": ["ma giam gia", "khuyen mai mua", "coupon"],
    }
    return any(
        contains_any(ascii_query, signals)
        for signals in out_of_domain_topics.values()
    )


def classify_request_shape(query: str) -> str:
    """Classify how the user asks, independently from the handbook topic."""
    ascii_query = strip_accents(normalize_query(query))
    unresolved_references = [
        "muc nay",
        "truong hop do",
        "bieu mau kia",
        "diem nhu vay",
        "chung chi do",
        "nganh nay",
        "cong thuc nay",
        "loai do",
        "phong do",
        "thu tuc nay",
        "quy dinh cua khoa em trong truong hop nay",
    ]
    if contains_any(ascii_query, unresolved_references):
        return "ambiguous"
    if _is_obvious_out_of_domain(ascii_query):
        return "out_of_domain"

    procedure_terms = [
        "quy trinh",
        "trinh tu",
        "thu tuc",
        "cac buoc",
        "ho so can",
        "nop ho so",
    ]
    if contains_any(ascii_query, procedure_terms):
        return "policy_or_procedure"

    consequence_terms = [
        "co bi",
        "bi xu ly",
        "xu ly",
        "xu ly ra sao",
        "anh huong",
        "trach nhiem",
        "ngoai le",
        "khieu nai",
        "quyen loi",
        "co quyen",
        "duoc phep",
        "co duoc",
        "thieu chu ky",
        "nop tre",
        "sau khi nop",
    ]
    if contains_any(ascii_query, consequence_terms):
        return "consequence_or_exception"

    formula_terms = ["cong thuc", "cach tinh", "tinh kieu", "tinh ra sao"]
    calculation_slots = (
        contains_any(ascii_query, ["diem hoc tap", "gpa"])
        and contains_any(ascii_query, ["diem ren luyen", "ren luyen"])
        and len(re.findall(r"\d+(?:[,.]\d+)?", _strip_cohort_tokens(ascii_query))) >= 2
    )
    if contains_any(ascii_query, formula_terms) or calculation_slots:
        return "formula_or_calculation"

    document_requirement_terms = [
        "tai bieu mau",
        "tai mau",
        "lay bieu mau",
        "lay mau",
        "bieu mau nao",
        "mau nao",
        "mau don nao",
        "can don gi",
    ]
    if contains_any(ascii_query, document_requirement_terms):
        return "document_requirement"

    contact_terms = [
        "email",
        "so dien thoai",
        "dien thoai",
        "website",
        "dia chi",
        "van phong",
        "lien he ai",
        "lien he don vi nao",
        "hoi phong nao",
        "hoi don vi nao",
        "o dau",
    ]
    if contains_any(ascii_query, contact_terms):
        return "contact_lookup"

    direct_value_terms = [
        "bao nhieu",
        "may nam",
        "bao lau",
        "tuong duong",
        "quy doi",
        "xep loai",
        "loai gi",
        "nam trong khoang",
        "nganh nao",
        "cac nganh",
        "khoa nao",
        "phu trach",
    ]
    if contains_any(ascii_query, direct_value_terms):
        return "direct_value_lookup"

    policy_terms = [
        "dieu kien",
        "quy dinh",
        "tieu chi",
        "khi nao",
        "neu",
        "truong hop",
    ]
    if contains_any(ascii_query, policy_terms):
        return "policy_query"
    return "open_question"


def deterministic_lookup_allowed(query: str, lookup_name: str) -> bool:
    """Require both a compatible request shape and the slots needed by a lookup."""
    shape = classify_request_shape(query)
    ascii_query = strip_accents(normalize_query(query))
    if lookup_name in {"foreign_language", "scholarship"}:
        return shape == "direct_value_lookup"
    if lookup_name == "study_duration":
        has_training_scope = contains_any(
            ascii_query,
            [
                "chinh quy",
                "vua lam vua hoc",
                "cap bang thu nhat",
                "bang dai hoc thu hai",
                "cao dang",
                "trung cap",
            ],
        )
        return shape == "direct_value_lookup" and has_training_scope
    return True


def _strip_cohort_tokens(query: str) -> str:
    query = re.sub(r"\bk\s*\d{2}(?:\s*-\s*k?\d{2})?\b", " ", query)
    return re.sub(r"\bkhoa\s*\d{2}\b", " ", query)


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
            "học bổng khuyến khích",
            "học bổng kkht",
            "quỹ học bổng",
            "mức học bổng",
            "tốt nghiệp",
            "xét tốt nghiệp",
            "cấp bằng",
            "thời gian học tập",
            "thời gian chuẩn",
            "thời gian tối đa",
            "học tối đa",
            "tối đa của chương trình",
            "chương trình đại học chính quy",
            "cảnh báo học tập",
            "buộc thôi học",
            "đình chỉ học tập",
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
            "liên hệ ai",
            "phòng nào",
            "xin giấy xác nhận",
            "giấy xác nhận",
            "giấy đang học",
            "xác nhận sinh viên",
        ],
    )



def route_query(query: str) -> dict[str, Any]:
    q = normalize_query(query)
    rules = load_query_routing_rules()
    request_shape = classify_request_shape(q)

    if request_shape == "ambiguous":
        return {
            "intent": "needs_clarification",
            "strategy": "none",
            "target_chunk_types": [],
            "needs_clarification": True,
            "clarification_question": (
                "Bạn có thể nói rõ đối tượng, biểu mẫu, chứng chỉ, phòng ban "
                "hoặc trường hợp cụ thể mà bạn đang hỏi không?"
            ),
        }

    if request_shape == "out_of_domain":
        return {
            "intent": "out_of_domain",
            "strategy": "none",
            "target_chunk_types": [],
        }

    if request_shape == "policy_or_procedure":
        return {
            "intent": "procedure_query",
            "strategy": "semantic_filtered_rerank",
            "target_chunk_types": ["regulation"],
        }

    if request_shape in {"policy_query", "consequence_or_exception"}:
        return {
            "intent": "regulation_query",
            "strategy": "semantic_filtered",
            "target_chunk_types": ["regulation"],
        }

    program_metadata = infer_program_lookup_metadata(q)

    has_document_requirement_signal = contains_any(
        q, rules["document_requirement_signal"]
    )
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

    if request_shape == "document_requirement":
        return {
            "intent": "regulation_query",
            "strategy": "semantic_filtered",
            "target_chunk_types": ["regulation"],
        }

    if request_shape == "contact_lookup":
        # Hỏi khoa cụ thể thì không được chuyển thành office/student service.
        if (
            contains_any(q, ["khoa"])
            and not has_explicit_office_entity
            and not has_reg_priority_signal
        ):
            return {
                "intent": "faculty_query",
                "strategy": "semantic_filtered_rerank",
                "target_chunk_types": ["faculty_directory"],
            }

        # Hỏi ngành thuộc khoa nào.
        if (
            program_metadata
            and program_metadata.get("action") == "resolve_faculty"
        ):
            return {
                "intent": "faculty_query",
                "strategy": "program_lookup",
                "target_chunk_types": ["program_directory"],
                **program_metadata,
            }

        asks_profile_field = contains_any(
            q,
            [
                "email",
                "số điện thoại",
                "điện thoại",
                "website",
                "địa chỉ",
                "văn phòng",
            ],
        )

        use_office_profile = asks_profile_field and (
            has_explicit_office_entity or has_ktx_signal
        )

        return {
            "intent": "office_query",
            "strategy": (
                "office_lookup"
                if use_office_profile
                else "student_service_lookup"
            ),
            "target_chunk_types": ["office_directory"],
            "lookup_scope": (
                "office"
                if use_office_profile
                else "student_service"
            ),
        }

    if has_reg_priority_signal:
        program_metadata = None
        has_faculty_signal = False
        has_reg_signal = True

    # 1. Formula lookup. The production system does not execute calculations.
    has_gpa = contains_any(q, rules["gpa_signal"])
    has_formula = contains_any(q, rules["formula_signal"])
    has_raw_scholarship_score = contains_any(q, rules["scholarship_score_signal"])
    calculation_values = re.findall(r"(?<!\d)\d+(?:[,.]\d+)?(?!\d)", strip_accents(q))
    asks_calculation_guidance = (
        contains_any(q, ["tính", "tinh"])
        and (has_gpa or has_raw_scholarship_score)
        and len(calculation_values) >= 2
    )

    if (has_formula and (has_gpa or has_raw_scholarship_score)) or asks_calculation_guidance:
        return {
            "intent": "formula_query",
            "strategy": "formula_lookup",
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

    if not has_reg_priority_signal and infer_score_lookup_metadata(q):
        return {
            "intent": "score_lookup_query",
            "strategy": "structured_lookup",
            "target_chunk_types": [],
        }

    if has_ktx_signal:
        if has_contact_question or contains_any(
            q,
            ["đơn vị nào", "don vi nao", "hỏi thông tin", "hoi thong tin", "liên hệ", "lien he"],
        ):
            return {
                "intent": "office_query",
                "strategy": "office_lookup",
                "target_chunk_types": ["office_directory"],
            }

        if has_document_requirement_signal or contains_any(
            q, rules["ktx_document_signal"]
        ):
            return {
                "intent": "needs_clarification",
                "strategy": "none",
                "target_chunk_types": [],
                "needs_clarification": True,
                "clarification_question": (
                    "Quy trình/hồ sơ Ký túc xá có thể thay đổi theo hệ thống riêng "
                    "của Trường. Bạn nên kiểm tra thông báo hoặc liên hệ đơn vị phụ trách KTX."
                ),
            }

        if contains_any(q, rules["ktx_regulation_signal"]):
            return {
                "intent": "needs_clarification",
                "strategy": "none",
                "target_chunk_types": [],
                "needs_clarification": True,
                "clarification_question": (
                    "Quy trình/điều kiện Ký túc xá không được dùng làm nguồn RAG chính "
                    "vì có thể được cập nhật trên hệ thống riêng của Trường. "
                    "Bạn muốn mình tra thông tin liên hệ KTX/phòng phụ trách không?"
                ),
            }

        return {
            "intent": "needs_clarification",
            "strategy": "none",
            "target_chunk_types": [],
            "needs_clarification": True,
            "clarification_question": (
                "Thông tin Ký túc xá nên kiểm tra theo thông báo/hệ thống hiện hành. "
                "Bạn muốn hỏi thông tin liên hệ hay quy định khác trong sổ tay?"
            ),
        }

    if contains_any(q, ["quy trình", "trình tự", "các bước"]) and contains_any(
        q,
        ["sinh viên", "khoa", "phòng", "đơn vị", "công việc"],
    ):
        return {
            "intent": "regulation_query",
            "strategy": "semantic_filtered",
            "target_chunk_types": ["regulation"],
        }

    if has_office_support_signal and not has_reg_priority_signal:
        return {
            "intent": "office_query",
            "strategy": "office_lookup",
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
        ["may diem", "mấy điểm", "bao nhieu diem", "bao nhiêu điểm", "d+", "diem d", "điểm d"],
    ) and contains_any(q, ["qua mon", "qua môn", "dat", "đạt"])
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

    has_direct_document_requirement_signal = contains_any(
        q,
        [
            "mau don",
            "bieu mau",
            "lay mau",
            "tai mau",
        ],
    )
    if (
        has_direct_document_requirement_signal
        and not has_ktx_signal
        and not has_faculty_signal
    ):
        return {
            "intent": "regulation_query",
            "strategy": "semantic_filtered",
            "target_chunk_types": ["regulation"],
        }

    if has_document_requirement_signal and not has_reg_signal and not has_ktx_signal and not has_faculty_signal:
        return {
            "intent": "regulation_query",
            "strategy": "semantic_filtered",
            "target_chunk_types": ["regulation"],
        }

    if contains_any(q, ["phuc khao", "phúc khảo"]) and contains_any(
        q, ["quy trinh", "quy trình", "thu tuc", "thủ tục"]
    ):
        return {
            "intent": "regulation_query",
            "strategy": "semantic_filtered",
            "target_chunk_types": ["regulation"],
        }

    # If a query contains multiple strong signals, let the AI router resolve the mixed intent.
    # Mixed queries are handled with multi-filter retrieval instead of forcing one intent too early.
    active_signals = []
    if has_document_requirement_signal:
        active_signals.append("regulation")
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
        if has_document_requirement_signal:
            target_chunk_types.append("regulation")
        if has_reg_signal:
            target_chunk_types.append("regulation")
        if has_office_signal:
            target_chunk_types.append("office_directory")
        if has_ktx_signal:
            target_chunk_types.append("regulation")
        if has_faculty_signal:
            target_chunk_types.extend(["faculty_directory", "program_directory"])

        # Multi-filter keeps likely chunk types so the reranker can select the best source.
        # This is safer than dropping one side of a mixed student question.
        return {
            "intent": "mixed_query",
            "strategy": "semantic_multi_filter",
            "target_chunk_types": list(dict.fromkeys(target_chunk_types)),
        }
    # -----------------------------------

    # 4. Form query
    if has_document_requirement_signal:
        return {
            "intent": "regulation_query",
            "strategy": "semantic_filtered",
            "target_chunk_types": ["regulation"],
        }

    # 5. Prefer faculty/program when the query clearly asks about a khoa/nganh,
    # unless it explicitly asks for an office/department.
    # Example: "Khoa CNTT o dau?" should not become office just because it contains "o dau".
    # Example: "Website phong CNTT la gi?" should still go to office lookup.
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
    # Example: "Website Phong Cong nghe Thong tin la gi?"
    # Do not treat KTX as a generic office entity here.
    if has_explicit_office_entity or (has_contact_question and not has_faculty_signal):
        return {
            "intent": "office_query",
            "strategy": "office_lookup",
            "target_chunk_types": ["office_directory"],
        }

    if has_document_requirement_signal and not has_reg_signal and not has_ktx_signal and not has_faculty_signal:
        return {
            "intent": "regulation_query",
            "strategy": "semantic_filtered",
            "target_chunk_types": ["regulation"],
        }

    if contains_any(q, ["phuc khao", "phúc khảo"]) and contains_any(
        q, ["quy trinh", "quy trình", "thu tuc", "thủ tục"]
    ):
        return {
            "intent": "regulation_query",
            "strategy": "semantic_filtered",
            "target_chunk_types": ["regulation"],
        }

    # 7. Remaining faculty query
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

    # 8. Pass/fail score questions
    # Specific score thresholds go to structured lookup; broader fail/retry rules go to regulation retrieval.
    # This keeps deterministic scoring separate from policy explanation.
    asks_passing_score = contains_any(
        q, rules["pass_fail_regulation_signal"]
    ) and contains_any(q, ["mấy điểm", "bao nhiêu điểm", "thang điểm", "quy đổi"])
    asks_passing_score = asks_passing_score or (
        contains_any(q, ["diem", "d+", "d", "điểm"])
        and contains_any(q, ["qua mon", "qua môn", "dat", "đạt", "khong dat", "không đạt"])
    )
    if asks_passing_score and not has_reg_priority_signal:
        return {
            "intent": "score_lookup_query",
            "strategy": "structured_lookup",
            "target_chunk_types": [],
        }

    # Broad pass/fail regulation questions without a concrete score threshold.
    if contains_any(q, rules["pass_fail_regulation_signal"]):
        return {
            "intent": "regulation_query",
            "strategy": "semantic_filtered",
            "target_chunk_types": ["regulation"],
        }
    # 9. Score lookup only handles clear table/range questions.
    ascii_q = strip_accents(q)
    asks_failed_grade_policy = bool(
        re.search(r"\bdiem\s+f\b", ascii_q, flags=re.IGNORECASE)
    ) and contains_any(
        q,
        ["bị", "thì sao", "xử lý", "rớt", "trượt"],
    )
    if asks_failed_grade_policy and contains_any(
        ascii_q,
        ["tinh", "quy doi", "he 4", "he thong tinh"],
    ):
        asks_failed_grade_policy = False
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
        not has_reg_priority_signal
        and (
            contains_any(q, rules["score_lookup_signal"])
            or asks_letter_grade
            or asks_gpa_classification
        )
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
