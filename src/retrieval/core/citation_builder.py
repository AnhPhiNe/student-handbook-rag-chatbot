import re
from typing import Any

from .source_contract import source_records_from_result


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
        is_table = item.get("chunk_type") in {
            "office_directory",
            "program_directory",
            "structured_lookup",
        }
        item["detail_kind"] = "table" if is_table else "article"
        if is_table:
            item["table_name"] = item.get("title")
        if not item.get("source_pages"):
            item["source_pages"] = parse_source_pages(metadata.get("source_pages"))
        if not item.get("source_label"):
            item["source_label"] = _build_source_label(metadata)
        if not item.get("source_url"):
            item["source_url"] = _first_value(
                metadata,
                ("source_url", "url", "document_url"),
            )
        if not item.get("cohort"):
            item["cohort"] = metadata.get("cohort")
        if not item.get("document_id"):
            item["document_id"] = metadata.get("document_id")
        if not item.get("applicability"):
            item["applicability"] = metadata.get("applicability")

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


_CITATION_METADATA_KEYS = {
    "applicability",
    "cohort",
    "content_type",
    "document_id",
    "source_pages",
    "source_parent_id",
    "source_parent_ids",
    "source_record_id",
    "source_records",
    "source_section",
    "source_section_id",
    "source_url",
}

_COLUMN_LABELS = {
    "certificate": "Chứng chỉ",
    "degree_level": "Trình độ",
    "equivalent_level_3": "Bậc 3 (B1)",
    "equivalent_level_4": "Bậc 4 (B2)",
    "faculty_name": "Khoa quản lý",
    "label": "Xếp loại",
    "language": "Ngoại ngữ",
    "level_or_scale": "Thang đo / Kỹ năng",
    "program_code": "Mã ngành",
    "program_name": "Tên ngành đào tạo",
    "scholarship_score_range": "Khoảng điểm học bổng",
}


