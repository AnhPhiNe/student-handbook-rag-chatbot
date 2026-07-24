import re
import unicodedata
from typing import Any, Callable

DOMAIN_SIGNALS = [
    # học vụ / học tập
    "hoc phan",
    "tin chi",
    "dang ky hoc",
    "hoc lai",
    "hoc vuot",
    "hoc vu",
    "tam nghi",
    "bao luu",
    "thoi hoc",
    "chuyen truong",
    "canh bao",
    "buoc thoi hoc",
    "tot nghiep",
    # điểm / xếp loại
    "diem",
    "gpa",
    "diem trung binh",
    "ren luyen",
    "xep loai",
    "hoc luc",
    "hoc bong",
    "cntt",
    "cong nghe thong tin",
    # biểu mẫu / thủ tục
    "mau don",
    "bieu mau",
    "don xin",
    "giay xac nhan",
    "giay to",
    "giay sinh vien",
    "ho so",
    "thu tuc",
    "quy trinh",
    # đơn vị / liên hệ
    "phong",
    "khoa",
    "ban",
    "trung tam",
    "thu vien",
    "email",
    "sdt",
    "so dien thoai",
    "dia chi",
    "van phong",
    # sinh viên / dịch vụ sinh viên
    "sinh vien",
    "ktx",
    "ky tuc xa",
    "noi tru",
    "hoc phi",
    "mien giam",
    "tro cap",
]

ORGANIZATIONAL_BAN_SIGNALS = [
    "ban giam hieu",
    "ban giam doc",
    "ban can su",
    "ban chu nhiem",
    "ban quan ly",
    "ban tu van",
    "phong ban",
]


GENERIC_CONTACT_ONLY_PATTERNS = [
    # Hỏi liên hệ nhưng không nói rõ liên hệ chuyện gì / đơn vị nào
    "lien he o dau",
    "lien he ai",
    "lien he voi ai",
    "can lien he ai",
    "nen lien he ai",
    "hoi ai",
    "hoi o dau",
    "gap ai",
    "gap o dau",
    # Hỏi đơn vị xử lý nhưng thiếu vấn đề cụ thể
    "phong nao xu ly",
    "phong nao phu trach",
    "don vi nao xu ly",
    "don vi nao phu trach",
    "bo phan nao xu ly",
    "bo phan nao phu trach",
    # Câu cực mơ hồ, không có entity rõ
    "o dau vay",
    "lam o dau",
    "nop o dau",
]


CONTACT_SIGNALS = [
    # Hỏi thông tin liên hệ
    "lien he",
    "email",
    "mail",
    "so dien thoai",
    "sdt",
    "dien thoai",
    "hotline",
    # Hỏi vị trí / nơi xử lý
    "o dau",
    "dia chi",
    "van phong",
    "phong lam viec",
    "tang",
    "toa nha",
    # Hỏi đơn vị phụ trách
    "phong nao",
    "don vi nao",
    "bo phan nao",
    "ai phu trach",
    "noi nao",
]

EXPLICIT_OFFICE_SIGNALS = ["phong", "ban", "trung tam", "thu vien"]
EXPLICIT_FACULTY_SIGNALS = ["khoa", "nganh", "chuyen nganh"]

GENERIC_AMBIGUOUS_TERMS = [
    "cntt",
    "cong nghe thong tin",
    "hoc vu",
    "giay to",
    "giay sinh vien",
    "hoc bong",
    "lien he",
]

ACADEMIC_AFFAIRS_SPECIFIC_SIGNALS = [
    "dang ky hoc phan",
    "hoc phan",
    "ket qua hoc tap",
    "bang diem",
    "diem",
    "khieu nai",
    "thanh tra",
    "phuc khao",
    "lich hoc",
    "thoi khoa bieu",
]

DOCUMENT_SPECIFIC_SIGNALS = [
    "xac nhan sinh vien",
    "vay von",
    "mien giam",
    "tro cap",
    "tam nghi",
    "bao luu",
    "nhap hoc",
    "tot nghiep",
    "ky tuc xa",
    "ktx",
    "bieu mau",
    "mau don",
    "don xin",
]

SCHOLARSHIP_SPECIFIC_SIGNALS = [
    "khuyen khich hoc tap",
    "chinh sach",
    "dieu kien",
    "tieu chi",
    "ho so",
    "bieu mau",
    "mau don",
    "quy trinh",
]

