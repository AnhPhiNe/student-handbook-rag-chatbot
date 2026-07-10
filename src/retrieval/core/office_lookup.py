import re
import unicodedata
from typing import Any

from src.common.cohort import normalize_cohort


STOPWORDS = {
    "ai",
    "ban",
    "can",
    "cho",
    "co",
    "cua",
    "dang",
    "de",
    "den",
    "duoc",
    "gi",
    "hoi",
    "la",
    "lam",
    "lien",
    "minh",
    "nao",
    "neu",
    "o",
    "phong",
    "sinh",
    "thi",
    "toi",
    "truong",
    "vien",
    "ve",
}

OFFICE_ALIASES: dict[str, list[str]] = {
    "phong cong tac chinh tri va hoc sinh sinh vien": [
        "ctct",
        "hssv",
        "ctct hssv",
        "hop thu sinh vien",
        "hoc bong",
        "hbkkht",
        "mien giam hoc phi",
        "tro cap",
        "vay von",
        "the sinh vien",
        "giay xac nhan",
        "xac nhan sinh vien",
        "tam nghi",
        "bao luu",
        "dung tien do",
        "ky luat",
        "ren luyen",
    ],
    "phong dao tao": [
        "dao tao",
        "hoc vu",
        "dang ky hoc phan",
        "thoi khoa bieu",
        "chuong trinh dao tao",
        "ctdt",
        "thuc tap",
        "xet tot nghiep",
        "tot nghiep",
        "bang tot nghiep",
        "song nganh",
        "van bang",
    ],
    "phong khao thi va dam bao chat luong": [
        "khao thi",
        "dam bao chat luong",
        "dbcl",
        "phuc khao",
        "diem thi",
        "lich thi",
        "ket qua thi",
        "de thi",
    ],
    "phong ke hoach tai chinh": [
        "ke hoach tai chinh",
        "khtc",
        "hoc phi",
        "tai chinh",
        "thu hoc phi",
        "hocphi",
        "bien lai",
    ],
    "phong cong nghe thong tin": [
        "cntt",
        "cong nghe thong tin",
        "email sinh vien",
        "tai khoan",
        "phan mem",
        "website",
        "cong thong tin",
        "he thong",
        "wifi",
    ],
    "trung tam ho tro sinh vien va phat trien khoi nghiep": [
        "ho tro sinh vien",
        "khoi nghiep",
        "viec lam",
        "tu van",
        "ngay hoi viec lam",
    ],
    "ky tuc xa": [
        "ky tuc xa",
        "ktx",
        "noi tru",
        "cho o",
    ],
}

CONTACT_CUES = {
    "email",
    "sdt",
    "so dien thoai",
    "dien thoai",
    "noi bo",
    "lien he",
    "gap ai",
    "hoi ai",
    "o dau",
    "phu trach",
    "nhiem vu",
    "website",
}


