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
    "form": "biểu mẫu/giấy tờ",
    "office_directory": "đơn vị/phòng ban liên hệ",
    "faculty_program_directory": "khoa/ngành đào tạo",
    "procedure": "quy trình/thủ tục",
    "regulation": "điều kiện/quy định",
}

CLOSE_SCORE_GAP_THRESHOLD = 0.12


def is_context_empty(retrieval_result: dict[str, Any]) -> bool:
    # Context rong nghia la retrieval khong co van ban, khong co lookup, cung khong co tool result.
    return not any(
        [
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

    structured_res = retrieval_result.get("structured_result")
    if _has_result(structured_res):
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
            "Bạn thử lại sau hoặc hỏi hẹp hơn theo biểu mẫu, phòng ban, "
            "quy định hay mốc điểm cần tra nhé."
        )

    if reason == "out_of_domain":
        return (
            "Mình chưa tìm thấy thông tin phù hợp trong Sổ tay sinh viên cho câu hỏi này. "
            "Sổ tay chủ yếu hỗ trợ các nội dung như quy định học vụ, biểu mẫu, "
            "điểm rèn luyện, học bổng, ký túc xá, phòng ban và khoa/ngành. "
            "Bạn có thể hỏi lại theo một nội dung liên quan đến sổ tay nhé."
        )

    return (
        "Mình chưa tìm thấy thông tin đủ rõ trong Sổ tay sinh viên cho câu hỏi này. "
        "Bạn có thể hỏi cụ thể hơn về biểu mẫu, phòng ban, quy định, mốc điểm "
        "hoặc thủ tục cần tra cứu."
    )


def detect_ambiguous_query(query: str, retrieval_result: dict[str, Any]) -> bool:
    # Neu co ket qua deterministic thi uu tien tra loi, vi cau hoi da du ro de tinh/tra bang.
    if can_answer_deterministically(retrieval_result):
        return False

    return _ambiguity_kind(query, retrieval_result) is not None


def is_out_of_domain_query(query: str, retrieval_result: dict[str, Any]) -> bool:
    """
    Disabled guardrail: Trust the AI Router and Query Rewriter instead of hardcoded keywords.
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
        return "Bạn muốn hỏi giấy xác nhận sinh viên, giấy vay vốn, hay biểu mẫu khác?"

    if ambiguity_kind == "scholarship":
        return (
            "Bạn muốn hỏi điều kiện xét học bổng, hồ sơ/biểu mẫu, "
            "hay đơn vị tiếp nhận/liên hệ?"
        )

    if ambiguity_kind == "generic_contact":
        return (
            "Bạn muốn liên hệ về vấn đề gì: học vụ, học bổng, ký túc xá, "
            "biểu mẫu/giấy tờ, hay một phòng/khoa cụ thể?"
        )

    options = _clarification_options_from_retrieval(retrieval_result)
    if len(options) >= 2:
        return f"Bạn muốn hỏi về {', '.join(options[:-1])} hay {options[-1]}?"

    return "Bạn muốn hỏi cụ thể về thủ tục, biểu mẫu, quy định hay đơn vị liên hệ?"


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

    # Tach cac tin hieu scope de phan biet: cau co "phong/khoa" ro thi bot mo ho hon.
    has_contact_signal = _contains_any(ascii_query, CONTACT_SIGNALS)
    has_office_signal = _contains_any(ascii_query, EXPLICIT_OFFICE_SIGNALS)
    has_faculty_signal = _contains_any(ascii_query, EXPLICIT_FACULTY_SIGNALS)
    has_explicit_scope = has_office_signal or has_faculty_signal
    if _is_generic_contact_query(ascii_query):
        return "generic_contact"

    # CNTT co the la Phong Cong nghe Thong tin hoac Khoa Cong nghe - Thong tin.
    if (
        _has_query_entity_conflict(ascii_query, retrieval_result)
        and not has_explicit_scope
        and (has_contact_signal or _is_short_query(ascii_query))
    ):
        return "information_technology"

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

    # "hoc bong hoi ai" co the hoi dieu kien, ho so, bieu mau hoac don vi lien he.
    if (
        "hoc bong" in ascii_query
        and has_contact_signal
        and not _contains_any(ascii_query, SCHOLARSHIP_SPECIFIC_SIGNALS)
    ):
        return "scholarship"

    # Neu top results den tu nhieu nhom gan diem nhau, hoi lai thay vi doan mot nhom.
    if (
        _retrieval_has_close_conflict(retrieval_result)
        and _query_is_under_specified(ascii_query)
        and not _has_resolving_specificity(ascii_query)
    ):
        return "retrieval_multi_context"

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
    if chunk_type == "faculty_program_directory":
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