SPECIFIC_ACTION_SIGNALS = [
    "co the",
    "muon",
    "can",
    "can mau",
    "gioi han",
    "so lan",
    "hoc vuot",
    "ra truong",
    "hoc lai",
    "tam nghi",
    "bao luu",
    "diem ren luyen",
    "loai gi",
    "xep loai",
    "quy doi",
    "dieu kien",
    "thu tuc",
    "quy trinh",
    "mau don",
    "bieu mau",
]

CHUNK_TYPE_LABELS = {
    "office_directory": "đơn vị/phòng ban liên hệ",
    "faculty_directory": "khoa/tổ",
    "program_directory": "ngành đào tạo",
    "faculty_program_directory": "khoa/ngành đào tạo",
    "regulation": "điều kiện/quy định",
}

CLOSE_SCORE_GAP_THRESHOLD = 0.12

def is_context_empty(retrieval_result: dict[str, Any]) -> bool:
    # Context rong nghia la retrieval khong co van ban, khong co lookup, cung khong co tool result.
    return not any(
        [
            bool(retrieval_result.get("retrieved_items")),
            str(retrieval_result.get("context_for_llm") or "").strip(),
            _has_result(retrieval_result.get("structured_result")),
            _has_formula_result(retrieval_result.get("formula_result")),
            _has_result(retrieval_result.get("tool_result")),
        ]
    )


def is_low_confidence(retrieval_result: dict[str, Any]) -> bool:
    # Neu da co ket qua deterministic thi khong xem la low-confidence.
    if can_answer_deterministically(retrieval_result):
        return False

    # Khong co context nao thi LLM khong co nguon de dua vao.
    if is_context_empty(retrieval_result):
        return True

    retrieved_items = retrieval_result.get("retrieved_items") or []
    citations = retrieval_result.get("citations") or []
    context = str(retrieval_result.get("context_for_llm") or "").strip()
    return not retrieved_items and not citations and not context


def can_answer_deterministically(retrieval_result: dict[str, Any]) -> bool:
    if retrieval_result.get("out_of_domain") or retrieval_result.get(
        "needs_clarification"
    ):
        return True

    # Retrieved synthetic candidates may be useful context, but they are not
    # a validated tool result. Only an explicit router+resolver contract (or
    # the isolated legacy debug path) may bypass the final LLM.
    if retrieval_result.get("deterministic_validated") is not True:
        return False

    structured_res = retrieval_result.get("structured_result")
    if _has_result(structured_res):
        if structured_res.get("lookup_type") == "program_directory":
            return True
        if structured_res.get("lookup_type") == "office_directory":
            return True
        if structured_res.get("lookup_type") == "foreign_language_equivalency":
            return True
        if structured_res.get("lookup_type") == "study_duration":
            return True
        if structured_res.get("lookup_type") == "scholarship_classification":
            return True
        if structured_res.get("lookup_type") == "grade_10_to_letter":
            return True
        row = structured_res.get("result")
        # NẾU LÀ DICT (kết quả 1 dòng ngắn gọn), ta CHẮC CHẮN không cần LLM.
        if isinstance(row, dict):
            return True
        # NẾU LÀ LIST (bảng biểu lớn), bắt buộc dùng LLM để đọc bảng và trả lời câu hỏi.
        if isinstance(row, list):
            return False

    return _has_formula_result(retrieval_result.get("formula_result")) or _has_result(
        retrieval_result.get("tool_result")
    )


def build_deterministic_answer(
    query: str,
    retrieval_result: dict[str, Any],
    selected_citations: list[dict[str, Any]] | None = None,
) -> str:
    structured_result = retrieval_result.get("structured_result")
    if _has_result(structured_result):
        return _format_structured_result(structured_result)

    formula_result = retrieval_result.get("formula_result")
    if _has_formula_result(formula_result):
        return _format_formula_result(formula_result)

    tool_result = retrieval_result.get("tool_result")
    if _has_result(tool_result):
        return _format_tool_result(tool_result)

    return build_fallback_answer(
        query, retrieval_result, reason="no_deterministic_result"
    )


