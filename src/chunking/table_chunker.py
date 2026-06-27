from typing import Any

from .chunk_schema import create_chunk
from .text_utils import format_source_pages, join_non_empty


def table_rows_to_text(rows: list[dict[str, Any]]) -> str:
    """Chuyển đổi danh sách các hàng (row) của bảng thành một chuỗi văn bản dễ đọc.

    Mỗi hàng trong bảng sẽ được định dạng thành một dòng văn bản,
    trong đó các cặp khóa-giá trị (key-value) của hàng được nối với nhau bằng dấu chấm phẩy.
    Đây là cách để biểu diễn dữ liệu bảng dưới dạng văn bản thuần túy.

    Args:
        rows: Một danh sách các từ điển, mỗi từ điển đại diện cho một hàng trong bảng.
              Mỗi từ điển chứa các cặp khóa-giá trị của các cột trong hàng đó.
              Ví dụ: `[{'Tên': 'Sản phẩm A', 'Giá': 100}, {'Tên': 'Sản phẩm B', 'Giá': 200}]`

    Returns:
        Một chuỗi văn bản, trong đó mỗi hàng được biểu diễn trên một dòng riêng biệt,
        bắt đầu bằng dấu gạch ngang và các thông tin của hàng được nối bằng dấu chấm phẩy.
        Ví dụ:
        - Tên: Sản phẩm A; Giá: 100
        - Tên: Sản phẩm B; Giá: 200
    """
    lines = []

    for row in rows:
        # Tạo một chuỗi từ các cặp khóa-giá trị của mỗi hàng.
        # Ví dụ: nếu row là {'Tên': 'Sản phẩm A', 'Giá': 100}
        # thì row_text sẽ là "Tên: Sản phẩm A; Giá: 100"
        row_text = "; ".join(f"{key}: {value}" for key, value in row.items())
        # Thêm dòng này vào danh sách các dòng, bắt đầu bằng dấu gạch ngang để dễ đọc.
        lines.append(f"- {row_text}")

    # Nối tất cả các dòng lại với nhau bằng ký tự xuống dòng để tạo thành một chuỗi văn bản hoàn chỉnh.
    return "\n".join(lines)


def build_table_chunks(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Xây dựng các "chunk" (đoạn thông tin) từ danh sách các bảng.

    Mỗi bảng sẽ được chuyển đổi thành một "chunk" riêng biệt, chứa nội dung
    của bảng dưới dạng văn bản và các siêu dữ liệu (metadata) liên quan.
    Các chunk này thường được sử dụng để lưu trữ hoặc xử lý thông tin
    trong các hệ thống tìm kiếm hoặc mô hình ngôn ngữ lớn (LLM).

    Args:
        tables: Một danh sách các từ điển, mỗi từ điển đại diện cho một bảng.
                Mỗi từ điển bảng có thể chứa các khóa như 'table_id', 'table_name',
                'source_pages' (danh sách các trang nguồn), 'rows' (danh sách các hàng dữ liệu),
                'review_status', v.v.

    Returns:
        Một danh sách các từ điển, mỗi từ điển là một "chunk" đã được tạo.
        Mỗi chunk chứa các thông tin như 'chunk_id', 'chunk_type', 'index_mode',
        'content' (nội dung văn bản của bảng), và 'metadata' (siêu dữ liệu chi tiết).
        Ví dụ về một chunk:
        {
            'chunk_id': 'table_123',
            'chunk_type': 'table',
            'index_mode': 'structured',
            'content': 'Bảng: Tên Bảng\nNguồn: Trang 1, Trang 2\nNội dung bảng:\n- Cột A: Giá trị 1; Cột B: Giá trị 2\nGhi chú: ...',
            'metadata': {
                'source_type': 'scoring_table',
                'table_id': '123',
                'table_name': 'Tên Bảng',
                'source_pages': ['1', '2'],
                'review_status': 'approved',
                'lookup_preferred': True
            }
        }
    """
    chunks = []

    for table in tables:
        # Lấy danh sách các trang nguồn từ bảng, nếu không có thì mặc định là danh sách rỗng.
        source_pages = table.get("source_pages", [])

        # Xây dựng nội dung văn bản cho chunk từ thông tin của bảng.
        # Sử dụng hàm join_non_empty để nối các phần tử không rỗng lại với nhau bằng ký tự xuống dòng.
        content = join_non_empty(
            [
                f"Bảng: {table.get('table_name')}",  # Tên của bảng
                f"Nguồn: {format_source_pages(source_pages)}",  # Định dạng các trang nguồn
                "Nội dung bảng:",  # Tiêu đề cho phần nội dung chi tiết của bảng
                table_rows_to_text(table.get("rows", [])),  # Chuyển đổi các hàng của bảng thành văn bản
                "Ghi chú: Bảng này ưu tiên dùng structured lookup thay vì để LLM tự suy đoán.",  # Ghi chú quan trọng
            ]
        )

        # Tạo một chunk mới bằng cách gọi hàm create_chunk.
        # Hàm này sẽ đóng gói tất cả thông tin cần thiết vào một định dạng chunk chuẩn.
        chunks.append(
            create_chunk(
                chunk_id=f"table_{table['table_id']}",  # ID duy nhất cho chunk, dựa trên ID của bảng
                chunk_type="table",  # Loại chunk là "table"
                index_mode="structured",  # Chế độ lập chỉ mục là "structured" (có cấu trúc)
                content=content,  # Nội dung văn bản đã tạo ở trên
                metadata={  # Các siêu dữ liệu bổ sung về bảng
                    "source_type": "scoring_table",  # Loại nguồn là bảng chấm điểm
                    "table_id": table.get("table_id"),  # ID của bảng
                    "table_name": table.get("table_name"),  # Tên của bảng
                    "source_pages": source_pages,  # Các trang nguồn
                    "review_status": table.get("review_status"),  # Trạng thái xem xét của bảng
                    "lookup_preferred": True,  # Ưu tiên tra cứu có cấu trúc hơn là để LLM tự suy đoán
                },
            )
        )

    return chunks