def _format_citation_value(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(_format_citation_value(item) for item in value)
    if isinstance(value, dict):
        return "; ".join(
            f"{key}: {_format_citation_value(item)}"
            for key, item in value.items()
            if item not in (None, "", [])
        )
    return str(value or "").replace("\n", " ").replace("|", "\\|").strip()


def format_rows_as_markdown_table(
    rows: list[dict[str, Any]],
    columns: list[str] | None = None,
) -> str:
    if not rows:
        return ""

    normalized_rows = []
    for row in rows:
        normalized = dict(row)
        nested_row = normalized.pop("row", None)
        if isinstance(nested_row, dict):
            normalized.update(nested_row)
        normalized_rows.append(normalized)

    if columns is None:
        columns = []
        for row in normalized_rows:
            for key in row:
                if key not in columns and key not in _CITATION_METADATA_KEYS and not key.startswith("_"):
                    columns.append(key)
    if not columns:
        return ""

    header = "| " + " | ".join(_COLUMN_LABELS.get(key, key) for key in columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    body = [
        "| "
        + " | ".join(_format_citation_value(row.get(key)) for key in columns)
        + " |"
        for row in normalized_rows
    ]
    return "\n".join([header, separator, *body])


def _lookup_rows(lookup_result: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("rows", "items", "result"):
        value = lookup_result.get(key)
        if isinstance(value, dict):
            return [value]
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            return value
    return []


def _lookup_content(
    lookup_result: dict[str, Any],
    source_record: dict[str, Any] | None = None,
) -> str:
    if lookup_result.get("lookup_type") == "formula":
        parts = [
            str(lookup_result.get("rule_name") or "").strip(),
            str(lookup_result.get("formula_text") or "").strip(),
            str(lookup_result.get("source_article") or "").strip(),
        ]
        return "\n\n".join(part for part in parts if part)

    nested_tables = [
        item
        for item in (lookup_result.get("items") or [])
        if isinstance(item, dict) and isinstance(item.get("rows"), list)
    ]
    source_table_id = (source_record or {}).get("table_id")
    if source_table_id:
        matching_tables = [
            item
            for item in nested_tables
            if item.get("table_id") == source_table_id
        ]
        if matching_tables:
            nested_tables = matching_tables
    if nested_tables:
        sections = []
        for table in nested_tables:
            table_content = format_rows_as_markdown_table(
                table.get("rows") or [],
                table.get("columns"),
            )
            if not table_content:
                continue
            label = table.get("applicability") or table.get("table_name")
            sections.append(
                f"**{label}**\n\n{table_content}" if label else table_content
            )
        return "\n\n".join(sections)

    rows = _lookup_rows(lookup_result)
    source_record_id = (source_record or {}).get("source_record_id")
    if source_record_id:
        matching_rows = [
            row
            for row in rows
            if str(
                row.get("source_record_id")
                or row.get("record_id")
                or row.get("id")
                or ""
            ).strip()
            == str(source_record_id).strip()
        ]
        if matching_rows:
            rows = matching_rows
    return format_rows_as_markdown_table(rows, lookup_result.get("columns"))


def _build_lookup_citations(lookup_result: dict[str, Any]) -> list[dict[str, Any]]:
    lookup_type = str(lookup_result.get("lookup_type") or "structured_lookup")
    citations = []

    for source_record in source_records_from_result(lookup_result):
        source_kind = source_record.get("source_kind")
        if source_kind == "formula":
            chunk_type = "formula"
        elif source_kind == "catalog" and lookup_type in {
            "program",
            "program_directory",
        }:
            chunk_type = "program_directory"
        elif source_kind == "catalog":
            chunk_type = "office_directory"
        else:
            chunk_type = "structured_lookup"

        title = (
            source_record.get("table_name")
            or lookup_result.get("rule_name")
            or lookup_result.get("table_name")
            or "Nguồn dữ liệu Sổ tay sinh viên"
        )
        parent_id = source_record.get("parent_section_id")
        source_section = parent_id or source_record.get("table_id")
        identity = (
            parent_id
            or source_record.get("source_record_id")
            or source_record.get("table_id")
        )
        citation = {
            "chunk_id": f"structured:{lookup_type}:{source_record['document_id']}:{identity}",
            "chunk_type": chunk_type,
            "title": title,
            "table_name": title if chunk_type != "formula" else None,
            "detail_kind": "article" if chunk_type == "formula" else "table",
            "source_kind": source_kind,
            "source_pages": source_record.get("source_pages") or [],
            "source_label": lookup_result.get("source_label")
            or ("Công thức/quy tắc trong Sổ tay sinh viên HCMUE" if chunk_type == "formula" else "Dữ liệu tra cứu trong Sổ tay sinh viên HCMUE"),
            "source_url": source_record.get("source_url"),
            "cohort": source_record.get("cohort"),
            "document_id": source_record.get("document_id"),
            "table_id": source_record.get("table_id"),
            "source_record_id": source_record.get("source_record_id"),
            "source_section": source_section,
            "source_parent_id": parent_id,
            "parent_section_id": parent_id,
            "applicability": source_record.get("applicability"),
            "request_index": lookup_result.get("request_index"),
            "query_span": lookup_result.get("query_span"),
            "request_cohort": lookup_result.get("request_cohort")
            or lookup_result.get("cohort"),
            "content": _lookup_content(lookup_result, source_record),
        }
        citations.append(citation)

    return citations


def build_citation_from_lookup(lookup_result: dict[str, Any]) -> list[dict[str, Any]]:
    if not lookup_result or not isinstance(lookup_result, dict):
        return []

    lookup_type = lookup_result.get("lookup_type")
    if lookup_type == "multi_request":
        citations = []
        for sub_result in lookup_result.get("sub_results") or []:
            if not isinstance(sub_result, dict):
                continue
            child = sub_result.get("result")
            if not isinstance(child, dict):
                continue
            child = {
                **child,
                "request_index": sub_result.get("request_index"),
                "query_span": sub_result.get("query_span"),
                "request_cohort": sub_result.get("cohort"),
            }
            citations.extend(build_citation_from_lookup(child))
        return _deduplicate_structured_citations(citations)

    if lookup_type in {"multi_cohort_structured", "multi_structured"}:
        citations = []
        for child in lookup_result.get("sub_lookups") or []:
            if isinstance(child, dict):
                citations.extend(build_citation_from_lookup(child))
        return _deduplicate_structured_citations(citations)

    if lookup_type == "structured_context":
        citations = []
        for item in lookup_result.get("items") or []:
            if not isinstance(item, dict):
                continue
            child = dict(lookup_result)
            child.update(item)
            child["lookup_type"] = item.get("lookup_type") or "structured_lookup"
            citations.extend(_build_lookup_citations(child))
        return _deduplicate_structured_citations(citations)

    return _build_lookup_citations(lookup_result)


def _deduplicate_structured_citations(
    citations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    deduplicated = []
    seen = set()
    for citation in citations:
        key = (
            citation.get("request_index"),
            citation.get("query_span"),
            citation.get("request_cohort"),
            citation.get("parent_section_id"),
            citation.get("document_id"),
            citation.get("cohort"),
            citation.get("title"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(citation)
    return deduplicated


def build_citation_from_formula(formula_result: dict[str, Any]) -> list[dict[str, Any]]:
    if not formula_result or not isinstance(formula_result, dict):
        return []
    normalized = dict(formula_result)
    normalized["lookup_type"] = "formula"
    return _build_lookup_citations(normalized)