def build_fallback_answer(
    query: str,
    retrieval_result: dict[str, Any] | None = None,
    reason: str | None = None,
) -> str:
    if reason in {"api_error", "rate_limit", "timeout"}:
        return (
            "Hiện tại mình chưa gọi được mô hình AI để diễn giải câu trả lời. "
            "Bạn có thể thử lại sau; nếu hệ thống đã tìm được nguồn liên quan, "
            "mình vẫn hiển thị nguồn bên dưới để bạn tra nhanh."
        )

    if reason == "retrieval_error":
        return (
            "Mình gặp lỗi khi tra cứu dữ liệu sổ tay cho câu hỏi này. "
            "Bạn thử lại sau hoặc hỏi hẹp hơn theo phòng ban, "
            "quy định hay mốc điểm cần tra nhé."
        )

    if reason == "out_of_domain":
        return (
            "Mình chưa tìm thấy thông tin phù hợp trong Sổ tay sinh viên cho câu hỏi này. "
            "Sổ tay chủ yếu hỗ trợ các nội dung như quy định học vụ, "
            "điểm rèn luyện, học bổng, ký túc xá, phòng ban và khoa/ngành. "
            "Bạn có thể hỏi lại theo một nội dung liên quan đến sổ tay nhé."
        )

    return (
        "Mình chưa tìm thấy thông tin đủ rõ trong Sổ tay sinh viên cho câu hỏi này. "
        "Bạn có thể hỏi cụ thể hơn về phòng ban, quy định, mốc điểm "
        "hoặc thủ tục cần tra cứu."
    )


def detect_ambiguous_query(query: str, retrieval_result: dict[str, Any]) -> bool:
    # Neu co ket qua deterministic thi uu tien tra loi, vi cau hoi da du ro de tinh/tra bang.
    if can_answer_deterministically(retrieval_result):
        return False

    return _ambiguity_kind(query, retrieval_result) is not None


def is_out_of_domain_query(query: str, retrieval_result: dict[str, Any]) -> bool:
    """
    Guardrail đã tắt: ưu tiên AI Router và Query Rewriter thay vì keyword hardcode.
    """
    return False


def _has_domain_signal(ascii_query: str) -> bool:
    # "ban" can mean a department, "bán" (sell), or "bạn" (you) after ASCII
    # normalization, so only count it in explicit organizational phrases.
    strong_domain_signals = [signal for signal in DOMAIN_SIGNALS if signal != "ban"]
    return _contains_any(ascii_query, strong_domain_signals) or _contains_any(
        ascii_query,
        ORGANIZATIONAL_BAN_SIGNALS,
    )


def build_clarification_question(query: str, retrieval_result: dict[str, Any]) -> str:
    ambiguity_kind = _ambiguity_kind(query, retrieval_result)

    # Moi ambiguity_kind co cau hoi lam ro rieng de user chi can chon scope, khong phai viet lai tu dau.
    if ambiguity_kind == "academic_affairs":
        return (
            "Bạn muốn hỏi về đăng ký học phần/kết quả học tập hay "
            "khiếu nại/thanh tra học vụ?"
        )

    if ambiguity_kind == "information_technology":
        return (
            "Bạn muốn liên hệ Phòng Công nghệ Thông tin hay Khoa Công nghệ - Thông tin?"
        )

    if ambiguity_kind == "student_documents":
        return "Bạn muốn hỏi giấy xác nhận sinh viên, giấy vay vốn, hay quy định nộp giấy tờ?"

    if ambiguity_kind == "scholarship":
        return (
            "Bạn muốn hỏi điều kiện xét học bổng, hồ sơ/giấy tờ, "
            "hay đơn vị tiếp nhận/liên hệ?"
        )

    if ambiguity_kind == "generic_contact":
        return (
            "Bạn muốn liên hệ về vấn đề gì: học vụ, học bổng, ký túc xá, "
            "giấy tờ, hay một phòng/khoa cụ thể?"
        )

    options = _clarification_options_from_retrieval(retrieval_result)
    if len(options) >= 2:
        return f"Bạn muốn hỏi về {', '.join(options[:-1])} hay {options[-1]}?"

    return "Bạn muốn hỏi cụ thể về thủ tục, quy định hay đơn vị liên hệ?"


def build_ambiguity_note(query: str, retrieval_result: dict[str, Any]) -> str:
    chunk_types = sorted(
        {
            item.get("metadata", {}).get("chunk_type")
            for item in retrieval_result.get("retrieved_items", [])
            if item.get("metadata", {}).get("chunk_type")
        }
    )

    if not chunk_types:
        return (
            "Câu hỏi hơi rộng, nên mình trả lời theo phần thông tin khớp nhất "
            "trong Sổ tay. Nếu bạn cần đúng một trường hợp cụ thể, hãy nói thêm "
            "bối cảnh."
        )

    readable_types = ", ".join(chunk_types)
    return (
        "Câu hỏi có thể liên quan nhiều nhóm thông tin "
        f"({readable_types}), nên mình tách các ý chính theo nguồn tìm được."
    )


