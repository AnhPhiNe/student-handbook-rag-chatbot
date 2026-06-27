from typing import Any

from .token_utils import count_tokens_approx
from .text_utils import normalize_text


def create_chunk(
    chunk_id: str,
    chunk_type: str,
    index_mode: str,
    content: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Tạo ra một "chunk" (một phần dữ liệu) với các thông tin cụ thể.

    Hàm này nhận vào các thông tin cơ bản của một chunk như ID, loại, chế độ lập chỉ mục,
    nội dung và các thông tin bổ sung (metadata). Nó sẽ chuẩn hóa nội dung đầu vào
    và ước tính số lượng token (đơn vị xử lý văn bản) trong nội dung đó.
    Kết quả trả về là một từ điển chứa tất cả các thông tin này, sẵn sàng để sử dụng
    trong các hệ thống tìm kiếm hoặc xử lý dữ liệu.

    Args:
        chunk_id: Một chuỗi định danh (ID) duy nhất cho chunk này.
                  Giúp phân biệt chunk này với các chunk khác.
        chunk_type: Loại của chunk, ví dụ: "text" (văn bản), "image_description" (mô tả ảnh).
                    Giúp hệ thống biết cách xử lý nội dung.
        index_mode: Chế độ lập chỉ mục cho chunk này, ví dụ: "semantic" (ngữ nghĩa),
                    "keyword" (từ khóa). Điều này ảnh hưởng đến cách chunk được tìm kiếm.
        content: Nội dung chính của chunk, thường là một đoạn văn bản.
                 Nội dung này sẽ được chuẩn hóa trước khi lưu.
        metadata: Một từ điển chứa các thông tin bổ sung không bắt buộc về chunk.
                  Ví dụ: {"author": "John Doe", "date": "2023-10-27"}.

    Returns:
        Một từ điển đại diện cho chunk đã tạo. Từ điển này bao gồm:
        - "chunk_id": ID duy nhất của chunk.
        - "chunk_type": Loại của chunk.
        - "index_mode": Chế độ lập chỉ mục.
        - "content": Nội dung đã được chuẩn hóa.
        - "token_count_approx": Số lượng token ước tính trong nội dung đã chuẩn hóa.
        - "metadata": Các thông tin bổ sung.
    """
    content = normalize_text(content)

    return {
        "chunk_id": chunk_id,
        "chunk_type": chunk_type,
        "index_mode": index_mode,
        "content": content,
        "token_count_approx": count_tokens_approx(content),
        "metadata": metadata,
    }