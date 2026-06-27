from typing import Any
from collections import Counter


def get_max_token_limits() -> dict[str, int]:
    """Lấy giới hạn token tối đa cho các loại chunk khác nhau.

    Hàm này trả về một từ điển (dictionary) chứa các giới hạn về số lượng token
    (đơn vị nhỏ nhất của văn bản, như từ hoặc ký hiệu) cho từng loại nội dung
    (gọi là "chunk"). Ví dụ, một "regulation" (quy định) có thể có giới hạn
    token khác với một "table" (bảng).

    Returns:
        dict[str, int]: Một từ điển nơi khóa là tên của loại chunk (ví dụ: "regulation")
            và giá trị là số lượng token tối đa cho phép cho loại chunk đó.
    """
    return {
        "regulation": 850,
        "form": 250,
        "table": 250,
        "formula": 180,
        "office_directory": 350,
        "faculty_program_directory": 350,
        "reference_directory": 350,
        "procedure": 500,
    }


def detect_overlong_chunks(
    chunks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Phát hiện các chunk (đoạn văn bản) bị quá dài so với giới hạn token cho phép.

    Hàm này duyệt qua một danh sách các chunk và so sánh số lượng token của mỗi chunk
    với giới hạn token đã được định nghĩa cho loại chunk đó. Nếu một chunk có số
    lượng token vượt quá giới hạn, nó sẽ được đánh dấu là "quá dài".

    Args:
        chunks (list[dict[str, Any]]): Một danh sách các từ điển, mỗi từ điển đại diện
            cho một chunk. Mỗi từ điển chunk cần có ít nhất các khóa sau:
            - "chunk_type" (str): Loại của chunk (ví dụ: "regulation", "table").
            - "token_count_approx" (int): Số lượng token ước tính của chunk.
            - "chunk_id" (Any): Mã định danh duy nhất của chunk.
            - "metadata" (dict, tùy chọn): Một từ điển chứa thông tin bổ sung,
              có thể bao gồm "source_pages" (danh sách các trang nguồn).

    Returns:
        list[dict[str, Any]]: Một danh sách các từ điển. Mỗi từ điển trong danh sách
            mô tả một chunk bị quá dài và chứa các thông tin chi tiết như:
            - "chunk_id" (Any): Mã định danh của chunk bị quá dài.
            - "chunk_type" (str): Loại của chunk đó.
            - "token_count_approx" (int): Số lượng token thực tế của chunk.
            - "limit" (int): Giới hạn token cho loại chunk này.
            - "excess" (int): Số lượng token vượt quá giới hạn (token_count_approx - limit).
            - "source_pages" (list[str], tùy chọn): Các trang nguồn mà chunk này xuất phát.
    """
    limits = get_max_token_limits()
    overlong = []

    for chunk in chunks:
        chunk_type = chunk.get("chunk_type")
        token_count = chunk.get("token_count_approx", 0)
        limit = limits.get(chunk_type)

        if limit is None:
            # Nếu không tìm thấy giới hạn cho loại chunk này, bỏ qua.
            continue

        if token_count > limit:
            overlong.append(
                {
                    "chunk_id": chunk.get("chunk_id"),
                    "chunk_type": chunk_type,
                    "token_count_approx": token_count,
                    "limit": limit,
                    "excess": token_count - limit,
                    "source_pages": chunk.get("metadata", {}).get("source_pages"),
                }
            )

    return overlong


def build_chunk_report(
    regulation_chunks: list[dict[str, Any]],
    table_chunks: list[dict[str, Any]],
    formula_chunks: list[dict[str, Any]],
    form_chunks: list[dict[str, Any]],
    directory_chunks: list[dict[str, Any]],
    procedure_chunks: list[dict[str, Any]],
    all_chunks: list[dict[str, Any]],
    validation_issues: list[dict[str, Any]],
) -> dict[str, Any]:
    """Xây dựng một báo cáo tổng hợp về các chunk (đoạn văn bản).

    Hàm này tổng hợp thông tin từ nhiều danh sách chunk khác nhau để tạo ra
    một báo cáo chi tiết. Báo cáo bao gồm số lượng chunk theo loại, số lượng
    token trung bình và tối đa, danh sách các chunk bị quá dài, và các vấn đề
    xác thực đã được tìm thấy.

    Args:
        regulation_chunks (list[dict[str, Any]]): Danh sách các chunk thuộc loại "regulation".
        table_chunks (list[dict[str, Any]]): Danh sách các chunk thuộc loại "table".
        formula_chunks (list[dict[str, Any]]): Danh sách các chunk thuộc loại "formula".
        form_chunks (list[dict[str, Any]]): Danh sách các chunk thuộc loại "form".
        directory_chunks (list[dict[str, Any]]): Danh sách các chunk thuộc loại thư mục
            (ví dụ: "office_directory", "faculty_program_directory", "reference_directory").
        procedure_chunks (list[dict[str, Any]]): Danh sách các chunk thuộc loại "procedure".
        all_chunks (list[dict[str, Any]]): Một danh sách chứa TẤT CẢ các chunk đã được xử lý.
            Mỗi chunk cần có ít nhất các khóa "chunk_type", "index_mode", và "token_count_approx".
        validation_issues (list[dict[str, Any]]): Một danh sách các từ điển, mỗi từ điển
            mô tả một vấn đề xác thực được tìm thấy trong quá trình xử lý chunk.

    Returns:
        dict[str, Any]: Một từ điển chứa báo cáo tổng hợp với các thông tin sau:
            - "total_chunks" (int): Tổng số lượng tất cả các chunk.
            - "regulation_chunks" (int): Số lượng chunk loại "regulation".
            - "table_chunks" (int): Số lượng chunk loại "table".
            - "formula_chunks" (int): Số lượng chunk loại "formula".
            - "form_chunks" (int): Số lượng chunk loại "form".
            - "directory_chunks" (int): Số lượng chunk loại thư mục.
            - "procedure_chunks" (int): Số lượng chunk loại "procedure".
            - "chunk_type_count" (dict[str, int]): Số lượng chunk cho mỗi loại chunk.
            - "index_mode_count" (dict[str, int]): Số lượng chunk cho mỗi chế độ index.
            - "avg_token_count_approx" (float): Số lượng token trung bình của tất cả các chunk.
            - "max_token_count_approx" (int): Số lượng token tối đa của một chunk bất kỳ.
            - "overlong_chunks_count" (int): Tổng số lượng chunk bị quá dài.
            - "overlong_chunks" (list[dict[str, Any]]): Danh sách chi tiết các chunk bị quá dài.
            - "validation_issues" (list[dict[str, Any]]): Danh sách các vấn đề xác thực.
    """
    overlong_chunks = detect_overlong_chunks(all_chunks)

    return {
        "total_chunks": len(all_chunks),
        "regulation_chunks": len(regulation_chunks),
        "table_chunks": len(table_chunks),
        "formula_chunks": len(formula_chunks),
        "form_chunks": len(form_chunks),
        "directory_chunks": len(directory_chunks),
        "procedure_chunks": len(procedure_chunks),
        "chunk_type_count": dict(Counter(chunk["chunk_type"] for chunk in all_chunks)),
        "index_mode_count": dict(Counter(chunk["index_mode"] for chunk in all_chunks)),
        "avg_token_count_approx": round(
            sum(chunk["token_count_approx"] for chunk in all_chunks)
            / max(len(all_chunks), 1),  # Tránh chia cho 0 nếu không có chunk nào
            2,
        ),
        "max_token_count_approx": max(
            [chunk["token_count_approx"] for chunk in all_chunks],
            default=0,  # Mặc định là 0 nếu không có chunk nào
        ),
        "overlong_chunks_count": len(overlong_chunks),
        "overlong_chunks": overlong_chunks,
        "validation_issues": validation_issues,
    }