def _is_generic_contact_query(ascii_query: str) -> bool:
    has_contact = _contains_any(ascii_query, CONTACT_SIGNALS)
    has_entity_scope = _contains_any(
        ascii_query,
        EXPLICIT_OFFICE_SIGNALS + EXPLICIT_FACULTY_SIGNALS,
    )
    has_specific_action = _contains_any(ascii_query, SPECIFIC_ACTION_SIGNALS)

    # Có entity rõ thì không hỏi lại:
    # "Phòng Đào tạo ở đâu?", "Khoa Tiếng Anh ở đâu?"
    if has_entity_scope:
        return False

    # Các phrase rất mơ hồ thì hỏi lại.
    if any(pattern in ascii_query for pattern in GENERIC_CONTACT_ONLY_PATTERNS):
        return True

    # Câu ngắn có tín hiệu hỏi liên hệ/địa điểm nhưng thiếu object rõ.
    if has_contact and not has_specific_action and len(_word_tokens(ascii_query)) <= 5:
        return True

    return False


def _ambiguity_kind(query: str, retrieval_result: dict[str, Any]) -> str | None:
    normalized_query = _normalize_query(query)
    ascii_query = _ascii_text(normalized_query)

    has_contact_signal = _contains_any(ascii_query, CONTACT_SIGNALS)
    if _is_generic_contact_query(ascii_query):
        return "generic_contact"

    # Đoạn check CNTT đã bị gỡ để LLM tự liệt kê cả Phòng và Khoa.

    # "hoc vu lien he ai" chua ro la dang ky hoc phan, diem, thanh tra hay phuc khao.
    if (
        "hoc vu" in ascii_query
        and not _contains_any(ascii_query, ACADEMIC_AFFAIRS_SPECIFIC_SIGNALS)
        and (has_contact_signal or _is_short_query(ascii_query))
    ):
        return "academic_affairs"

    # "giay to sinh vien" qua rong, can hoi ro loai giay/bieu mau.
    if (
        _mentions_generic_student_document(ascii_query)
        and not _contains_any(ascii_query, DOCUMENT_SPECIFIC_SIGNALS)
        and (has_contact_signal or "lam" in ascii_query or _is_short_query(ascii_query))
    ):
        return "student_documents"

    # Đoạn check học bổng và retrieval_multi_context đã bị gỡ để LLM tự tổng hợp các nguồn.

    return None


def _has_query_entity_conflict(
    ascii_query: str, retrieval_result: dict[str, Any]
) -> bool:
    # Mot alias trong query nhung map ra nhieu entity_type la dau hieu can lam ro.
    detected_entities = retrieval_result.get("detected_entities") or []
    entity_types_by_alias: dict[str, set[str]] = {}

    for entity in detected_entities:
        entity_type = str(entity.get("entity_type") or "").strip()
        if not entity_type:
            continue

        aliases = list(entity.get("aliases") or [])
        canonical_name = entity.get("canonical_name")
        if canonical_name:
            aliases.append(str(canonical_name))

        for alias in aliases:
            normalized_alias = _ascii_text(_normalize_query(str(alias)))
            if normalized_alias and normalized_alias in ascii_query:
                entity_types_by_alias.setdefault(normalized_alias, set()).add(
                    entity_type
                )

    return any(len(entity_types) > 1 for entity_types in entity_types_by_alias.values())


def _mentions_generic_student_document(ascii_query: str) -> bool:
    return (
        "giay to" in ascii_query
        or "giay sinh vien" in ascii_query
        or ("giay" in ascii_query and "sinh vien" in ascii_query)
    )


def _query_is_under_specified(ascii_query: str) -> bool:
    if _is_short_query(ascii_query):
        return True

    has_generic_term = _contains_any(ascii_query, GENERIC_AMBIGUOUS_TERMS)
    has_action = _contains_any(ascii_query, SPECIFIC_ACTION_SIGNALS)
    return has_generic_term and not has_action


def _has_resolving_specificity(ascii_query: str) -> bool:
    if _contains_any(ascii_query, EXPLICIT_OFFICE_SIGNALS + EXPLICIT_FACULTY_SIGNALS):
        return True

    token_count = len(_word_tokens(ascii_query))
    return token_count >= 5 and _contains_any(ascii_query, SPECIFIC_ACTION_SIGNALS)


def _retrieval_has_close_conflict(retrieval_result: dict[str, Any]) -> bool:
    # Chi can xet top 5 de bat xung dot gan nhat, tranh de tail result lam nhieu.
    items = retrieval_result.get("retrieved_items") or []
    if len(items) < 2:
        return False

    return _has_close_group_competition(
        items, _chunk_type_group
    ) or _has_close_group_competition(
        items,
        _entity_type_group,
    )