def normalize_text(text: Any) -> str:
    value = str(text or "").lower()
    value = value.replace("đ", "d").replace("Đ", "d")
    decomposed = unicodedata.normalize("NFD", value)
    value = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    value = re.sub(r"[^a-z0-9@._+-]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def tokenize(text: Any) -> set[str]:
    return {
        token
        for token in normalize_text(text).split()
        if len(token) >= 2 and token not in STOPWORDS
    }


def _strip_order_prefix(value: Any) -> str:
    return re.sub(r"^\s*\d+\.\s*", "", str(value or "")).strip()


def _office_search_text(record: dict[str, Any]) -> str:
    return " ".join(
        str(value)
        for value in [
            record.get("unit_name"),
            record.get("summary"),
            record.get("raw_text"),
            record.get("source_section"),
        ]
        if value
    )


def _alias_score(query_norm: str, unit_norm: str, search_norm: str) -> float:
    score = 0.0
    for office_name, aliases in OFFICE_ALIASES.items():
        office_norm = normalize_text(office_name)
        office_matched = office_norm in unit_norm or office_norm in search_norm
        if not office_matched:
            continue
        if office_norm in query_norm:
            score += 12
        for alias in aliases:
            alias_norm = normalize_text(alias)
            if alias_norm and alias_norm in query_norm:
                score += 7
    return score


def _score_office(query: str, record: dict[str, Any]) -> float:
    query_norm = normalize_text(query)
    unit_name = _strip_order_prefix(record.get("unit_name"))
    unit_norm = normalize_text(unit_name)
    search_norm = normalize_text(_office_search_text(record))
    query_tokens = tokenize(query)
    unit_tokens = tokenize(unit_name)
    search_tokens = tokenize(search_norm)

    if not query_tokens:
        return 0.0

    score = 0.0
    score += len(query_tokens & unit_tokens) * 5
    score += len(query_tokens & search_tokens) * 1.6

    if unit_norm and (unit_norm in query_norm or query_norm in unit_norm):
        score += 14

    score += _alias_score(query_norm, unit_norm, search_norm)

    if any(cue in query_norm for cue in CONTACT_CUES):
        score += 2

    return score


def _extract_emails(raw_text: str) -> list[str]:
    return sorted(set(re.findall(r"[A-Za-z0-9._%+-]+@hcmue\.edu\.vn", raw_text)))


def _extract_websites(raw_text: str) -> list[str]:
    matches = re.findall(r"(?:https?://)?[A-Za-z0-9.-]+\.hcmue\.edu\.vn", raw_text)
    return sorted(set(match.rstrip(".,;") for match in matches))


def _extract_phones(raw_text: str) -> list[str]:
    phones = re.findall(r"\(?0\d{2,3}\)?[ .-]?\d{3,4}[ .-]?\d{3,4}", raw_text)
    return sorted(set(phone.strip() for phone in phones))


def _extract_internal_numbers(raw_text: str) -> list[str]:
    numbers: set[str] = set()
    for line in raw_text.splitlines():
        if "nội bộ" not in line.lower() and "noi bo" not in normalize_text(line):
            continue
        for number in re.findall(r"\b\d{2,4}\b", line):
            numbers.add(number)
    return sorted(numbers)


def _extract_responsibilities(raw_text: str, limit: int = 4) -> list[str]:
    responsibilities: list[str] = []
    for line in raw_text.splitlines():
        line = re.sub(r"^[•\-–+\s]+", "", line.strip())
        if not line or len(line) < 18:
            continue
        norm = normalize_text(line)
        if any(
            marker in norm
            for marker in (
                "phu trach",
                "thuc hien",
                "quan ly",
                "tham muu",
                "cap",
                "giai quyet",
                "to chuc",
                "ho tro",
            )
        ):
            responsibilities.append(line)
        if len(responsibilities) >= limit:
            break
    return responsibilities


def _summarize_office(record: dict[str, Any]) -> dict[str, Any]:
    raw_text = str(record.get("raw_text") or "")
    return {
        "record_id": record.get("record_id"),
        "unit_name": _strip_order_prefix(record.get("unit_name")),
        "content_type": record.get("content_type") or "office_directory",
        "source_pages": record.get("source_pages") or [],
        "source_section": record.get("source_section"),
        "cohort": record.get("cohort"),
        "document_id": record.get("document_id"),
        "emails": _extract_emails(raw_text),
        "phones": _extract_phones(raw_text),
        "internal_numbers": _extract_internal_numbers(raw_text),
        "websites": _extract_websites(raw_text),
        "responsibilities": _extract_responsibilities(raw_text),
        "summary": (record.get("summary") or raw_text[:500]).strip(),
    }


def office_lookup(
    query: str,
    office_directory: list[dict[str, Any]],
    cohort: str | None = None,
    detected_entities: list[dict[str, Any]] | None = None,
    routing: dict[str, Any] | None = None,
    top_k: int = 3,
) -> dict[str, Any] | None:
    """Tra cuu phong ban/lien he tu office_directory thay vi dua vao semantic RAG."""
    routing = routing or {}
    target_types = set(routing.get("target_chunk_types") or [])
    routed_to_office = (
        routing.get("intent") == "office_query"
        or routing.get("content_type") == "office_directory"
        or "office_directory" in target_types
    )
    query_norm = normalize_text(query)
    has_contact_signal = any(cue in query_norm for cue in CONTACT_CUES)
    has_alias_signal = any(
        normalize_text(alias) in query_norm
        for aliases in OFFICE_ALIASES.values()
        for alias in aliases
    )
    entity_targets = {
        target
        for entity in (detected_entities or [])
        for target in (entity.get("target_chunk_types") or [])
    }
    routed_to_office = routed_to_office or "office_directory" in entity_targets

    if not routed_to_office and not has_contact_signal and not has_alias_signal:
        return None

    normalized_cohort = normalize_cohort(cohort)
    candidates = office_directory
    if normalized_cohort:
        cohort_matches = [
            item
            for item in candidates
            if normalize_cohort(item.get("cohort")) == normalized_cohort
        ]
        if cohort_matches:
            candidates = cohort_matches

    scored = [
        (score, record)
        for record in candidates
        if (score := _score_office(query, record)) >= 5
    ]
    scored.sort(key=lambda item: item[0], reverse=True)
    matches = [
        _summarize_office(record) | {"score": round(score, 2)}
        for score, record in scored[:top_k]
    ]

    if not matches:
        return None

    source_pages = sorted(
        {
            int(page)
            for match in matches
            for page in match.get("source_pages", [])
            if str(page).isdigit()
        }
    )
    document_ids = {
        str(match.get("document_id")) for match in matches if match.get("document_id")
    }

    return {
        "lookup_type": "office_directory",
        "lookup_scope": "office",
        "input_value": query,
        "result": matches,
        "items": matches,
        "office_count": len(matches),
        "source_pages": source_pages,
        "table_name": "Danh sach phong ban lien he",
        "source_label": "Danh muc phong ban/lien he trong So tay sinh vien HCMUE",
        "cohort": normalized_cohort,
        "document_id": next(iter(document_ids)) if len(document_ids) == 1 else None,
        "source_section": "office_directory",
        "content_type": "office_directory",
    }
