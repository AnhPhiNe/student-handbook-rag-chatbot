import json
import re
from typing import Any

from src.common.legal_reference import article_label_from_heading, normalize_article_label
from src.common.source_identity import canonical_article_source_id


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
        document_identity = (
            metadata.get("document_title")
            or metadata.get("document_id")
            or item.get("document_identity")
            or item.get("source_label")
        )
        item["document_id"] = metadata.get("document_id") or item.get("document_id")
        item["document_identity"] = document_identity
        item["cohort"] = metadata.get("cohort") or item.get("cohort")
        article_label = normalize_article_label(
            metadata.get("article"),
            metadata.get("source_section"),
            metadata.get("title"),
            article_label_from_heading(parent_content.splitlines()[0])
            if parent_content
            else None,
        )
        item["article_label"] = article_label
        item["parent_article"] = article_label
        item["canonical_source_id"] = canonical_article_source_id(
            document_identity=document_identity,
            cohort=item.get("cohort"),
            article_label=article_label,
        )
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
        raw_content = item.get("document") or item.get("content") or ""
        focused_content = item.get("content") or ""
        source_heading = (
            article_label_from_heading(str(raw_content).splitlines()[0])
            if raw_content
            else None
        )
        article_label = normalize_article_label(
            metadata.get("article"),
            metadata.get("source_section"),
            metadata.get("title"),
            source_heading,
        )
        document_identity = metadata.get("document_title") or metadata.get("document_id")
        source_parent_id = (
            metadata.get("source_parent_id")
            or metadata.get("parent_section_id")
            or item.get("parent_id")
            or item.get("chunk_id")
        )
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
                "source_cohort": metadata.get("source_cohort")
                or metadata.get("cohort"),
                "applicable_cohorts": list(
                    metadata.get("applicable_cohorts") or []
                ),
                "applicability_validated": bool(
                    metadata.get("applicability_validated")
                ),
                "applicability_basis_parent_id": metadata.get(
                    "applicability_basis_parent_id"
                ),
                "document_id": metadata.get("document_id"),
                "document_identity": document_identity,
                "source_section": metadata.get("source_section"),
                "source_parent_id": source_parent_id,
                "parent_section_id": source_parent_id,
                "article_label": article_label,
                "canonical_source_id": canonical_article_source_id(
                    document_identity=document_identity,
                    cohort=metadata.get("cohort"),
                    article_label=article_label,
                ),
                "applicability": metadata.get("applicability"),
                "distance": item.get("distance"),
                "rerank": item.get("rerank"),
                "retrieval_purpose": item.get("retrieval_purpose"),
                "content": sanitize_citation_content(
                    raw_content
                ),
                "relevant_excerpt": sanitize_citation_content(focused_content),
            }
        )

    return citations


def build_citation_from_lookup(lookup_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Build source-bound citations for deterministic structured evidence."""
    if not isinstance(lookup_result, dict) or not lookup_result:
        return []

    sub_lookups = lookup_result.get("sub_lookups")
    if isinstance(sub_lookups, list) and sub_lookups:
        citations: list[dict[str, Any]] = []
        for item in sub_lookups:
            if isinstance(item, dict):
                citations.extend(build_citation_from_lookup(item))
        return citations

    lookup_type = str(lookup_result.get("lookup_type") or "structured_lookup")
    chunk_type = str(
        lookup_result.get("content_type")
        or (lookup_type if lookup_type in {"program_directory", "office_directory", "faculty_directory"} else "structured_lookup")
    )
    source_pages = parse_source_pages(lookup_result.get("source_pages"))
    source_section = _first_value(
        lookup_result,
        ("source_parent_id", "parent_section_id", "source_section", "section_id"),
    )
    source_label = _first_value(
        lookup_result,
        ("source_label", "document_title", "source_name", "file_name"),
    )
    document_id = _first_value(
        lookup_result,
        ("document_id", "source_document_id", "handbook_id"),
    )
    # A structured record is citable only when it is anchored to the handbook
    # by a page, section, document, or explicit source label.
    if not (source_pages or source_section or document_id or source_label):
        return []

    content_value = lookup_result.get("result")
    if content_value is None:
        content_value = lookup_result.get("items")
    if content_value is None:
        content_value = lookup_result
    try:
        content = json.dumps(content_value, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        content = str(content_value)

    return [
        {
            "chunk_id": source_section or document_id or f"structured:{lookup_type}",
            "chunk_type": chunk_type,
            "evidence_kind": "structured_result",
            "title": lookup_result.get("table_name")
            or lookup_result.get("title")
            or lookup_type,
            "source_pages": source_pages,
            "source_label": str(source_label) if source_label else None,
            "source_url": _first_value(lookup_result, ("source_url", "url", "document_url")),
            "cohort": lookup_result.get("cohort"),
            "document_id": document_id,
            "source_section": source_section,
            "source_parent_id": source_section,
            "parent_section_id": source_section,
            "applicability": lookup_result.get("applicability"),
            "content": sanitize_citation_content(content),
        }
    ]


def build_citation_from_formula(formula_result: dict[str, Any]) -> list[dict[str, Any]]:
    """Formula results use the same source-binding rules as other lookups."""
    return build_citation_from_lookup(formula_result)