def _has_close_group_competition(
    items: list[dict[str, Any]],
    group_getter: Callable[[dict[str, Any]], str],
) -> bool:
    scored_groups: dict[str, float] = {}
    unscored_groups: list[str] = []

    for item in items[:5]:
        group = group_getter(item)
        if not group:
            continue

        score = _relevance_score(item)
        if score is None:
            if group not in unscored_groups:
                unscored_groups.append(group)
            continue

        scored_groups[group] = max(score, scored_groups.get(group, float("-inf")))

    if len(scored_groups) >= 2:
        top_scores = sorted(scored_groups.values(), reverse=True)
        return (top_scores[0] - top_scores[1]) <= CLOSE_SCORE_GAP_THRESHOLD

    return len(scored_groups) == 0 and len(unscored_groups) >= 2


def _chunk_type_group(item: dict[str, Any]) -> str:
    return str(item.get("metadata", {}).get("chunk_type") or "").strip()


def _entity_type_group(item: dict[str, Any]) -> str:
    metadata = item.get("metadata", {})
    entity_type = str(metadata.get("entity_type") or "").strip()
    if entity_type:
        return entity_type

    chunk_type = str(metadata.get("chunk_type") or "").strip()
    if chunk_type == "office_directory":
        return "office"
    if chunk_type in {"faculty_directory", "program_directory", "faculty_program_directory"}:
        return "faculty"
    return ""


def _relevance_score(item: dict[str, Any]) -> float | None:
    rerank = item.get("rerank") or {}
    if isinstance(rerank, dict) and rerank.get("final_score") is not None:
        return float(rerank["final_score"])

    if item.get("score") is not None:
        return float(item["score"])

    if item.get("distance") is not None:
        return 1.0 - float(item["distance"])

    return None


def _clarification_options_from_retrieval(
    retrieval_result: dict[str, Any],
) -> list[str]:
    options: list[str] = []
    for chunk_type in _retrieved_chunk_types(retrieval_result):
        label = CHUNK_TYPE_LABELS.get(chunk_type)
        if label and label not in options:
            options.append(label)
    return options[:3]


def _retrieved_chunk_types(retrieval_result: dict[str, Any]) -> list[str]:
    seen: set[str] = set()
    chunk_types: list[str] = []

    for item in retrieval_result.get("retrieved_items", []):
        chunk_type = str(item.get("metadata", {}).get("chunk_type") or "").strip()
        if not chunk_type or chunk_type in seen:
            continue
        seen.add(chunk_type)
        chunk_types.append(chunk_type)

    return chunk_types


def _is_short_query(ascii_query: str) -> bool:
    return len(_word_tokens(ascii_query)) <= 3


def _word_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text)


def _contains_any(text: str, keywords: list[str]) -> bool:
    padded_text = f" {text} "

    for keyword in keywords:
        keyword = keyword.strip()
        if not keyword:
            continue

        if " " in keyword:
            if f" {keyword} " in padded_text:
                return True
        else:
            if re.search(rf"\b{re.escape(keyword)}\b", text):
                return True

    return False


def _normalize_query(query: str) -> str:
    normalized = query.lower().replace("–", "-").replace("—", "-")
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


def _ascii_text(text: str) -> str:
    text = text.replace("đ", "d").replace("Đ", "D")
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(
        char for char in decomposed if unicodedata.category(char) != "Mn"
    )
    stripped = re.sub(r"[^a-zA-Z0-9]+", " ", stripped)
    return re.sub(r"\s+", " ", stripped.lower()).strip()


def _has_result(value: Any) -> bool:
    return isinstance(value, dict) and value.get("result") is not None


def _has_formula_result(value: Any) -> bool:
    return isinstance(value, dict) and bool(value.get("formula_text"))


