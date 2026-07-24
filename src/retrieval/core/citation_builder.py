import re
from typing import Any


_FOCUS_MARKERS = (
    "THÔNG TIN TRỌNG TÂM ĐÃ TÁCH TỪ NGUỒN:",
    "THÔNG TIN TRỌNG TÂM TỪ NGUỒN:",
)
_CONTENT_MARKER = "Nội dung:"
_PAGE_FOOTER_RE = re.compile(r"^(?:\d+\s+)?SỔ TAY SINH VIÊN KHÓA\s+\d+\s*$")
_NEW_PARAGRAPH_RE = re.compile(
    r"^(?:Điều\s+\d+\.|\d+\.\s|[a-zđ]\)|[-•]\s+|Tài liệu:|Phần:|Chương:|Tiêu đề:)",
    re.IGNORECASE,
)


def parse_source_pages(value: Any) -> list[int]:
    if value is None:
        return []

    if isinstance(value, list):
        return [int(v) for v in value]

    if isinstance(value, int):
        return [value]

    if isinstance(value, str):
        pages = []
        for item in value.split(","):
            item = item.strip()
            if item.isdigit():
                pages.append(int(item))
        return pages

    return []


def _first_value(source: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = source.get(key)
        if value not in (None, "", []):
            return value
    return None


def sanitize_citation_content(value: Any) -> str:
    """Làm sạch nội dung nguồn trước khi gửi về UI citation."""
    if value is None:
        return ""

    text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""

    for marker in _FOCUS_MARKERS:
        if marker in text:
            text = text.split(marker, 1)[0].strip()

    if _CONTENT_MARKER in text:
        text = text.split(_CONTENT_MARKER, 1)[1].strip()

    lines = [
        line.strip()
        for line in text.split("\n")
        if line.strip() and not _PAGE_FOOTER_RE.match(line.strip())
    ]
    if not lines:
        return ""

    paragraphs: list[str] = []
    for line in lines:
        if not paragraphs or _starts_new_paragraph(line):
            paragraphs.append(line)
        else:
            paragraphs[-1] = f"{paragraphs[-1]} {line}"

    cleaned = "\n\n".join(paragraphs)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()


def _starts_new_paragraph(line: str) -> bool:
    return bool(_NEW_PARAGRAPH_RE.match(line))


def _build_source_label(metadata: dict[str, Any]) -> str | None:
    label = _first_value(
        metadata,
        (
            "source_label",
            "source_name",
            "document_title",
            "file_name",
            "source_file",
        ),
    )
    if label:
        return str(label)

    chunk_type = metadata.get("chunk_type")
    if chunk_type == "faculty_directory":
        return "Khoa/tổ"
    if chunk_type == "program_directory":
        return "Ngành đào tạo"
    if chunk_type == "contact":
        return "Thông tin liên hệ"
    if chunk_type == "rule":
        return "Quy định"
    if chunk_type == "table":
        return "Bảng quy định"
    return None


def build_citations_from_vector_results(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    citations = []

    for item in results:
        metadata = item.get("metadata", {})
        citations.append(
            {
                "chunk_id": item.get("chunk_id"),
                "chunk_type": metadata.get("chunk_type"),
                "title": metadata.get("title")
                or metadata.get("form_name")
                or metadata.get("unit_name")
                or metadata.get("faculty_or_unit_name")
                or metadata.get("program_name")
                or metadata.get("faculty_name")
                or metadata.get("procedure_name")
                or metadata.get("rule_name"),
                "source_pages": parse_source_pages(metadata.get("source_pages")),
                "source_label": _build_source_label(metadata),
                "source_url": _first_value(metadata, ("source_url", "url", "document_url")),
                "cohort": metadata.get("cohort"),
                "document_id": metadata.get("document_id"),
                "source_section": metadata.get("source_section"),
                "applicability": metadata.get("applicability"),
                "distance": item.get("distance"),
                "rerank": item.get("rerank"),
                "retrieval_purpose": item.get("retrieval_purpose"),
                "content": sanitize_citation_content(
                    item.get("document") or item.get("content")
                ),
            }
        )

    return citations


def build_citation_from_lookup(lookup_result: dict[str, Any]) -> list[dict[str, Any]]:
    if lookup_result.get("lookup_type") == "structured_context":
        citations = []
        seen = set()
        for item in lookup_result.get("items") or []:
            source_parent_id = item.get("source_parent_id")
            key = (source_parent_id, item.get("cohort"), item.get("table_id"))
            if key in seen:
                continue
            seen.add(key)
            citations.append(
                {
                    "chunk_type": "structured_lookup",
                    "title": item.get("table_name") or "Bảng dữ liệu Sổ tay sinh viên",
                    "source_pages": item.get("source_pages") or [],
                    "source_label": "Bảng dữ liệu được chuẩn hóa từ Sổ tay sinh viên HCMUE",
                    "cohort": item.get("cohort"),
                    "document_id": item.get("document_id"),
                    "source_section": source_parent_id,
                    "source_parent_id": source_parent_id,
                    "parent_section_id": source_parent_id,
                    "content": f"{item.get('table_name')}: {len(item.get('rows') or [])} dòng được chọn.",
                }
            )
        return citations

    if lookup_result.get("lookup_type") == "program_directory":
        programs = lookup_result.get("result") or []
        preview = "; ".join(
            str(program.get("program_name"))
            for program in programs[:8]
            if program.get("program_name")
        )
        if len(programs) > 8:
            preview = f"{preview}; ..."

        return [
            {
                "chunk_type": "program_directory",
                "title": lookup_result.get("table_name")
                or "Danh sach nganh dao tao",
                "source_pages": lookup_result.get("source_pages", []),
                "source_label": lookup_result.get("source_label")
                or "Danh muc nganh dao tao trong So tay sinh vien HCMUE",
                "source_url": lookup_result.get("source_url"),
                "cohort": lookup_result.get("cohort"),
                "document_id": lookup_result.get("document_id"),
                "source_section": lookup_result.get("source_section"),
                "source_parent_id": lookup_result.get("source_parent_id"),
                "parent_section_id": lookup_result.get("source_parent_id"),
                "applicability": lookup_result.get("applicability"),
                "content": preview
                or "Du lieu nganh dao tao duoc trich xuat tu So tay sinh vien HCMUE.",
            }
        ]

    if lookup_result.get("lookup_type") == "office_directory":
        offices = lookup_result.get("result") or []
        preview = "; ".join(
            str(office.get("unit_name"))
            for office in offices[:5]
            if office.get("unit_name")
        )
        first_office = offices[0] if offices else {}
        return [
            {
                "chunk_type": "office_directory",
                "title": first_office.get("unit_name") or lookup_result.get("table_name"),
                "source_pages": lookup_result.get("source_pages", []),
                "source_label": lookup_result.get("source_label")
                or "Danh muc phong ban/lien he trong So tay sinh vien",
                "source_url": lookup_result.get("source_url"),
                "cohort": lookup_result.get("cohort"),
                "document_id": lookup_result.get("document_id"),
                "source_section": lookup_result.get("source_section"),
                "source_parent_id": lookup_result.get("source_parent_id"),
                "parent_section_id": lookup_result.get("source_parent_id"),
                "applicability": lookup_result.get("applicability"),
                "content": preview
                or "Du lieu phong ban/lien he duoc trich xuat tu So tay sinh vien HCMUE.",
            }
        ]

    if lookup_result.get("lookup_type") == "foreign_language_equivalency":
        items = lookup_result.get("items") or []
        preview = "; ".join(
            str(item.get("certificate"))
            for item in items[:5]
            if item.get("certificate")
        )
        return [
            {
                "chunk_type": "structured_lookup",
                "title": lookup_result.get("table_name")
                or "Bang quy doi chuan dau ra ngoai ngu",
                "source_pages": lookup_result.get("source_pages", []),
                "source_label": lookup_result.get("source_label")
                or "Bang quy doi chuan dau ra ngoai ngu trong So tay sinh vien HCMUE",
                "source_url": lookup_result.get("source_url"),
                "cohort": lookup_result.get("cohort"),
                "document_id": lookup_result.get("document_id"),
                "source_section": lookup_result.get("source_section"),
                "source_parent_id": lookup_result.get("source_parent_id"),
                "parent_section_id": lookup_result.get("source_parent_id"),
                "applicability": lookup_result.get("applicability"),
                "content": preview
                or "Du lieu quy doi chuan dau ra ngoai ngu duoc trich xuat tu So tay sinh vien HCMUE.",
            }
        ]

    if lookup_result.get("lookup_type") in {
        "study_duration",
        "scholarship_classification",
    }:
        items = lookup_result.get("items") or []
        if lookup_result.get("lookup_type") == "study_duration":
            preview = "; ".join(
                str(row.get("Chương trình đào tạo"))
                for table in items[:3]
                for row in (table.get("rows") or [])[:2]
                if row.get("Chương trình đào tạo")
            )
        else:
            preview = "; ".join(
                str(row.get("label")) for row in items[:5] if row.get("label")
            )
        return [
            {
                "chunk_type": "structured_lookup",
                "title": lookup_result.get("table_name") or "Bang tra cuu",
                "source_pages": lookup_result.get("source_pages", []),
                "source_label": lookup_result.get("source_label")
                or "Bang du lieu duoc trich xuat tu So tay sinh vien HCMUE",
                "source_url": lookup_result.get("source_url"),
                "cohort": lookup_result.get("cohort"),
                "document_id": lookup_result.get("document_id"),
                "source_section": lookup_result.get("source_section"),
                "source_parent_id": lookup_result.get("source_parent_id"),
                "parent_section_id": lookup_result.get("source_parent_id"),
                "applicability": lookup_result.get("applicability"),
                "content": preview
                or "Du lieu bang duoc trich xuat tu So tay sinh vien HCMUE.",
            }
        ]

    return [
        {
            "chunk_type": "structured_lookup",
            "title": lookup_result.get("table_name")
            or "Bảng quy chế (Trích xuất tự động)",
            "source_pages": lookup_result.get("source_pages", []),
            "source_label": lookup_result.get("source_label")
            or "Bảng quy định được trích xuất",
            "source_url": lookup_result.get("source_url"),
            "cohort": lookup_result.get("cohort"),
            "document_id": lookup_result.get("document_id"),
            "source_section": lookup_result.get("source_section"),
            "source_parent_id": lookup_result.get("source_parent_id"),
            "parent_section_id": lookup_result.get("source_parent_id"),
            "applicability": lookup_result.get("applicability"),
            "content": "Dữ liệu được trích xuất trực tiếp từ cơ sở dữ liệu bảng quy chế trong Sổ tay Sinh viên HCMUE.",
        }
    ]


def build_citation_from_formula(formula_result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "chunk_type": "formula",
            "title": formula_result.get("rule_name"),
            "source_pages": formula_result.get("source_pages", []),
            "source_label": formula_result.get("source_label")
            or "Công thức/quy tắc được trích xuất",
            "source_url": formula_result.get("source_url"),
            "cohort": formula_result.get("cohort"),
            "document_id": formula_result.get("document_id"),
            "source_section": formula_result.get("source_section"),
            "source_parent_id": formula_result.get("source_parent_id"),
            "parent_section_id": formula_result.get("source_parent_id"),
            "applicability": formula_result.get("applicability"),
        }
    ]
