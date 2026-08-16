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


def format_rows_as_markdown_table(
    rows: list[dict[str, Any]],
    columns: list[str] | None = None,
    column_labels: dict[str, str] | None = None,
) -> str:
    """Format structured table rows into a standard GitHub Markdown table."""
    if not rows:
        return ""
    if not columns:
        cols: list[str] = []
        for r in rows:
            if isinstance(r, dict):
                for k in r.keys():
                    if (
                        k not in cols
                        and not k.startswith("_")
                        and k not in ("matched_level", "matched_value")
                    ):
                        cols.append(k)
        columns = cols
    if not columns:
        return ""

    labels = column_labels or {}
    headers = [str(labels.get(c, c)) for c in columns]
    header_line = "| " + " | ".join(headers) + " |"
    separator_line = "| " + " | ".join("---" for _ in columns) + " |"

    body_lines: list[str] = []
    for r in rows:
        if isinstance(r, dict):
            row_vals = [
                str(r.get(c, "")).replace("\n", " ").replace("|", "\\|").strip()
                for c in columns
            ]
            body_lines.append("| " + " | ".join(row_vals) + " |")

    return "\n".join([header_line, separator_line] + body_lines)


def build_citation_from_lookup(lookup_result: dict[str, Any]) -> list[dict[str, Any]]:
    if not lookup_result or not isinstance(lookup_result, dict):
        return []

    # 1. Multi-cohort structured comparison
    if lookup_result.get("lookup_type") == "multi_cohort_structured":
        sub_citations: list[dict[str, Any]] = []
        for sub in lookup_result.get("sub_lookups") or []:
            if isinstance(sub, dict):
                sub_citations.extend(build_citation_from_lookup(sub))
        if sub_citations:
            return sub_citations

    # 2. Structured context (multiple tables bundled)
    if lookup_result.get("lookup_type") == "structured_context":
        citations = []
        seen = set()
        for item in lookup_result.get("items") or []:
            source_parent_id = item.get("source_parent_id")
            key = (source_parent_id, item.get("cohort"), item.get("table_id"))
            if key in seen:
                continue
            seen.add(key)
            t_name = item.get("table_name") or "Bảng dữ liệu Sổ tay sinh viên"
            r = item.get("rows") or []
            c = item.get("columns")
            table_md = format_rows_as_markdown_table(r, c)
            content = (
                f"**{t_name}**\n\n{table_md}"
                if table_md
                else f"{t_name}: {len(r)} dòng dữ liệu."
            )
            citations.append(
                {
                    "chunk_type": "structured_lookup",
                    "title": t_name,
                    "source_pages": item.get("source_pages") or [],
                    "source_label": "Bảng dữ liệu được chuẩn hóa từ Sổ tay sinh viên HCMUE",
                    "cohort": item.get("cohort"),
                    "document_id": item.get("document_id"),
                    "source_section": source_parent_id,
                    "source_parent_id": source_parent_id,
                    "parent_section_id": source_parent_id,
                    "content": content,
                }
            )
        return citations

    # 3. Program directory
    if lookup_result.get("lookup_type") in ("program_directory", "program"):
        programs = lookup_result.get("result") or lookup_result.get("items") or []
        if isinstance(programs, dict):
            programs = [programs]
        prog_labels = {
            "program_code": "Mã ngành",
            "program_name": "Tên ngành đào tạo",
            "degree_level": "Trình độ",
            "faculty_name": "Khoa quản lý",
        }
        prog_cols = ["program_code", "program_name", "degree_level", "faculty_name"]
        table_md = format_rows_as_markdown_table(programs, prog_cols, prog_labels)
        return [
            {
                "chunk_type": "program_directory",
                "title": lookup_result.get("table_name") or "Danh mục ngành đào tạo",
                "source_pages": lookup_result.get("source_pages", []),
                "source_label": lookup_result.get("source_label")
                or "Danh mục ngành đào tạo trong Sổ tay sinh viên HCMUE",
                "source_url": lookup_result.get("source_url"),
                "cohort": lookup_result.get("cohort"),
                "document_id": lookup_result.get("document_id"),
                "source_section": lookup_result.get("source_section"),
                "source_parent_id": lookup_result.get("source_parent_id"),
                "parent_section_id": lookup_result.get("source_parent_id"),
                "applicability": lookup_result.get("applicability"),
                "content": table_md
                or "Dữ liệu ngành đào tạo được trích xuất từ Sổ tay sinh viên HCMUE.",
            }
        ]

    # 4. Office directory / Faculty profiles
    if lookup_result.get("lookup_type") in (
        "office_directory",
        "student_office",
        "student_faculty",
    ):
        offices = lookup_result.get("result") or lookup_result.get("items") or []
        if isinstance(offices, dict):
            offices = [offices]
        first_office = offices[0] if offices else {}
        off_labels = {
            "unit_name": "Tên đơn vị / Phòng ban",
            "location": "Địa điểm / Phòng",
            "email": "Email",
            "phone": "Số điện thoại",
            "website": "Website",
        }
        off_cols = ["unit_name", "location", "email", "phone", "website"]
        table_md = format_rows_as_markdown_table(offices, off_cols, off_labels)
        return [
            {
                "chunk_type": "office_directory",
                "title": first_office.get("unit_name")
                or lookup_result.get("table_name")
                or "Danh bạ phòng ban",
                "source_pages": lookup_result.get("source_pages", []),
                "source_label": lookup_result.get("source_label")
                or "Danh mục phòng ban / liên hệ trong Sổ tay sinh viên",
                "source_url": lookup_result.get("source_url"),
                "cohort": lookup_result.get("cohort"),
                "document_id": lookup_result.get("document_id"),
                "source_section": lookup_result.get("source_section"),
                "source_parent_id": lookup_result.get("source_parent_id"),
                "parent_section_id": lookup_result.get("source_parent_id"),
                "applicability": lookup_result.get("applicability"),
                "content": table_md
                or "Dữ liệu phòng ban / liên hệ được trích xuất từ Sổ tay sinh viên HCMUE.",
            }
        ]

    # 5. Foreign Language Equivalency
    if lookup_result.get("lookup_type") in (
        "foreign_language_equivalency",
        "foreign_language",
    ):
        items = lookup_result.get("items") or (
            [lookup_result.get("result")]
            if lookup_result.get("result")
            and isinstance(lookup_result.get("result"), dict)
            else []
        )
        fl_labels = {
            "language": "Ngoại ngữ",
            "certificate": "Chứng chỉ",
            "level_or_scale": "Thang đo / Kỹ năng",
            "equivalent_level_3": "Bậc 3 (B1)",
            "equivalent_level_4": "Bậc 4 (B2)",
        }
        fl_cols = [
            "language",
            "certificate",
            "level_or_scale",
            "equivalent_level_3",
            "equivalent_level_4",
        ]
        table_md = format_rows_as_markdown_table(items, fl_cols, fl_labels)
        return [
            {
                "chunk_type": "structured_lookup",
                "title": lookup_result.get("table_name")
                or "Bảng quy đổi chuẩn đầu ra ngoại ngữ",
                "source_pages": lookup_result.get("source_pages", []),
                "source_label": lookup_result.get("source_label")
                or "Bảng quy đổi chuẩn đầu ra ngoại ngữ trong Sổ tay sinh viên HCMUE",
                "source_url": lookup_result.get("source_url"),
                "cohort": lookup_result.get("cohort"),
                "document_id": lookup_result.get("document_id"),
                "source_section": lookup_result.get("source_section"),
                "source_parent_id": lookup_result.get("source_parent_id"),
                "parent_section_id": lookup_result.get("source_parent_id"),
                "applicability": lookup_result.get("applicability"),
                "content": table_md
                or "Dữ liệu quy đổi chuẩn đầu ra ngoại ngữ được trích xuất từ Sổ tay sinh viên HCMUE.",
            }
        ]

    # 6. Study Duration
    if lookup_result.get("lookup_type") == "study_duration":
        items = lookup_result.get("items") or []
        md_tables = []
        for t in items:
            if isinstance(t, dict):
                app = t.get("applicability") or t.get("table_name") or ""
                r = t.get("rows") or []
                c = t.get("columns") or [
                    "Chương trình đào tạo",
                    "Thời gian học tập chuẩn",
                    "Thời gian học tập tối đa",
                ]
                md = format_rows_as_markdown_table(r, c)
                if md:
                    if app:
                        md_tables.append(f"**{app}**\n\n{md}")
                    else:
                        md_tables.append(md)
        table_md = "\n\n".join(md_tables)
        return [
            {
                "chunk_type": "structured_lookup",
                "title": lookup_result.get("table_name")
                or "Thời gian học tập chuẩn và tối đa",
                "source_pages": lookup_result.get("source_pages", []),
                "source_label": lookup_result.get("source_label")
                or "Bảng thời gian đào tạo trong Sổ tay sinh viên HCMUE",
                "source_url": lookup_result.get("source_url"),
                "cohort": lookup_result.get("cohort"),
                "document_id": lookup_result.get("document_id"),
                "source_section": lookup_result.get("source_section"),
                "source_parent_id": lookup_result.get("source_parent_id"),
                "parent_section_id": lookup_result.get("source_parent_id"),
                "applicability": lookup_result.get("applicability"),
                "content": table_md
                or "Dữ liệu thời gian đào tạo được trích xuất từ Sổ tay sinh viên HCMUE.",
            }
        ]

    # 7. Scholarship Classification
    if lookup_result.get("lookup_type") == "scholarship_classification":
        items = lookup_result.get("items") or (
            [lookup_result.get("result")]
            if lookup_result.get("result")
            and isinstance(lookup_result.get("result"), dict)
            else []
        )
        sch_labels = {
            "label": "Loại học bổng",
            "scholarship_score": "Điểm học bổng",
            "min_gpa": "Điểm học tập (GPA)",
            "min_conduct": "Điểm rèn luyện",
        }
        table_md = format_rows_as_markdown_table(items, column_labels=sch_labels)
        return [
            {
                "chunk_type": "structured_lookup",
                "title": lookup_result.get("table_name")
                or "Bảng xếp loại học bổng khuyến khích học tập",
                "source_pages": lookup_result.get("source_pages", []),
                "source_label": lookup_result.get("source_label")
                or "Bảng xếp loại học bổng trong Sổ tay sinh viên HCMUE",
                "source_url": lookup_result.get("source_url"),
                "cohort": lookup_result.get("cohort"),
                "document_id": lookup_result.get("document_id"),
                "source_section": lookup_result.get("source_section"),
                "source_parent_id": lookup_result.get("source_parent_id"),
                "parent_section_id": lookup_result.get("source_parent_id"),
                "applicability": lookup_result.get("applicability"),
                "content": table_md
                or "Dữ liệu xếp loại học bổng được trích xuất từ Sổ tay sinh viên HCMUE.",
            }
        ]

    # 8. General structured lookup fallback (scoring, academic, conduct, etc.)
    rows = lookup_result.get("rows")
    if not rows and lookup_result.get("items") and isinstance(lookup_result["items"], list):
        if (
            lookup_result["items"]
            and isinstance(lookup_result["items"][0], dict)
            and "rows" in lookup_result["items"][0]
        ):
            rows = []
            for sub_t in lookup_result["items"]:
                rows.extend(sub_t.get("rows", []))
        else:
            rows = lookup_result["items"]
    elif not rows and lookup_result.get("result") and isinstance(lookup_result["result"], list):
        rows = lookup_result["result"]
    elif not rows and lookup_result.get("result") and isinstance(lookup_result["result"], dict):
        rows = [lookup_result["result"]]

    cols = lookup_result.get("columns")
    table_md = format_rows_as_markdown_table(rows, cols) if rows else ""
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
            "content": table_md
            or "Dữ liệu được trích xuất trực tiếp từ cơ sở dữ liệu bảng quy chế trong Sổ tay Sinh viên HCMUE.",
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