def _format_structured_result(structured_result: dict[str, Any]) -> str:
    if structured_result.get("lookup_type") == "program_directory":
        return _format_program_directory_result(structured_result)
    if structured_result.get("lookup_type") == "office_directory":
        return _format_office_directory_result(structured_result)
    if structured_result.get("lookup_type") == "foreign_language_equivalency":
        return _format_foreign_language_equivalency_result(structured_result)
    if structured_result.get("lookup_type") == "study_duration":
        return _format_study_duration_result(structured_result)
    if structured_result.get("lookup_type") == "scholarship_classification":
        return _format_scholarship_classification_result(structured_result)
    if structured_result.get("lookup_type") == "grade_10_to_letter":
        return _format_grade_10_to_letter_result(structured_result)

    table_name = structured_result.get("table_name") or "bảng tra cứu"
    input_value = structured_result.get("input_value")
    row = structured_result.get("result")

    if isinstance(row, dict):
        label = row.get("label") or row.get("classification") or row.get("status")
        score_4 = row.get("score_4")
        letter_grade = row.get("letter_grade")
        range_text = row.get("range") or row.get("score_10_range")

        if label:
            range_part = f" (khoảng {range_text})" if range_text else ""
            return f"Tra theo {table_name}, giá trị {input_value} được xếp loại: {label}{range_part}."

        if letter_grade is not None and score_4 is not None:
            return (
                f"Tra theo {table_name}, điểm chữ {letter_grade} "
                f"tương ứng thang điểm 4 là {score_4}."
            )

        fields = ", ".join(f"{key}: {value}" for key, value in row.items())
        return f"Tra theo {table_name}, giá trị {input_value} có kết quả: {fields}."

    return f"Tra theo {table_name}, giá trị {input_value} có kết quả: {row}."


def _format_office_directory_result(structured_result: dict[str, Any]) -> str:
    offices = structured_result.get("result") or []
    if not offices:
        return "Mình chưa tìm thấy phòng ban phù hợp trong danh mục liên hệ hiện có."

    requested_field = str(structured_result.get("requested_field") or "all")
    show_all = requested_field == "all"
    lines = ["Mình tìm thấy đơn vị phù hợp để bạn liên hệ:"]
    for office in offices[:3]:
        name = office.get("unit_name") or "Phòng ban"
        pages = office.get("source_pages") or []
        page_text = f" (trang {', '.join(str(page) for page in pages)})" if pages else ""
        lines.append(f"- {name}{page_text}")

        emails = office.get("emails") or []
        phones = office.get("phones") or []
        internal_numbers = office.get("internal_numbers") or []
        websites = office.get("websites") or []
        office_address = str(office.get("office") or "").strip()
        responsibilities = office.get("responsibilities") or []

        if (show_all or requested_field == "email") and emails:
            lines.append(f"  Email: {', '.join(emails)}")
        if (show_all or requested_field == "phone") and phones:
            lines.append(f"  Số điện thoại: {', '.join(phones)}")
        if show_all and internal_numbers:
            lines.append(f"  Số máy nội bộ: {', '.join(internal_numbers)}")
        if (show_all or requested_field == "website") and websites:
            lines.append(f"  Website: {', '.join(websites)}")
        if (show_all or requested_field == "office") and office_address:
            lines.append(f"  Địa chỉ: {office_address}")
        if show_all and responsibilities:
            lines.append("  Phụ trách liên quan:")
            for item in responsibilities[:2]:
                lines.append(f"  - {_compact_text(item, limit=150)}")

    return "\n".join(lines)


def _format_foreign_language_equivalency_result(
    structured_result: dict[str, Any],
) -> str:
    result = structured_result.get("result") or {}
    items = structured_result.get("items") or []
    cohort = structured_result.get("cohort")
    prefix = "Theo bảng quy đổi chuẩn đầu ra ngoại ngữ"
    if cohort:
        prefix += f" áp dụng cho {cohort}"

    if isinstance(result, dict) and result.get("matched_level"):
        level_label = "bậc 4" if result.get("matched_level") == "bac_4" else "bậc 3"
        value = result.get("matched_value")
        value_text = f" {value:g}" if isinstance(value, (int, float)) else ""
        return (
            f"{prefix}, {result.get('certificate')}{value_text} tương đương {level_label}. "
            f"Mốc bậc 3: {result.get('equivalent_level_3')}; "
            f"mốc bậc 4: {result.get('equivalent_level_4')}."
        )

    rows = items if items else result.get("rows") if isinstance(result, dict) else []
    if isinstance(result, dict) and not rows:
        rows = [result]

    if not rows:
        return (
            "Mình chưa tìm thấy dòng quy đổi ngoại ngữ phù hợp trong bảng "
            "chuẩn đầu ra ngoại ngữ hiện có."
        )

    lines = [f"{prefix}, các mốc quy đổi phù hợp là:"]
    for row in rows[:8]:
        lines.append(
            "- "
            f"{row.get('certificate')}: "
            f"bậc 3 = {row.get('equivalent_level_3') or 'không nêu'}; "
            f"bậc 4 = {row.get('equivalent_level_4') or 'không nêu'}."
        )
    if len(rows) > 8:
        lines.append(f"- Còn {len(rows) - 8} dòng khác trong bảng quy đổi.")
    return "\n".join(lines)


