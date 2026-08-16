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

    blocks: list[str] = []
    in_table = False

    for line in lines:
        if _is_table_row(line):
            if in_table:
                blocks[-1] = f"{blocks[-1]}\n{line}"
            else:
                blocks.append(line)
                in_table = True
        else:
            in_table = False
            if not blocks or _starts_new_paragraph(line):
                blocks.append(line)
            else:
                blocks[-1] = f"{blocks[-1]} {line}"

    cleaned = "\n\n".join(blocks)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip()


def _is_table_row(line: str) -> bool:
    return line.startswith("|") and line.endswith("|")


def _starts_new_paragraph(line: str) -> bool:
    return bool(_NEW_PARAGRAPH_RE.match(line))


def enrich_citations_with_parent_details(
    citations: list[dict[str, Any]],
    parents_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach display-safe parent metadata to citations that point to a handbook section.

    Structured lookups intentionally keep a short table preview as their citation
    content. The UI still needs the parent article for an Article reference to be
    truthful and readable, so this function adds it without changing retrieval.
    """

    enriched: list[dict[str, Any]] = []
    for citation in citations:
        item = dict(citation)
        parent_id = str(
            item.get("parent_section_id")
            or item.get("source_parent_id")
            or item.get("source_section")
            or ""
        ).strip()
        parent = parents_by_id.get(parent_id)
        if not parent:
            enriched.append(item)
            continue

        metadata = parent.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        parent_content = str(parent.get("content") or "").strip()

        item["parent_section_id"] = parent_id
        item["source_parent_id"] = parent_id
        item["parent_article"] = metadata.get("article")
        item["parent_title"] = metadata.get("title")
        item["parent_content"] = parent_content or None
        item["detail_kind"] = "table" if item.get("chunk_type") == "structured_lookup" else "article"
        if item.get("chunk_type") == "structured_lookup":
            item["table_name"] = item.get("title")

        enriched.append(item)

    return enriched


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


def build_citation_from_lookup(_lookup_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Structured lookups provide self-contained answers without synthetic citation cards."""
    return []


def build_citation_from_formula(_formula_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Formula lookups provide self-contained answers without synthetic citation cards."""
    return []
