from typing import Any

from .chunk_schema import create_chunk
from .text_utils import format_source_pages, join_non_empty


def variables_to_text(variables: dict[str, str]) -> str:
    """Chuyển đổi một từ điển các biến số thành một chuỗi văn bản dễ đọc.

    Hàm này nhận vào một từ điển, trong đó khóa là tên của biến và giá trị là mô tả
    hoặc giá trị của biến đó. Sau đó, nó định dạng mỗi cặp khóa-giá trị thành một
    dòng riêng biệt, bắt đầu bằng dấu gạch ngang, giúp người dùng dễ dàng đọc và hiểu.

    Args:
        variables (dict[str, str]): Một từ điển chứa các biến số.
            Mỗi khóa là tên biến (kiểu chuỗi), và mỗi giá trị là mô tả
            hoặc giá trị của biến đó (kiểu chuỗi).

    Returns:
        str: Một chuỗi đã được định dạng, trong đó mỗi biến số được hiển thị
            trên một dòng riêng, bắt đầu bằng dấu gạch ngang.
            Ví dụ: "- Tên biến: Giá trị biến".
    """
    return "\n".join(f"- {key}: {value}" for key, value in variables.items())


def build_formula_chunks(formulas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Xây dựng các "chunk" (khối dữ liệu) từ một danh sách các công thức.

    Hàm này duyệt qua từng công thức trong danh sách đầu vào, trích xuất các thông tin
    quan trọng như tên công thức, biểu thức, biến số và nguồn.
    Sau đó, nó định dạng các thông tin này thành một chuỗi nội dung dễ hiểu
    và tạo ra một "chunk" dữ liệu hoàn chỉnh. Mỗi chunk bao gồm một ID duy nhất,
    loại chunk, chế độ lập chỉ mục, nội dung mô tả công thức, và các siêu dữ liệu
    (metadata) chi tiết về công thức đó. Các chunk này thường được sử dụng để
    lập chỉ mục trong các hệ thống tìm kiếm hoặc để gọi các công cụ tự động.

    Args:
        formulas (list[dict[str, Any]]): Một danh sách các từ điển, trong đó mỗi
            từ điển đại diện cho một công thức. Mỗi từ điển công thức có thể
            chứa các khóa như 'rule_name' (tên công thức), 'formula_text' (biểu thức),
            'variables' (các biến số),
            'source_pages' (trang nguồn), 'rule_id' (ID công thức), v.v.

    Returns:
        list[dict[str, Any]]: Một danh sách các "chunk" đã được tạo.
            Mỗi chunk là một từ điển đã được định dạng, chứa các khóa như
            'chunk_id' (ID của chunk), 'chunk_type' (loại chunk, ví dụ: "formula"),
            'index_mode' (chế độ lập chỉ mục), 'content' (nội dung mô tả công thức),
            và 'metadata' (một từ điển chứa các thông tin chi tiết khác về công thức).
    """
    chunks = []

    for index, formula in enumerate(formulas, start=1):
        source_pages = formula.get("source_pages", [])
        source_page_key = "_".join(str(page) for page in source_pages[:2]) or str(index)

        content = join_non_empty(
            [
                f"Công thức: {formula.get('rule_name')}",
                f"Biểu thức: {formula.get('formula_text')}",
                "Biến số:",
                variables_to_text(formula.get("variables", {})),
                f"Nguồn: {format_source_pages(source_pages)}",
                "Ghi chú: Công thức này dùng để tra cứu và hướng dẫn cách áp dụng.",
            ]
        )

        chunks.append(
            create_chunk(
                chunk_id=f"formula_{formula['rule_id']}_{source_page_key}_{index}",
                chunk_type="formula",
                index_mode="tool",
                content=content,
                metadata={
                    "source_type": "formula_rule",
                    "rule_id": formula.get("rule_id"),
                    "rule_name": formula.get("rule_name"),
                    "calculation_type": formula.get("calculation_type"),
                    "source_article": formula.get("source_article"),
                    "source_pages": source_pages,
                    "review_status": formula.get("review_status"),
                    "tool_preferred": True,
                },
            )
        )

    return chunks