def _format_study_duration_result(structured_result: dict[str, Any]) -> str:
    result = structured_result.get("result") or {}
    tables = result.get("tables") or structured_result.get("items") or []
    cohort = structured_result.get("cohort")
    prefix = "Theo bảng thời gian học tập chuẩn và tối đa"
    if cohort:
        prefix += f" áp dụng cho {cohort}"

    if not tables:
        return "Mình chưa tìm thấy bảng thời gian học tập phù hợp trong dữ liệu hiện có."

    lines = [f"{prefix}:"]
    mode_labels = {
        "chinh_quy": "hệ chính quy",
        "vua_lam_vua_hoc": "hệ vừa làm vừa học",
    }
    for table in tables:
        mode = mode_labels.get(table.get("training_mode"), "hệ đào tạo")
        rows = table.get("rows") or []
        lines.append(f"- {mode}:")
        for row in rows:
            program = row.get("Chương trình đào tạo") or "Chương trình đào tạo"
            standard = row.get("Thời gian học tập chuẩn") or "không nêu"
            maximum = row.get("Thời gian học tập tối đa") or "không nêu"
            lines.append(f"  - {program}: chuẩn {standard}, tối đa {maximum}.")
    return "\n".join(lines)


def _format_scholarship_classification_result(
    structured_result: dict[str, Any],
) -> str:
    result = structured_result.get("result") or {}
    rows = structured_result.get("items") or result.get("rows") if isinstance(result, dict) else []
    if isinstance(result, dict) and not rows and result.get("label"):
        rows = [result]

    cohort = structured_result.get("cohort")
    prefix = "Theo bảng xếp loại học bổng khuyến khích học tập"
    if cohort:
        prefix += f" áp dụng cho {cohort}"

    if not rows:
        return "Mình chưa tìm thấy mốc xếp loại học bổng phù hợp trong dữ liệu hiện có."

    lines = [f"{prefix}:"]
    matched_score = result.get("matched_score") if isinstance(result, dict) else None
    if matched_score is not None:
        lines[0] = f"{prefix}, điểm học bổng {matched_score:g} thuộc mốc:"

    for row in rows:
        lines.append(
            "- "
            f"{row.get('label')}: "
            f"điểm học bổng {row.get('scholarship_score_range')}; "
            f"điểm học tập {row.get('academic_score_range')}; "
            f"điểm rèn luyện {row.get('conduct_score_condition')}."
        )
    return "\n".join(lines)


def _compact_text(value: Any, limit: int = 140) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _display_text(value: Any) -> str:
    return str(value or "").replace("–", "-").replace("—", "-")


def _format_grade_10_to_letter_result(structured_result: dict[str, Any]) -> str:
    tables = structured_result.get("result") or []
    cohort = structured_result.get("cohort")
    requested_grade = structured_result.get("requested_letter_grade")
    requested_rows = structured_result.get("requested_grade_rows") or []
    grade_4 = structured_result.get("letter_grade_4") or {}
    input_value = structured_result.get("input_value")

    prefix = "Theo bảng quy đổi điểm"
    if cohort:
        prefix += f" áp dụng cho {cohort}"

    if tables and isinstance(tables, list) and isinstance(tables[0], dict) and tables[0].get("row"):
        score_text = f"{input_value:g}" if isinstance(input_value, (int, float)) else str(input_value)
        lines = [f"{prefix}, điểm {score_text} tương ứng:"]
        for item in tables:
            row = item.get("row") or {}
            applicability = item.get("applicability") or item.get("table_name")
            letter_grade = row.get("letter_grade") or "không nêu"
            score_range = row.get("score_10_range") or row.get("range")
            status = row.get("status")
            parts = [f"- {applicability}: điểm chữ {letter_grade}"]
            if score_range:
                parts.append(f"khoảng điểm {score_range}")
            if status:
                parts.append(f"trạng thái {status}")
            lines.append("; ".join(parts) + ".")
        return "\n".join(lines)

    if requested_grade and requested_rows:
        lines = [f"{prefix}, điểm chữ {requested_grade} có kết quả như sau:"]
        if grade_4.get("score_4") is not None:
            lines.append(
                f"- Quy đổi hệ 4: {requested_grade} = {grade_4.get('score_4')}."
            )
        for item in requested_rows:
            row = item.get("row") or {}
            applicability = item.get("applicability") or item.get("table_name")
            status = row.get("status")
            score_range = row.get("score_10_range")
            threshold = item.get("pass_threshold")
            parts = [f"- {applicability}: {requested_grade}"]
            if score_range:
                parts.append(f"khoảng điểm {score_range}")
            if status:
                parts.append(f"trạng thái {status}")
            if threshold:
                parts.append(f"ngưỡng qua môn {threshold}")
            lines.append("; ".join(parts) + ".")
        return "\n".join(lines)

    if tables:
        lines = [f"{prefix}, ngưỡng đạt/qua môn được tóm tắt như sau:"]
        for table in tables:
            applicability = table.get("applicability") or table.get("table_name")
            threshold = table.get("pass_threshold")
            if threshold:
                lines.append(f"- {applicability}: {threshold}.")

        rows = tables[0].get("rows") or []
        passed_rows = [
            row for row in rows if str(row.get("status") or "").lower() == "đạt"
        ]
        failed_rows = [
            row
            for row in rows
            if str(row.get("status") or "").lower() == "không đạt"
        ]
        if passed_rows and failed_rows and len(tables) == 1:
            lines.append(
                "Đạt: "
                + ", ".join(
                    f"{row.get('letter_grade')} ({row.get('score_10_range')})"
                    for row in passed_rows
                )
                + "."
            )
            lines.append(
                "Không đạt: "
                + ", ".join(
                    f"{row.get('letter_grade')} ({row.get('score_10_range')})"
                    for row in failed_rows
                )
                + "."
            )
        return "\n".join(lines)

    return (
        f"Tra theo {structured_result.get('table_name') or 'bảng quy đổi điểm'}, "
        f"kết quả: {structured_result.get('result')}."
    )


