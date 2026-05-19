from typing import Any

from .chunk_schema import create_chunk
from .text_utils import format_source_pages, join_non_empty


def variables_to_text(variables: dict[str, str]) -> str:
    return "\n".join(f"- {key}: {value}" for key, value in variables.items())


def build_formula_chunks(formulas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks = []

    for formula in formulas:
        source_pages = formula.get("source_pages", [])

        content = join_non_empty(
            [
                f"Công thức: {formula.get('rule_name')}",
                f"Biểu thức: {formula.get('formula_text')}",
                "Biến số:",
                variables_to_text(formula.get("variables", {})),
                f"Hàm tính toán: {formula.get('calculator_function')}",
                f"Nguồn: {format_source_pages(source_pages)}",
                "Ghi chú: Nếu người dùng yêu cầu tính toán, hệ thống nên gọi calculator function.",
            ]
        )

        chunks.append(
            create_chunk(
                chunk_id=f"formula_{formula['rule_id']}",
                chunk_type="formula",
                index_mode="tool",
                content=content,
                metadata={
                    "source_type": "formula_rule",
                    "rule_id": formula.get("rule_id"),
                    "rule_name": formula.get("rule_name"),
                    "calculation_type": formula.get("calculation_type"),
                    "calculator_function": formula.get("calculator_function"),
                    "source_article": formula.get("source_article"),
                    "source_pages": source_pages,
                    "review_status": formula.get("review_status"),
                    "tool_preferred": True,
                },
            )
        )

    return chunks