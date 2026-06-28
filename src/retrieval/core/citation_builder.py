from typing import Any


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
    if chunk_type == "form":
        return "Biểu mẫu"
    if chunk_type == "contact":
        return "Thông tin liên hệ"
    if chunk_type == "procedure":
        return "Quy trình"
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
                or metadata.get("procedure_name")
                or metadata.get("rule_name"),
                "source_pages": parse_source_pages(metadata.get("source_pages")),
                "source_label": _build_source_label(metadata),
                "source_url": _first_value(metadata, ("source_url", "url", "document_url")),
                "cohort": metadata.get("cohort"),
                "applicability": metadata.get("applicability"),
                "distance": item.get("distance"),
                "retrieval_purpose": item.get("retrieval_purpose"),
                "content": item.get("document") or item.get("content"),
            }
        )

    return citations


def build_citation_from_lookup(lookup_result: dict[str, Any]) -> list[dict[str, Any]]:
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
            "applicability": formula_result.get("applicability"),
        }
    ]
