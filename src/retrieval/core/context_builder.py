from typing import Any


def build_context_from_vector_results(results: list[dict[str, Any]], max_items: int = 5) -> str:
    blocks = []

    for idx, item in enumerate(results[:max_items], start=1):
        metadata = item.get("metadata", {})
        title = (
            metadata.get("title")
            or metadata.get("form_name")
            or metadata.get("unit_name")
            or metadata.get("faculty_or_unit_name")
            or metadata.get("procedure_name")
            or metadata.get("rule_name")
            or item.get("chunk_id")
        )

        blocks.append(
            f"[Nguồn {idx}]\n"
            f"Tiêu đề: {title}\n"
            f"Loại: {metadata.get('chunk_type')}\n"
            f"Trang: {metadata.get('source_pages')}\n"
            f"Nội dung:\n{item.get('content')}"
        )

    return "\n\n---\n\n".join(blocks)


def build_context_from_lookup(lookup_result: dict[str, Any]) -> str:
    return (
        f"Kết quả tra cứu bảng: {lookup_result.get('table_name')}\n"
        f"Giá trị đầu vào: {lookup_result.get('input_value')}\n"
        f"Kết quả: {lookup_result.get('result')}\n"
        f"Trang nguồn: {lookup_result.get('source_pages')}"
    )


def build_context_from_tool(tool_result: dict[str, Any]) -> str:
    return (
        f"Kết quả công cụ tính toán: {tool_result.get('tool_name')}\n"
        f"Input: {tool_result.get('inputs')}\n"
        f"Kết quả: {tool_result.get('result')}\n"
        f"Ghi chú: {tool_result.get('note')}"
    )
def build_context_from_formula(formula_result: dict[str, Any]) -> str:
    variables = formula_result.get("variables") or {}
    variable_lines = "\n".join(f"- {key}: {value}" for key, value in variables.items())
    raw_excerpt = formula_result.get("raw_excerpt", "")
    excerpt_text = f"\n\nTrích dẫn quy định chi tiết:\n{raw_excerpt}" if raw_excerpt else ""
    
    return (
        f"Công thức: {formula_result.get('rule_name')}\n"
        f"Biểu thức: {formula_result.get('formula_text')}\n"
        f"Biến số:\n{variable_lines}\n"
        f"Nguồn: {formula_result.get('source_article')}, trang {formula_result.get('source_pages')}"
        f"{excerpt_text}"
    )
