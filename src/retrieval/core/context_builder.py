from typing import Any


def build_context_from_vector_results(
    results: list[dict[str, Any]],
    max_items: int = 5,
    *,
    related_items: list[dict[str, Any]] | None = None,
) -> str:
    primary_blocks = []

    for idx, item in enumerate(results[:max_items], start=1):
        metadata = item.get("metadata", {})
        title = _context_item_title(item, metadata)
        cohort_line = f"Cohort: {metadata.get('cohort')}\n" if metadata.get("cohort") else ""
        primary_blocks.append(
            f"[{idx}]\n"
            f"Title: {title}\n"
            f"{cohort_line}"
            f"Type: {metadata.get('chunk_type')}\n"
            f"Pages: {metadata.get('source_pages')}\n"
            f"Content:\n{item.get('content')}"
        )

    related_blocks = []
    for idx, item in enumerate((related_items or [])[:max_items], start=1):
        metadata = item.get("metadata", {})
        title = _context_item_title(item, metadata)
        related_blocks.append(
            f"[R{idx}]\n"
            f"Title: {title}\n"
            f"Type: {metadata.get('chunk_type')}\n"
            f"Graph depth: {metadata.get('related_graph_depth')}\n"
            f"Linked from primary: {metadata.get('related_source_primary_id')}\n"
            f"Pages: {metadata.get('source_pages')}\n"
            f"Content:\n{item.get('content')}"
        )

    sections = []
    if primary_blocks:
        sections.append("PRIMARY SOURCES\n\n" + "\n\n---\n\n".join(primary_blocks))
    if related_blocks:
        sections.append("RELATED SOURCES\n\n" + "\n\n---\n\n".join(related_blocks))
    return "\n\n===\n\n".join(sections)


def _context_item_title(item: dict[str, Any], metadata: dict[str, Any]) -> str:
    return str(
        metadata.get("title")
        or metadata.get("article")
        or metadata.get("form_name")
        or metadata.get("unit_name")
        or metadata.get("faculty_or_unit_name")
        or metadata.get("program_name")
        or metadata.get("faculty_name")
        or metadata.get("procedure_name")
        or metadata.get("rule_name")
        or item.get("chunk_id")
        or "Source"
    )