def _format_program_directory_result(structured_result: dict[str, Any]) -> str:
    programs = structured_result.get("result") or []
    cohort = structured_result.get("cohort")
    scope = structured_result.get("lookup_scope")

    if scope == "program_exists":
        searched_program = structured_result.get("searched_program") or "ngành được hỏi"
        if structured_result.get("exists") and programs:
            program_name = programs[0].get("program_name") or searched_program
            faculty_name = programs[0].get("faculty_name")
            faculty_text = f", thuộc {faculty_name}" if faculty_name else ""
            return (
                f"Có. {program_name} có trong danh mục ngành áp dụng cho "
                f"{cohort}{faculty_text}."
            )
        return (
            f"Không. Theo danh mục ngành áp dụng cho {cohort}, "
            f"không có ngành {searched_program}."
        )

    if not programs:
        return "Mình chưa tìm thấy danh sách ngành phù hợp trong dữ liệu sổ tay."

    title = "Các ngành đào tạo"
    if cohort:
        title += f" áp dụng cho {cohort}"
    if scope == "faculty":
        first_faculty = programs[0].get("faculty_name")
        if first_faculty:
            title = f"{first_faculty} có các ngành đào tạo"

    grouped: dict[str, list[dict[str, Any]]] = {}
    for program in programs:
        faculty = str(program.get("faculty_name") or "Chưa xác định khoa phụ trách")
        grouped.setdefault(faculty, []).append(program)

    lines = [f"{title} ({len(programs)} ngành):"]
    for faculty, items in grouped.items():
        lines.append("")
        lines.append(f"{faculty}:")
        for item in items:
            pages = item.get("source_pages") or []
            page_text = (
                f" (trang {', '.join(str(page) for page in pages)})"
                if pages
                else ""
            )
            lines.append(f"- {item.get('program_name')}{page_text}")

    return "\n".join(lines)


def _format_tool_result(tool_result: dict[str, Any]) -> str:
    tool_name = tool_result.get("tool_name") or "công cụ tính toán"
    result = tool_result.get("result")
    inputs = tool_result.get("inputs") or {}
    note = tool_result.get("note")

    input_text = ""
    if isinstance(inputs, dict) and inputs:
        input_text = " với " + ", ".join(
            f"{key}={value}" for key, value in inputs.items()
        )

    answer = f"Kết quả từ {tool_name}{input_text}: {result}."
    if note:
        answer = f"{answer}\n\n{note}"
    return answer


def _format_formula_result(formula_result: dict[str, Any]) -> str:
    rule_name = formula_result.get("rule_name") or "Công thức"
    formula_text = formula_result.get("formula_text") or ""
    variables = formula_result.get("variables") or {}

    variable_text = ""
    if isinstance(variables, dict) and variables:
        lines = [f"- {key}: {value}" for key, value in variables.items()]
        variable_text = "\n\nTrong đó:\n" + "\n".join(lines)

    return f"{rule_name}: {formula_text}.{variable_text}"
