from typing import Any

from .chunk_schema import create_chunk
from .text_utils import format_source_pages, join_non_empty, normalize_text
from .token_utils import count_tokens_approx, split_text_by_paragraph


def steps_to_text(steps: list[str]) -> str:
    """Chuyển đổi một danh sách các bước thành một chuỗi văn bản dễ đọc.

    Hàm này nhận vào một danh sách các chuỗi (mỗi chuỗi là một bước) và ghép chúng lại
    thành một chuỗi văn bản duy nhất, trong đó mỗi bước được bắt đầu bằng dấu gạch ngang.
    Nếu danh sách rỗng, nó sẽ trả về một thông báo mặc định.

    Args:
        steps (list[str]): Một danh sách các chuỗi, mỗi chuỗi đại diện cho một bước.
                           Ví dụ: ["Bước 1: Làm A", "Bước 2: Làm B"].

    Returns:
        str: Một chuỗi văn bản đã được định dạng, với mỗi bước trên một dòng mới
             và bắt đầu bằng "- ". Nếu danh sách `steps` rỗng, trả về
             "Không phát hiện bước rõ ràng.".
             Ví dụ: "- Bước 1: Làm A\n- Bước 2: Làm B".
    """
    if not steps:
        return "Không phát hiện bước rõ ràng."

    return "\n".join(f"- {step}" for step in steps)


def build_procedure_content(procedure: dict[str, Any]) -> str:
    """Xây dựng nội dung đầy đủ của một quy trình từ thông tin trong dictionary.

    Hàm này lấy các thông tin như tên quy trình, các bước đã phát hiện, nội dung thô
    và nguồn từ một dictionary `procedure` và ghép chúng lại thành một chuỗi văn bản
    duy nhất, có cấu trúc rõ ràng.

    Args:
        procedure (dict[str, Any]): Một dictionary chứa thông tin chi tiết về quy trình.
                                    Các khóa mong đợi bao gồm "procedure_name",
                                    "steps_detected", "raw_text", và "source_pages".

    Returns:
        str: Một chuỗi văn bản tổng hợp toàn bộ nội dung của quy trình, bao gồm
             tên, các bước, nội dung đầy đủ và thông tin nguồn.
             Ví dụ: "Quy trình: Tên Quy Trình\nCác bước phát hiện:\n- Bước 1\nNội dung đầy đủ:...\nNguồn: Trang 1-2".
    """
    source_pages = procedure.get("source_pages", [])

    return join_non_empty(
        [
            f"Quy trình: {procedure.get('procedure_name')}",
            "Các bước phát hiện:",
            steps_to_text(procedure.get("steps_detected", [])),
            "Nội dung đầy đủ:",
            normalize_text(procedure.get("raw_text", "")),
            f"Nguồn: {format_source_pages(source_pages)}",
        ]
    )


def split_long_procedure_content(
    content: str,
    max_tokens: int,
) -> list[str]:
    """Chia nhỏ nội dung quy trình dài thành nhiều phần nhỏ hơn dựa trên giới hạn token.

    Nếu nội dung của quy trình quá dài (vượt quá `max_tokens`), hàm này sẽ chia
    nội dung đó thành các đoạn nhỏ hơn, đảm bảo mỗi đoạn không vượt quá số lượng token
    cho phép. Việc chia được thực hiện theo đoạn văn (paragraph) để giữ ngữ cảnh.

    Args:
        content (str): Chuỗi văn bản đầy đủ của nội dung quy trình cần chia.
        max_tokens (int): Số lượng token tối đa mà mỗi phần (chunk) được phép có.

    Returns:
        list[str]: Một danh sách các chuỗi, mỗi chuỗi là một phần của nội dung
                   đã được chia. Nếu nội dung ban đầu không quá dài, danh sách
                   sẽ chỉ chứa một phần duy nhất là chính nội dung đó.
    """
    if count_tokens_approx(content) <= max_tokens:
        return [content]

    return split_text_by_paragraph(
        text=content,
        max_tokens=max_tokens,
        overlap_tokens=0,
    )


def build_procedure_chunks(
    procedures: list[dict[str, Any]],
    max_tokens: int = 500,
) -> list[dict[str, Any]]:
    """Tạo ra các "chunk" (đoạn dữ liệu nhỏ) từ một danh sách các quy trình.

    Hàm này duyệt qua từng quy trình trong danh sách, xây dựng nội dung đầy đủ
    cho mỗi quy trình, sau đó chia nhỏ nội dung đó thành các phần (chunk) nếu
    nó quá dài. Mỗi chunk được tạo ra sẽ có một ID duy nhất và chứa các metadata
    liên quan đến quy trình gốc.

    Args:
        procedures (list[dict[str, Any]]): Một danh sách các dictionary, mỗi dictionary
                                           đại diện cho một quy trình và chứa các thông tin
                                           như "procedure_id", "procedure_name", "raw_text",
                                           "steps_detected", "source_pages", "review_status".
        max_tokens (int, optional): Số lượng token tối đa cho mỗi chunk được tạo ra.
                                    Mặc định là 500.

    Returns:
        list[dict[str, Any]]: Một danh sách các dictionary, mỗi dictionary là một "chunk"
                              đã được tạo. Mỗi chunk bao gồm `chunk_id`, `chunk_type`,
                              `index_mode`, `content` và `metadata` chi tiết.
    """
    chunks = []

    for procedure in procedures:
        source_pages = procedure.get("source_pages", [])
        content = build_procedure_content(procedure)

        parts = split_long_procedure_content(
            content=content,
            max_tokens=max_tokens,
        )

        for idx, part in enumerate(parts, start=1):
            # Thêm hậu tố vào ID nếu quy trình được chia thành nhiều phần
            suffix = f"_part_{idx}" if len(parts) > 1 else ""

            chunks.append(
                create_chunk(
                    chunk_id=f"procedure_{procedure['procedure_id']}{suffix}",
                    chunk_type="procedure",
                    index_mode="semantic",  # Chế độ lập chỉ mục ngữ nghĩa
                    content=part,
                    metadata={
                        "source_type": "procedure",
                        "procedure_id": procedure.get("procedure_id"),
                        "procedure_name": procedure.get("procedure_name"),
                        "source_pages": source_pages,
                        "review_status": procedure.get("review_status"),
                        "split_from_record": len(parts) > 1,  # Cho biết chunk này có phải là một phần của bản ghi lớn hơn không
                        "part_index": idx,  # Chỉ số của phần này (nếu được chia)
                        "total_parts": len(parts),  # Tổng số phần (nếu được chia)
                    },
                )
            )

    return chunks